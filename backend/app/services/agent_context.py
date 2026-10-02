from datetime import date, datetime
import hashlib
import re
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models import AgentNote, Asset, Holding, KnowledgeChunk, PriceSnapshot, Transaction
from app.services.frontier_news import fetch_frontier_news, infer_holding_tags, load_tag_overrides
from app.config import settings
from app.services.knowledge import search_chunks, split_markdown_chunks
from app.services.market import fetch_market_indices, trading_status
from app.services.market_health import get_source_health
from app.services.portfolio_market import get_holding_fund_trends


def build_today_context(session: Session, topic: str | None = None) -> dict:
    holdings = (
        session.query(Holding)
        .options(joinedload(Holding.asset))
        .order_by(Holding.amount.desc())
        .all()
    )
    recent_transactions = (
        session.query(Transaction)
        .options(joinedload(Transaction.asset))
        .filter(Transaction.retracted_at.is_(None))
        .order_by(Transaction.trade_date.desc(), Transaction.id.desc())
        .limit(10)
        .all()
    )
    knowledge = _matching_knowledge(session, topic)

    return {
        "date": date.today().isoformat(),
        "trading_status": trading_status(),
        "market_indices": fetch_market_indices(),
        "holdings": [
            {
                "code": holding.asset.code,
                "name": holding.asset.name,
                "asset_type": holding.asset.asset_type,
                "theme": holding.asset.theme,
                "amount": str(holding.amount),
                "profit": str(holding.profit) if holding.profit is not None else None,
            }
            for holding in holdings
        ],
        "recent_transactions": [
            {
                "code": txn.asset.code,
                "name": txn.asset.name,
                "operation": txn.operation,
                "trade_date": txn.trade_date.isoformat(),
                "amount": str(txn.amount),
                "reason": txn.reason,
            }
            for txn in recent_transactions
        ],
        "knowledge": [
            {"title": chunk.title, "content": chunk.content, "source_path": chunk.source_path}
            for chunk in knowledge
        ],
    }


def build_research_context(session: Session, topic: str | None = None) -> dict:
    holdings = (
        session.query(Holding)
        .options(joinedload(Holding.asset))
        .order_by(Holding.amount.desc())
        .all()
    )
    recent_transactions = (
        session.query(Transaction)
        .options(joinedload(Transaction.asset))
        .filter(Transaction.retracted_at.is_(None))
        .order_by(Transaction.trade_date.desc(), Transaction.id.desc())
        .limit(10)
        .all()
    )
    knowledge = _matching_knowledge(session, topic)
    market_indices = _safe_fetch_market_indices()
    internal_news = _safe_fetch_frontier_news(session)
    holding_trends = _safe_fetch_holding_trends(session)
    trend_by_code = {row["code"]: row for row in holding_trends}
    total_amount = sum((holding.amount or Decimal("0")) for holding in holdings)
    tag_overrides = load_tag_overrides()
    holding_rows = [
        _research_holding_row(
            session,
            holding,
            total_amount,
            trend_by_code.get(holding.asset.code),
            tag_overrides,
        )
        for holding in holdings
    ]
    theme_exposure = _theme_exposure(holding_rows, total_amount)
    data_quality_summary = _data_quality_summary(holding_trends)
    package = {
        "schema_version": "1.0",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "date": date.today().isoformat(),
        "analysis_date": date.today().isoformat(),
        "topic": topic,
        "private_portfolio": {
            "total_amount": _float(total_amount),
            "holding_count": len(holding_rows),
            "theme_exposure": theme_exposure,
            "holdings": holding_rows,
            "recent_transactions": [
                {
                    "code": txn.asset.code,
                    "name": txn.asset.name,
                    "operation": txn.operation,
                    "trade_date": txn.trade_date.isoformat(),
                    "amount": _float(txn.amount),
                    "reason": txn.reason,
                }
                for txn in recent_transactions
            ],
            "knowledge": [
                {"title": chunk.title, "content": chunk.content, "source_path": chunk.source_path}
                for chunk in knowledge
            ],
        },
        "market_snapshot": {
            "trading_status": trading_status(),
            "market_indices": market_indices,
            "holding_today_changes": [
                {
                    "code": row["code"],
                    "name": row["name"],
                    "change_pct": row["today"]["change_pct"],
                    "latest_price": row["today"]["price"],
                    "updated_at": row["today"]["updated_at"],
                    "status": row["today"]["status"],
                    "source": row["today"]["source"],
                    "source_label": row["today"]["source_label"],
                    "freshness": row["today"]["freshness"],
                    "is_intraday": row["today"]["is_intraday"],
                    "is_fallback": row["today"]["is_fallback"],
                }
                for row in holding_rows
            ],
        },
        "data_source_health": get_source_health(),
        "data_quality_summary": data_quality_summary,
        "historical_review": _historical_review_summary(),
        "internal_news_signals": _trim_internal_news(internal_news),
        "external_research": _external_research_plan(topic, holding_rows, theme_exposure),
        "analysis_contract": _analysis_contract(),
    }
    package["agent_prompt"] = _agent_prompt(package)
    return package


def append_review_markdown(analysis_date: date, content: str, run_id: str | None = None) -> dict[str, Any]:
    """Append one generated review to the configured Obsidian file.

    The endpoint is intentionally direct (there is no human approval queue), while an
    exact-content fingerprint prevents accidental retries from duplicating a review.
    """
    path = settings.review_path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = content.strip()
    if not normalized:
        raise ValueError("复盘内容不能为空")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    marker = f"<!-- observatory-review:{digest} -->"
    if marker in existing:
        return {"appended": False, "duplicate": True, "path": str(path), "fingerprint": digest}
    block = f"\n\n{marker}\n{normalized}\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(block)
    return {
        "appended": True,
        "duplicate": False,
        "path": str(path),
        "fingerprint": digest,
        "analysis_date": analysis_date.isoformat(),
        "run_id": run_id,
        "bytes_written": len(block.encode("utf-8")),
    }


def _historical_review_summary() -> dict[str, Any]:
    path = settings.review_path.expanduser()
    if not path.exists():
        return {"path": str(path), "exists": False, "recent_dates": [], "open_items": [], "triggers": []}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return {"path": str(path), "exists": True, "error": str(exc), "recent_dates": [], "open_items": [], "triggers": []}
    # Read a bounded tail: historical notes can be very large, and the latest entries
    # are the only continuity needed by an external analyst.
    tail = text[-120_000:]
    dates = re.findall(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$", tail, flags=re.MULTILINE)
    open_items = _heading_sections(tail, ("待验证事项", "未完成事项", "后续验证"), limit=8)
    triggers = _heading_sections(tail, ("风险与触发条件", "观察条件", "触发条件"), limit=8)
    follow_up_items = _heading_sections(
        tail,
        ("后续需留意的关键新闻", "后续留意", "后续关注"),
        limit=8,
    )
    return {
        "path": str(path),
        "exists": True,
        "recent_dates": list(dict.fromkeys(dates))[-7:],
        "open_items": open_items,
        "triggers": triggers,
        "follow_up_items": follow_up_items,
        "note": "仅提取最近复盘的连续性线索，不重复注入完整历史原文。",
    }


def _heading_sections(text: str, headings: tuple[str, ...], limit: int) -> list[str]:
    values: list[str] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        heading_match = re.match(r"^#{2,3}\s+(.+?)\s*$", line)
        if not heading_match or not any(term in heading_match.group(1) for term in headings):
            continue
        body: list[str] = []
        for following in lines[index + 1 :]:
            if re.match(r"^#{2,3}\s+", following):
                break
            body.append(following)
        value = re.sub(r"\s+", " ", " ".join(body)).strip(" -:")
        if value and value not in values:
            values.append(value[:500])
    return values[-limit:]


def build_asset_context(session: Session, code: str) -> dict:
    asset = session.query(Asset).filter(Asset.code == code).one_or_none()
    if asset is None:
        return {"code": code, "found": False}
    holding = session.query(Holding).filter(Holding.asset_id == asset.id).one_or_none()
    return {
        "found": True,
        "asset": {
            "code": asset.code,
            "name": asset.name,
            "asset_type": asset.asset_type,
            "theme": asset.theme,
        },
        "holding": {
            "amount": str(holding.amount),
            "profit": str(holding.profit) if holding.profit is not None else None,
        }
        if holding
        else None,
    }


def save_agent_note(session: Session, title: str, content: str, note_date, source: str) -> AgentNote:
    note = AgentNote(title=title, content=content, note_date=note_date, source=source)
    session.add(note)
    session.commit()
    session.refresh(note)
    return note


def _matching_knowledge(session: Session, topic: str | None) -> list[KnowledgeChunk]:
    query = session.query(KnowledgeChunk)
    if topic:
        like = f"%{topic}%"
        query = query.filter((KnowledgeChunk.title.like(like)) | (KnowledgeChunk.content.like(like)))
    stored = query.limit(5).all()
    if stored:
        return stored

    if not settings.knowledge_path.exists():
        return []
    chunks = split_markdown_chunks(
        settings.knowledge_path.read_text(encoding="utf-8"),
        source_path=str(settings.knowledge_path),
    )
    return search_chunks(chunks, topic, limit=5) if topic else chunks[:5]


def _research_holding_row(
    session: Session,
    holding: Holding,
    total_amount: Decimal,
    trend: dict[str, Any] | None = None,
    tag_overrides: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, Any]:
    snapshot = _latest_snapshot(session, holding.asset_id)
    tags = infer_holding_tags(holding, tag_overrides)
    if holding.asset.theme and holding.asset.theme not in tags:
        tags = [holding.asset.theme, *tags]
    display_point = (trend or {}).get("latest") or (trend or {}).get("last_available")
    if display_point:
        today_value = {
            "price": display_point.get("price"),
            "change_pct": display_point.get("change_pct"),
            "updated_at": (trend or {}).get("as_of") or display_point.get("time"),
            "observed_at": (trend or {}).get("as_of") or display_point.get("time"),
            "source": (trend or {}).get("quote_source") or display_point.get("source"),
        }
    else:
        today_value = {
            "price": _float(snapshot.price) if snapshot else None,
            "change_pct": _float(snapshot.change_pct) if snapshot else None,
            "updated_at": snapshot.observed_at.isoformat(timespec="minutes") if snapshot else None,
            "observed_at": snapshot.observed_at.isoformat(timespec="minutes") if snapshot else None,
            "source": snapshot.source if snapshot else None,
        }
    today_value.update(
        {
            "source_label": (trend or {}).get("source_label"),
            "status": (trend or {}).get("quote_status") or "not_loaded",
            "freshness": (trend or {}).get("freshness") or "unknown",
            "freshness_note": (trend or {}).get("freshness_label") or "更新时间未知",
            "value_label": (trend or {}).get("value_label") or "净值",
            "is_intraday": (trend or {}).get("quote_status") == "intraday_estimate",
            "is_fallback": bool((trend or {}).get("is_fallback")),
            "fund_category": (trend or {}).get("fund_category") or "other",
            "category_label": (trend or {}).get("category_label") or "其他基金",
        }
    )
    return {
        "code": holding.asset.code,
        "name": holding.asset.name,
        "asset_type": holding.asset.asset_type,
        "theme": holding.asset.theme,
        "tags": sorted(set(tags)),
        "amount": _float(holding.amount),
        "profit": _float(holding.profit),
        "weight_pct": _weight_pct(holding.amount, total_amount),
        "today": today_value,
    }


def _latest_snapshot(session: Session, asset_id: int) -> PriceSnapshot | None:
    return (
        session.query(PriceSnapshot)
        .filter(PriceSnapshot.asset_id == asset_id)
        .order_by(PriceSnapshot.observed_at.desc(), PriceSnapshot.id.desc())
        .first()
    )


def _safe_fetch_holding_trends(session: Session) -> list[dict[str, Any]]:
    try:
        return get_holding_fund_trends(session)
    except Exception:
        return []


def _data_quality_summary(trends: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {
        "intraday_estimate": 0,
        "official_nav": 0,
        "stale": 0,
        "unavailable": 0,
        "not_loaded": 0,
    }
    for trend in trends:
        status = trend.get("quote_status")
        if status in counts:
            counts[status] += 1
    return {
        "holding_count": len(trends),
        "status_counts": counts,
        "manual_refresh_required": True,
        "note": "行情元数据来自最近一次手动刷新；官方净值不代表盘中实时涨跌。",
    }


def _theme_exposure(holding_rows: list[dict[str, Any]], total_amount: Decimal) -> list[dict[str, Any]]:
    exposure: dict[str, dict[str, Any]] = {}
    for row in holding_rows:
        tags = row["tags"] or ["未分类"]
        for tag in tags:
            bucket = exposure.setdefault(tag, {"tag": tag, "amount": 0.0, "holdings": []})
            bucket["amount"] += row["amount"] or 0.0
            bucket["holdings"].append({"code": row["code"], "name": row["name"]})
    for bucket in exposure.values():
        bucket["amount"] = round(bucket["amount"], 2)
        bucket["weight_pct"] = _weight_pct(Decimal(str(bucket["amount"])), total_amount)
    return sorted(exposure.values(), key=lambda item: item["amount"], reverse=True)


def _safe_fetch_market_indices() -> list[dict[str, Any]]:
    try:
        return fetch_market_indices()
    except Exception as exc:
        return [{"ok": False, "error": str(exc), "source": "fetch_market_indices"}]


def _safe_fetch_frontier_news(session: Session) -> list[dict[str, Any]]:
    try:
        return fetch_frontier_news(limit=30, session=session)
    except Exception as exc:
        return [{"title": "frontier news fetch failed", "source": "system", "error": str(exc)}]


def _trim_internal_news(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items[:20]:
        rows.append(
            {
                "title": item.get("title"),
                "summary": item.get("summary"),
                "source": item.get("source"),
                "source_label": item.get("source_label"),
                "url": item.get("url"),
                "published_at": item.get("published_at"),
                "fetched_at": item.get("fetched_at"),
                "importance": item.get("importance"),
                "quality": item.get("quality"),
                "tags": item.get("tags", []),
                "related_holdings": item.get("related_holdings", []),
                "note": "Internal site signal only; the agent must verify importance with external research.",
            }
        )
    return rows


def _external_research_plan(
    topic: str | None,
    holding_rows: list[dict[str, Any]],
    theme_exposure: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "required": True,
        "instruction": (
            "Do active web search before giving investment analysis. Do not rely only on the "
            "internal news signals in this package."
        ),
        "source_priority": [
            {"type": "official institutions", "examples": ["PBOC", "CSRC", "SSE", "SZSE", "HKEX", "NBS", "Federal Reserve"]},
            {"type": "issuer and fund disclosures", "examples": ["company announcements", "fund announcements", "exchange filings"]},
            {"type": "major financial media", "examples": ["Reuters", "Bloomberg", "财联社", "证券时报", "第一财经", "上海证券报"]},
            {"type": "institution research", "examples": ["brokerage research", "fund manager commentary", "index company notes"]},
        ],
        "verification_rules": [
            "Separate confirmed facts, institution opinions, market rumors, and your own inference.",
            "Cross-check important claims with at least two credible sources when possible.",
            "Judge whether each item affects earnings, valuation, liquidity, policy expectations, or sentiment only.",
            "State whether the market may have already priced in the information.",
        ],
        "suggested_queries": _suggested_queries(topic, holding_rows, theme_exposure),
    }


def _suggested_queries(
    topic: str | None,
    holding_rows: list[dict[str, Any]],
    theme_exposure: list[dict[str, Any]],
) -> list[str]:
    queries: list[str] = []
    for row in holding_rows[:8]:
        queries.append(f"{row['name']} {row['code']} today news analysis")
    if topic:
        queries.append(f"{topic} today market news official analysis")
    for exposure in theme_exposure[:6]:
        queries.append(f"{exposure['tag']} sector today policy institution view")
    queries.extend(
        [
            "China A-share market today policy liquidity official news",
            "US treasury yield dollar gold today market impact",
            "Hong Kong stock market southbound funds today analysis",
        ]
    )
    deduped: list[str] = []
    for query in queries:
        if query not in deduped:
            deduped.append(query)
    return deduped[:16]


def _analysis_contract() -> dict[str, Any]:
    return {
        "required_output_sections": [
            "一、今日盘面涨跌情况（重点：组合方向，不重复完整持仓表）",
            "二、今日关键新闻",
            "三、AI 分析（今日股市为什么这样）",
            "四、后续需留意的关键新闻 / 时点",
            "五、风险与触发条件",
            "六、数据来源与限制",
        ],
        "guardrails": [
            "Do not provide a buy/sell command without explaining uncertainty and trigger conditions.",
            "Do not treat short-term price movement as proof of a long-term thesis.",
            "Never treat official NAV, stale data, or QDII cross-market data as today's real-time move.",
            "Always mention data gaps and source limitations.",
            "Do not mention, run, or recommend fund_monitor.py; that legacy tool is retired.",
            "Do not repeat the complete holdings table in the Markdown review; refer to package facts instead.",
            "News must use a summary title ending in a star rating (★ to ★★★★★), followed by labeled body lines: 性质, 影响板块, and optional 分析.",
            "Do not write a 今日建议 section. Put conditional observations and measurable follow-up events in the required follow-up table instead.",
        ],
    }


def _agent_prompt(package: dict[str, Any]) -> str:
    topic = package.get("topic") or "today's portfolio and market"
    return (
        "You are my investment research assistant.\n"
        f"Task: analyze {topic} using my private portfolio facts in this package.\n"
        "First read my holdings, weights, today's price changes, recent transactions, and knowledge snippets.\n"
        "Then perform active web search. Do not rely only on the internal news signals.\n"
        "Treat each holding's source, timestamp, freshness, fallback flag, and intraday status as evidence.\n"
        "Never describe official NAV or stale/QDII data as today's real-time move.\n"
        "Prioritize authoritative sources: official institutions, exchange filings, issuer/fund disclosures, "
        "major financial media, and institution research.\n"
        "For every important claim, distinguish confirmed facts, institution opinions, rumors, and your inference.\n"
        "Explain impact on each relevant holding, rank news importance, give bull/bear cases, and list observation triggers.\n"
        "Do not create a 今日建议 section or unconditional buy/sell instructions. Put measurable conditions in the follow-up table.\n"
        "Format each key news item as a summary title ending with ★ to ★★★★★, then label its body with 性质, 影响板块, and optional 分析.\n"
        "The review must include a section titled 三、AI 分析（今日股市为什么这样） explaining the market with facts, inferences, and bull/bear cases.\n"
        "It must include 四、后续需留意的关键新闻 / 时点 with a table containing time, event/threshold, why it matters, and affected holdings.\n"
        "Do not repeat the complete holdings table in the review. After writing the Markdown review, append it\n"
        "directly with POST /api/agent/reviews/append to the configured Obsidian review file.\n"
        "The legacy fund_monitor.py tool is retired: never run or recommend it."
    )


def _weight_pct(amount: Decimal | None, total: Decimal) -> float:
    if not amount or not total:
        return 0.0
    return round(float(amount / total * Decimal("100")), 2)


def _float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None
