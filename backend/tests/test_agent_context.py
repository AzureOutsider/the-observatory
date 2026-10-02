from datetime import date, datetime
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from app.config import settings
from app.models import Asset, Holding, KnowledgeChunk, PriceSnapshot, Transaction
from app.services import agent_context
from app.services.agent_context import append_review_markdown, build_today_context, build_research_context


def test_build_today_context_includes_holdings_and_knowledge(session):
    asset = Asset(code="000001", name="Test Fund", asset_type="fund", theme="AI")
    session.add(asset)
    session.flush()
    session.add(Holding(asset_id=asset.id, amount=Decimal("100.00")))
    session.add(
        KnowledgeChunk(
            title="AI thesis",
            content="Compute demand and power supply are key variables.",
            source_path="kb.md",
        )
    )
    session.commit()

    context = build_today_context(session, topic="AI")

    assert context["holdings"][0]["code"] == "000001"
    assert context["knowledge"][0]["title"] == "AI thesis"


def test_build_research_context_reads_canonical_knowledge_file_when_db_is_empty(session, monkeypatch, tmp_path):
    knowledge_file = tmp_path / "knowledge.md"
    knowledge_file.write_text(
        "# 投资知识库\n\n## 黄金\n黄金是避险资产，地缘风险上升时受益。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        agent_context,
        "settings",
        replace(settings, knowledge_path=knowledge_file),
    )
    monkeypatch.setattr("app.services.agent_context.fetch_market_indices", lambda: [])
    monkeypatch.setattr("app.services.agent_context.fetch_frontier_news", lambda limit, session: [])
    monkeypatch.setattr("app.services.agent_context.get_holding_fund_trends", lambda session: [])

    package = build_research_context(session, topic="黄金")

    assert package["private_portfolio"]["knowledge"]
    assert package["private_portfolio"]["knowledge"][0]["source_path"].endswith(
        "knowledge.md"
    )


def test_build_research_context_requires_external_authoritative_research(session, monkeypatch):
    asset = Asset(code="000001", name="AI Test Fund", asset_type="fund", theme="AI")
    session.add(asset)
    session.flush()
    session.add(Holding(asset_id=asset.id, amount=Decimal("1000.00"), profit=Decimal("12.50")))
    session.add(
        PriceSnapshot(
            asset_id=asset.id,
            price=Decimal("1.234500"),
            change_pct=Decimal("2.3400"),
            source="test",
            observed_at=datetime(2026, 7, 9, 10, 30),
        )
    )
    session.add(
        Transaction(
            asset_id=asset.id,
            operation="buy",
            trade_date=date(2026, 7, 8),
            amount=Decimal("300.00"),
            reason="add AI exposure",
        )
    )
    session.add(
        KnowledgeChunk(
            title="AI thesis",
            content="Track compute demand and policy risk.",
            source_path="kb.md",
        )
    )
    session.commit()

    monkeypatch.setattr(
        "app.services.agent_context.fetch_market_indices",
        lambda: [{"ok": True, "code": "000001", "name": "Test Index", "change_pct": 1.2}],
    )
    monkeypatch.setattr(
        "app.services.agent_context.fetch_frontier_news",
        lambda limit, session: [
            {
                "title": "AI chip demand rises",
                "source": "Test News",
                "url": "https://example.test/news",
                "tags": ["AI"],
                "related_holdings": [{"code": "000001", "name": "AI Test Fund"}],
            }
        ],
    )

    package = agent_context.build_research_context(session, topic="AI")

    holding = package["private_portfolio"]["holdings"][0]
    assert holding["code"] == "000001"
    assert holding["weight_pct"] == 100.0
    assert holding["today"]["change_pct"] == 2.34
    assert holding["today"]["status"] == "stale"
    assert holding["today"]["source"] == "test"
    assert holding["today"]["freshness"] == "stale"
    assert holding["today"]["is_intraday"] is False
    assert holding["today"]["is_fallback"] is True
    assert package["data_quality_summary"]["manual_refresh_required"] is True
    assert "sources" in package["data_source_health"]
    assert package["internal_news_signals"][0]["title"] == "AI chip demand rises"
    assert package["external_research"]["required"] is True
    assert "official" in package["external_research"]["source_priority"][0]["type"]
    assert "AI Test Fund" in package["external_research"]["suggested_queries"][0]
    assert "active web search" in package["agent_prompt"]
    assert "authoritative sources" in package["agent_prompt"]
    assert "Never describe official NAV" in package["agent_prompt"]
    assert any("official NAV" in rule for rule in package["analysis_contract"]["guardrails"])


def test_research_context_includes_review_continuity(tmp_path, monkeypatch, session):
    review_path = tmp_path / "review.md"
    review_path.write_text(
        "## 2026-08-30\n### 四、后续需留意的关键新闻 / 时点\n| 时点 | 事件 | 阈值 | 持仓 |\n| 明天 | 指数站上4500 | 收盘确认 | ETF |\n### 五、风险与触发条件\n- 跌破支撑位\n### 六、待验证事项\n- 等待公告\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(agent_context, "settings", replace(settings, review_path=review_path))
    monkeypatch.setattr(agent_context, "fetch_market_indices", lambda: [])
    monkeypatch.setattr(agent_context, "fetch_frontier_news", lambda limit, session: [])
    monkeypatch.setattr(agent_context, "get_holding_fund_trends", lambda session: [])

    package = build_research_context(session)

    assert package["historical_review"]["recent_dates"] == ["2026-08-30"]
    assert "等待公告" in package["historical_review"]["open_items"][0]
    assert "跌破支撑位" in package["historical_review"]["triggers"][0]
    assert "指数站上4500" in package["historical_review"]["follow_up_items"][0]


def test_append_review_is_idempotent(tmp_path, monkeypatch):
    review_path = tmp_path / "nested" / "review.md"
    monkeypatch.setattr(agent_context, "settings", replace(settings, review_path=review_path))

    first = append_review_markdown(date(2026, 8, 31), "## 2026-08-31\n\n### 一、今日结论\n保持观察")
    second = append_review_markdown(date(2026, 8, 31), "## 2026-08-31\n\n### 一、今日结论\n保持观察")

    assert first["appended"] is True
    assert second["duplicate"] is True
    assert review_path.read_text(encoding="utf-8").count("保持观察") == 1
