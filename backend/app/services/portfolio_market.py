from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models import Holding, PriceSnapshot
from app.services.fund_metadata import category_info, freshness_info, infer_fund_category, source_label
from app.services.market import fetch_fund_estimate

EstimateFetcher = Callable[[str], dict[str, Any]]


def refresh_holding_fund_trends(
    session: Session,
    fetcher: EstimateFetcher = fetch_fund_estimate,
) -> list[dict[str, Any]]:
    holdings = (
        session.query(Holding)
        .options(joinedload(Holding.asset))
        .join(Holding.asset)
        .filter_by(asset_type="fund")
        .order_by(Holding.amount.desc())
        .all()
    )

    quote_results: dict[int, dict[str, Any]] = {}
    for holding in holdings:
        estimate = fetcher(holding.asset.code)
        quote_results[holding.asset_id] = estimate
        if not estimate.get("ok"):
            _clear_intraday_series(session, holding.asset_id, "sina_xincai_estimate")
            continue

        fetched_name = estimate.get("name")
        if fetched_name:
            holding.asset.name = str(fetched_name)

        source = str(estimate.get("source") or "fund_estimate")
        points = estimate.get("points") or []
        if points:
            _replace_intraday_series(session, holding.asset_id, source, points)
        else:
            if estimate.get("data_status") == "official_nav":
                _clear_intraday_series(session, holding.asset_id, "sina_xincai_estimate")
            _upsert_snapshot(session, holding.asset_id, source, estimate)

    session.commit()
    return get_holding_fund_trends(session, quote_results=quote_results)


def _replace_intraday_series(
    session: Session,
    asset_id: int,
    source: str,
    points: list[dict[str, Any]],
) -> None:
    observed_dates = {_parse_observed_at(point.get("time")).date() for point in points}
    for observed_date in observed_dates:
        start = datetime.combine(observed_date, time.min)
        end = datetime.combine(observed_date, time.max)
        (
            session.query(PriceSnapshot)
            .filter(
                PriceSnapshot.asset_id == asset_id,
                PriceSnapshot.source == source,
                PriceSnapshot.observed_at >= start,
                PriceSnapshot.observed_at <= end,
            )
            .delete(synchronize_session=False)
        )
    for point in points:
        _upsert_snapshot(session, asset_id, source, point)


def _clear_intraday_series(
    session: Session,
    asset_id: int,
    source: str,
    observed_date: date | None = None,
) -> None:
    target_date = observed_date or date.today()
    start = datetime.combine(target_date, time.min)
    end = datetime.combine(target_date, time.max)
    (
        session.query(PriceSnapshot)
        .filter(
            PriceSnapshot.asset_id == asset_id,
            PriceSnapshot.source == source,
            PriceSnapshot.observed_at >= start,
            PriceSnapshot.observed_at <= end,
        )
        .delete(synchronize_session=False)
    )


def _upsert_snapshot(
    session: Session,
    asset_id: int,
    source: str,
    point: dict[str, Any],
) -> None:
    observed_at = _parse_observed_at(point.get("time"))
    price = _decimal_or_none(point.get("estimate_nav") or point.get("nav"), "0.000000")
    change_pct = _decimal_or_none(point.get("change_pct"), "0.0000")
    if price is None or price <= 0:
        return

    existing_snapshots = (
        session.query(PriceSnapshot)
        .filter(
            PriceSnapshot.asset_id == asset_id,
            PriceSnapshot.observed_at == observed_at,
            PriceSnapshot.source == source,
        )
        .order_by(PriceSnapshot.id.asc())
        .all()
    )
    existing = existing_snapshots[0] if existing_snapshots else None
    if existing is None:
        existing = PriceSnapshot(asset_id=asset_id, source=source, observed_at=observed_at)
        session.add(existing)
    for duplicate in existing_snapshots[1:]:
        session.delete(duplicate)
    existing.price = price
    existing.change_pct = change_pct
    existing.raw_payload = json.dumps(point, ensure_ascii=False)


def get_holding_fund_trends(
    session: Session,
    day: date | None = None,
    quote_results: dict[int, dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    target_day = day or date.today()
    current = now or datetime.now()
    start = datetime.combine(target_day, time.min)
    end = datetime.combine(target_day, time.max)
    visibility_end = min(end, current + timedelta(minutes=5)) if target_day == current.date() else end

    holdings = (
        session.query(Holding)
        .options(joinedload(Holding.asset))
        .join(Holding.asset)
        .filter_by(asset_type="fund")
        .order_by(Holding.amount.desc())
        .all()
    )

    trends: list[dict[str, Any]] = []
    for holding in holdings:
        all_day_snapshots = (
            session.query(PriceSnapshot)
            .filter(
                PriceSnapshot.asset_id == holding.asset_id,
                PriceSnapshot.observed_at >= start,
                PriceSnapshot.observed_at <= end,
            )
            .order_by(PriceSnapshot.observed_at.asc(), PriceSnapshot.id.asc())
            .all()
        )
        future_sources = {
            snapshot.source
            for snapshot in all_day_snapshots
            if target_day == current.date() and snapshot.observed_at > visibility_end
        }
        snapshots = [
            snapshot
            for snapshot in all_day_snapshots
            if snapshot.observed_at <= visibility_end and snapshot.source not in future_sources
        ]
        latest = snapshots[-1] if snapshots else None
        last_available_query = (
            session.query(PriceSnapshot)
            .filter(PriceSnapshot.asset_id == holding.asset_id)
        )
        if target_day == current.date():
            last_available_query = last_available_query.filter(
                PriceSnapshot.observed_at <= visibility_end
            )
            if future_sources:
                last_available_query = last_available_query.filter(
                    or_(
                        PriceSnapshot.observed_at < start,
                        ~PriceSnapshot.source.in_(future_sources),
                    )
                )
        last_available = (
            last_available_query
            .order_by(PriceSnapshot.observed_at.desc(), PriceSnapshot.id.desc())
            .first()
        )
        quote = (quote_results or {}).get(holding.asset_id)
        cached_status = _snapshot_status(latest)
        if (quote and quote.get("data_status") == "official_nav") or (
            quote is None and cached_status == "official_nav"
        ):
            snapshots = []
            latest = None
        quote_status, quote_message = _quote_state(quote, latest, last_available)
        metadata = _trend_metadata(holding, quote, quote_status, latest, last_available)
        trends.append(
            {
                "code": holding.asset.code,
                "name": holding.asset.name,
                "asset_type": holding.asset.asset_type,
                "amount": float(holding.amount),
                "profit": float(holding.profit) if holding.profit is not None else None,
                "latest": _snapshot_to_point(latest) if latest else None,
                "last_available": _snapshot_to_point(last_available) if last_available else None,
                "points": [_snapshot_to_point(snapshot) for snapshot in snapshots],
                "quote_status": quote_status,
                "quote_message": quote_message,
                **metadata,
                "value_label": _value_label(quote, last_available, metadata["fund_category"]),
            }
        )

    trends.sort(
        key=lambda item: (
            item["latest"] is None,
            -(item["latest"]["change_pct"] if item["latest"] else -9999),
        )
    )
    return trends


def _trend_metadata(
    holding: Holding,
    quote: dict[str, Any] | None,
    status: str,
    latest: PriceSnapshot | None,
    last_available: PriceSnapshot | None,
) -> dict[str, Any]:
    display_snapshot = latest or last_available
    quote_source = str(quote.get("source") or "") if quote else ""
    snapshot_source = display_snapshot.source if display_snapshot else ""
    source = quote_source or snapshot_source or None
    as_of = str(quote.get("time") or "") if quote else ""
    if not as_of and display_snapshot:
        as_of = display_snapshot.observed_at.isoformat(timespec="minutes")
    category = infer_fund_category(
        holding.asset.code,
        str(quote.get("name") or holding.asset.name) if quote else holding.asset.name,
        str(quote.get("fund_type") or "") if quote else None,
    )
    details = category_info(category)
    freshness, freshness_label = freshness_info(status, as_of)
    is_fallback = bool(quote and quote.get("warnings")) or status in {"official_nav", "stale"}
    return {
        "quote_source": source,
        "source_label": source_label(source),
        "as_of": as_of or None,
        "freshness": freshness,
        "freshness_label": freshness_label,
        "is_fallback": is_fallback,
        "fund_category": category,
        "category_label": details["label"],
        "category_note": details["note"],
    }


def _quote_state(
    quote: dict[str, Any] | None,
    latest: PriceSnapshot | None,
    last_available: PriceSnapshot | None,
) -> tuple[str, str | None]:
    if quote is not None:
        if not quote.get("ok"):
            return "unavailable", str(quote.get("error") or "基金行情暂不可用")
        status = str(quote.get("data_status") or "intraday_estimate")
        return status, str(quote.get("message") or "") or None
    if latest is not None:
        return "intraday_estimate", "盘中估值，仅供参考"
    if last_available is not None:
        if _snapshot_status(last_available) == "official_nav":
            payload = _snapshot_payload(last_available)
            return "official_nav", str(payload.get("message") or "最新官方净值（非实时估值）")
        return "stale", "暂无今日数据，显示最近一次可用快照"
    return "not_loaded", "尚未获取行情"


def _snapshot_to_point(snapshot: PriceSnapshot | None) -> dict[str, Any]:
    if snapshot is None:
        return {}
    return {
        "time": snapshot.observed_at.isoformat(timespec="minutes"),
        "price": float(snapshot.price) if snapshot.price is not None else None,
        "change_pct": float(snapshot.change_pct) if snapshot.change_pct is not None else None,
        "source": snapshot.source,
    }


def _snapshot_payload(snapshot: PriceSnapshot | None) -> dict[str, Any]:
    if snapshot is None or not snapshot.raw_payload:
        return {}
    try:
        payload = json.loads(snapshot.raw_payload)
        return payload if isinstance(payload, dict) else {}
    except (TypeError, ValueError):
        return {}


def _snapshot_status(snapshot: PriceSnapshot | None) -> str | None:
    payload = _snapshot_payload(snapshot)
    status = payload.get("data_status")
    if status:
        return str(status)
    if snapshot and snapshot.source == "eastmoney_official_nav":
        return "official_nav"
    if snapshot and snapshot.source == "tencent_fund_quote":
        estimate_nav = payload.get("estimate_nav")
        if estimate_nav in (None, "", 0, 0.0, "0", "0.0000"):
            return "official_nav"
    return None


def _value_label(
    quote: dict[str, Any] | None,
    last_available: PriceSnapshot | None,
    category: str,
) -> str:
    if quote and quote.get("value_label"):
        return str(quote["value_label"])
    payload = _snapshot_payload(last_available)
    if payload.get("value_label"):
        return str(payload["value_label"])
    if category == "money":
        return "每万份收益"
    is_official = (quote and quote.get("data_status") == "official_nav") or (
        payload.get("data_status") == "official_nav"
    )
    return "净值" if is_official else "估值"


def _parse_observed_at(value: object) -> datetime:
    if isinstance(value, str) and value.strip():
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(value.strip(), fmt)
            except ValueError:
                pass
    return datetime.now()


def _decimal_or_none(value: object, places: str) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value)).quantize(Decimal(places))
