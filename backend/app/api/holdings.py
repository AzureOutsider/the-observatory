from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.db import get_session
from app.models import Holding, Transaction
from app.schemas import HoldingRead, HoldingUpdate, ImportHoldingsRequest, ImportHoldingsResponse
from app.services.importer import import_holdings_file

router = APIRouter(tags=["holdings"])


@router.get("/holdings", response_model=list[HoldingRead])
def list_holdings(session: Session = Depends(get_session)):
    _restore_missing_holdings(session)
    return (
        session.query(Holding)
        .options(joinedload(Holding.asset))
        .order_by(Holding.amount.desc())
        .all()
    )


def _restore_missing_holdings(session: Session) -> None:
    """Create snapshots for position-changing transactions recorded before auto-sync existed."""
    asset_ids = {
        asset_id
        for (asset_id,) in session.query(Transaction.asset_id)
        .outerjoin(Holding, Holding.asset_id == Transaction.asset_id)
        .filter(
            Holding.id.is_(None),
            Transaction.retracted_at.is_(None),
            Transaction.operation.in_(("buy", "sell", "transfer", "adjustment")),
        )
        .distinct()
        .all()
    }
    changed = False
    for asset_id in asset_ids:
        transactions = (
            session.query(Transaction)
            .filter(Transaction.asset_id == asset_id, Transaction.retracted_at.is_(None))
            .order_by(Transaction.id.asc())
            .all()
        )
        amount = Decimal("0")
        units = Decimal("0")
        has_units = False
        seen: set[tuple[object, ...]] = set()
        for transaction in transactions:
            if transaction.operation not in {"buy", "sell", "transfer", "adjustment"}:
                continue
            key = (
                transaction.operation,
                transaction.trade_date,
                transaction.amount,
                transaction.units,
                transaction.price,
                transaction.fee,
                transaction.reason,
            )
            if key in seen:
                continue
            seen.add(key)
            if transaction.operation == "adjustment":
                amount = transaction.amount or Decimal("0")
                if transaction.units is not None:
                    units = transaction.units
                    has_units = True
                continue
            sign = Decimal("-1") if transaction.operation == "sell" else Decimal("1")
            amount = max(Decimal("0"), amount + sign * (transaction.amount or Decimal("0")))
            if transaction.units is not None:
                units = max(Decimal("0"), units + sign * transaction.units)
                has_units = True
        if seen:
            session.add(Holding(asset_id=asset_id, amount=amount, units=units if has_units else None))
            changed = True
    if changed:
        session.commit()


@router.patch("/holdings/{holding_id}", response_model=HoldingRead)
def update_holding(holding_id: int, payload: HoldingUpdate, session: Session = Depends(get_session)):
    holding = (
        session.query(Holding)
        .options(joinedload(Holding.asset))
        .filter(Holding.id == holding_id)
        .one_or_none()
    )
    if holding is None:
        raise HTTPException(status_code=404, detail="持仓不存在")

    updates = payload.model_dump(exclude_unset=True)
    correction_reason = updates.pop("correction_reason", None)
    if not updates:
        raise HTTPException(status_code=400, detail="至少填写一个需要修正的字段")
    for field, value in updates.items():
        if value is not None and hasattr(value, "is_finite") and not value.is_finite():
            raise HTTPException(status_code=422, detail=f"{field} 必须是有限数字")
        setattr(holding, field, value)
    holding.last_manual_adjustment_at = datetime.now(timezone.utc).replace(tzinfo=None)
    holding.last_manual_adjustment_reason = (correction_reason or "").strip() or "未注明修正原因"
    holding.last_update_type = "manual_correction"

    session.commit()
    session.refresh(holding)
    return holding


@router.post("/import/holdings", response_model=ImportHoldingsResponse)
def import_holdings(payload: ImportHoldingsRequest, session: Session = Depends(get_session)):
    path = Path(payload.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {payload.path}")
    result = import_holdings_file(path, session)
    return ImportHoldingsResponse(imported=result.imported, skipped=result.skipped)
