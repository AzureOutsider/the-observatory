import json
from decimal import Decimal

from app.models import Asset, Holding
from app.services.importer import import_holdings_file


def test_import_holdings_creates_assets_and_holdings(tmp_path, session):
    source = tmp_path / "fund_holdings.json"
    source.write_text(
        json.dumps(
            [{"name": "Test Fund", "code": "000001", "amount": 123.45, "profit": 6.78}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = import_holdings_file(source, session)

    assert result.imported == 1
    assert result.skipped == 0
    asset = session.query(Asset).one()
    holding = session.query(Holding).one()
    assert asset.code == "000001"
    assert asset.name == "Test Fund"
    assert asset.asset_type == "fund"
    assert holding.amount == Decimal("123.4500")
    assert holding.profit == Decimal("6.7800")


def test_import_holdings_skips_rows_without_code(tmp_path, session):
    source = tmp_path / "fund_holdings.json"
    source.write_text(json.dumps([{"name": "No Code", "amount": 10}]), encoding="utf-8")

    result = import_holdings_file(source, session)

    assert result.imported == 0
    assert result.skipped == 1
    assert session.query(Asset).count() == 0
