from datetime import date

from app.models import Asset, DailyBar, Watchlist, WatchlistItem
from app.services import historical_market
from app.services.historical_market import get_watchlist_item_history


def test_stock_history_is_cached_and_returned_in_ascending_date_order(session):
    watchlist = Watchlist(name="Historical stock")
    asset = Asset(code="609900", name="示例标的01", asset_type="stock")
    session.add_all([watchlist, asset])
    session.flush()
    item = WatchlistItem(watchlist_id=watchlist.id, asset_id=asset.id)
    session.add(item)
    session.commit()

    calls: list[tuple[str, date, date]] = []

    def fetcher(code: str, start_date: date, end_date: date):
        calls.append((code, start_date, end_date))
        return [
            {"bar_date": date(2026, 8, 28), "open_price": 11.9, "high_price": 12.4, "low_price": 11.8, "close_price": 12.3, "change_pct": 1.1, "source": "test_stock_history"},
            {"bar_date": date(2026, 8, 27), "open_price": 11.7, "high_price": 12.0, "low_price": 11.6, "close_price": 11.9, "change_pct": 0.5, "source": "test_stock_history"},
        ]

    result = get_watchlist_item_history(
        session,
        watchlist.id,
        item.id,
        today=date(2026, 8, 31),
        refresh=True,
        stock_fetcher=fetcher,
    )

    assert calls == [("609900", date(2026, 2, 28), date(2026, 8, 31))]
    assert [point["date"] for point in result["points"]] == ["2026-08-27", "2026-08-28"]
    assert result["value_label"] == "收盘价"
    assert result["cache_status"] == "fresh"
    assert session.query(DailyBar).count() == 2


def test_fund_history_uses_unit_nav_and_cached_data_when_source_fails(session):
    watchlist = Watchlist(name="Historical fund")
    asset = Asset(code="000001", name="测试基金", asset_type="fund")
    session.add_all([watchlist, asset])
    session.flush()
    item = WatchlistItem(watchlist_id=watchlist.id, asset_id=asset.id)
    session.add(item)
    session.commit()

    result = get_watchlist_item_history(
        session,
        watchlist.id,
        item.id,
        today=date(2026, 8, 31),
        refresh=True,
        fund_fetcher=lambda code, start, end: [
            {"bar_date": date(2026, 8, 28), "close_price": 1.2345, "change_pct": 0.3, "source": "test_fund_history"},
        ],
    )
    assert result["value_label"] == "单位净值"
    assert result["points"][0]["value"] == 1.2345

    cached = get_watchlist_item_history(
        session,
        watchlist.id,
        item.id,
        today=date(2026, 8, 31),
        refresh=True,
        fund_fetcher=lambda code, start, end: (_ for _ in ()).throw(RuntimeError("source unavailable")),
    )
    assert cached["cache_status"] == "cached"
    assert cached["points"]
    assert "缓存" in cached["message"]


def test_eastmoney_history_parsers_normalize_payload(monkeypatch):
    monkeypatch.setattr(
        historical_market,
        "_get_json",
        lambda url, **kwargs: {"data": {"klines": ["2026-08-28,11.9,12.3,12.4,11.8,100,1200,5.0,1.1,0.4,2.0"]}},
    )
    stock = historical_market.fetch_stock_history("609900", date(2026, 8, 1), date(2026, 8, 31))
    assert stock[0]["bar_date"] == date(2026, 8, 28)
    assert stock[0]["close_price"] == 12.3

    monkeypatch.setattr(
        historical_market,
        "_get_json",
        lambda url, **kwargs: {"Data": {"LSJZList": [{"FSRQ": "2026-08-28", "DWJZ": "1.2345", "JZZZL": "0.30"}]}},
    )
    fund = historical_market.fetch_fund_history("000001", date(2026, 8, 1), date(2026, 8, 31))
    assert fund[0]["bar_date"] == date(2026, 8, 28)
    assert fund[0]["close_price"] == 1.2345


def test_etf_link_fund_codes_use_nav_history_not_market_price_history():
    assert historical_market._is_etf_or_stock(Asset(code="519900", name="光伏ETF", asset_type="fund")) is True
    assert historical_market._is_etf_or_stock(Asset(code="999991", name="示例纳斯达克100ETF联接A", asset_type="fund")) is False
    assert historical_market._is_etf_or_stock(Asset(code="999992", name="示例海外ETF联接D", asset_type="fund")) is False
