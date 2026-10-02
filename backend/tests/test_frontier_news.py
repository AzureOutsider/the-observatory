from dataclasses import replace
from decimal import Decimal

from app.config import settings
from app.models import Asset, Holding
from app.services import frontier_news
from app.services.frontier_news import (
    attach_related_holdings,
    filter_tagged_news,
    infer_holding_tags,
    load_tag_overrides,
    tag_news_item,
)


def test_tag_news_item_matches_multiple_investment_themes():
    item = {
        "title": "AI芯片需求升温，半导体设备公司订单增长",
        "url": "https://example.com/a",
        "source": "test",
    }

    tagged = tag_news_item(item)

    assert "人工智能" in tagged["tags"]
    assert "半导体" in tagged["tags"]


def test_tag_news_item_matches_gold_and_rate_themes():
    item = {
        "title": "美联储降息预期升温，黄金价格刷新高位",
        "url": "https://example.com/b",
        "source": "test",
    }

    tagged = tag_news_item(item)

    assert "黄金" in tagged["tags"]
    assert "美联储" in tagged["tags"]


def test_tag_news_item_uses_summary_when_title_is_generic():
    tagged = tag_news_item({"title": "市场快讯", "summary": "半导体设备订单明显增长", "source": "test"})

    assert "半导体" in tagged["tags"]


def test_filter_tagged_news_by_tag():
    items = [
        {"title": "黄金上涨", "url": "", "source": "test"},
        {"title": "人形机器人产业链放量", "url": "", "source": "test"},
    ]

    filtered = filter_tagged_news(items, tag="人形机器人")

    assert len(filtered) == 1
    assert filtered[0]["title"] == "人形机器人产业链放量"
    assert filtered[0]["tags"] == ["人形机器人"]


def test_tag_overrides_load_from_optional_private_file(monkeypatch, tmp_path):
    override_path = tmp_path / "tag_overrides.json"
    monkeypatch.setattr(frontier_news, "settings", replace(settings, tag_overrides_path=override_path))

    assert load_tag_overrides() == {}

    override_path.write_text(
        '{"999991": ["人工智能", "半导体", "无效标签"], "999992": "黄金"}',
        encoding="utf-8",
    )
    assert load_tag_overrides() == {"999991": ("人工智能", "半导体")}


def test_infer_holding_tags_from_private_code_override(session):
    asset = Asset(code="999991", name="示例基金", asset_type="fund")
    session.add(asset)
    session.flush()
    holding = Holding(asset_id=asset.id, amount=Decimal("100.00"), asset=asset)

    tags = infer_holding_tags(holding, {"999991": ("人工智能", "半导体")})

    assert "人工智能" in tags
    assert "半导体" in tags


def test_attach_related_holdings_matches_news_tags(session):
    asset = Asset(code="999992", name="示例黄金ETF联接", asset_type="fund")
    session.add(asset)
    session.flush()
    session.add(Holding(asset_id=asset.id, amount=Decimal("100.00")))
    session.commit()

    items = [tag_news_item({"title": "黄金价格刷新高位", "url": "", "source": "test"})]

    enriched = attach_related_holdings(items, session)

    assert enriched[0]["related_holdings"][0]["code"] == "999992"
    assert enriched[0]["related_holdings"][0]["matched_tags"] == ["黄金"]


def test_default_market_tag_does_not_attach_generic_holdings(session):
    asset = Asset(code="999993", name="示例海外基金", asset_type="fund")
    session.add(asset)
    session.flush()
    session.add(Holding(asset_id=asset.id, amount=Decimal("10.00")))
    session.commit()

    items = [tag_news_item({"title": "海外市场消息待确认", "url": "", "source": "test"})]

    enriched = attach_related_holdings(items, session)

    assert enriched[0]["tags"] == ["市场"]
    assert enriched[0]["related_holdings"] == []
