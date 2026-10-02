from datetime import datetime

from app.services import market


def test_stock_symbol_supports_shanghai_etf_codes():
    assert market._stock_symbol("519900") == "sh"


def test_parse_xincai_fund_estimate_returns_intraday_points():
    payload = 'var t=(({yes:"1.6000",detail:"09:30,1.6080,09:31,1.6160"}));'

    result = market._parse_xincai_fund_estimate("999991", payload)

    assert result["ok"] is True
    assert result["nav"] == 1.6
    assert result["estimate_nav"] == 1.616
    assert result["change_pct"] == 1.0
    assert result["data_status"] == "intraday_estimate"
    assert len(result["points"]) == 2
    assert result["points"][0]["time"].endswith("09:30")
    assert result["points"][0]["change_pct"] == 0.5


def test_parse_xincai_fund_estimate_rejects_future_points_from_stale_daily_cache():
    payload = 'var t=(({yes:"1.6000",detail:"09:30,1.6080,10:06,1.6160,15:03,1.6200"}));'

    result = market._parse_xincai_fund_estimate(
        "999991",
        payload,
        now=datetime(2026, 8, 4, 10, 10),
    )

    assert result["ok"] is False
    assert "未来时间点" in result["error"]


def test_parse_tencent_fund_quote_returns_official_nav_when_estimate_is_zero():
    payload = (
        'v_jj999991="999991~示例人工智能基金A~0.0000~0.0000~~'
        '1.6056~1.6056~-0.2485~2026-07-29~";'
    )

    result = market._parse_tencent_fund_quote("999991", payload)

    assert result["ok"] is True
    assert result["name"] == "示例人工智能基金A"
    assert result["nav"] == 1.6056
    assert result["estimate_nav"] is None
    assert result["change_pct"] == -0.2485
    assert result["time"] == "2026-07-29 15:00"
    assert result["data_status"] == "official_nav"
    assert result["message"] == "最新官方净值（非实时估值）"


def test_parse_tencent_fund_quote_prefers_intraday_estimate_when_present():
    payload = (
        'v_jj999991="999991~示例人工智能基金A~1.6200~0.8968~~'
        '1.6056~1.6056~-0.2485~2026-07-30 10:30~";'
    )

    result = market._parse_tencent_fund_quote("999991", payload)

    assert result["estimate_nav"] == 1.62
    assert result["change_pct"] == 0.8968
    assert result["data_status"] == "intraday_estimate"
    assert result["message"] == "盘中估值，仅供参考"


def test_parse_tencent_fund_quote_rejects_zero_official_nav():
    payload = 'v_jj999992="999992~示例货币基金A~0.0000~0.0000~~0.0000~0.0000~0.0000~~";'

    result = market._parse_tencent_fund_quote("999992", payload)

    assert result["ok"] is False
    assert result["error"] == "腾讯行情未返回有效净值"


def test_fetch_fund_estimate_uses_eastmoney_official_nav_as_fallback(monkeypatch):
    monkeypatch.setattr(
        market,
        "_fetch_xincai_fund_estimate",
        lambda code: {"ok": False, "code": code, "error": "estimate unavailable"},
    )
    monkeypatch.setattr(
        market,
        "_fetch_tencent_fund_quote",
        lambda code: {"ok": False, "code": code, "error": "primary unavailable"},
    )
    monkeypatch.setattr(
        market,
        "_fetch_eastmoney_official_nav",
        lambda code: {
            "ok": True,
            "code": code,
            "name": "Fallback Fund",
            "nav": 1.2345,
            "estimate_nav": None,
            "change_pct": 0.12,
            "time": "2026-07-29 15:00",
            "source": "eastmoney_official_nav",
            "data_status": "official_nav",
            "message": "最新官方净值（非实时估值）",
        },
    )

    result = market.fetch_fund_estimate("000001")

    assert result["ok"] is True
    assert result["source"] == "eastmoney_official_nav"
    assert result["warnings"] == ["estimate unavailable", "primary unavailable"]


def test_fetch_fund_estimate_backfills_name_when_intraday_source_omits_it(monkeypatch):
    monkeypatch.setattr(
        market,
        "_fetch_xincai_fund_estimate",
        lambda code: {
            "ok": True,
            "code": code,
            "name": "",
            "estimate_nav": 1.2,
            "change_pct": 0.5,
            "time": "2026-08-31 10:30",
            "source": "sina_xincai_estimate",
        },
    )
    monkeypatch.setattr(
        market,
        "_fetch_tencent_fund_quote",
        lambda code: {"ok": True, "code": code, "name": "国泰中证白酒指数A"},
    )

    result = market.fetch_fund_estimate("519900")

    assert result["name"] == "国泰中证白酒指数A"
    assert result["source"] == "sina_xincai_estimate"
