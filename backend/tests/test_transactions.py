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


def test_create_buy_transaction(session):
    app = create_app()
    app.dependency_overrides[get_session] = override_session(session)
    client = TestClient(app)
    session.add(Asset(code="000001", name="Test Fund", asset_type="fund"))
    session.commit()

    response = client.post(
        "/api/transactions",
        json={
            "asset_code": "000001",
            "asset_type": "fund",
            "operation": "buy",
            "trade_date": str(date(2026, 7, 8)),
            "amount": "100.00",
            "units": "10.0",
            "price": "10.0",
            "fee": "0",
            "reason": "initial test buy",
        },
    )

    assert response.status_code == 201
    row = session.query(Transaction).one()
    assert row.operation == "buy"
    assert row.amount == Decimal("100.0000")
    assert row.asset.code == "000001"
    holding = session.query(Holding).one()
    assert holding.amount == Decimal("100.0000")
    assert holding.units == Decimal("10.000000")


def test_duplicate_transaction_retry_does_not_duplicate_holding(session):
    client = make_client(session)
    payload = {
        "asset_code": "519900",
        "asset_type": "fund",
        "asset_name": "Photovoltaic ETF",
        "operation": "buy",
        "trade_date": str(date(2026, 7, 8)),
        "amount": "83.40",
        "units": "100",
        "fee": "0",
    }

    first = client.post("/api/transactions", json=payload)
    second = client.post("/api/transactions", json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert session.query(Transaction).count() == 1
    assert session.query(Holding).one().amount == Decimal("83.4000")


def test_delete_buy_transaction_reverses_holding(session):
    client = make_client(session)
    payload = {
        "asset_code": "609900",
        "asset_type": "stock",
        "operation": "buy",
        "trade_date": str(date(2026, 7, 8)),
        "amount": "1200",
        "units": "100",
        "fee": "0",
    }
    created = client.post("/api/transactions", json=payload)
    transaction_id = created.json()["id"]

    response = client.delete(f"/api/transactions/{transaction_id}")

    assert response.status_code == 200
    retracted = session.query(Transaction).one()
    assert retracted.retracted_at is not None
    assert retracted.retraction_reason == "用户手动撤回"
    assert '"amount_before": "1200.0000"' in retracted.retraction_effect
    assert '"amount_after": "0.0000"' in retracted.retraction_effect
    holding = session.query(Holding).one()
    assert holding.amount == Decimal("0.0000")
    assert holding.units == Decimal("0.000000")


def test_adjustment_transaction_cannot_be_deleted(session):
    client = make_client(session)
    created = client.post(
        "/api/transactions",
        json={
            "asset_code": "000001",
            "asset_type": "fund",
            "operation": "adjustment",
            "trade_date": str(date(2026, 7, 8)),
            "amount": "100",
        },
    )

    response = client.delete(f"/api/transactions/{created.json()['id']}")

    assert response.status_code == 400


def test_rejects_invalid_operation(session):
    app = create_app()
    app.dependency_overrides[get_session] = override_session(session)
    client = TestClient(app)

    response = client.post(
        "/api/transactions",
        json={
            "asset_code": "000001",
            "asset_type": "fund",
            "operation": "gamble",
            "trade_date": str(date(2026, 7, 8)),
            "amount": "100.00",
        },
    )

    assert response.status_code == 422


def test_rejects_more_than_two_fractional_share_digits(session):
    response = make_client(session).post(
        "/api/transactions",
        json={
            "asset_code": "519900",
            "asset_type": "fund",
            "operation": "buy",
            "trade_date": str(date(2026, 7, 8)),
            "amount": "100",
            "units": "10.123",
        },
    )

    assert response.status_code == 422
