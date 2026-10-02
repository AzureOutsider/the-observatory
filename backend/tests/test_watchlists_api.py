from decimal import Decimal

from app.api import watchlists
from app.api.watchlists import _ensure_default_watchlist
from app.models import Asset, Holding, Watchlist, WatchlistItem
from app.schemas import WatchlistItemCreate, WatchlistItemUpdate, WatchlistRefreshRequest


def test_default_watchlist_imports_existing_holdings_once(session):
    first = Asset(code="999991", name="Fund A", asset_type="fund")
    second = Asset(code="999992", name="Fund B", asset_type="fund")
    session.add_all([first, second])
    session.flush()
    session.add_all([
        Holding(asset_id=first.id, amount=Decimal("100")),
        Holding(asset_id=second.id, amount=Decimal("50")),
    ])
    session.commit()

    watchlist = _ensure_default_watchlist(session)
    assert {item.asset_id for item in watchlist.items} == {first.id, second.id}

    _ensure_default_watchlist(session)
    assert session.query(WatchlistItem).filter(WatchlistItem.watchlist_id == watchlist.id).count() == 2


def test_resolve_asset_name_uses_market_quote(monkeypatch):
    monkeypatch.setattr(
        watchlists,
        "fetch_stock_quote",
        lambda code: {"ok": True, "name": "示例标的01"},
    )

    assert watchlists._resolve_asset_name("609900", "stock") == "示例标的01"


def test_add_tracking_keeps_official_name_separate_from_custom_name(monkeypatch, session):
    watchlist = Watchlist(name="Name separation")
    session.add(watchlist)
    session.commit()
    monkeypatch.setattr(watchlists, "fetch_stock_quote", lambda code: {"ok": True, "name": "示例标的01"})

    result = watchlists.add_watchlist_item(
        watchlist.id,
        WatchlistItemCreate(asset_code="609900", asset_type="stock", asset_name="我的浦发"),
        session,
    )

    asset = session.query(Asset).filter_by(code="609900", asset_type="stock").one()
    assert result["id"]
    assert asset.name == "示例标的01"
    assert asset.custom_name == "我的浦发"


def test_tracking_item_can_update_clear_and_delete_custom_name(session):
    watchlist = Watchlist(name="Detail actions")
    asset = Asset(code="609900", name="示例标的01", custom_name="我的浦发", asset_type="stock")
    session.add_all([watchlist, asset])
    session.flush()
    item = WatchlistItem(watchlist_id=watchlist.id, asset_id=asset.id)
    session.add(item)
    session.commit()

    payload = watchlists.get_watchlist_item(watchlist.id, item.id, session)
    assert payload["official_name"] == "示例标的01"
    assert payload["display_name"] == "我的浦发"

    updated = watchlists.update_watchlist_item(
        watchlist.id,
        item.id,
        WatchlistItemUpdate(custom_name="新名称"),
        session,
    )
    assert updated["official_name"] == "示例标的01"
    assert updated["custom_name"] == "新名称"

    watchlists.update_watchlist_item(watchlist.id, item.id, WatchlistItemUpdate(custom_name=None), session)
    assert session.get(Asset, asset.id).custom_name is None

    watchlists.remove_watchlist_item(watchlist.id, item.id, session)
    assert session.get(WatchlistItem, item.id) is None


def test_tracking_item_tags_are_normalized_without_clearing_name(session):
    watchlist = Watchlist(name="Tag actions")
    asset = Asset(code="609900", name="示例标的01", custom_name="银行观察", asset_type="stock")
    session.add_all([watchlist, asset])
    session.flush()
    item = WatchlistItem(watchlist_id=watchlist.id, asset_id=asset.id)
    session.add(item)
    session.commit()

    updated = watchlists.update_watchlist_item(
        watchlist.id,
        item.id,
        WatchlistItemUpdate(tags=[" 持仓 ", "#银行", "持仓", ""]),
        session,
    )

    assert updated["tags"] == ["持仓", "银行"]
    assert updated["custom_name"] == "银行观察"


def test_selected_refresh_rejects_items_from_another_watchlist(session, monkeypatch):
    first = Watchlist(name="First")
    second = Watchlist(name="Second")
    asset = Asset(code="609900", name="示例标的01", asset_type="stock")
    session.add_all([first, second, asset])
    session.flush()
    foreign_item = WatchlistItem(watchlist_id=second.id, asset_id=asset.id)
    session.add(foreign_item)
    session.commit()
    monkeypatch.setattr(watchlists, "refresh_watchlist_trends", lambda *args, **kwargs: [])

    try:
        watchlists.refresh_selected_watchlist_trends(
            first.id,
            WatchlistRefreshRequest(item_ids=[foreign_item.id]),
            session,
        )
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400
    else:
        raise AssertionError("foreign tracking item should be rejected")
