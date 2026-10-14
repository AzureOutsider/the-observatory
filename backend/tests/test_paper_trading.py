from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

from app.db import get_session
from app.main import create_app
from app.models import Asset, Holding, PaperAsset, PaperPriceSnapshot, PaperTrade, PriceSnapshot, Transaction


def make_client(session):
    def override_session():
        yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


def test_paper_buys_are_isolated_from_real_assets_holdings_and_transactions(session, monkeypatch):
    from app.api import paper_trading

    quote_calls = []
    real_asset = Asset(code="999001", name="Real asset", asset_type="fund")
    session.add(Holding(asset=real_asset, amount=Decimal("500"), units=Decimal("100"), cost_basis=Decimal("400")))
    session.commit()
    def quote(code, **kwargs):
        quote_calls.append(code)
        return {
            "ok": True, "code": code, "name": "Market test asset", "estimate_nav": 1.5,
            "nav": None, "data_status": "intraday_estimate", "time": "2026-10-14 11:30:00", "source": "test",
        }

    monkeypatch.setattr(paper_trading, "fetch_fund_estimate", quote)
    client = make_client(session)

    response = client.post("/api/paper/trades", json={
        "asset_code": "999001", "asset_name": "Paper test asset", "asset_type": "fund",
        "operation": "buy", "trade_date": "2026-10-14", "units": "1000", "price": "1.2",
    })

    assert response.status_code == 201
    assert Decimal(response.json()["amount"]) == Decimal("1200.1000")
    assert session.query(PaperAsset).count() == 1
    assert session.query(PaperTrade).count() == 1
    assert session.query(Asset).count() == 1
    assert session.query(Transaction).count() == 0
    real_holding = session.query(Holding).one()
    assert real_holding.units == Decimal("100")
    assert real_holding.amount == Decimal("500")

    portfolio = client.get("/api/paper/portfolio")

    assert portfolio.status_code == 200
    virtual_position = portfolio.json()[0]
    assert virtual_position["name"] == "Paper test asset"
    assert Decimal(virtual_position["units"]) == Decimal("1000")
    assert Decimal(virtual_position["cost_basis"]) == Decimal("1200.1000")
    assert virtual_position["market_value"] is None
    assert virtual_position["quote_status"] == "not_loaded"
    assert quote_calls == []
    assert session.query(PaperPriceSnapshot).count() == 0
    assert session.query(PriceSnapshot).count() == 0
    refreshed = client.post("/api/paper/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json() == {"updated": 1, "failed": 0}
    valued = client.get("/api/paper/portfolio").json()[0]
    assert Decimal(valued["market_value"]) == Decimal("1500.0000")
    assert Decimal(valued["unrealized_profit"]) == Decimal("299.9000")
    assert valued["quote_status"] == "intraday_estimate"
    assert len(client.get(f"/api/paper/assets/{virtual_position['id']}/quotes").json()) == 1
    assert session.query(Asset).count() == 1
    assert session.query(PriceSnapshot).count() == 0
    assert real_holding.units == Decimal("100")


def test_paper_buy_sell_uses_average_cost_and_tracks_realized_profit(session, monkeypatch):
    from app.api import paper_trading

    client = make_client(session)
    monkeypatch.setattr(paper_trading, "fetch_stock_quote", lambda code: {
        "ok": True, "code": code, "name": "Example Stock", "price": 3.5,
        "time": "2026-10-14 14:55:00", "source": "test", "data_status": "intraday_estimate",
    })
    for units, price in [("100", "2"), ("100", "3")]:
        response = client.post("/api/paper/trades", json={
            "asset_code": "600000", "asset_name": "Example Stock", "asset_type": "stock",
            "operation": "buy", "trade_date": "2026-10-13", "units": units, "price": price,
        })
        assert response.status_code == 201
    sold = client.post("/api/paper/trades", json={
        "asset_code": "600000", "asset_name": "Example Stock", "asset_type": "stock",
        "operation": "sell", "trade_date": "2026-10-14", "units": "100", "price": "4", "fee": "0.1",
    })

    assert sold.status_code == 201
    assert Decimal(sold.json()["amount"]) == Decimal("399.9000")
    refresh = client.post("/api/paper/refresh")
    assert refresh.status_code == 200
    row = client.get("/api/paper/portfolio").json()[0]
    assert Decimal(row["units"]) == Decimal("100")
    assert Decimal(row["cost_basis"]) == Decimal("250.1000")
    assert Decimal(row["realized_profit"]) == Decimal("149.8000")
    assert Decimal(row["market_value"]) == Decimal("350.0000")
    assert Decimal(row["unrealized_profit"]) == Decimal("99.9000")
    assert Decimal(row["total_profit"]) == Decimal("249.7000")
    history = client.get(f"/api/paper/assets/{row['id']}/trades").json()
    assert [trade["operation"] for trade in history] == ["sell", "buy", "buy"]


def test_paper_sale_rejects_insufficient_simulated_units_without_touching_real_book(session):
    client = make_client(session)
    real_asset = Asset(code="600000", name="Real holding", asset_type="stock")
    session.add(Holding(asset=real_asset, amount=Decimal("1000"), units=Decimal("500"), cost_basis=Decimal("800")))
    session.commit()
    buy = client.post("/api/paper/trades", json={
        "asset_code": "600000", "asset_name": "Paper Stock", "asset_type": "stock",
        "operation": "buy", "trade_date": "2026-10-14", "units": "10", "price": "3",
    })

    response = client.post("/api/paper/trades", json={
        "asset_code": "600000", "asset_name": "Paper Stock", "asset_type": "stock",
        "operation": "sell", "trade_date": "2026-10-14", "units": "11", "price": "4",
    })

    assert buy.status_code == 201
    assert response.status_code == 422
    assert "模拟持仓" in response.json()["detail"]
    assert session.query(PaperTrade).count() == 1
    assert session.query(Transaction).count() == 0
    assert session.query(Holding).one().units == Decimal("500")


def test_paper_trade_retraction_preserves_history_and_guards_later_sales(session):
    client = make_client(session)
    buy = client.post("/api/paper/trades", json={
        "asset_code": "999015", "asset_name": "Paper Fund", "asset_type": "fund",
        "operation": "buy", "trade_date": "2026-10-13", "units": "10", "price": "2",
    })
    sell = client.post("/api/paper/trades", json={
        "asset_code": "999015", "asset_name": "Paper Fund", "asset_type": "fund",
        "operation": "sell", "trade_date": "2026-10-14", "units": "8", "price": "3",
    })

    blocked = client.delete(f"/api/paper/trades/{buy.json()['id']}")
    assert blocked.status_code == 400
    assert "后续" in blocked.json()["detail"]
    assert client.delete(f"/api/paper/trades/{sell.json()['id']}").status_code == 200
    assert client.delete(f"/api/paper/trades/{buy.json()['id']}").status_code == 200
    assert client.get("/api/paper/portfolio").json()[0]["is_open"] is False
    history = client.get(f"/api/paper/assets/{buy.json()['asset_id']}/trades").json()
    assert all(row["retracted_at"] for row in history)
    assert session.query(Transaction).count() == 0


def test_identical_intentional_paper_trades_are_kept_and_only_explicit_retry_keys_deduplicate(session):
    client = make_client(session)
    payload = {
        "asset_code": "999010", "asset_name": "Paper ETF", "asset_type": "fund",
        "operation": "buy", "trade_date": "2026-10-14", "units": "100", "price": "1.25", "fee": "0.1",
    }
    first = client.post("/api/paper/trades", json=payload)
    repeated_purchase = client.post("/api/paper/trades", json=payload)
    assert first.status_code == repeated_purchase.status_code == 201
    assert first.json()["id"] != repeated_purchase.json()["id"]

    retry_payload = {**payload, "units": "10", "idempotency_key": "b7e09eb5-1e82-4f17-981b-168612a3c3da"}
    original = client.post("/api/paper/trades", json=retry_payload)
    retry = client.post("/api/paper/trades", json=retry_payload)
    assert original.status_code == retry.status_code == 201
    assert original.json()["id"] == retry.json()["id"]
    conflict = client.post("/api/paper/trades", json={**retry_payload, "price": "1.3"})
    assert conflict.status_code == 409
    assert session.query(PaperTrade).count() == 3


def test_paper_retry_is_stable_after_asset_display_name_changes(session):
    client = make_client(session)
    payload = {
        "asset_code": "999011", "asset_name": "Original name", "asset_type": "fund",
        "operation": "buy", "trade_date": "2026-10-14", "units": "10", "price": "1.25",
        "idempotency_key": "5a80141b-31cc-4c4e-a05b-ce5d585bc8b2",
    }
    original = client.post("/api/paper/trades", json=payload)
    rename = client.post("/api/paper/trades", json={**payload, "asset_name": "Updated name", "idempotency_key": None})
    retry = client.post("/api/paper/trades", json=payload)

    assert original.status_code == rename.status_code == retry.status_code == 201
    assert retry.json()["id"] == original.json()["id"]
    assert session.query(PaperTrade).count() == 2


def test_paper_idempotency_integrity_error_during_flush_returns_conflict(session):
    client = make_client(session)
    asset = PaperAsset(code="999012", name="Paper ETF", asset_type="fund")
    session.add(asset)
    session.commit()
    key = "c36f74eb-702c-43ca-811c-2c388a30f183"

    def fail_before_flush(current_session, flush_context, instances):
        if any(isinstance(row, PaperTrade) and row.idempotency_key == key for row in current_session.new):
            raise IntegrityError("INSERT paper trade", {}, RuntimeError("simulated concurrent unique conflict"))

    event.listen(session, "before_flush", fail_before_flush)
    try:
        response = client.post("/api/paper/trades", json={
            "asset_code": asset.code, "asset_name": asset.name, "asset_type": "fund",
            "operation": "buy", "trade_date": "2026-10-14", "units": "10", "price": "1.25",
            "idempotency_key": key,
        })
    finally:
        event.remove(session, "before_flush", fail_before_flush)

    assert response.status_code == 409
    assert session.query(PaperTrade).count() == 0


def test_concurrent_first_paper_asset_insert_returns_retryable_conflict(session):
    client = make_client(session)

    def fail_asset_insert(current_session, flush_context, instances):
        if any(isinstance(row, PaperAsset) and row.code == "999013" for row in current_session.new):
            raise IntegrityError("INSERT paper asset", {}, RuntimeError("simulated concurrent unique conflict"))

    event.listen(session, "before_flush", fail_asset_insert)
    try:
        response = client.post("/api/paper/trades", json={
            "asset_code": "999013", "asset_name": "Paper ETF", "asset_type": "fund",
            "operation": "buy", "trade_date": "2026-10-14", "units": "10", "price": "1.25",
        })
    finally:
        event.remove(session, "before_flush", fail_asset_insert)

    assert response.status_code == 409
    assert "并发创建" in response.json()["detail"]
    assert session.query(PaperAsset).count() == 0
    assert session.query(PaperTrade).count() == 0


def test_paper_rejects_invalid_trade_and_unknown_asset_history(session):
    client = make_client(session)
    response = client.post("/api/paper/trades", json={
        "asset_code": "600000", "asset_name": "Example", "asset_type": "stock",
        "operation": "buy", "trade_date": str(date(2026, 10, 14)), "units": "-1", "price": "2",
    })
    assert response.status_code == 422
    assert client.get("/api/paper/assets/999/trades").status_code == 404
    assert session.query(PaperAsset).count() == 0


def test_paper_quote_failure_keeps_trade_and_does_not_create_real_snapshots(session, monkeypatch):
    from app.api import paper_trading

    asset = PaperAsset(code="999014", name="Paper ETF", asset_type="fund")
    trade = PaperTrade(
        asset=asset, operation="buy", trade_date=date(2026, 10, 14), amount=Decimal("10.1"),
        units=Decimal("10"), price=Decimal("1"), fee=Decimal("0.1"),
    )
    session.add(trade)
    session.commit()
    monkeypatch.setattr(paper_trading, "fetch_fund_estimate", lambda code, **kwargs: {"ok": False, "error": "source offline"})

    result = make_client(session).post("/api/paper/refresh")

    assert result.status_code == 200
    assert result.json() == {"updated": 0, "failed": 1}
    position = make_client(session).get("/api/paper/portfolio").json()[0]
    assert position["is_open"] is True
    assert position["market_value"] is None
    assert position["quote_status"] == "not_loaded"
    assert session.query(PaperTrade).count() == 1
    assert session.query(PaperPriceSnapshot).count() == 0
    assert session.query(PriceSnapshot).count() == 0
