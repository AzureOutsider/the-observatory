from datetime import date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db import get_session
from app.main import create_app
from app.models import Asset, Holding, Transaction


def override_session(session):
    def dependency():
        try:
            yield session
        finally:
            pass

    return dependency


def make_client(session):
    app = create_app()
    app.dependency_overrides[get_session] = override_session(session)
    return TestClient(app)


def test_update_holding_fields(session):
    asset = Asset(code="000001", name="Test Fund", asset_type="fund")
    holding = Holding(asset=asset, amount=Decimal("100.00"), profit=Decimal("2.00"))
    session.add(holding)
    session.commit()

    response = make_client(session).patch(
        f"/api/holdings/{holding.id}",
        json={"amount": "1250.50", "profit": "18.25", "units": "100.5", "correction_reason": "与券商账单核对"},
    )

    assert response.status_code == 200
    session.refresh(holding)
    assert holding.amount == Decimal("1250.5000")
    assert holding.profit == Decimal("18.2500")
    assert holding.units == Decimal("100.500000")
    assert holding.last_manual_adjustment_at is not None
    assert holding.last_manual_adjustment_reason == "与券商账单核对"
    assert holding.last_update_type == "manual_correction"
    assert response.json()["manual_adjusted"] is True


def test_update_holding_rejects_empty_payload_and_missing_row(session):
    client = make_client(session)
    empty = client.patch("/api/holdings/1", json={})
    assert empty.status_code == 404

    asset = Asset(code="000002", name="Test Stock", asset_type="stock")
    holding = Holding(asset=asset, amount=Decimal("10"))
    session.add(holding)
    session.commit()

    response = client.patch(f"/api/holdings/{holding.id}", json={})
    assert response.status_code == 400


def test_update_holding_rejects_negative_amount(session):
    asset = Asset(code="000003", name="Test ETF", asset_type="fund")
    holding = Holding(asset=asset, amount=Decimal("10"))
    session.add(holding)
    session.commit()

    response = make_client(session).patch(f"/api/holdings/{holding.id}", json={"amount": "-1"})
    assert response.status_code == 422


def test_list_holdings_restores_missing_snapshot_and_deduplicates_exact_retries(session):
    asset = Asset(code="519900", name="Photovoltaic ETF", asset_type="fund")
    session.add(asset)
    session.flush()
    for _ in range(3):
        session.add(Transaction(asset_id=asset.id, operation="buy", trade_date=date(2026, 8, 31), amount=Decimal("83.40"), units=Decimal("100"), fee=Decimal("0")))
    session.commit()

    response = make_client(session).get("/api/holdings")

    assert response.status_code == 200
    assert response.json()[0]["asset"]["code"] == "519900"
    assert Decimal(response.json()[0]["amount"]) == Decimal("83.4000")
    assert Decimal(response.json()[0]["cost_basis"]) == Decimal("83.4000")


def test_restore_missing_snapshot_reduces_average_cost_on_sale(session):
    asset = Asset(code="519900", name="Example ETF", asset_type="fund")
    session.add(asset)
    session.flush()
    session.add_all([
        Transaction(asset_id=asset.id, operation="buy", trade_date=date(2026, 1, 2),
                    amount=Decimal("300"), units=Decimal("400"), fee=Decimal("0")),
        Transaction(asset_id=asset.id, operation="sell", trade_date=date(2026, 1, 3),
                    amount=Decimal("100"), units=Decimal("100"), fee=Decimal("0")),
    ])
    session.commit()

    response = make_client(session).get("/api/holdings")

    assert response.status_code == 200
    row = response.json()[0]
    assert Decimal(row["units"]) == Decimal("300")
    assert Decimal(row["cost_basis"]) == Decimal("225")


def test_rename_holding_survives_market_name_update_without_changing_position(session):
    asset = Asset(code="519900", name="Short name", asset_type="fund")
    holding = Holding(asset=asset, amount=Decimal("100"), units=Decimal("50"), cost_basis=Decimal("80"))
    session.add(holding)
    session.commit()
    client = make_client(session)
    response = client.patch(f"/api/holdings/{holding.id}", json={"custom_name": "  Example Semiconductor ETF  "})
    assert response.status_code == 200
    assert response.json()["asset"]["custom_name"] == "Example Semiconductor ETF"
    assert response.json()["manual_adjusted"] is False
    assert holding.last_manual_adjustment_at is None
    assert holding.amount == Decimal("100")
    assert holding.units == Decimal("50")
    assert holding.cost_basis == Decimal("80")
    assert session.query(Transaction).count() == 0
    asset.name = "Updated market name"
    session.commit()
    row = client.get("/api/holdings").json()[0]
    assert row["asset"]["custom_name"] == "Example Semiconductor ETF"
    assert row["asset"]["name"] == "Updated market name"
    cleared = client.patch(f"/api/holdings/{holding.id}", json={"custom_name": " "})
    assert cleared.status_code == 200
    assert cleared.json()["asset"]["custom_name"] is None
    assert holding.last_manual_adjustment_at is None


def test_rename_and_snapshot_correction_records_manual_audit(session):
    holding = Holding(asset=Asset(code="519900", name="ETF", asset_type="fund"), amount=Decimal("100"))
    session.add(holding)
    session.commit()
    response = make_client(session).patch(f"/api/holdings/{holding.id}", json={
        "custom_name": "Example ETF", "units": "80", "correction_reason": "broker reconciliation",
    })
    assert response.status_code == 200
    assert response.json()["asset"]["custom_name"] == "Example ETF"
    assert response.json()["manual_adjusted"] is True
    assert holding.last_manual_adjustment_reason == "broker reconciliation"


def test_rename_rejects_overlong_name(session):
    holding = Holding(asset=Asset(code="519900", name="ETF", asset_type="fund"), amount=Decimal("100"))
    session.add(holding)
    session.commit()
    assert make_client(session).patch(f"/api/holdings/{holding.id}", json={"custom_name": "x" * 256}).status_code == 422
    assert holding.asset.custom_name is None


def test_holding_history_filters_asset_identity_and_keeps_retractions_in_date_order(session):
    asset = Asset(code="519900", name="ETF", asset_type="fund")
    other = Asset(code="519900", name="Index with same code", asset_type="index")
    holding = Holding(asset=asset, amount=Decimal("100"))
    session.add_all([holding, other])
    session.flush()
    rows = [
        Transaction(asset_id=asset.id, operation="buy", trade_date=date(2026, 1, 3), amount=Decimal("20.1"), units=Decimal("10"), price=Decimal("2"), fee=Decimal("0.1"), reason="initial buy"),
        Transaction(asset_id=other.id, operation="buy", trade_date=date(2026, 1, 4), amount=Decimal("50")),
        Transaction(asset_id=asset.id, operation="sell", trade_date=date(2026, 1, 2), amount=Decimal("9.9"), fee=Decimal("0.1"), retracted_at=datetime(2026, 1, 4), retraction_reason="duplicate"),
        Transaction(asset_id=asset.id, operation="note", trade_date=date(2026, 1, 3), amount=Decimal("0"), reason="review"),
    ]
    session.add_all(rows)
    session.commit()
    client = make_client(session)
    response = client.get(f"/api/holdings/{holding.id}/transactions")
    assert response.status_code == 200
    result = response.json()
    assert [row["id"] for row in result] == [rows[3].id, rows[0].id, rows[2].id]
    assert result[1]["reason"] == "initial buy"
    assert Decimal(result[1]["price"]) == Decimal("2")
    assert Decimal(result[1]["units"]) == Decimal("10")
    assert Decimal(result[1]["fee"]) == Decimal("0.1")
    assert result[2]["retracted_at"] is not None
    assert result[2]["retraction_reason"] == "duplicate"
    assert client.get("/api/holdings/9999/transactions").status_code == 404


def test_holding_history_without_recorded_transactions_is_empty(session):
    holding = Holding(asset=Asset(code="519900", name="ETF", asset_type="fund"), amount=Decimal("100"))
    session.add(holding)
    session.commit()
    response = make_client(session).get(f"/api/holdings/{holding.id}/transactions")
    assert response.status_code == 200
    assert response.json() == []
