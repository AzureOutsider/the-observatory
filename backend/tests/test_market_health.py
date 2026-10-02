from datetime import datetime

from app.services.fund_metadata import infer_fund_category
from app.services.market_health import MarketSourceHealth


def test_source_health_distinguishes_success_no_data_and_failure():
    registry = MarketSourceHealth()
    observed = datetime(2026, 7, 30, 10, 30)

    registry.record("test_source", "success", now=observed)
    registry.record("test_source", "no_data", "no estimate for this fund", now=observed)
    registry.record("test_source", "failure", "connection timeout", now=observed)

    source = next(item for item in registry.snapshot()["sources"] if item["source"] == "test_source")
    assert source["attempts"] == 3
    assert source["successes"] == 1
    assert source["no_datas"] == 1
    assert source["failures"] == 1
    assert source["status"] == "degraded"
    assert source["availability_rate"] == 66.7


def test_fund_category_inference_handles_special_fund_types():
    assert infer_fund_category("999992", "示例货币基金A") == "money"
    assert infer_fund_category("000001", "稳健纯债基金") == "bond"
    assert infer_fund_category("000002", "纳斯达克100 QDII") == "qdii"
    assert infer_fund_category("000003", "黄金ETF联接") == "other"
    assert infer_fund_category("000005", "示例上海金ETF联接C") == "other"
    assert infer_fund_category("000004", "人工智能混合") == "equity"
