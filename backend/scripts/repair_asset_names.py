"""Repair asset names in the local database from the canonical holdings file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db import SessionLocal, init_db
from app.models import Asset

DEFAULT_SOURCE = Path(__file__).resolve().parents[1] / "data" / "fund_holdings.json"


def repair_asset_names(source: str | Path, *, dry_run: bool = False) -> int:
    source_path = Path(source)
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    names = {
        str(row.get("code", "")).strip(): str(row.get("name", "")).strip()
        for row in payload
        if str(row.get("code", "")).strip() and str(row.get("name", "")).strip()
    }

    updated = 0
    with SessionLocal() as session:
        for asset in session.query(Asset).filter(Asset.asset_type == "fund").all():
            name = names.get(asset.code)
            if name and asset.name != name:
                asset.name = name
                updated += 1
        if dry_run:
            session.rollback()
        else:
            session.commit()
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.source.exists():
        raise SystemExit(f"Canonical holdings file not found: {args.source}")
    init_db()
    updated = repair_asset_names(args.source, dry_run=args.dry_run)
    action = "would update" if args.dry_run else "updated"
    print(f"{action} {updated} asset name(s)")


if __name__ == "__main__":
    main()
