import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Asset, Holding, Watchlist, WatchlistItem
from app.services.market import fetch_fund_estimate, fetch_stock_quote
from app.schemas import WatchlistCreate, WatchlistItemCreate, WatchlistItemUpdate, WatchlistRefreshRequest
from app.services.historical_market import get_watchlist_item_history
from app.services.tracking_market import get_watchlist_trends, refresh_watchlist_trends

router = APIRouter(tags=["watchlists"])


@router.get("/watchlists")
def list_watchlists(session: Session = Depends(get_session)):
    _ensure_default_watchlist(session)
    rows = session.query(Watchlist).order_by(Watchlist.name).all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "items": [
                {
                    "id": item.id,
                    "tags": _item_tags(item),
                    "asset": {
                        "id": item.asset.id,
                        "code": item.asset.code,
                        "name": item.asset.name,
                        "official_name": item.asset.name,
                        "custom_name": item.asset.custom_name,
                        "asset_type": item.asset.asset_type,
                    },
                }
                for item in row.items
            ],
        }
        for row in rows
    ]


@router.post("/watchlists", status_code=201)
def create_watchlist(payload: WatchlistCreate, session: Session = Depends(get_session)):
    row = Watchlist(name=payload.name, description=payload.description)
    session.add(row)
    session.commit()
    session.refresh(row)
    return {"id": row.id, "name": row.name, "description": row.description}


def _ensure_default_watchlist(session: Session) -> Watchlist:
    row = session.query(Watchlist).filter(Watchlist.name == "我的追踪").one_or_none()
    if row is None:
        row = Watchlist(name="我的追踪", description="在走势页手动添加的股票和基金")
        session.add(row)
        session.flush()
    existing_asset_ids = {
        item.asset_id
        for item in session.query(WatchlistItem).filter(WatchlistItem.watchlist_id == row.id).all()
    }
    holdings = session.query(Holding).all()
    next_order = session.query(WatchlistItem).filter(WatchlistItem.watchlist_id == row.id).count()
    for holding in holdings:
        if holding.asset_id not in existing_asset_ids:
            session.add(WatchlistItem(watchlist_id=row.id, asset_id=holding.asset_id, sort_order=next_order))
            existing_asset_ids.add(holding.asset_id)
            next_order += 1
    session.commit()
    session.refresh(row)
    return row


@router.post("/watchlists/{watchlist_id}/items", status_code=201)
def add_watchlist_item(
    watchlist_id: int,
    payload: WatchlistItemCreate,
    session: Session = Depends(get_session),
):
    code = payload.asset_code.strip().lower().removeprefix("sh").removeprefix("sz").removeprefix("bj")
    if len(code) != 6 or not code.isdigit() or payload.asset_type not in {"stock", "fund"}:
        raise HTTPException(status_code=400, detail="请输入有效的 6 位股票或基金代码")
    watchlist = session.get(Watchlist, watchlist_id)
    if watchlist is None:
        raise HTTPException(status_code=404, detail="追踪列表不存在")
    asset = (
        session.query(Asset)
        .filter(Asset.code == code, Asset.asset_type == payload.asset_type)
        .one_or_none()
    )
    custom_name = payload.asset_name.strip() if payload.asset_name and payload.asset_name.strip() else None
    if asset is None:
        resolved_name = _resolve_asset_name(code, payload.asset_type)
        asset = Asset(
            code=code,
            name=resolved_name or code,
            asset_type=payload.asset_type,
            custom_name=custom_name,
        )
        session.add(asset)
        session.flush()
    elif asset.name == asset.code:
        resolved_name = _resolve_asset_name(code, payload.asset_type)
        if resolved_name:
            asset.name = resolved_name
    if custom_name:
        asset.custom_name = custom_name
    existing = (
        session.query(WatchlistItem)
        .filter(WatchlistItem.watchlist_id == watchlist_id, WatchlistItem.asset_id == asset.id)
        .one_or_none()
    )
    if existing is not None:
        return {"id": existing.id, "watchlist_id": existing.watchlist_id, "asset_id": existing.asset_id}
    item = WatchlistItem(watchlist_id=watchlist_id, asset_id=asset.id)
    session.add(item)
    session.commit()
    session.refresh(item)
    return {"id": item.id, "watchlist_id": watchlist_id, "asset_id": asset.id}


def _resolve_asset_name(code: str, asset_type: str) -> str | None:
    try:
        quote = fetch_fund_estimate(code) if asset_type == "fund" else fetch_stock_quote(code)
        name = quote.get("name") if quote.get("ok") else None
        return str(name).strip() if name else None
    except Exception:
        return None


@router.get("/watchlists/{watchlist_id}/trends")
def watchlist_trends(watchlist_id: int, refresh: bool = False, session: Session = Depends(get_session)):
    if session.get(Watchlist, watchlist_id) is None:
        raise HTTPException(status_code=404, detail="追踪列表不存在")
    if refresh:
        return refresh_watchlist_trends(session, watchlist_id)
    return get_watchlist_trends(session, watchlist_id)


@router.post("/watchlists/{watchlist_id}/trends/refresh")
def refresh_selected_watchlist_trends(
    watchlist_id: int,
    payload: WatchlistRefreshRequest,
    session: Session = Depends(get_session),
):
    if session.get(Watchlist, watchlist_id) is None:
        raise HTTPException(status_code=404, detail="追踪列表不存在")
    existing_ids = {
        item_id
        for (item_id,) in session.query(WatchlistItem.id)
        .filter(
            WatchlistItem.watchlist_id == watchlist_id,
            WatchlistItem.id.in_(payload.item_ids),
        )
        .all()
    }
    if len(existing_ids) != len(set(payload.item_ids)):
        raise HTTPException(status_code=400, detail="刷新范围包含无效追踪项")
    return refresh_watchlist_trends(session, watchlist_id, item_ids=payload.item_ids)


@router.get("/watchlists/{watchlist_id}/items/{item_id}")
def get_watchlist_item(watchlist_id: int, item_id: int, session: Session = Depends(get_session)):
    item = _get_watchlist_item(session, watchlist_id, item_id)
    return _watchlist_item_payload(item)


@router.get("/watchlists/{watchlist_id}/items/{item_id}/history")
def watchlist_item_history(
    watchlist_id: int,
    item_id: int,
    range: str = "6m",
    refresh: bool = False,
    session: Session = Depends(get_session),
):
    if range != "6m":
        raise HTTPException(status_code=400, detail="当前仅支持近半年历史走势")
    try:
        return get_watchlist_item_history(session, watchlist_id, item_id, refresh=refresh)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/watchlists/{watchlist_id}/items/{item_id}")
def update_watchlist_item(
    watchlist_id: int,
    item_id: int,
    payload: WatchlistItemUpdate,
    session: Session = Depends(get_session),
):
    item = _get_watchlist_item(session, watchlist_id, item_id)
    if "custom_name" in payload.model_fields_set:
        item.asset.custom_name = payload.custom_name.strip() if payload.custom_name and payload.custom_name.strip() else None
    if "tags" in payload.model_fields_set:
        item.tags_json = json.dumps(_normalize_tags(payload.tags or []), ensure_ascii=False)
    session.commit()
    session.refresh(item)
    return _watchlist_item_payload(item)


@router.delete("/watchlists/{watchlist_id}/items/{item_id}")
def remove_watchlist_item(watchlist_id: int, item_id: int, session: Session = Depends(get_session)):
    item = _get_watchlist_item(session, watchlist_id, item_id)
    session.delete(item)
    session.commit()
    return {"status": "ok", "id": item_id}


def _get_watchlist_item(session: Session, watchlist_id: int, item_id: int) -> WatchlistItem:
    item = (
        session.query(WatchlistItem)
        .filter(WatchlistItem.id == item_id, WatchlistItem.watchlist_id == watchlist_id)
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="追踪项不存在")
    return item


def _watchlist_item_payload(item: WatchlistItem) -> dict:
    return {
        "id": item.id,
        "watchlist_id": item.watchlist_id,
        "asset_id": item.asset_id,
        "asset": {
            "id": item.asset.id,
            "code": item.asset.code,
            "name": item.asset.name,
            "official_name": item.asset.name,
            "custom_name": item.asset.custom_name,
            "asset_type": item.asset.asset_type,
        },
        "official_name": item.asset.name,
        "custom_name": item.asset.custom_name,
        "display_name": item.asset.custom_name or item.asset.name,
        "tags": _item_tags(item),
    }


def _normalize_tags(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = str(value).strip().strip("#")[:24]
        key = tag.casefold()
        if tag and key not in seen:
            result.append(tag)
            seen.add(key)
    return result[:12]


def _item_tags(item: WatchlistItem) -> list[str]:
    try:
        value = json.loads(item.tags_json or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return _normalize_tags(value) if isinstance(value, list) else []
