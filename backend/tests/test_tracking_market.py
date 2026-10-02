from datetime import date, datetime
from decimal import Decimal
from threading import Barrier
import time

from app.models import Asset, PriceSnapshot, Watchlist, WatchlistItem
from app.services.tracking_market import get_watchlist_trends, refresh_watchlist_trends


def test_refresh_watchlist_trends_supports_funds_and_stocks(session):
    watchlist = Watchlist(name="Test tracking")
    fund = Asset(code="999991", name="Old fund name", asset_type="fund")
    stock = Asset(code="609900", name="Old stock name", asset_type="stock")
    session.add_all([watchlist, fund, stock])
    session.flush()
    session.add_all([
        WatchlistItem(watchlist_id=watchlist.id, asset_id=fund.id),
        WatchlistItem(watchlist_id=watchlist.id, asset_id=stock.id),
    ])
    session.commit()

    quote_time = datetime.now().replace(second=0, microsecond=0).strftime("%Y-%m-%d %H:%M")

    def fund_fetcher(code: str):
        return {
            "ok": True,
            "code": code,
            "name": "Tracked fund",
            "source": "test_fund",
            "data_status": "intraday_estimate",
            "time": quote_time,
            "estimate_nav": 1.25,
            "change_pct": 0.5,
        }

    def stock_fetcher(code: str):
        return {
            "ok": True,
            "code": code,
            "name": "Tracked stock",
            "source": "test_stock",
            "data_status": "intraday_estimate",
            "time": quote_time,
            "price": 12.5,
            "change_pct": -0.8,
        }

    rows = refresh_watchlist_trends(session, watchlist.id, fund_fetcher, stock_fetcher)

    assert [row["code"] for row in rows] == ["999991", "609900"]
    assert rows[0]["latest"]["price"] == 1.25
    assert rows[1]["latest"]["price"] == 12.5
    assert rows[1]["asset_type"] == "stock"
    assert session.get(Asset, fund.id).name == "Tracked fund"
    assert session.get(Asset, stock.id).name == "Tracked stock"


def test_get_watchlist_trends_returns_stale_snapshot_without_refresh(session):
    watchlist = Watchlist(name="Cached tracking")
    asset = Asset(code="609900", name="Cached stock", asset_type="stock")
    session.add_all([watchlist, asset])
    session.flush()
    session.add(WatchlistItem(watchlist_id=watchlist.id, asset_id=asset.id))
    session.add(
        PriceSnapshot(
            asset_id=asset.id,
            price=Decimal("12.3"),
            change_pct=Decimal("1.2"),
            source="test_stock",
            observed_at=datetime(2026, 8, 30, 15, 0),
        )
    )
    session.commit()

    rows = get_watchlist_trends(session, watchlist.id)

    assert rows[0]["quote_status"] == "stale"
    assert rows[0]["last_available"]["price"] == 12.3


def test_cached_curve_is_not_marked_as_source_fallback(session):
    watchlist = Watchlist(name="Curve tracking")
    asset = Asset(code="609900", name="Cached stock", asset_type="stock")
    session.add_all([watchlist, asset])
    session.flush()
    session.add(WatchlistItem(watchlist_id=watchlist.id, asset_id=asset.id))
    session.add(
        PriceSnapshot(
            asset_id=asset.id,
            price=Decimal("12.3"),
            change_pct=Decimal("1.2"),
            source="sina_stock",
            observed_at=datetime.now().replace(second=0, microsecond=0),
        )
    )
    session.commit()

    rows = get_watchlist_trends(session, watchlist.id)

    assert rows[0]["points"]
    assert rows[0]["is_fallback"] is False


def test_trend_uses_custom_name_but_returns_official_name(session):
    watchlist = Watchlist(name="Custom display")
    asset = Asset(code="609900", name="示例标的01", custom_name="我的银行", asset_type="stock")
    session.add_all([watchlist, asset])
    session.flush()
    session.add(WatchlistItem(watchlist_id=watchlist.id, asset_id=asset.id))
    session.commit()

    rows = get_watchlist_trends(session, watchlist.id)

    assert rows[0]["name"] == "我的银行"
    assert rows[0]["official_name"] == "示例标的01"
    assert rows[0]["custom_name"] == "我的银行"


def test_refresh_fetches_watchlist_quotes_concurrently(session):
    watchlist = Watchlist(name="Concurrent tracking")
    first = Asset(code="000001", name="Fund A", asset_type="fund")
    second = Asset(code="000002", name="Fund B", asset_type="fund")
    session.add_all([watchlist, first, second])
    session.flush()
    session.add_all([
        WatchlistItem(watchlist_id=watchlist.id, asset_id=first.id),
        WatchlistItem(watchlist_id=watchlist.id, asset_id=second.id),
    ])
    session.commit()
    rendezvous = Barrier(2)

    def fund_fetcher(code: str):
        rendezvous.wait(timeout=2)
        return {
            "ok": True,
            "code": code,
            "name": code,
            "source": "test",
            "data_status": "intraday_estimate",
            "time": "2026-08-31 10:30",
            "estimate_nav": 1.25,
            "change_pct": 0.5,
        }

    rows = refresh_watchlist_trends(session, watchlist.id, fund_fetcher, fund_fetcher)

    assert len(rows) == 2


def test_refresh_returns_timed_out_items_without_waiting_for_slow_fetcher(session, monkeypatch):
    watchlist = Watchlist(name="Timeout tracking")
    asset = Asset(code="000001", name="Slow fund", asset_type="fund")
    session.add_all([watchlist, asset])
    session.flush()
    session.add(WatchlistItem(watchlist_id=watchlist.id, asset_id=asset.id))
    session.commit()
    monkeypatch.setattr(
        "app.services.tracking_market.WATCHLIST_REFRESH_TIMEOUT_SECONDS",
        0.05,
    )

    def slow_fetcher(code: str):
        time.sleep(0.2)
        return {"ok": True, "code": code, "price": 1, "change_pct": 0, "time": "2026-08-31 10:30"}

    started = time.perf_counter()
    rows = refresh_watchlist_trends(session, watchlist.id, slow_fetcher, slow_fetcher)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.15
    assert rows[0]["quote_status"] == "unavailable"
    assert "超时" in rows[0]["quote_message"]


def test_refresh_only_updates_selected_items_and_returns_their_tags(session):
    watchlist = Watchlist(name="Filtered tracking")
    first = Asset(code="000001", name="Fund A", asset_type="fund")
    second = Asset(code="000002", name="Fund B", asset_type="fund")
    session.add_all([watchlist, first, second])
    session.flush()
    first_item = WatchlistItem(
        watchlist_id=watchlist.id,
        asset_id=first.id,
        tags_json='["重点观察"]',
    )
    second_item = WatchlistItem(watchlist_id=watchlist.id, asset_id=second.id)
    session.add_all([first_item, second_item])
    session.commit()
    requested_codes = []

    def fund_fetcher(code: str):
        requested_codes.append(code)
        return {
            "ok": True,
            "code": code,
            "source": "test",
            "data_status": "intraday_estimate",
            "time": "2026-09-03 10:30",
            "estimate_nav": 1.25,
            "change_pct": 0.5,
        }

    rows = refresh_watchlist_trends(
        session,
        watchlist.id,
        fund_fetcher,
        fund_fetcher,
        item_ids=[first_item.id],
    )

    assert requested_codes == ["000001"]
    assert [row["watchlist_item_id"] for row in rows] == [first_item.id]
    assert rows[0]["tags"] == ["重点观察"]
    assert session.query(PriceSnapshot).filter_by(asset_id=second.id).count() == 0


def test_repeated_curve_refresh_does_not_duplicate_snapshots_and_downsamples(session):
    watchlist = Watchlist(name="Bulk curve")
    asset = Asset(code="000001", name="Fund A", asset_type="fund")
    session.add_all([watchlist, asset])
    session.flush()
    item = WatchlistItem(watchlist_id=watchlist.id, asset_id=asset.id)
    session.add(item)
    session.commit()
    today = date.today().isoformat()
    points = [
        {
            "time": f"{today} {9 + (index + 30) // 60:02d}:{(index + 30) % 60:02d}",
            "price": 1 + index / 1000,
            "change_pct": index / 100,
        }
        for index in range(100)
    ]

    def fund_fetcher(code: str):
        return {
            "ok": True,
            "code": code,
            "source": "test_curve",
            "data_status": "intraday_estimate",
            "time": points[-1]["time"],
            "points": points,
        }

    first_rows = refresh_watchlist_trends(session, watchlist.id, fund_fetcher, fund_fetcher)
    second_rows = refresh_watchlist_trends(session, watchlist.id, fund_fetcher, fund_fetcher)

    assert session.query(PriceSnapshot).filter_by(asset_id=asset.id).count() == 100
    assert len(first_rows[0]["points"]) == 64
    assert len(second_rows[0]["points"]) == 64
    assert first_rows[0]["points"][0]["time"].endswith("09:30")
    assert first_rows[0]["points"][-1]["time"].endswith("11:09")
