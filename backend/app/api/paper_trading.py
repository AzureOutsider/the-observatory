from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db import get_session
from app.models import PaperAsset, PaperPriceSnapshot, PaperTrade
from app.schemas import PaperPortfolioPosition, PaperQuoteRead, PaperTradeCreate, PaperTradeRead
from app.services.market import fetch_fund_estimate, fetch_stock_quote

router = APIRouter(tags=["paper trading"])
FOUR_PLACES = Decimal("0.0001")
SIX_PLACES = Decimal("0.000001")


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)


def _replay(trades: list[PaperTrade], *, ignored_trade_id: int | None = None) -> tuple[Decimal, Decimal, Decimal]:
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
            cost_basis = _money(cost_basis + amount)
            continue
        if shares > units:
            raise ValueError("模拟卖出份额超过此前日期的模拟持仓；请检查交易日期或先补录买入")
        removed_cost = _money(cost_basis * shares / units) if units else Decimal("0")
        realized_profit = _money(realized_profit + amount - removed_cost)
        units -= shares
        cost_basis = _money(max(Decimal("0"), cost_basis - removed_cost))
    return units, cost_basis, realized_profit


def _trade_amount(payload: PaperTradeCreate) -> Decimal:
    gross = Decimal(payload.units) * Decimal(payload.price)
    amount = gross + payload.fee if payload.operation == "buy" else gross - payload.fee
    if amount < 0:
        raise HTTPException(status_code=422, detail="卖出手续费不能高于卖出金额")
    return _money(amount)


def _same_idempotent_request(trade: PaperTrade, payload: PaperTradeCreate, code: str) -> bool:
    return (
        trade.asset.code == code
        and trade.asset.asset_type == payload.asset_type
        and trade.operation == payload.operation
        and trade.trade_date == payload.trade_date
        and trade.units == Decimal(payload.units).quantize(SIX_PLACES)
        and trade.price == Decimal(payload.price).quantize(SIX_PLACES)
        and trade.fee == _money(payload.fee)
        and (trade.reason or None) == ((payload.reason or "").strip() or None)
    )


def _find_idempotent_trade(session: Session, key) -> PaperTrade | None:
    return (
        session.query(PaperTrade)
        .options(joinedload(PaperTrade.asset))
        .filter_by(idempotency_key=str(key))
        .one_or_none()
    )


def _quote_price(asset_type: str, quote: dict) -> Decimal | None:
    if not quote.get("ok"):
        return None
    value = quote.get("price") if asset_type == "stock" else (
        quote.get("nav") if quote.get("data_status") == "official_nav" else quote.get("estimate_nav") or quote.get("nav")
    )
    if value in (None, ""):
        return None
    try:
        price = Decimal(str(value))
    except Exception:
        return None
    if not price.is_finite():
        return None
    return price.quantize(SIX_PLACES, rounding=ROUND_HALF_UP) if price > 0 else None


@router.get("/paper/portfolio", response_model=list[PaperPortfolioPosition])
def paper_portfolio(session: Session = Depends(get_session)):
    assets = session.query(PaperAsset).options(selectinload(PaperAsset.trades)).order_by(PaperAsset.id.desc()).all()
    latest_quotes: dict[int, PaperPriceSnapshot] = {}
    latest_ids = (
        session.query(PaperPriceSnapshot.asset_id, func.max(PaperPriceSnapshot.id).label("snapshot_id"))
        .group_by(PaperPriceSnapshot.asset_id)
        .subquery()
    )
    snapshots = session.query(PaperPriceSnapshot).join(latest_ids, PaperPriceSnapshot.id == latest_ids.c.snapshot_id).all()
    latest_quotes = {snapshot.asset_id: snapshot for snapshot in snapshots}
    positions: list[PaperPortfolioPosition] = []
    for asset in assets:
        trades = [row for row in asset.trades if row.retracted_at is None]
        units, cost_basis, realized_profit = _replay(trades)
        market_price = market_value = unrealized_profit = total_profit = None
        quote_status = "closed" if units == 0 else "unavailable"
        quote_message = quote_source = quote_time = None
        snapshot = latest_quotes.get(asset.id) if units > 0 else None
        if snapshot is not None:
            market_price = Decimal(snapshot.price)
            market_value = _money(units * market_price)
            unrealized_profit = _money(market_value - cost_basis)
            total_profit = _money(realized_profit + unrealized_profit)
            quote_status = snapshot.quote_status
            quote_message = snapshot.message
            quote_source = snapshot.source
            quote_time = snapshot.quote_time
        elif units > 0:
            quote_status = "not_loaded"
            quote_message = "尚无模拟行情快照，请手动刷新行情"
        positions.append(PaperPortfolioPosition(
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
        ))
    return positions


@router.post("/paper/refresh")
def refresh_paper_quotes(session: Session = Depends(get_session)):
    assets = session.query(PaperAsset).options(selectinload(PaperAsset.trades)).all()
    asset_inputs: list[tuple[int, str, str]] = []
    for asset in assets:
        units, _, _ = _replay([row for row in asset.trades if row.retracted_at is None])
        if units > 0:
            asset_inputs.append((asset.id, asset.code, asset.asset_type))
    session.commit()
    if not asset_inputs:
        return {"updated": 0, "failed": 0, "message": "没有待估值的模拟持仓"}

    def fetch(asset: tuple[int, str, str]) -> tuple[tuple[int, str, str], dict]:
        _, code, asset_type = asset
        try:
            quote = fetch_stock_quote(code) if asset_type == "stock" else fetch_fund_estimate(code, record_health=False)
            return asset, quote
        except Exception as exc:
            return asset, {"ok": False, "error": str(exc)}

    with ThreadPoolExecutor(max_workers=min(6, len(asset_inputs))) as executor:
        results = list(executor.map(fetch, asset_inputs))

    updated = failed = 0
    captured_at = datetime.now().astimezone().replace(tzinfo=None)
    for asset_input, quote in results:
        asset_id, _, asset_type = asset_input
        price = _quote_price(asset_type, quote)
        if price is None:
            failed += 1
            continue
        session.add(PaperPriceSnapshot(
            asset_id=asset_id,
            captured_at=captured_at,
            price=price,
            change_pct=Decimal(str(quote["change_pct"])) if quote.get("change_pct") is not None else None,
            quote_status=str(quote.get("data_status") or "intraday_estimate"),
            quote_time=str(quote.get("time") or "") or None,
            source=str(quote.get("source") or "") or None,
            message=str(quote.get("message") or "") or None,
        ))
        updated += 1
    session.commit()
    return {"updated": updated, "failed": failed}


@router.get("/paper/assets/{asset_id}/quotes", response_model=list[PaperQuoteRead])
def paper_asset_quotes(asset_id: int, session: Session = Depends(get_session)):
    if session.get(PaperAsset, asset_id) is None:
        raise HTTPException(status_code=404, detail="模拟标的不存在")
    return (
        session.query(PaperPriceSnapshot)
        .filter(PaperPriceSnapshot.asset_id == asset_id)
        .order_by(PaperPriceSnapshot.captured_at.asc(), PaperPriceSnapshot.id.asc())
        .all()
    )


@router.get("/paper/assets/{asset_id}/trades", response_model=list[PaperTradeRead])
def paper_asset_trades(asset_id: int, session: Session = Depends(get_session)):
    asset = session.get(PaperAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="模拟标的不存在")
    return (
        session.query(PaperTrade)
        .filter(PaperTrade.asset_id == asset_id)
        .order_by(PaperTrade.trade_date.desc(), PaperTrade.id.desc())
        .all()
    )


@router.post("/paper/trades", response_model=PaperTradeRead, status_code=status.HTTP_201_CREATED)
def create_paper_trade(payload: PaperTradeCreate, session: Session = Depends(get_session)):
    code = payload.asset_code.strip().upper()
    name = payload.asset_name.strip()
    if not code or not name:
        raise HTTPException(status_code=422, detail="请填写标的代码和名称")
    if payload.idempotency_key is not None:
        existing = _find_idempotent_trade(session, payload.idempotency_key)
        if existing is not None:
            if not _same_idempotent_request(existing, payload, code):
                raise HTTPException(status_code=409, detail="此模拟请求标识已用于不同操作")
            return existing
    asset = session.query(PaperAsset).filter_by(code=code, asset_type=payload.asset_type).one_or_none()
    if asset is None:
        asset = PaperAsset(code=code, name=name, asset_type=payload.asset_type)
        session.add(asset)
        try:
            session.flush()
        except IntegrityError as exc:
            session.rollback()
            if payload.idempotency_key is not None:
                existing = _find_idempotent_trade(session, payload.idempotency_key)
                if existing is not None:
                    if _same_idempotent_request(existing, payload, code):
                        return existing
                    raise HTTPException(status_code=409, detail="此模拟请求标识已用于不同操作") from exc
            asset = session.query(PaperAsset).filter_by(code=code, asset_type=payload.asset_type).one_or_none()
            if asset is None:
                raise HTTPException(status_code=409, detail="模拟标的正在并发创建，请读取模拟盘后重试") from exc
            if payload.idempotency_key is not None:
                existing = _find_idempotent_trade(session, payload.idempotency_key)
                if existing is not None:
                    if _same_idempotent_request(existing, payload, code):
                        return existing
                    raise HTTPException(status_code=409, detail="此模拟请求标识已用于不同操作") from exc
            asset.name = name
    else:
        asset.name = name

    amount = _trade_amount(payload)
    normalized_fee = _money(payload.fee)
    normalized_units = Decimal(payload.units).quantize(SIX_PLACES)
    normalized_price = Decimal(payload.price).quantize(SIX_PLACES)
    trade = PaperTrade(
        asset_id=asset.id,
        operation=payload.operation,
        trade_date=payload.trade_date,
        amount=amount,
        units=normalized_units,
        price=normalized_price,
        fee=normalized_fee,
        reason=payload.reason.strip() if payload.reason and payload.reason.strip() else None,
        idempotency_key=str(payload.idempotency_key) if payload.idempotency_key is not None else None,
    )
    session.add(trade)
    try:
        session.flush()
        all_trades = session.query(PaperTrade).filter(PaperTrade.asset_id == asset.id).all()
        _replay(all_trades)
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        session.rollback()
        if payload.idempotency_key is None:
            raise
        existing = (
            session.query(PaperTrade)
            .options(joinedload(PaperTrade.asset))
            .filter_by(idempotency_key=str(payload.idempotency_key))
            .one_or_none()
        )
        if existing is not None and _same_idempotent_request(existing, payload, code):
            return existing
        raise HTTPException(status_code=409, detail="模拟操作发生并发冲突，请读取模拟流水后重试") from exc
    session.refresh(trade)
    return trade


@router.delete("/paper/trades/{trade_id}")
def retract_paper_trade(trade_id: int, session: Session = Depends(get_session)):
    trade = (
        session.query(PaperTrade)
        .options(joinedload(PaperTrade.asset))
        .filter(PaperTrade.id == trade_id)
        .one_or_none()
    )
    if trade is None:
        raise HTTPException(status_code=404, detail="模拟操作不存在")
    if trade.retracted_at is not None:
        raise HTTPException(status_code=400, detail="这条模拟操作已经撤回")
    trades = session.query(PaperTrade).filter(PaperTrade.asset_id == trade.asset_id).all()
    try:
        _replay(trades, ignored_trade_id=trade.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="该操作之后已有模拟操作，请先撤回后续操作") from exc
    trade.retracted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    trade.retraction_reason = "用户手动撤回"
    session.commit()
    return {"status": "ok", "id": trade_id}
