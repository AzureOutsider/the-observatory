from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session, joinedload

from app.models import PaperPriceSnapshot, PaperTrade
from app.schemas import (
    PaperAgentContext,
    PaperAgentOperation,
    PaperAgentPosition,
    PaperAgentSummary,
    PaperQuoteRead,
    PaperTradeRead,
)
from app.services.paper_portfolio import get_paper_portfolio, money


def build_paper_agent_context(session: Session) -> PaperAgentContext:
    """Build a standalone Agent package from the simulated ledger only."""
    portfolio = get_paper_portfolio(session)
    trades = (
        session.query(PaperTrade)
        .options(joinedload(PaperTrade.asset))
        .order_by(PaperTrade.trade_date.desc(), PaperTrade.id.desc())
        .all()
    )
    quotes = (
        session.query(PaperPriceSnapshot)
        .order_by(PaperPriceSnapshot.captured_at.asc(), PaperPriceSnapshot.id.asc())
        .all()
    )
    trades_by_asset: dict[int, list[PaperTradeRead]] = {}
    operations: list[PaperAgentOperation] = []
    for trade in trades:
        read = PaperTradeRead.model_validate(trade)
        trades_by_asset.setdefault(trade.asset_id, []).append(read)
        operations.append(
            PaperAgentOperation(
                **read.model_dump(),
                asset_code=trade.asset.code,
                asset_name=trade.asset.name,
                asset_type=trade.asset.asset_type,
                cash_flow=money(-read.amount if read.operation == "buy" else read.amount),
            )
        )
    quotes_by_asset: dict[int, list[PaperQuoteRead]] = {}
    for quote in quotes:
        quotes_by_asset.setdefault(quote.asset_id, []).append(PaperQuoteRead.model_validate(quote))

    positions: list[PaperAgentPosition] = []
    for position in portfolio:
        position_data = position.model_dump()
        if not position.is_open:
            position_data.update(
                market_value=Decimal("0"),
                unrealized_profit=Decimal("0"),
                total_profit=position.realized_profit,
            )
        positions.append(
            PaperAgentPosition(
                **position_data,
                trades=trades_by_asset.get(position.id, []),
                quotes=quotes_by_asset.get(position.id, []),
            )
        )
    open_positions = [position for position in portfolio if position.is_open]
    unpriced_count = sum(1 for position in open_positions if position.market_value is None)
    total_cost_basis = money(sum((position.cost_basis for position in portfolio), Decimal("0")))
    total_realized = money(sum((position.realized_profit for position in portfolio), Decimal("0")))
    total_market_value = (
        money(sum((position.market_value or Decimal("0") for position in open_positions), Decimal("0")))
        if unpriced_count == 0
        else None
    )
    total_unrealized = (
        money(sum((position.unrealized_profit or Decimal("0") for position in open_positions), Decimal("0")))
        if unpriced_count == 0
        else None
    )
    now = datetime.now().astimezone()
    return PaperAgentContext(
        schema_version="1.0",
        generated_at=now,
        date=now.date(),
        scope="paper_portfolio_only",
        real_portfolio_included=False,
        agent_notes=[
            "这是独立模拟账本，不代表真实持仓或真实交易。",
            "买入金额 = 份额 × 成交价 + 手续费；卖出到账 = 份额 × 成交价 − 手续费。",
            "operations.cash_flow 中买入为负数（模拟支出），卖出为正数（模拟到账）。",
            "行情快照仅用于复盘估值，不会修改模拟成交价。",
            "撤回操作保留在 operations 历史中，但不参与当前持仓和盈亏计算。",
        ],
        summary=PaperAgentSummary(
            asset_count=len(portfolio),
            open_position_count=len(open_positions),
            operation_count=len(operations),
            active_operation_count=sum(1 for trade in trades if trade.retracted_at is None),
            total_cost_basis=total_cost_basis,
            total_market_value=total_market_value,
            total_realized_profit=total_realized,
            total_unrealized_profit=total_unrealized,
            total_profit=money(total_realized + total_unrealized) if total_unrealized is not None else None,
            unpriced_open_position_count=unpriced_count,
        ),
        positions=positions,
        operations=operations,
    )
