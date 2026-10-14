from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.models import PaperAsset, PaperPriceSnapshot, PaperTrade
from app.schemas import PaperPortfolioPosition

FOUR_PLACES = Decimal("0.0001")
SIX_PLACES = Decimal("0.000001")


def money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)


def replay_paper_trades(
    trades: list[PaperTrade], *, ignored_trade_id: int | None = None
) -> tuple[Decimal, Decimal, Decimal]:
    units = Decimal("0")
    cost_basis = Decimal("0")
    realized_profit = Decimal("0")
    active = sorted(
        (row for row in trades if row.retracted_at is None and row.id != ignored_trade_id),
        key=lambda row: (row.trade_date, row.id),
    )
    for trade in active:
        shares = Decimal(trade.units)
        amount = Decimal(trade.amount)
        if trade.operation == "buy":
            units += shares
            cost_basis = money(cost_basis + amount)
            continue
        if shares > units:
            raise ValueError("模拟卖出份额超过此前日期的模拟持仓；请检查交易日期或先补录买入")
        removed_cost = money(cost_basis * shares / units) if units else Decimal("0")
        realized_profit = money(realized_profit + amount - removed_cost)
        units -= shares
        cost_basis = money(max(Decimal("0"), cost_basis - removed_cost))
    return units, cost_basis, realized_profit


def get_paper_portfolio(session: Session) -> list[PaperPortfolioPosition]:
    assets = (
        session.query(PaperAsset)
        .options(selectinload(PaperAsset.trades))
        .order_by(PaperAsset.id.desc())
        .all()
    )
    ranked_snapshots = (
        session.query(
            PaperPriceSnapshot.id.label("snapshot_id"),
            func.row_number()
            .over(
                partition_by=PaperPriceSnapshot.asset_id,
                order_by=(PaperPriceSnapshot.captured_at.desc(), PaperPriceSnapshot.id.desc()),
            )
            .label("snapshot_rank"),
        )
        .subquery()
    )
    snapshots = (
        session.query(PaperPriceSnapshot)
        .join(ranked_snapshots, PaperPriceSnapshot.id == ranked_snapshots.c.snapshot_id)
        .filter(ranked_snapshots.c.snapshot_rank == 1)
        .all()
    )
    latest_quotes = {snapshot.asset_id: snapshot for snapshot in snapshots}
    positions: list[PaperPortfolioPosition] = []
    for asset in assets:
        trades = [row for row in asset.trades if row.retracted_at is None]
        units, cost_basis, realized_profit = replay_paper_trades(trades)
        market_price = market_value = unrealized_profit = total_profit = None
        quote_status = "closed" if units == 0 else "unavailable"
        quote_message = quote_source = quote_time = None
        snapshot = latest_quotes.get(asset.id) if units > 0 else None
        if snapshot is not None:
            market_price = Decimal(snapshot.price)
            market_value = money(units * market_price)
            unrealized_profit = money(market_value - cost_basis)
            total_profit = money(realized_profit + unrealized_profit)
            quote_status = snapshot.quote_status
            quote_message = snapshot.message
            quote_source = snapshot.source
            quote_time = snapshot.quote_time
        elif units > 0:
            quote_status = "not_loaded"
            quote_message = "尚无模拟行情快照，请手动刷新行情"
        positions.append(
            PaperPortfolioPosition(
                id=asset.id,
                code=asset.code,
                name=asset.name,
                asset_type=asset.asset_type,
                units=units.quantize(SIX_PLACES),
                cost_basis=cost_basis,
                realized_profit=realized_profit,
                market_price=market_price,
                market_value=market_value,
                unrealized_profit=unrealized_profit,
                total_profit=total_profit,
                quote_status=quote_status,
                quote_message=quote_message,
                quote_source=quote_source,
                quote_time=quote_time,
                trade_count=len(trades),
                is_open=units > 0,
            )
        )
    return positions
