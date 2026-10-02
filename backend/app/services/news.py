from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from xml.etree import ElementTree
from typing import Any, Callable

from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models import NewsItem
from app.services.fund_metadata import parse_datetime
from app.services.market_health import market_source_health

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

SourceFetcher = Callable[[int], list[dict[str, Any]]]
SOURCE_LABELS = {
    "wallstreetcn": "华尔街见闻",
    "sina": "新浪财经",
    "federal_reserve": "美联储",
}


def fetch_news(
    limit: int = 20,
    session: Session | None = None,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """Return normalized news, using SQLite cache unless an explicit refresh is requested."""
    bounded_limit = max(1, min(limit, 200))
    if session is not None:
        cached = _read_cached_news(session, bounded_limit)
        if cached and not refresh and _cache_is_fresh(cached):
            return cached

    fetched = _fetch_all_sources(bounded_limit)
    if fetched and session is not None:
        _store_news(session, fetched)
        prune_old_news(session)
        return _sort_news(fetched)[:bounded_limit]
    if fetched:
        return _sort_news(fetched)[:bounded_limit]
    if session is not None:
        # A temporary upstream outage should not blank the user's news page.
        return _read_cached_news(session, bounded_limit, allow_stale=True)
    return []


def _fetch_all_sources(limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=len(SOURCE_FETCHERS), thread_name_prefix="news") as pool:
        futures = {
            pool.submit(fetcher, limit): source
            for source, fetcher in SOURCE_FETCHERS.items()
        }
        for future in as_completed(futures):
            source = futures[future]
            health_source = f"{source}_news"
            try:
                source_rows = future.result()
                market_source_health.record(health_source, "success" if source_rows else "no_data")
                rows.extend(_normalise_item(item, source) for item in source_rows)
            except Exception as exc:
                market_source_health.record(health_source, "failure", str(exc))
    return _dedupe(rows)


def _fetch_wallstreetcn(limit: int) -> list[dict[str, Any]]:
    url = f"https://api-one.wallstcn.com/apiv1/content/lives?channel=global-channel&limit={limit}"
    data = _request_json(url)
    return list((data.get("data") or {}).get("items") or [])


def _fetch_sina(limit: int) -> list[dict[str, Any]]:
    url = f"https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&k=&num={limit}&page=1"
    data = _request_json(url, referer="https://finance.sina.com.cn/")
    return list((data.get("result") or {}).get("data") or [])


def _fetch_federal_reserve(limit: int) -> list[dict[str, Any]]:
    """Read the Federal Reserve's public press-release RSS feed."""
    url = "https://www.federalreserve.gov/feeds/press_all.xml"
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=settings.request_timeout_seconds) as response:
        root = ElementTree.fromstring(response.read())
    rows: list[dict[str, Any]] = []
    for item in root.findall(".//item")[:limit]:
        rows.append(
            {
                "title": _xml_text(item.findtext("title")),
                "link": _xml_text(item.findtext("link")),
                "description": _xml_text(item.findtext("description")),
                "pubDate": _xml_text(item.findtext("pubDate")),
            }
        )
    return rows


SOURCE_FETCHERS: dict[str, SourceFetcher] = {
    "wallstreetcn": _fetch_wallstreetcn,
    "sina": _fetch_sina,
    "federal_reserve": _fetch_federal_reserve,
}


def _request_json(url: str, referer: str | None = None) -> dict[str, Any]:
    headers = {**HEADERS, **({"Referer": referer} if referer else {})}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=settings.request_timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _normalise_item(row: dict[str, Any], source: str) -> dict[str, Any]:
    title = _clean_text(
        row.get("title")
        or row.get("subject")
        or row.get("content_text")
        or row.get("content")
        or ""
    )
    content = _clean_text(
        row.get("summary")
        or row.get("description")
        or row.get("content_text")
        or row.get("content")
        or ""
    )
    if content == title:
        content = ""
    url = str(row.get("url") or row.get("link") or row.get("uri") or "").strip()
    published_at = _published_at(row)
    fetched_at = datetime.now()
    importance = _importance_score(title)
    content_hash = hashlib.sha256(_normalise_title(title).encode("utf-8")).hexdigest()
    return {
        "title": title[:500],
        "summary": content[:4000] or None,
        "url": url[:1000] or None,
        "source": source,
        "source_label": SOURCE_LABELS[source],
        "published_at": published_at.isoformat(timespec="seconds") if published_at else None,
        "fetched_at": fetched_at.isoformat(timespec="seconds"),
        "importance": importance,
        "quality": "full" if content else "headline_only",
        "content_hash": content_hash,
    }


def _published_at(row: dict[str, Any]) -> datetime | None:
    for key in ("published_at", "pub_time", "publish_time", "display_time", "created_at", "ctime", "time", "pubDate"):
        value = row.get(key)
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
            try:
                return datetime.fromtimestamp(float(value))
            except (OverflowError, OSError, ValueError):
                continue
        parsed = parse_datetime(value)
        if parsed:
            return parsed
        if isinstance(value, str) and value.strip():
            try:
                return parsedate_to_datetime(value).replace(tzinfo=None)
            except (TypeError, ValueError, IndexError, OverflowError):
                pass
    return None


def _store_news(session: Session, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    # SQLite UPSERT: INSERT ... ON CONFLICT(content_hash) DO UPDATE.
    # One statement per batch, no read-then-write race window. Requires the
    # unique index uq_news_items_content_hash created in app.db.init_db().
    payload = [
        {
            "title": row["title"],
            "summary": row["summary"],
            "url": row["url"],
            "source": row["source"],
            "published_at": _parse_iso(row["published_at"]),
            "fetched_at": _parse_iso(row["fetched_at"]),
            "importance": row["importance"],
            "quality": row["quality"],
            "content_hash": row["content_hash"],
        }
        for row in rows
    ]
    stmt = sqlite_insert(NewsItem).values(payload)
    stmt = stmt.on_conflict_do_update(
        index_elements=[NewsItem.content_hash],
        set_={
            "title": stmt.excluded.title,
            "summary": stmt.excluded.summary,
            "url": stmt.excluded.url,
            "source": stmt.excluded.source,
            "published_at": stmt.excluded.published_at,
            "fetched_at": stmt.excluded.fetched_at,
            "importance": stmt.excluded.importance,
            "quality": stmt.excluded.quality,
        },
    )
    session.execute(stmt)
    session.commit()


def prune_old_news(session: Session, retention_days: int | None = None) -> int:
    """Delete news older than the retention window.

    A news item's age is based on its publish time, falling back to the time
    it was fetched for headline-only items without a parseable publish time.
    Returns the number of deleted rows. A non-positive retention disables
    pruning.
    """
    days = settings.news_retention_days if retention_days is None else retention_days
    if days <= 0:
        return 0
    cutoff = datetime.now() - timedelta(days=days)
    deleted = (
        session.query(NewsItem)
        .filter(func.coalesce(NewsItem.published_at, NewsItem.fetched_at) < cutoff)
        .delete(synchronize_session=False)
    )
    session.commit()
    return deleted


def _read_cached_news(session: Session, limit: int, allow_stale: bool = False) -> list[dict[str, Any]]:
    rows = (
        session.query(NewsItem)
        .order_by(NewsItem.importance.desc(), NewsItem.published_at.desc(), NewsItem.fetched_at.desc(), NewsItem.id.desc())
        .limit(max(limit, 80))
        .all()
    )
    if not rows:
        return []
    now = datetime.now()
    result: list[dict[str, Any]] = []
    for row in rows:
        fetched_at = row.fetched_at or row.updated_at or row.created_at
        stale = not fetched_at or now - fetched_at > timedelta(seconds=settings.news_cache_ttl_seconds)
        if stale and not allow_stale:
            continue
        result.append(_serialize(row, stale=stale))
    return _sort_news(result)[:limit]


def _cache_is_fresh(rows: list[dict[str, Any]]) -> bool:
    return bool(rows) and all(row.get("quality") != "stale" for row in rows)


def _serialize(row: NewsItem, stale: bool = False) -> dict[str, Any]:
    return {
        "title": row.title,
        "summary": row.summary,
        "url": row.url,
        "source": row.source,
        "source_label": SOURCE_LABELS.get(row.source, row.source),
        "published_at": row.published_at.isoformat(timespec="seconds") if row.published_at else None,
        "fetched_at": row.fetched_at.isoformat(timespec="seconds") if row.fetched_at else None,
        "importance": row.importance or 1,
        "quality": "stale" if stale else (row.quality or "headline_only"),
        "content_hash": row.content_hash,
    }


def _sort_news(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            int(row.get("importance") or 1),
            row.get("published_at") or "",
            row.get("fetched_at") or "",
        ),
        reverse=True,
    )


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        key = row.get("content_hash") or hashlib.sha256(row["title"].encode("utf-8")).hexdigest()
        if not row["title"] or key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _importance_score(title: str) -> int:
    high = ("降息", "加息", "政策", "监管", "制裁", "战争", "暴跌", "暴涨", "IPO", "财报")
    medium = ("涨停", "跌停", "利率", "通胀", "CPI", "PPI", "美联储", "央行", "公告")
    if any(keyword.lower() in title.lower() for keyword in high):
        return 5
    if any(keyword.lower() in title.lower() for keyword in medium):
        return 4
    return 3 if len(title) > 20 else 2


def _normalise_title(value: str) -> str:
    return re.sub(r"[\W_]+", "", value.lower(), flags=re.UNICODE)


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", str(value or "")))).strip()


def _xml_text(value: str | None) -> str:
    return _clean_text(value or "")


def _parse_iso(value: str | None) -> datetime | None:
    return parse_datetime(value)
