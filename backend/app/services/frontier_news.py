from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models import Holding, PriceSnapshot
from app.services.market import fetch_news

logger = logging.getLogger(__name__)

TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "人工智能": ("AI", "人工智能", "大模型", "算力", "英伟达", "NVIDIA", "微软", "OpenAI"),
    "半导体": ("半导体", "芯片", "晶圆", "光刻", "存储", "美光", "台积电", "中芯", "英伟达"),
    "人形机器人": ("人形机器人", "机器人", "具身智能", "特斯拉机器人", "Optimus"),
    "算力": ("算力", "数据中心", "服务器", "GPU", "液冷", "云计算"),
    "光模块": ("光模块", "CPO", "光通信", "硅光"),
    "黄金": ("黄金", "金价", "贵金属", "上海金", "避险"),
    "债券": ("债券", "债市", "国债", "收益率", "利率债", "信用债"),
    "美联储": ("美联储", "降息", "加息", "鲍威尔", "FOMC", "联邦基金利率"),
    "通胀": ("通胀", "CPI", "PPI", "PCE", "物价"),
    "美元": ("美元", "美元指数", "DXY", "汇率"),
    "红利": ("红利", "高股息", "股息", "分红"),
    "银行": ("银行", "息差", "存款", "贷款", "拨备"),
    "房地产": ("房地产", "地产", "房企", "楼市", "房贷"),
    "新能源": ("新能源", "光伏", "风电", "储能", "锂电"),
    "电池": ("电池", "锂电", "固态电池", "储能"),
    "电力": ("电力", "电网", "火电", "水电", "核电", "绿电"),
    "消费": ("消费", "食品饮料", "白酒", "零售", "餐饮"),
    "医药": ("医药", "创新药", "医疗", "药企", "医保"),
    "军工": ("军工", "航天", "航空", "卫星", "商业航天"),
    "A股": ("A股", "沪指", "上证", "深证", "创业板", "科创"),
    "港股": ("港股", "恒生", "港交所", "南向资金"),
    "美股": ("美股", "纳指", "纳斯达克", "标普", "道指"),
}

DEFAULT_TAG = "市场"

ASSET_NAME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "人工智能": ("人工智能", "AI", "创新成长"),
    "半导体": ("半导体", "芯片", "科创创业"),
    "算力": ("算力", "人工智能"),
    "黄金": ("黄金", "上海金"),
    "债券": ("债", "货币"),
    "红利": ("红利", "高股息"),
    "银行": ("银行",),
    "港股": ("恒生", "港股"),
    "美股": ("纳斯达克", "标普", "S&P", "500"),
    "新能源": ("新能源", "碳中和", "储能"),
    "电池": ("电池", "储能"),
    "电力": ("电力",),
    "消费": ("食品饮料", "消费"),
    "A股": ("沪深", "中证", "创业板", "科创", "基建"),
}


def load_tag_overrides() -> dict[str, tuple[str, ...]]:
    """Read optional private code-to-theme tags from local data, never from source."""
    path = settings.tag_overrides_path.expanduser()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Cannot read tag overrides at %s: %s", path, exc)
        return {}
    if not isinstance(payload, dict):
        logger.warning("Tag overrides at %s must be a JSON object", path)
        return {}

    allowed_tags = set(TAG_KEYWORDS) | {DEFAULT_TAG}
    overrides: dict[str, tuple[str, ...]] = {}
    for code, tags in payload.items():
        if not isinstance(code, str) or not isinstance(tags, list):
            continue
        valid = tuple(tag for tag in tags if isinstance(tag, str) and tag in allowed_tags)
        if valid:
            overrides[code.strip()] = valid
    return overrides


def available_news_tags() -> list[str]:
    return [DEFAULT_TAG, *TAG_KEYWORDS.keys()]


def fetch_frontier_news(
    limit: int = 40,
    tag: str | None = None,
    session: Session | None = None,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    items = filter_tagged_news(fetch_news(limit=limit, session=session, refresh=refresh), tag=tag)
    if session is not None:
        items = attach_related_holdings(items, session)
    return items


def filter_tagged_news(items: list[dict[str, Any]], tag: str | None = None) -> list[dict[str, Any]]:
    tagged = [tag_news_item(item) for item in items]
    if tag and tag != "全部":
        tagged = [item for item in tagged if tag in item["tags"]]
    return tagged


def tag_news_item(item: dict[str, Any]) -> dict[str, Any]:
    title = str(item.get("title") or "")
    searchable_text = f"{title} {item.get('summary') or ''}"
    tags = [
        tag
        for tag, keywords in TAG_KEYWORDS.items()
        if any(keyword.lower() in searchable_text.lower() for keyword in keywords)
    ]
    return {
        **item,
        "tags": tags or [DEFAULT_TAG],
    }


def attach_related_holdings(items: list[dict[str, Any]], session: Session) -> list[dict[str, Any]]:
    tag_overrides = load_tag_overrides()
    holdings = (
        session.query(Holding)
        .options(joinedload(Holding.asset))
        .order_by(Holding.amount.desc())
        .all()
    )
    holding_context = [
        {
            "code": holding.asset.code,
            "name": holding.asset.name,
            "amount": float(holding.amount),
            "tags": infer_holding_tags(holding, tag_overrides),
            "latest_change_pct": _latest_change_pct(session, holding.asset_id),
        }
        for holding in holdings
    ]

    enriched: list[dict[str, Any]] = []
    for item in items:
        item_tags = set(item.get("tags", []))
        matchable_tags = item_tags - {DEFAULT_TAG}
        related = [
            {**holding, "matched_tags": sorted(matchable_tags.intersection(holding["tags"]))}
            for holding in holding_context
            if matchable_tags.intersection(holding["tags"])
        ]
        enriched.append({**item, "related_holdings": related})
    return enriched


def infer_holding_tags(
    holding: Holding,
    tag_overrides: dict[str, tuple[str, ...]] | None = None,
) -> list[str]:
    overrides = tag_overrides if tag_overrides is not None else load_tag_overrides()
    tags = set(overrides.get(holding.asset.code, ()))
    name = " ".join(filter(None, (holding.asset.name, holding.asset.custom_name, holding.asset.theme)))
    for tag, keywords in ASSET_NAME_KEYWORDS.items():
        if any(keyword.lower() in name.lower() for keyword in keywords):
            tags.add(tag)
    return sorted(tags or {DEFAULT_TAG})


def _latest_change_pct(session: Session, asset_id: int) -> float | None:
    snapshot = (
        session.query(PriceSnapshot)
        .filter(PriceSnapshot.asset_id == asset_id)
        .order_by(PriceSnapshot.observed_at.desc(), PriceSnapshot.id.desc())
        .first()
    )
    value: Decimal | None = snapshot.change_pct if snapshot else None
    return float(value) if value is not None else None
