from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, joinedload

from app.models import Holding, PortfolioValuationRun
from app.services.market import fetch_fund_estimate, fetch_stock_quote

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
CLOSE_TIME = time(15, 5)
MoneyFetcher = Callable[[str], dict[str, Any]]


def refresh_closed_portfolio(
    session: Session,
    *,
    now: datetime | None = None,
    fund_fetcher: MoneyFetcher = fetch_fund_estimate,
    stock_fetcher: MoneyFetcher = fetch_stock_quote,
    force: bool = False,
) -> dict[str, Any]:
    """Refresh eligible holdings once after the mainland market close."""
    local_now = _local_now(now)
    valuation_date = local_now.date()
    if local_now.weekday() >= 5:
        return _result(valuation_date, "weekend", 0, 0)
    if not force and local_now.time() < CLOSE_TIME:
        return _result(valuation_date, "not_due", 0, 0)

    run = session.query(PortfolioValuationRun).filter_by(valuation_date=valuation_date).one_or_none()
    if run and run.completed_at is not None and not force:
        return _result(valuation_date, "already_completed", run.updated_count, run.failed_count)
    if run is None:
        run = PortfolioValuationRun(valuation_date=valuation_date)
        session.add(run)
        session.flush()

    holdings = (
        session.query(Holding)
        .options(joinedload(Holding.asset))
        .filter(Holding.units.is_not(None), Holding.units > 0)
        .all()
    )
    # Do not keep a SQLite transaction open while waiting on remote quote
    # providers. A long-running close valuation otherwise blocks watchlist
    # snapshot commits and makes the trends page appear to time out.
    holding_inputs = [
        {
            "id": holding.id,
            "code": holding.asset.code,
            "asset_type": holding.asset.asset_type,
            "units": Decimal(str(holding.units)),
            "cost_basis": Decimal(str(holding.cost_basis)) if holding.cost_basis is not None else None,
        }
        for holding in holdings
    ]
    session.commit()
    updated_count = 0
    failed_count = 0
    updates: list[tuple[int, Decimal, Decimal | None, str]] = []
    for item in holding_inputs:
        fetcher = fund_fetcher if item["asset_type"] == "fund" else stock_fetcher
        try:
            quote = fetcher(item["code"])
        except Exception:
            quote = {"ok": False}
        price = _close_price(quote, item["asset_type"])
        if not quote.get("ok") or price is None or price <= 0:
            failed_count += 1
            continue
        amount = (item["units"] * price).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        profit = None
        if item["cost_basis"] is not None:
            profit = (amount - item["cost_basis"]).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
        source = str(quote.get("source") or ("基金收盘估值" if item["asset_type"] == "fund" else "股票收盘行情"))
        updates.append((item["id"], amount, profit, source))
        updated_count += 1

    valuation_at = datetime.now(SHANGHAI_TZ).replace(tzinfo=None)
    for holding_id, amount, profit, source in updates:
        holding = session.get(Holding, holding_id)
        if holding is None:
            continue
        holding.amount = amount
        holding.profit = profit
        holding.last_valuation_at = valuation_at
        holding.last_valuation_source = source
        holding.last_update_type = "close_valuation"

    run.updated_count = updated_count
    run.failed_count = failed_count
    run.completed_at = datetime.now(timezone.utc).replace(tzinfo=None) if failed_count == 0 else None
    session.commit()
    status = "completed" if failed_count == 0 else "partial_failure"
    return _result(valuation_date, status, updated_count, failed_count)


def _close_price(quote: dict[str, Any], asset_type: str) -> Decimal | None:
    if not quote.get("ok"):
        return None
    raw = quote.get("price") if asset_type == "stock" else (
        quote.get("nav") if quote.get("data_status") == "official_nav" else quote.get("estimate_nav") or quote.get("nav")
    )
    if raw in (None, ""):
        return None
    try:
        return Decimal(str(raw))
    except Exception:
        return None


def _local_now(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(SHANGHAI_TZ)
    if value.tzinfo is None:
        return value.replace(tzinfo=SHANGHAI_TZ)
    return value.astimezone(SHANGHAI_TZ)


def _result(valuation_date: date, status: str, updated_count: int, failed_count: int) -> dict[str, Any]:
    return {
        "valuation_date": valuation_date.isoformat(),
        "status": status,
        "updated_count": updated_count,
        "failed_count": failed_count,
        "close_time": CLOSE_TIME.strftime("%H:%M"),
    }
