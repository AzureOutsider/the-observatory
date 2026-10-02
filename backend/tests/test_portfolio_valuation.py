from datetime import datetime
from decimal import Decimal

from app.models import Asset, Holding, PortfolioValuationRun
from app.services.portfolio_valuation import refresh_closed_portfolio


def test_close_valuation_updates_only_holdings_with_units(session):
    fund = Asset(code="519900", name="Photovoltaic ETF", asset_type="fund")
    manual = Asset(code="000001", name="Manual Fund", asset_type="fund")
    session.add_all([fund, manual])
    session.flush()
    session.add_all(
        [
            Holding(asset_id=fund.id, amount=Decimal("82.90"), units=Decimal("100"), cost_basis=Decimal("82.90")),
            Holding(asset_id=manual.id, amount=Decimal("500.00"), profit=Decimal("10.00")),
        ]
    )
    session.commit()

    result = refresh_closed_portfolio(
        session,
        now=datetime(2026, 8, 31, 15, 6),
        fund_fetcher=lambda code: {
            "ok": True,
            "data_status": "official_nav",
            "nav": "0.8500",
            "code": code,
        },
    )

    session.refresh(session.query(Holding).filter_by(asset_id=fund.id).one())
    updated = session.query(Holding).filter_by(asset_id=fund.id).one()
    unchanged = session.query(Holding).filter_by(asset_id=manual.id).one()
    assert result["status"] == "completed"
    assert result["updated_count"] == 1
    assert updated.amount == Decimal("85.0000")
    assert updated.profit == Decimal("2.1000")
    assert updated.last_valuation_at is not None
    assert updated.last_valuation_source == "基金收盘估值"
    assert updated.last_update_type == "close_valuation"
    assert unchanged.amount == Decimal("500.0000")
    assert session.query(PortfolioValuationRun).count() == 1


def test_close_valuation_does_not_run_before_close_or_twice(session):
    asset = Asset(code="609900", name="Stock", asset_type="stock")
    session.add(asset)
    session.flush()
    session.add(Holding(asset_id=asset.id, amount=Decimal("100"), units=Decimal("10"), cost_basis=Decimal("90")))
    session.commit()

    before = refresh_closed_portfolio(session, now=datetime(2026, 8, 31, 14, 59), stock_fetcher=lambda _: {"ok": True, "price": 20})
    after = refresh_closed_portfolio(session, now=datetime(2026, 8, 31, 15, 6), stock_fetcher=lambda _: {"ok": True, "price": 20})
    repeated = refresh_closed_portfolio(session, now=datetime(2026, 8, 31, 15, 7), stock_fetcher=lambda _: {"ok": True, "price": 30})

    assert before["status"] == "not_due"
    assert after["status"] == "completed"
    assert repeated["status"] == "already_completed"
    assert session.query(Holding).one().amount == Decimal("200.0000")


def test_close_valuation_retries_when_source_fails(session):
    asset = Asset(code="519900", name="ETF", asset_type="fund")
    session.add(asset)
    session.flush()
    session.add(Holding(asset_id=asset.id, amount=Decimal("82.9"), units=Decimal("100"), cost_basis=Decimal("82.9")))
    session.commit()

    failed = refresh_closed_portfolio(session, now=datetime(2026, 8, 31, 15, 6), fund_fetcher=lambda _: {"ok": False})
    recovered = refresh_closed_portfolio(session, now=datetime(2026, 8, 31, 15, 16), fund_fetcher=lambda _: {"ok": True, "estimate_nav": 0.86})

    assert failed["status"] == "partial_failure"
    assert recovered["status"] == "completed"
    assert session.query(Holding).one().amount == Decimal("86.0000")


def test_close_valuation_releases_database_transaction_before_remote_fetch(session):
    asset = Asset(code="609900", name="Stock", asset_type="stock")
    session.add(asset)
    session.flush()
    session.add(Holding(asset_id=asset.id, amount=Decimal("100"), units=Decimal("10")))
    session.commit()

    def fetch_quote(_: str):
        assert not session.in_transaction()
        return {"ok": True, "price": 20}

    result = refresh_closed_portfolio(
        session,
        now=datetime(2026, 8, 31, 15, 6),
        stock_fetcher=fetch_quote,
    )

    assert result["status"] == "completed"
