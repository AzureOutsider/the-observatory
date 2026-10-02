import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Asset, Holding


@dataclass(frozen=True)
class ImportResult:
    imported: int
    skipped: int


def quantize_money(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.0001"))


def import_holdings_file(path: str | Path, session: Session) -> ImportResult:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    imported = 0
    skipped = 0

    for row in payload:
        code = str(row.get("code", "")).strip()
        if not code:
            skipped += 1
            continue

        name = str(row.get("name") or code).strip()
        asset = (
            session.query(Asset)
            .filter(Asset.code == code, Asset.asset_type == "fund")
            .one_or_none()
        )
        if asset is None:
            asset = Asset(code=code, name=name, asset_type="fund")
            session.add(asset)
            session.flush()
        else:
            asset.name = name

        holding = session.query(Holding).filter(Holding.asset_id == asset.id).one_or_none()
        if holding is None:
            holding = Holding(asset_id=asset.id)
            session.add(holding)

        holding.amount = quantize_money(row.get("amount", 0))
        holding.profit = quantize_money(row.get("profit", 0))
        holding.last_update_type = "import"
        imported += 1

    session.commit()
    return ImportResult(imported=imported, skipped=skipped)
