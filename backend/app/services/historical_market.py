from __future__ import annotations

import json
import urllib.parse
import urllib.request
from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy.orm import Session, joinedload

from app.models import Asset, DailyBar, WatchlistItem

HistoryFetcher = Callable[[str, date, date], list[dict[str, Any]]]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def get_watchlist_item_history(
    session: Session,
    watchlist_id: int,
    item_id: int,
    *,
    refresh: bool = False,
    today: date | None = None,
    stock_fetcher: HistoryFetcher | None = None,
    fund_fetcher: HistoryFetcher | None = None,
) -> dict[str, Any]:
    item = (
        session.query(WatchlistItem)
        .options(joinedload(WatchlistItem.asset))
        .filter(WatchlistItem.id == item_id, WatchlistItem.watchlist_id == watchlist_id)
        .one_or_none()
    )
    if item is None:
        raise LookupError("追踪项不存在")

    end_date = today or date.today()
    start_date = _subtract_months(end_date, 6)
    rows = _query_bars(session, item.asset.id, start_date, end_date)
    cache_fresh = bool(rows and rows[-1].bar_date >= _latest_expected_date(end_date))
    source_status = "cached" if rows else "unavailable"
    source = rows[-1].source if rows else None
    source_error: str | None = None

    if refresh or not cache_fresh:
        fetcher = (stock_fetcher or fetch_stock_history) if _is_etf_or_stock(item.asset) else (fund_fetcher or fetch_fund_history)
        try:
            points = fetcher(item.asset.code, start_date, end_date)
            _upsert_bars(session, item.asset.id, points)
            session.commit()
            rows = _query_bars(session, item.asset.id, start_date, end_date)
            if points:
                source = rows[-1].source if rows else source
                source_status = "fresh"
            elif rows:
                source_status = "cached"
            else:
                source_status = "unavailable"
        except Exception as exc:
            session.rollback()
            source_error = str(exc)
            source_status = "cached" if rows else "unavailable"

    value_label = "收盘价" if _is_etf_or_stock(item.asset) else "单位净值"
    return {
        "watchlist_item_id": item.id,
        "code": item.asset.code,
        "name": item.asset.custom_name or item.asset.name,
        "official_name": item.asset.name,
        "custom_name": item.asset.custom_name,
        "asset_type": item.asset.asset_type,
        "value_label": value_label,
        "range": "6m",
        "range_label": "近半年",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "source": source,
        "source_label": _source_label(source),
        "cache_status": source_status,
        "message": f"{_history_message(source_status)}：{source_error}" if source_error and source_status == "unavailable" else _history_message(source_status),
        "points": [_bar_payload(row) for row in rows],
    }


def fetch_stock_history(code: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
    market = "1" if code.startswith(("5", "6")) else "0"
    query = urllib.parse.urlencode(
        {
            "secid": f"{market}.{code}",
            "klt": "101",
            "fqt": "1",
            "beg": start_date.strftime("%Y%m%d"),
            "end": end_date.strftime("%Y%m%d"),
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        }
    )
    try:
        payload = _get_json(
            f"https://push2his.eastmoney.com/api/qt/stock/kline/get?{query}",
            referer="https://quote.eastmoney.com/",
        )
    except Exception:
        return _fetch_sina_stock_history(code, start_date, end_date)
    rows = ((payload.get("data") or {}).get("klines") or []) if isinstance(payload, dict) else []
    points: list[dict[str, Any]] = []
    for raw in rows:
        fields = str(raw).split(",")
        if len(fields) < 6:
            continue
        bar_date = _parse_date(fields[0])
        close_price = _to_float(fields[2])
        if bar_date is None or close_price is None:
            continue
        points.append(
            {
                "bar_date": bar_date,
                "open_price": _to_float(fields[1]),
                "close_price": close_price,
                "high_price": _to_float(fields[3]),
                "low_price": _to_float(fields[4]),
                "change_pct": _to_float(fields[8]) if len(fields) > 8 else None,
                "source": "eastmoney_stock_history",
            }
        )
    return points or _fetch_sina_stock_history(code, start_date, end_date)


def _fetch_sina_stock_history(code: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
    market = "sh" if code.startswith(("5", "6")) else "sz"
    query = urllib.parse.urlencode({"symbol": f"{market}{code}", "scale": "240", "ma": "no", "datalen": "200"})
    payload = _get_json(f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?{query}")
    rows = payload if isinstance(payload, list) else []
    points: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        bar_date = _parse_date(raw.get("day"))
        close_price = _to_float(raw.get("close"))
        if bar_date is None or close_price is None or not (start_date <= bar_date <= end_date):
            continue
        points.append(
            {
                "bar_date": bar_date,
                "open_price": _to_float(raw.get("open")),
                "close_price": close_price,
                "high_price": _to_float(raw.get("high")),
                "low_price": _to_float(raw.get("low")),
                "change_pct": None,
                "source": "sina_stock_history",
            }
        )
    for index, point in enumerate(points):
        if index == 0:
            continue
        previous = points[index - 1]["close_price"]
        if previous:
            point["change_pct"] = round((point["close_price"] / previous - 1) * 100, 4)
    return points


def fetch_fund_history(code: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_dates: set[str] = set()
    for page_index in range(1, 20):
        query = urllib.parse.urlencode(
            {
                "fundCode": code,
                "pageIndex": str(page_index),
                "pageSize": "20",
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
            }
        )
        payload = _get_json(
            f"https://api.fund.eastmoney.com/f10/lsjz?{query}",
            referer="https://fundf10.eastmoney.com/",
        )
        data = (payload.get("Data") or {}) if isinstance(payload, dict) else {}
        page_rows = data.get("LSJZList") or []
        if not page_rows:
            break
        new_rows = [row for row in page_rows if str(row.get("FSRQ") or "") not in seen_dates]
        if not new_rows:
            break
        rows.extend(new_rows)
        seen_dates.update(str(row.get("FSRQ") or "") for row in new_rows)
        parsed_dates = [_parse_date(row.get("FSRQ")) for row in new_rows]
        if any(row_date is not None and row_date <= start_date for row_date in parsed_dates):
            break
    points: list[dict[str, Any]] = []
    for row in rows:
        bar_date = _parse_date(row.get("FSRQ"))
        close_price = _to_float(row.get("DWJZ"))
        if bar_date is None or close_price is None or close_price <= 0:
            continue
        points.append(
            {
                "bar_date": bar_date,
                "close_price": close_price,
                "change_pct": _to_float(row.get("JZZZL")),
                "source": "eastmoney_fund_history",
            }
        )
    return points


def _is_etf_or_stock(asset: Asset) -> bool:
    if asset.asset_type == "stock":
        return True
    # ETF联接基金 often contain "ETF" in their name but use fund NAV history.
    # Only exchange-traded code families should use market-price history here.
    return asset.code.startswith(("15", "5", "56", "58")) and not asset.code.startswith("015")


def _query_bars(session: Session, asset_id: int, start_date: date, end_date: date) -> list[DailyBar]:
    return (
        session.query(DailyBar)
        .filter(
            DailyBar.asset_id == asset_id,
            DailyBar.bar_date >= start_date,
            DailyBar.bar_date <= end_date,
        )
        .order_by(DailyBar.bar_date.asc(), DailyBar.id.asc())
        .all()
    )


def _upsert_bars(session: Session, asset_id: int, points: list[dict[str, Any]]) -> None:
    for point in points:
        bar_date = point.get("bar_date")
        if not isinstance(bar_date, date):
            continue
        close_price = _to_float(point.get("close_price"))
        if close_price is None or close_price <= 0:
            continue
        row = (
            session.query(DailyBar)
            .filter(DailyBar.asset_id == asset_id, DailyBar.bar_date == bar_date)
            .one_or_none()
        )
        if row is None:
            row = DailyBar(asset_id=asset_id, bar_date=bar_date, close_price=Decimal(str(close_price)), source=str(point.get("source") or "history"))
            session.add(row)
        row.open_price = _decimal_or_none(point.get("open_price"))
        row.high_price = _decimal_or_none(point.get("high_price"))
        row.low_price = _decimal_or_none(point.get("low_price"))
        row.close_price = Decimal(str(close_price))
        row.change_pct = _decimal_or_none(point.get("change_pct"))
        row.source = str(point.get("source") or row.source or "history")


def _bar_payload(row: DailyBar) -> dict[str, Any]:
    return {
        "date": row.bar_date.isoformat(),
        "value": float(row.close_price),
        "open": float(row.open_price) if row.open_price is not None else None,
        "high": float(row.high_price) if row.high_price is not None else None,
        "low": float(row.low_price) if row.low_price is not None else None,
        "change_pct": float(row.change_pct) if row.change_pct is not None else None,
    }


def _get_json(url: str, *, referer: str | None = None) -> Any:
    headers = {**HEADERS, **({"Referer": referer} if referer else {})}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _subtract_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 - months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    return value.replace(year=year, month=month, day=min(value.day, monthrange(year, month)[1]))


def _latest_expected_date(end_date: date) -> date:
    return end_date - timedelta(days=3)


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "", "-") else None
    except (TypeError, ValueError):
        return None


def _decimal_or_none(value: Any) -> Decimal | None:
    parsed = _to_float(value)
    return Decimal(str(parsed)) if parsed is not None else None


def _source_label(source: str | None) -> str | None:
    return {
        "eastmoney_stock_history": "东方财富历史行情",
        "sina_stock_history": "新浪历史行情",
        "eastmoney_fund_history": "东方财富历史净值",
    }.get(source, source)


def _history_message(status: str) -> str:
    if status == "fresh":
        return "已更新近半年历史数据"
    if status == "cached":
        return "数据源暂不可用，显示本地缓存"
    return "暂无可用历史数据"
