from datetime import date, datetime
from decimal import Decimal

from app.models import Asset, Holding, PriceSnapshot
from app.services.portfolio_market import get_holding_fund_trends, refresh_holding_fund_trends


def test_refresh_holding_fund_trends_saves_snapshot_per_holding(session):
    today = date.today().isoformat()
    quote_time = datetime.now().replace(second=0, microsecond=0).strftime("%Y-%m-%d %H:%M")
    first = Asset(code="000001", name="Fund A", asset_type="fund")
    second = Asset(code="000002", name="Fund B", asset_type="fund")
    session.add_all([first, second])
    session.flush()
    session.add_all(
        [
            Holding(asset_id=first.id, amount=Decimal("100.00")),
            Holding(asset_id=second.id, amount=Decimal("50.00")),
        ]
    )
    session.commit()

    def fake_fetcher(code: str):
        return {
            "ok": True,
            "code": code,
            "name": f"Fetched {code}",
            "estimate_nav": 1.23 if code == "000001" else 2.34,
            "nav": 1.20,
            "change_pct": 0.56 if code == "000001" else -1.25,
            "time": quote_time,
            "source": "test",
        }

    trends = refresh_holding_fund_trends(session, fetcher=fake_fetcher)

    assert [trend["code"] for trend in trends] == ["000001", "000002"]
    assert trends[0]["latest"]["change_pct"] == 0.56
    assert trends[1]["latest"]["change_pct"] == -1.25
    assert len(trends[0]["points"]) == 1
    assert session.query(PriceSnapshot).count() == 2
    assert trends[0]["quote_source"] == "test"
    assert trends[0]["source_label"] == "test"
    assert trends[0]["as_of"] == quote_time
    assert trends[0]["fund_category"] == "equity"
    assert trends[0]["category_label"] == "股票型/混合型"


def test_refresh_holding_fund_trends_updates_same_timestamp_snapshot(session):
    asset = Asset(code="000001", name="Fund A", asset_type="fund")
    session.add(asset)
    session.flush()
    session.add(Holding(asset_id=asset.id, amount=Decimal("100.00")))
    session.commit()

    def fake_fetcher(code: str):
        return {
            "ok": True,
            "code": code,
            "name": "Fetched Fund",
            "estimate_nav": 1.24,
            "change_pct": 0.66,
            "time": "2026-07-08 10:30",
            "source": "test",
        }

    refresh_holding_fund_trends(session, fetcher=fake_fetcher)
    refresh_holding_fund_trends(session, fetcher=fake_fetcher)

    assert session.query(PriceSnapshot).count() == 1


def test_refresh_holding_fund_trends_collapses_existing_duplicate_snapshots(session):
    asset = Asset(code="000001", name="Fund A", asset_type="fund")
    session.add(asset)
    session.flush()
    session.add(Holding(asset_id=asset.id, amount=Decimal("100.00")))
    observed_at = datetime(2026, 7, 8, 10, 30)
    session.add_all(
        [
            PriceSnapshot(
                asset_id=asset.id,
                price=Decimal("1.100000"),
                change_pct=Decimal("0.1000"),
                source="test",
                observed_at=observed_at,
            ),
            PriceSnapshot(
                asset_id=asset.id,
                price=Decimal("1.200000"),
                change_pct=Decimal("0.2000"),
                source="test",
                observed_at=observed_at,
            ),
        ]
    )
    session.commit()

    def fake_fetcher(code: str):
        return {
            "ok": True,
            "code": code,
            "name": "Fetched Fund",
            "estimate_nav": 1.24,
            "change_pct": 0.66,
            "time": "2026-07-08 10:30",
            "source": "test",
        }

    refresh_holding_fund_trends(session, fetcher=fake_fetcher)

    snapshots = session.query(PriceSnapshot).all()
    assert len(snapshots) == 1
    assert snapshots[0].price == Decimal("1.240000")


def test_refresh_holding_fund_trends_returns_fetch_failure_per_holding(session):
    asset = Asset(code="000001", name="Fund A", asset_type="fund")
    session.add(asset)
    session.flush()
    session.add(Holding(asset_id=asset.id, amount=Decimal("100.00")))
    session.commit()

    trends = refresh_holding_fund_trends(
        session,
        fetcher=lambda code: {
            "ok": False,
            "code": code,
            "error": "all fund quote sources unavailable",
        },
    )

    assert trends[0]["latest"] is None
    assert trends[0]["quote_status"] == "unavailable"
    assert trends[0]["quote_message"] == "all fund quote sources unavailable"


def test_refresh_holding_fund_trends_exposes_latest_official_nav_as_fallback(session):
    asset = Asset(code="000001", name="Fund A", asset_type="fund")
    session.add(asset)
    session.flush()
    session.add(Holding(asset_id=asset.id, amount=Decimal("100.00")))
    session.commit()

    trends = refresh_holding_fund_trends(
        session,
        fetcher=lambda code: {
            "ok": True,
            "code": code,
            "name": "Fund A",
            "nav": 1.2345,
            "estimate_nav": None,
            "change_pct": 0.12,
            "time": "2026-07-29 15:00",
            "source": "official_nav_test",
            "data_status": "official_nav",
            "message": "最新官方净值（非实时估值）",
        },
    )

    assert trends[0]["latest"] is None
    assert trends[0]["last_available"]["price"] == 1.2345
    assert trends[0]["quote_status"] == "official_nav"
    assert trends[0]["quote_message"] == "最新官方净值（非实时估值）"
    assert trends[0]["is_fallback"] is True
    assert trends[0]["freshness"] == "official"

    cached = get_holding_fund_trends(session, day=date(2026, 7, 29))
    assert cached[0]["quote_status"] == "official_nav"
    assert cached[0]["points"] == []
    assert cached[0]["source_label"] == "official_nav_test"
    assert cached[0]["value_label"] == "净值"


def test_official_nav_is_not_exposed_as_intraday_trend_even_when_dated_today(session):
    quote_time = datetime.now().replace(second=0, microsecond=0).strftime("%Y-%m-%d %H:%M")
    asset = Asset(code="000001", name="Fund A", asset_type="fund")
    session.add(asset)
    session.flush()
    session.add(Holding(asset_id=asset.id, amount=Decimal("100.00")))
    session.commit()

    trends = refresh_holding_fund_trends(
        session,
        fetcher=lambda code: {
            "ok": True,
            "code": code,
            "name": "Fund A",
            "nav": 1.2345,
            "estimate_nav": None,
            "change_pct": 0.12,
            "time": quote_time,
            "source": "official_nav_test",
            "data_status": "official_nav",
            "message": "最新官方净值（非实时估值）",
        },
    )

    assert trends[0]["latest"] is None
    assert trends[0]["points"] == []
    assert trends[0]["last_available"]["price"] == 1.2345


def test_refresh_holding_fund_trends_saves_all_intraday_points(session):
    today = date.today().isoformat()
    asset = Asset(code="000001", name="Fund A", asset_type="fund")
    session.add(asset)
    session.flush()
    session.add(Holding(asset_id=asset.id, amount=Decimal("100.00")))
    session.commit()

    trends = refresh_holding_fund_trends(
        session,
        fetcher=lambda code: {
            "ok": True,
            "code": code,
            "name": "Fund A",
            "nav": 1.2,
            "estimate_nav": 1.212,
            "change_pct": 1.0,
            "time": f"{today} 09:31",
            "source": "intraday_test",
            "data_status": "intraday_estimate",
            "message": "盘中估值，仅供参考",
            "points": [
                {"time": f"{today} 09:30", "estimate_nav": 1.206, "change_pct": 0.5},
                {"time": f"{today} 09:31", "estimate_nav": 1.212, "change_pct": 1.0},
            ],
        },
    )

    assert len(trends[0]["points"]) == 2
    assert trends[0]["points"][0]["change_pct"] == 0.5
    assert trends[0]["latest"]["change_pct"] == 1.0
    assert session.query(PriceSnapshot).count() == 2


def test_refresh_replaces_contaminated_same_day_intraday_series(session):
    today = date.today().isoformat()
    asset = Asset(code="000001", name="Fund A", asset_type="fund")
    session.add(asset)
    session.flush()
    session.add(Holding(asset_id=asset.id, amount=Decimal("100.00")))
    session.add(
        PriceSnapshot(
            asset_id=asset.id,
            price=Decimal("1.300000"),
            change_pct=Decimal("3.0000"),
            source="sina_xincai_estimate",
            observed_at=datetime.strptime(f"{today} 15:03", "%Y-%m-%d %H:%M"),
        )
    )
    session.commit()

    refresh_holding_fund_trends(
        session,
        fetcher=lambda code: {
            "ok": True,
            "code": code,
            "name": "Fund A",
            "nav": 1.2,
            "estimate_nav": 1.212,
            "change_pct": 1.0,
            "time": f"{today} 10:06",
            "source": "sina_xincai_estimate",
            "data_status": "intraday_estimate",
            "points": [
                {"time": f"{today} 09:30", "estimate_nav": 1.206, "change_pct": 0.5},
                {"time": f"{today} 10:06", "estimate_nav": 1.212, "change_pct": 1.0},
            ],
        },
    )

    snapshots = session.query(PriceSnapshot).order_by(PriceSnapshot.observed_at).all()
    assert [snapshot.observed_at.strftime("%H:%M") for snapshot in snapshots] == ["09:30", "10:06"]


def test_cached_trends_hide_entire_source_series_when_it_contains_future_points(session):
    target_day = date(2026, 8, 4)
    asset = Asset(code="000001", name="Fund A", asset_type="fund")
    session.add(asset)
    session.flush()
    session.add(Holding(asset_id=asset.id, amount=Decimal("100.00")))
    session.add_all(
        [
            PriceSnapshot(
                asset_id=asset.id,
                price=Decimal("1.100000"),
                change_pct=Decimal("0.1000"),
                source="sina_xincai_estimate",
                observed_at=datetime(2026, 8, 4, 9, 30),
            ),
            PriceSnapshot(
                asset_id=asset.id,
                price=Decimal("1.200000"),
                change_pct=Decimal("0.2000"),
                source="sina_xincai_estimate",
                observed_at=datetime(2026, 8, 4, 15, 3),
            ),
        ]
    )
    session.commit()

    trends = get_holding_fund_trends(
        session,
        day=target_day,
        now=datetime(2026, 8, 4, 10, 10),
    )

    assert trends[0]["points"] == []
    assert trends[0]["latest"] is None
    assert trends[0]["quote_status"] == "not_loaded"
