from datetime import date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
import pytest

from app.db import get_session
from app.main import create_app
from app.models import Asset, Holding, Transaction
from app.services.portfolio_valuation import refresh_closed_portfolio


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
            "units": "10.0",
            "price": "10.0",
            "fee": "0.1",
            "reason": "initial test buy",
        },
    )

    assert response.status_code == 201
    row = session.query(Transaction).one()
    assert row.operation == "buy"
    assert row.amount == Decimal("100.1000")
    assert row.asset.code == "000001"
    holding = session.query(Holding).one()
    assert holding.amount == Decimal("100.1000")
    assert holding.units == Decimal("10.000000")
    assert holding.cost_basis == Decimal("100.1000")


def test_buy_accumulates_cost_basis_and_units(session):
    client = make_client(session)
    # An existing valued position must retain its previous cost, not its market value.
    session.add(Holding(asset=Asset(code="519900", name="Example ETF", asset_type="fund"),
                        units=Decimal("100"), amount=Decimal("90"), cost_basis=Decimal("80")))
    session.commit()
    second = client.post("/api/transactions", json={"asset_code": "519900", "operation": "buy",
                         "trade_date": "2026-01-02", "units": "300", "price": "0.75"})
    assert second.status_code == 201
    assert Decimal(second.json()["fee"]) == Decimal("0.1")
    holding = session.query(Holding).one()
    assert holding.units == Decimal("400.000000")
    assert holding.cost_basis == Decimal("305.1000")
    assert holding.profit == holding.amount - holding.cost_basis
    assert client.delete(f"/api/transactions/{second.json()['id']}").status_code == 200
    session.refresh(holding)
    assert holding.cost_basis == Decimal("80")
    assert holding.units == Decimal("100")


def test_buy_keeps_manually_corrected_cost_even_when_history_matches_units(session):
    client = make_client(session)
    created = client.post("/api/transactions", json={
        "asset_code": "519900", "operation": "buy", "trade_date": "2026-01-02",
        "units": "100", "price": "0.8", "fee": "0",
    })
    assert created.status_code == 201
    holding = session.query(Holding).one()
    holding.cost_basis = Decimal("75")
    session.commit()

    added = client.post("/api/transactions", json={
        "asset_code": "519900", "operation": "buy", "trade_date": "2026-01-03",
        "units": "300", "price": "0.75", "fee": "0.1",
    })
    assert added.status_code == 201
    session.refresh(holding)
    assert holding.cost_basis == Decimal("300.1")
    assert holding.units == Decimal("400")


@pytest.mark.parametrize("profit, expected_cost", [(Decimal("10"), Decimal("110.1")), (None, None)])
def test_existing_position_without_cost_is_not_assumed_to_have_zero_cost(session, profit, expected_cost):
    session.add(Holding(asset=Asset(code="519900", name="Example ETF", asset_type="fund"),
                        units=Decimal("100"), amount=Decimal("100"), profit=profit))
    session.commit()
    response = make_client(session).post("/api/transactions", json={
        "asset_code": "519900", "operation": "buy", "trade_date": "2026-01-02",
        "units": "10", "price": "2", "fee": "0.1",
    })
    assert response.status_code == 201
    assert session.query(Holding).one().cost_basis == expected_cost


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
    assert holding.cost_basis == Decimal("0")


def test_amount_is_calculated_even_if_caller_sends_incorrect_amount(session):
    response = make_client(session).post("/api/transactions", json={
        "asset_code": "519900", "operation": "buy", "trade_date": "2026-01-02",
        "units": "10.12", "price": "1.234567", "amount": "9999",
    })
    assert response.status_code == 201
    assert Decimal(response.json()["amount"]) == Decimal("12.5938")


@pytest.mark.parametrize("fee,expected_amount", [(None, "438.5000"), ("0.25", "438.3500"), ("0", "438.6000")])
def test_sell_deducts_fee_from_proceeds_and_retraction_restores_holding(session, fee, expected_amount):
    client = make_client(session)
    session.add(Holding(asset=Asset(code="519900", name="Example ETF", asset_type="fund"),
                        units=Decimal("400"), amount=Decimal("584.6"), cost_basis=Decimal("400")))
    session.commit()
    payload = {
        "asset_code": "519900", "operation": "sell", "trade_date": "2026-01-03",
        "units": "300", "price": "1.462", "amount": "9999",
    }
    if fee is not None:
        payload["fee"] = fee

    response = client.post("/api/transactions", json=payload)

    assert response.status_code == 201
    assert Decimal(response.json()["amount"]) == Decimal(expected_amount)
    assert Decimal(response.json()["fee"]) == Decimal("0.1" if fee is None else fee)
    holding = session.query(Holding).one()
    assert holding.units == Decimal("100")
    assert holding.cost_basis == Decimal("100")
    assert client.delete(f"/api/transactions/{response.json()['id']}").status_code == 200
    session.refresh(holding)
    assert holding.units == Decimal("400")
    assert holding.amount == Decimal("584.6")
    assert holding.cost_basis == Decimal("400")


def test_trade_from_operation_form_succeeds_without_amount(session):
    response = make_client(session).post("/api/transactions", json={
        "asset_code": "588080", "asset_type": "fund", "operation": "buy",
        "trade_date": "2026-10-12", "units": "300", "price": "1.462", "fee": "0.1",
    })

    assert response.status_code == 201
    assert Decimal(response.json()["amount"]) == Decimal("438.7000")
    assert response.json()["asset"]["code"] == "588080"
    holding = session.query(Holding).one()
    assert holding.units == Decimal("300.000000")
    assert holding.amount == Decimal("438.7000")


@pytest.mark.parametrize("operation", ["buy", "sell", "transfer", "adjustment", "dividend"])
def test_missing_calculation_inputs_rejected(session, operation):
    response = make_client(session).post("/api/transactions", json={
        "asset_code": "519900", "operation": operation, "trade_date": "2026-01-02", "units": "10",
    })
    assert response.status_code == 422
    assert session.query(Transaction).count() == 0


def test_sell_reduces_average_cost_and_full_sale_retraction_restores_it(session):
    client = make_client(session)
    session.add(Holding(asset=Asset(code="519900", name="Example ETF", asset_type="fund"),
                        units=Decimal("400"), amount=Decimal("400"), cost_basis=Decimal("300")))
    session.commit()
    payload = {"asset_code": "519900", "operation": "sell", "trade_date": "2026-01-03", "price": "1", "fee": "0"}
    partial = client.post("/api/transactions", json={**payload, "units": "100"})
    assert partial.status_code == 201
    holding = session.query(Holding).one()
    assert holding.units == Decimal("300")
    assert holding.cost_basis == Decimal("225")
    full = client.post("/api/transactions", json={**payload, "units": "300"})
    assert full.status_code == 201
    session.refresh(holding)
    assert holding.cost_basis == Decimal("0")
    assert client.delete(f"/api/transactions/{full.json()['id']}").status_code == 200
    session.refresh(holding)
    assert holding.cost_basis == Decimal("225")
    assert holding.units == Decimal("300")


def test_older_position_transaction_must_be_retracted_after_later_changes(session):
    client = make_client(session)
    session.add(Holding(asset=Asset(code="519900", name="Example ETF", asset_type="fund"),
                        units=Decimal("100"), amount=Decimal("200"), cost_basis=Decimal("100")))
    session.commit()
    buy = client.post("/api/transactions", json={
        "asset_code": "519900", "operation": "buy", "trade_date": "2026-01-02",
        "units": "100", "price": "2", "fee": "0",
    })
    sale = client.post("/api/transactions", json={
        "asset_code": "519900", "operation": "sell", "trade_date": "2026-01-03",
        "units": "50", "price": "2", "fee": "0",
    })
    assert buy.status_code == 201
    assert sale.status_code == 201
    holding = session.query(Holding).one()
    assert holding.units == Decimal("150")
    assert holding.cost_basis == Decimal("225")

    blocked = client.delete(f"/api/transactions/{buy.json()['id']}")

    assert blocked.status_code == 400
    assert "倒序" in blocked.json()["detail"]
    session.refresh(holding)
    assert holding.units == Decimal("150")
    assert holding.cost_basis == Decimal("225")
    assert session.query(Transaction).filter(Transaction.id == buy.json()["id"]).one().retracted_at is None

    assert client.delete(f"/api/transactions/{sale.json()['id']}").status_code == 200
    assert client.delete(f"/api/transactions/{buy.json()['id']}").status_code == 200
    session.refresh(holding)
    assert holding.units == Decimal("100")
    assert holding.amount == Decimal("200")
    assert holding.cost_basis == Decimal("100")


def test_transaction_cannot_be_retracted_after_manual_holding_correction(session):
    client = make_client(session)
    session.add(Holding(asset=Asset(code="519900", name="Example ETF", asset_type="fund"),
                        units=Decimal("100"), amount=Decimal("200"), cost_basis=Decimal("100")))
    session.commit()
    created = client.post("/api/transactions", json={
        "asset_code": "519900", "operation": "buy", "trade_date": "2026-01-02",
        "units": "100", "price": "2", "fee": "0",
    })
    holding = session.query(Holding).one()
    corrected = client.patch(f"/api/holdings/{holding.id}", json={
        "cost_basis": "250", "correction_reason": "broker reconciliation",
    })
    assert created.status_code == 201
    assert corrected.status_code == 200

    response = client.delete(f"/api/transactions/{created.json()['id']}")

    assert response.status_code == 400
    assert "手动修正" in response.json()["detail"]
    assert session.query(Transaction).filter(Transaction.id == created.json()["id"]).one().retracted_at is None
    session.refresh(holding)
    assert holding.units == Decimal("200")
    assert holding.cost_basis == Decimal("250")


def test_close_valuation_uses_accumulated_cost_after_added_buy(session):
    session.add(Holding(asset=Asset(code="519900", name="Example ETF", asset_type="fund"),
                        units=Decimal("100"), amount=Decimal("90"), cost_basis=Decimal("80")))
    session.commit()
    added = make_client(session).post("/api/transactions", json={
        "asset_code": "519900", "operation": "buy", "trade_date": "2026-01-02",
        "units": "300", "price": "0.75", "fee": "0.1",
    })
    assert added.status_code == 201
    result = refresh_closed_portfolio(session, now=datetime(2026, 1, 2, 15, 6),
                                     fund_fetcher=lambda _: {"ok": True, "estimate_nav": "0.77"})

    assert result["status"] == "completed"
    holding = session.query(Holding).one()
    assert holding.amount == Decimal("308")
    assert holding.cost_basis == Decimal("305.1")
    assert holding.profit == Decimal("2.9")


@pytest.mark.parametrize("operation", ["dividend", "adjustment", "transfer"])
def test_other_operations_compute_amount(session, operation):
    response = make_client(session).post("/api/transactions", json={
        "asset_code": "519900", "operation": operation, "trade_date": "2026-01-02",
        "units": "10", "price": "2", "fee": "0",
    })
    assert response.status_code == 201
    assert Decimal(response.json()["amount"]) == Decimal("20")


def test_note_does_not_require_or_change_amount(session):
    response = make_client(session).post("/api/transactions", json={
        "asset_code": "519900", "operation": "note", "trade_date": "2026-01-02", "reason": "Example note",
    })
    assert response.status_code == 201
    assert Decimal(response.json()["amount"]) == 0
    assert session.query(Holding).count() == 0


def test_legacy_sale_without_cost_record_does_not_guess_retraction_cost(session):
    asset = Asset(code="519900", name="Example ETF", asset_type="fund")
    holding = Holding(asset=asset, units=Decimal("300"), amount=Decimal("300"), cost_basis=Decimal("225"))
    session.add(holding)
    session.flush()
    transaction = Transaction(asset_id=asset.id, operation="sell", trade_date=date(2026, 1, 2),
                              amount=Decimal("100"), units=Decimal("100"), fee=Decimal("0"))
    session.add(transaction)
    session.commit()

    response = make_client(session).delete(f"/api/transactions/{transaction.id}")

    assert response.status_code == 400
    assert transaction.retracted_at is None
    assert holding.units == Decimal("300")
    assert holding.cost_basis == Decimal("225")


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
