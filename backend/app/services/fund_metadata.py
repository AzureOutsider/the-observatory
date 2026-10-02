from __future__ import annotations

from datetime import datetime
from typing import Any


SOURCE_LABELS = {
    "sina_stock": "新浪股票行情",
    "sina_xincai_estimate": "新浪新财",
    "tencent_fund_quote": "腾讯基金行情",
    "eastmoney_official_nav": "东方财富官方净值",
    "wallstreetcn_news": "华尔街见闻",
    "sina_news": "新浪财经",
    "federal_reserve_news": "美联储",
}

CATEGORY_INFO = {
    "equity": {
        "label": "股票型/混合型",
        "note": "盘中估值仅供参考，最终以基金净值为准",
    },
    "bond": {
        "label": "债券型",
        "note": "多数时间只有官方净值，盘中估值可能不可用",
    },
    "money": {
        "label": "货币型",
        "note": "主要关注每万份收益，不适合绘制股票式盘中净值曲线",
    },
    "qdii": {
        "label": "QDII/海外",
        "note": "受海外市场交易时段影响，数据可能延迟或跨交易日",
    },
    "other": {
        "label": "其他基金",
        "note": "按数据源实际返回内容展示",
    },
}


def source_label(source: str | None) -> str | None:
    if not source:
        return None
    return SOURCE_LABELS.get(source, source)


def category_info(category: str | None) -> dict[str, str]:
    return CATEGORY_INFO.get(category or "other", CATEGORY_INFO["other"])


def infer_fund_category(
    code: str | None,
    name: str | None = None,
    fund_type: str | None = None,
) -> str:
    text = f"{name or ''} {code or ''}".lower()
    if fund_type == "005" or any(word in text for word in ("货币", "现金", "理财")):
        return "money"
    if any(
        word in text
        for word in ("qdii", "海外", "全球", "纳斯达克", "标普", "恒生", "日经", "德国", "美国")
    ):
        return "qdii"
    if any(word in text for word in ("债", "纯债", "短债", "中短", "信用债", "利率债")):
        return "bond"
    if any(word in text for word in ("黄金", "上海金", "商品", "原油", "reits", "reit", "fof")):
        return "other"
    if code or name:
        return "equity"
    return "other"


def parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    cleaned = value.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def freshness_info(
    status: str,
    as_of: Any,
    now: datetime | None = None,
) -> tuple[str, str]:
    """Return a stable machine value and concise Chinese label for freshness."""
    if status == "official_nav":
        return "official", "官方净值（非实时）"
    if status in {"unavailable", "not_loaded"}:
        return status, "暂无可用数据"

    observed = parse_datetime(as_of)
    if observed is None:
        return "unknown", "更新时间未知"
    current = now or datetime.now()
    age_minutes = (current - observed).total_seconds() / 60
    if observed.date() != current.date() or age_minutes > 120:
        return "stale", "数据较旧"
    if age_minutes > 30:
        return "delayed", "数据有延迟"
    return "fresh", "近期更新"
