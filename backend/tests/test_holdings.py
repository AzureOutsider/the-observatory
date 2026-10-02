from datetime import date
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
