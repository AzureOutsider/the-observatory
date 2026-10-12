from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.db import get_session
from app.models import Asset, Holding, Transaction
from app.schemas import TransactionCreate, TransactionRead

router = APIRouter(tags=["transactions"])


def _money(value: Decimal | None, places: str = "0.0000") -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def _optional_money(value: Decimal | None, places: str) -> Decimal | None:
    return None if value is None else _money(value, places)


def _audit_money(value: Decimal | None, places: str = "0.0000") -> str | None:
    return None if value is None else str(_money(value, places))


def _calculated_amount(payload: TransactionCreate) -> Decimal:
    """Calculate trade cash from shares, unit price and fee at the API boundary."""
    if payload.operation == "note":
        return Decimal("0.0000")
    if payload.units is not None and payload.price is not None:
        return _money(_money(payload.units, "0.000000") * _money(payload.price, "0.000000") + _money(payload.fee))
    # Retain the old amount-only API for existing integrations. The web form
    # supplies shares and price, and any caller-supplied amount is ignored there.
    return _money(payload.amount)


def _holding_cost(holding: Holding) -> Decimal | None:
    if holding.cost_basis is not None:
        return holding.cost_basis
    if holding.profit is not None:
        return max(Decimal("0"), (holding.amount or Decimal("0")) - holding.profit)
    if not holding.amount and not holding.units:
        return Decimal("0")
    return None


def _find_recent_duplicate(payload: TransactionCreate, asset_id: int, amount: Decimal, session: Session) -> Transaction | None:
    """Treat an accidental rapid retry as the same write, without blocking later trades."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=45)
    query = (
        session.query(Transaction)
        .filter(
            Transaction.asset_id == asset_id,
            Transaction.operation == payload.operation,
            Transaction.trade_date == payload.trade_date,
            Transaction.amount == amount,
            Transaction.fee == _money(payload.fee),
            Transaction.created_at >= cutoff,
            Transaction.retracted_at.is_(None),
        )
    )
    for row in query.order_by(Transaction.id.desc()).all():
        if row.units != _optional_money(payload.units, "0.000000"):
            continue
        if row.price != _optional_money(payload.price, "0.000000"):
            continue
        if (row.reason or None) == (payload.reason or None):
            return row
    return None


def _apply_transaction_to_holding(transaction: Transaction, session: Session) -> None:
    """Keep the current snapshot useful when a user records a position-changing action."""
    holding = session.query(Holding).filter(Holding.asset_id == transaction.asset_id).one_or_none()
    amount = transaction.amount or Decimal("0")
    units = transaction.units

    if transaction.operation == "note" or transaction.operation == "dividend":
        return
    if holding is None:
        if transaction.operation == "sell":
            return
        holding = Holding(asset_id=transaction.asset_id, amount=Decimal("0"))
        session.add(holding)
        session.flush()

    if transaction.operation == "adjustment":
        holding.amount = amount
        if units is not None:
            holding.units = units
        holding.last_update_type = "transaction"
        return

    old_units = holding.units or Decimal("0")
    old_cost = _holding_cost(holding)
    if old_cost is not None:
        if transaction.operation in {"buy", "transfer"}:
            holding.cost_basis = _money(old_cost + amount)
        elif transaction.operation == "sell":
            if units is not None and old_units > 0:
                holding.cost_basis = _money(old_cost * max(Decimal("0"), old_units - units) / old_units)
            elif holding.amount:
                holding.cost_basis = _money(old_cost * max(Decimal("0"), holding.amount - amount) / holding.amount)
            else:
                holding.cost_basis = old_cost
        # Record the cost removed on a sale so even a full-sale retraction can
        # restore it without inferring it from the remaining (zero) position.
        transaction.holding_cost_delta = holding.cost_basis - old_cost

    sign = Decimal("-1") if transaction.operation == "sell" else Decimal("1")
    holding.amount = max(Decimal("0"), (holding.amount or Decimal("0")) + sign * amount)
    if units is not None:
        holding.units = max(Decimal("0"), (holding.units or Decimal("0")) + sign * units)
    if holding.cost_basis is not None:
        holding.profit = _money(holding.amount - holding.cost_basis)
    holding.last_update_type = "transaction"


@router.post("/transactions", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
def create_transaction(payload: TransactionCreate, session: Session = Depends(get_session)):
    amount = _calculated_amount(payload)
    asset = (
        session.query(Asset)
        .filter(Asset.code == payload.asset_code, Asset.asset_type == payload.asset_type)
        .one_or_none()
    )
    if asset is None:
        asset = Asset(
            code=payload.asset_code,
            name=payload.asset_name or payload.asset_code,
            asset_type=payload.asset_type,
        )
        session.add(asset)
        session.flush()

    duplicate = _find_recent_duplicate(payload, asset.id, amount, session)
    if duplicate is not None:
        return duplicate

    transaction = Transaction(
        asset_id=asset.id,
        operation=payload.operation,
        trade_date=payload.trade_date,
        amount=amount,
        units=_money(payload.units, "0.000000") if payload.units is not None else None,
        price=_money(payload.price, "0.000000") if payload.price is not None else None,
        fee=_money(payload.fee),
        reason=payload.reason,
    )
    session.add(transaction)
    session.flush()
    _apply_transaction_to_holding(transaction, session)
    session.commit()
    session.refresh(transaction)
    return transaction


@router.delete("/transactions/{transaction_id}")
def delete_transaction(transaction_id: int, session: Session = Depends(get_session)):
    transaction = (
        session.query(Transaction)
        .options(joinedload(Transaction.asset))
        .filter(Transaction.id == transaction_id)
        .one_or_none()
    )
    if transaction is None:
        raise HTTPException(status_code=404, detail="操作记录不存在")
    if transaction.retracted_at is not None:
        raise HTTPException(status_code=400, detail="这条流水已经撤回")
    if transaction.operation == "adjustment":
        raise HTTPException(status_code=400, detail="调整流水无法安全撤回，请使用持仓修正")

    position_operations = ("buy", "sell", "transfer", "adjustment")
    if transaction.operation in position_operations:
        later_operation = (
            session.query(Transaction.id)
            .filter(
                Transaction.asset_id == transaction.asset_id,
                Transaction.id > transaction.id,
                Transaction.operation.in_(position_operations),
                Transaction.retracted_at.is_(None),
            )
            .first()
        )
        if later_operation is not None:
            raise HTTPException(status_code=400, detail="请先按倒序撤回后续持仓操作，避免成本和持仓错位")

    holding = session.query(Holding).filter(Holding.asset_id == transaction.asset_id).one_or_none()
    if (
        holding is not None
        and transaction.operation in position_operations
        and holding.last_manual_adjustment_at is not None
        and transaction.created_at is not None
        and holding.last_manual_adjustment_at > transaction.created_at
    ):
        raise HTTPException(status_code=400, detail="这条流水之后已手动修正持仓，请先核对持仓再撤回")
    effect = {
        "holding_id": holding.id if holding else None,
        "amount_before": _audit_money(holding.amount) if holding else None,
        "units_before": _audit_money(holding.units, "0.000000") if holding and holding.units is not None else None,
        "cost_basis_before": _audit_money(holding.cost_basis) if holding else None,
    }
    if holding is not None and transaction.operation in {"buy", "sell", "transfer"}:
        cost = _holding_cost(holding)
        cost_delta = transaction.holding_cost_delta
        if cost is not None:
            if cost_delta is None and transaction.operation in {"buy", "transfer"}:
                cost_delta = transaction.amount or Decimal("0")
            if cost_delta is None and transaction.operation == "sell":
                raise HTTPException(status_code=400, detail="旧卖出流水缺少成本记录，请使用持仓修正核对成本")
            holding.cost_basis = _money(max(Decimal("0"), cost - (cost_delta or Decimal("0"))))
        sign = Decimal("-1") if transaction.operation in {"buy", "transfer"} else Decimal("1")
        holding.amount = max(Decimal("0"), (holding.amount or Decimal("0")) + sign * (transaction.amount or Decimal("0")))
        if transaction.units is not None:
            holding.units = max(Decimal("0"), (holding.units or Decimal("0")) + sign * transaction.units)
        if holding.cost_basis is not None:
            holding.profit = _money(holding.amount - holding.cost_basis)
        holding.last_update_type = "transaction_retraction"
        effect["amount_after"] = _audit_money(holding.amount)
        effect["units_after"] = _audit_money(holding.units, "0.000000") if holding.units is not None else None
        effect["cost_basis_after"] = _audit_money(holding.cost_basis)

    transaction.retracted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    transaction.retraction_reason = "用户手动撤回"
    transaction.retraction_effect = json.dumps(effect, ensure_ascii=False)
    session.commit()
    return {"status": "ok", "id": transaction_id}


@router.get("/transactions", response_model=list[TransactionRead])
def list_transactions(session: Session = Depends(get_session)):
    return (
        session.query(Transaction)
        .options(joinedload(Transaction.asset))
        .order_by(Transaction.trade_date.desc(), Transaction.id.desc())
        .all()
    )
