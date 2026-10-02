from __future__ import annotations

import json
from concurrent.futures import Future, ThreadPoolExecutor, wait
from datetime import date, datetime, time
from decimal import Decimal
from threading import Lock
from typing import Any, Callable

from sqlalchemy.orm import Session, joinedload

from app.models import PriceSnapshot, WatchlistItem
from app.services.fund_metadata import category_info, freshness_info, infer_fund_category, source_label
from app.services.market import fetch_fund_estimate, fetch_stock_quote

QuoteFetcher = Callable[[str], dict[str, Any]]
WATCHLIST_REFRESH_TIMEOUT_SECONDS = 12
WATCHLIST_MAX_WORKERS = 32
WATCHLIST_CURVE_MAX_POINTS = 64
_refresh_flights: dict[tuple[int, tuple[int, ...] | None], Future[list[dict[str, Any]]]] = {}
_refresh_flights_lock = Lock()


def refresh_watchlist_trends(
    session: Session,
    watchlist_id: int,
    fund_fetcher: QuoteFetcher = fetch_fund_estimate,
    stock_fetcher: QuoteFetcher = fetch_stock_quote,
    item_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    selection = tuple(sorted(set(item_ids))) if item_ids is not None else None
    if fund_fetcher is not fetch_fund_estimate or stock_fetcher is not fetch_stock_quote:
        return _refresh_watchlist_trends(session, watchlist_id, fund_fetcher, stock_fetcher, item_ids)

    key = (watchlist_id, selection)
    with _refresh_flights_lock:
        flight = _refresh_flights.get(key)
        if flight is None:
            flight = Future()
            _refresh_flights[key] = flight
            owns_flight = True
        else:
            owns_flight = False
    if not owns_flight:
        return flight.result(timeout=WATCHLIST_REFRESH_TIMEOUT_SECONDS + 10)
    try:
        result = _refresh_watchlist_trends(session, watchlist_id, fund_fetcher, stock_fetcher, item_ids)
        flight.set_result(result)
        return result
    except BaseException as exc:
        flight.set_exception(exc)
        raise
    finally:
        with _refresh_flights_lock:
            if _refresh_flights.get(key) is flight:
                del _refresh_flights[key]


def _refresh_watchlist_trends(
    session: Session,
    watchlist_id: int,
    fund_fetcher: QuoteFetcher,
    stock_fetcher: QuoteFetcher,
    item_ids: list[int] | None,
) -> list[dict[str, Any]]:
    items = _items(session, watchlist_id, item_ids)
    if not items:
        return []
    quote_results: dict[int, dict[str, Any]] = {}
    snapshot_inputs: list[tuple[int, str, dict[str, Any]]] = []
    # Quote sources are network-bound and some free endpoints stall. Submit the
    # whole batch at once, then enforce a request budget so one slow item cannot
    # hold the page open. Database writes stay on this request thread.
    executor = ThreadPoolExecutor(max_workers=min(WATCHLIST_MAX_WORKERS, max(1, len(items))))
    futures = {
        item.id: executor.submit(
            _fetch_item_quote,
            item.asset.code,
            item.asset.asset_type,
            fund_fetcher,
            stock_fetcher,
        )
        for item in items
    }
    done, _ = wait(futures.values(), timeout=WATCHLIST_REFRESH_TIMEOUT_SECONDS)
    try:
        for item in items:
            future = futures[item.id]
            if future not in done:
                quote = {
                    "ok": False,
                    "code": item.asset.code,
                    "error": "行情刷新超时，已显示最近一次快照",
                    "health_outcome": "failure",
                }
            else:
                try:
                    quote = future.result()
                except Exception as exc:
                    quote = {"ok": False, "code": item.asset.code, "error": str(exc)}
            quote_results[item.id] = quote
            if quote.get("name"):
                item.asset.name = str(quote["name"])
            if quote.get("ok"):
                points = quote.get("points") or [_quote_point(quote)]
                for point in points:
                    if point.get("time"):
                        snapshot_inputs.append(
                            (item.asset.id, str(quote.get("source") or "tracking"), point)
                        )
    finally:
        # Timed-out network calls finish in the background and never touch the
        # SQLAlchemy session. Cancelling queued futures avoids extra work.
        executor.shutdown(wait=False, cancel_futures=True)
    _persist_snapshots(session, snapshot_inputs)
    session.commit()
    return get_watchlist_trends(
        session,
        watchlist_id,
        quote_results=quote_results,
        item_ids=item_ids,
    )


def _fetch_item_quote(
    code: str,
    asset_type: str,
    fund_fetcher: QuoteFetcher,
    stock_fetcher: QuoteFetcher,
) -> dict[str, Any]:
    if asset_type == "fund":
        fetcher = fund_fetcher
    elif asset_type == "stock":
        fetcher = stock_fetcher
    else:
        return {"ok": False, "code": code, "error": "当前仅支持股票和基金追踪"}
    try:
        return fetcher(code)
    except Exception as exc:
        return {"ok": False, "code": code, "error": str(exc), "health_outcome": "failure"}


def get_watchlist_trends(
    session: Session,
    watchlist_id: int,
    day: date | None = None,
    quote_results: dict[int, dict[str, Any]] | None = None,
    item_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    target_day = day or date.today()
    start = datetime.combine(target_day, time.min)
    end = datetime.combine(target_day, time.max)
    results: list[dict[str, Any]] = []
    for item in _items(session, watchlist_id, item_ids):
        snapshots = (
            session.query(PriceSnapshot)
            .filter(
                PriceSnapshot.asset_id == item.asset.id,
                PriceSnapshot.observed_at >= start,
                PriceSnapshot.observed_at <= end,
            )
            .order_by(PriceSnapshot.observed_at.asc(), PriceSnapshot.id.asc())
            .all()
        )
        latest = snapshots[-1] if snapshots else None
        last_available = (
            session.query(PriceSnapshot)
            .filter(PriceSnapshot.asset_id == item.asset.id)
            .order_by(PriceSnapshot.observed_at.desc(), PriceSnapshot.id.desc())
            .first()
        )
        quote = (quote_results or {}).get(item.id)
        display = latest or last_available
        status = _quote_status(quote, display)
        points = [] if status == "official_nav" else [
            _snapshot_point(row) for row in _downsample_snapshots(snapshots)
        ]
        category = infer_fund_category(item.asset.code, item.asset.name) if item.asset.asset_type == "fund" else "other"
        details = category_info(category)
        as_of = str(quote.get("time") or "") if quote else ""
        if not as_of and display:
            as_of = display.observed_at.isoformat(timespec="minutes")
        freshness, freshness_label = freshness_info(status, as_of)
        results.append(
            {
                "code": item.asset.code,
                "name": item.asset.custom_name or item.asset.name,
                "official_name": item.asset.name,
                "custom_name": item.asset.custom_name,
                "watchlist_item_id": item.id,
                "tags": _parse_tags(item.tags_json),
                "asset_type": item.asset.asset_type,
                "amount": 0,
                "profit": None,
                "latest": _snapshot_point(latest) if latest and status != "official_nav" else None,
                "last_available": _snapshot_point(last_available) if last_available else None,
                "points": points,
                "quote_status": status,
                "quote_message": _quote_message(quote, status),
                "quote_source": (quote or {}).get("source") or (display.source if display else None),
                "source_label": source_label((quote or {}).get("source") or (display.source if display else None)),
                "as_of": as_of or None,
                "freshness": freshness,
                "freshness_label": freshness_label,
                # A cached intraday series remains a usable curve after the market closes.
                # Only an actual source fallback or official NAV should carry that label.
                "is_fallback": status == "official_nav" or bool((quote or {}).get("warnings")),
                "fund_category": category,
                "category_label": details["label"],
                "category_note": details["note"],
                "value_label": "现价" if item.asset.asset_type == "stock" else "净值",
            }
        )
    return results


def _items(
    session: Session,
    watchlist_id: int,
    item_ids: list[int] | None = None,
) -> list[WatchlistItem]:
    query = (
        session.query(WatchlistItem)
        .options(joinedload(WatchlistItem.asset))
        .filter(WatchlistItem.watchlist_id == watchlist_id)
    )
    if item_ids is not None:
        query = query.filter(WatchlistItem.id.in_(item_ids))
    return query.order_by(WatchlistItem.sort_order.asc(), WatchlistItem.id.asc()).all()


def _quote_point(quote: dict[str, Any]) -> dict[str, Any]:
    return {
        "time": quote.get("time") or datetime.now().strftime("%Y-%m-%d %H:%M"),
        "price": quote.get("price") or quote.get("estimate_nav") or quote.get("nav"),
        "change_pct": quote.get("change_pct"),
    }


def _persist_snapshots(
    session: Session,
    inputs: list[tuple[int, str, dict[str, Any]]],
) -> None:
    pending: dict[tuple[int, str, datetime], tuple[Decimal, Decimal | None, str]] = {}
    for asset_id, source, point in inputs:
        observed_at = _parse_time(point.get("time"))
        price_value = point.get("price") or point.get("estimate_nav") or point.get("nav")
        if observed_at is None or price_value in (None, ""):
            continue
        pending[(asset_id, source, observed_at)] = (
            Decimal(str(price_value)),
            Decimal(str(point["change_pct"])) if point.get("change_pct") is not None else None,
            json.dumps(point, ensure_ascii=False),
        )
    if not pending:
        return

    asset_ids = {key[0] for key in pending}
    sources = {key[1] for key in pending}
    observed_values = [key[2] for key in pending]
    existing_rows = (
        session.query(PriceSnapshot)
        .filter(
            PriceSnapshot.asset_id.in_(asset_ids),
            PriceSnapshot.source.in_(sources),
            PriceSnapshot.observed_at >= min(observed_values),
            PriceSnapshot.observed_at <= max(observed_values),
        )
        .order_by(PriceSnapshot.id.asc())
        .all()
    )
    existing_by_key: dict[tuple[int, str, datetime], PriceSnapshot] = {}
    for row in existing_rows:
        existing_by_key.setdefault((row.asset_id, row.source, row.observed_at), row)

    for key, (price, change_pct, raw_payload) in pending.items():
        row = existing_by_key.get(key)
        if row is None:
            asset_id, source, observed_at = key
            session.add(
                PriceSnapshot(
                    asset_id=asset_id,
                    source=source,
                    observed_at=observed_at,
                    price=price,
                    change_pct=change_pct,
                    raw_payload=raw_payload,
                )
            )
            continue
        if row.price != price:
            row.price = price
        if row.change_pct != change_pct:
            row.change_pct = change_pct
        if row.raw_payload != raw_payload:
            row.raw_payload = raw_payload


def _downsample_snapshots(
    snapshots: list[PriceSnapshot],
    limit: int = WATCHLIST_CURVE_MAX_POINTS,
) -> list[PriceSnapshot]:
    if len(snapshots) <= limit:
        return snapshots
    last_index = len(snapshots) - 1
    indices = {round(index * last_index / (limit - 1)) for index in range(limit)}
    return [snapshots[index] for index in sorted(indices)]


def _parse_tags(value: str | None) -> list[str]:
    try:
        tags = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(tag) for tag in tags if str(tag).strip()] if isinstance(tags, list) else []


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _snapshot_point(snapshot: PriceSnapshot) -> dict[str, Any]:
    return {
        "time": snapshot.observed_at.isoformat(timespec="minutes"),
        "price": float(snapshot.price) if snapshot.price is not None else None,
        "change_pct": float(snapshot.change_pct) if snapshot.change_pct is not None else None,
        "source": snapshot.source,
    }


def _quote_status(quote: dict[str, Any] | None, display: PriceSnapshot | None) -> str:
    if quote is not None:
        if not quote.get("ok"):
            return "unavailable"
        return str(quote.get("data_status") or "intraday_estimate")
    return "stale" if display else "not_loaded"


def _quote_message(quote: dict[str, Any] | None, status: str) -> str:
    if quote and quote.get("message"):
        return str(quote["message"])
    if quote and not quote.get("ok"):
        return str(quote.get("error") or "行情获取失败")
    if status == "stale":
        return "暂无最新数据，显示最近一次快照"
    if status == "not_loaded":
        return "尚未获取行情"
    return "盘中行情，仅供参考"
