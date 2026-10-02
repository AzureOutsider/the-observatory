from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.db import get_session
from app.models import Asset, Holding, Transaction
from app.schemas import TransactionCreate, TransactionRead

router = APIRouter(tags=["transactions"])


def _money(value: Decimal | None, places: str = "0.0000") -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal(places))


def _optional_money(value: Decimal | None, places: str) -> Decimal | None:
    return None if value is None else _money(value, places)


def _audit_money(value: Decimal | None, places: str = "0.0000") -> str | None:
    return None if value is None else str(_money(value, places))


def _find_recent_duplicate(payload: TransactionCreate, asset_id: int, session: Session) -> Transaction | None:
    """Treat an accidental rapid retry as the same write, without blocking later trades."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=45)
    query = (
        session.query(Transaction)
        .filter(
            Transaction.asset_id == asset_id,
            Transaction.operation == payload.operation,
            Transaction.trade_date == payload.trade_date,
            Transaction.amount == _money(payload.amount),
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

    sign = Decimal("-1") if transaction.operation == "sell" else Decimal("1")
    holding.amount = max(Decimal("0"), (holding.amount or Decimal("0")) + sign * amount)
    if units is not None:
        holding.units = max(Decimal("0"), (holding.units or Decimal("0")) + sign * units)
    holding.last_update_type = "transaction"


@router.post("/transactions", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
def create_transaction(payload: TransactionCreate, session: Session = Depends(get_session)):
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

    duplicate = _find_recent_duplicate(payload, asset.id, session)
    if duplicate is not None:
        return duplicate

    transaction = Transaction(
        asset_id=asset.id,
        operation=payload.operation,
        trade_date=payload.trade_date,
        amount=_money(payload.amount),
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

    holding = session.query(Holding).filter(Holding.asset_id == transaction.asset_id).one_or_none()
    effect = {
        "holding_id": holding.id if holding else None,
        "amount_before": _audit_money(holding.amount) if holding else None,
        "units_before": _audit_money(holding.units, "0.000000") if holding and holding.units is not None else None,
    }
    if holding is not None and transaction.operation in {"buy", "sell", "transfer"}:
        sign = Decimal("-1") if transaction.operation in {"buy", "transfer"} else Decimal("1")
        holding.amount = max(Decimal("0"), (holding.amount or Decimal("0")) + sign * (transaction.amount or Decimal("0")))
        if transaction.units is not None:
            holding.units = max(Decimal("0"), (holding.units or Decimal("0")) + sign * transaction.units)
        holding.last_update_type = "transaction_retraction"
        effect["amount_after"] = _audit_money(holding.amount)
        effect["units_after"] = _audit_money(holding.units, "0.000000") if holding.units is not None else None

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
