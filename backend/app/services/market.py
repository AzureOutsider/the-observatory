from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timedelta
from html import unescape
from typing import Any

from app.services.market_health import market_source_health
from app.services.news import fetch_news as fetch_normalized_news
from app.config import settings

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def fetch_fund_estimate(code: str) -> dict[str, Any]:
    estimate = _fetch_xincai_fund_estimate(code)
    _record_source_result("sina_xincai_estimate", estimate)
    if estimate.get("ok"):
        if not estimate.get("name"):
            metadata = _fetch_tencent_fund_quote(code)
            _record_source_result("tencent_fund_quote", metadata)
            if metadata.get("name"):
                estimate["name"] = metadata["name"]
        return estimate

    secondary = _fetch_tencent_fund_quote(code)
    _record_source_result("tencent_fund_quote", secondary)
    if secondary.get("ok"):
        secondary["warnings"] = [str(estimate.get("error") or "intraday estimate unavailable")]
        return secondary

    fallback = _fetch_eastmoney_official_nav(code)
    _record_source_result("eastmoney_official_nav", fallback)
    if fallback.get("ok"):
        fallback["warnings"] = [
            str(estimate.get("error") or "intraday estimate unavailable"),
            str(secondary.get("error") or "secondary source unavailable"),
        ]
        return fallback

    return {
        "ok": False,
        "code": code,
        "error": (
            "基金行情数据源均不可用："
            f"新浪新财：{estimate.get('error') or '未知错误'}；"
            f"腾讯行情：{secondary.get('error') or '未知错误'}；"
            f"东方财富官方净值：{fallback.get('error') or '未知错误'}"
        ),
    }


def _fetch_xincai_fund_estimate(code: str) -> dict[str, Any]:
    url = (
        "https://app.xincai.com/fund/api/jsonp.json/var%20t=/"
        f"XinCaiFundService.getFundYuCeNav?symbol={code}"
    )
    try:
        req = urllib.request.Request(
            url,
            headers={**HEADERS, "Referer": "https://finance.sina.com.cn/"},
        )
        with urllib.request.urlopen(req, timeout=settings.market_request_timeout_seconds) as response:
            text = response.read().decode("utf-8", errors="replace")
        return _parse_xincai_fund_estimate(code, text)
    except Exception as exc:
        return {"code": code, "ok": False, "error": str(exc), "health_outcome": "failure"}


def _parse_xincai_fund_estimate(
    code: str,
    text: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    previous_match = re.search(r'yes:"([^"]*)"', text)
    detail_match = re.search(r'detail:"([^"]*)"', text)
    previous_nav = _positive_float(previous_match.group(1)) if previous_match else None
    if previous_nav is None or not detail_match:
        return {"code": code, "ok": False, "error": "新浪新财未返回盘中估值"}

    values = [part.strip() for part in detail_match.group(1).split(",")]
    if len(values) < 2 or len(values) % 2 != 0:
        return {"code": code, "ok": False, "error": "新浪新财估值明细格式异常"}

    current = now or datetime.now()
    today = current.date().isoformat()
    future_limit = current + timedelta(minutes=5)
    points: list[dict[str, Any]] = []
    for index in range(0, len(values), 2):
        point_time = values[index]
        point_nav = _positive_float(values[index + 1])
        if not re.fullmatch(r"\d{2}:\d{2}", point_time) or point_nav is None:
            continue
        observed_at = datetime.strptime(f"{today} {point_time}", "%Y-%m-%d %H:%M")
        if observed_at > future_limit:
            return {
                "code": code,
                "ok": False,
                "error": "新浪新财返回了未来时间点，疑似上一交易日缓存",
            }
        points.append(
            {
                "time": f"{today} {point_time}",
                "estimate_nav": point_nav,
                "change_pct": round((point_nav / previous_nav - 1) * 100, 4),
            }
        )
    if not points:
        return {"code": code, "ok": False, "error": "新浪新财未返回有效盘中点"}

    latest = points[-1]
    return {
        "ok": True,
        "code": code,
        "name": "",
        "nav": previous_nav,
        "estimate_nav": latest["estimate_nav"],
        "change_pct": latest["change_pct"],
        "time": latest["time"],
        "source": "sina_xincai_estimate",
        "data_status": "intraday_estimate",
        "message": "盘中估值，仅供参考",
        "value_label": "估值",
        "points": points,
    }


def _fetch_tencent_fund_quote(code: str) -> dict[str, Any]:
    url = f"https://qt.gtimg.cn/q=jj{code}"
    try:
        req = urllib.request.Request(
            url,
            headers={**HEADERS, "Referer": "https://gu.qq.com/"},
        )
        with urllib.request.urlopen(req, timeout=settings.market_request_timeout_seconds) as response:
            text = response.read().decode("gbk", errors="replace")
        return _parse_tencent_fund_quote(code, text)
    except Exception as exc:
        return {"code": code, "ok": False, "error": str(exc), "health_outcome": "failure"}


def _parse_tencent_fund_quote(code: str, text: str) -> dict[str, Any]:
    match = re.search(r'="([^"]*)"', text)
    if not match:
        return {"code": code, "ok": False, "error": "腾讯行情返回格式异常"}

    fields = match.group(1).split("~")
    if len(fields) < 9 or fields[0] != code:
        return {"code": code, "ok": False, "error": "腾讯行情未返回该基金"}

    estimate_nav = _positive_float(fields[2])
    official_nav = _positive_float(fields[5])
    quote_time = fields[8].strip()
    if estimate_nav is not None:
        return {
            "ok": True,
            "code": fields[0],
            "name": fields[1],
            "nav": official_nav,
            "estimate_nav": estimate_nav,
            "change_pct": _safe_float(fields[3]),
            "time": _normalise_quote_time(quote_time),
            "source": "tencent_fund_quote",
            "data_status": "intraday_estimate",
            "message": "盘中估值，仅供参考",
        }

    if official_nav is None:
        return {"code": code, "ok": False, "error": "腾讯行情未返回有效净值"}

    return {
        "ok": True,
        "code": fields[0],
        "name": fields[1],
        "nav": official_nav,
        "estimate_nav": None,
        "change_pct": _safe_float(fields[7]),
        "time": _normalise_quote_time(quote_time),
        "source": "tencent_fund_quote",
        "data_status": "official_nav",
        "message": "最新官方净值（非实时估值）",
    }


def _fetch_eastmoney_official_nav(code: str) -> dict[str, Any]:
    url = f"https://api.fund.eastmoney.com/f10/lsjz?fundCode={code}&pageIndex=1&pageSize=1"
    try:
        req = urllib.request.Request(
            url,
            headers={**HEADERS, "Referer": "https://fundf10.eastmoney.com/"},
        )
        with urllib.request.urlopen(req, timeout=settings.market_request_timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
        rows = data.get("Data", {}).get("LSJZList", []) if data.get("Data") else []
        if not rows:
            return {"code": code, "ok": False, "error": "东方财富未返回最新净值"}
        row = rows[0]
        nav = _safe_float(row.get("DWJZ"))
        if nav is None or nav <= 0:
            return {"code": code, "ok": False, "error": "东方财富最新净值为空"}
        fund_data = data.get("Data", {}) or {}
        fund_type = str(fund_data.get("FundType") or "")
        fund_name = str(
            fund_data.get("FundName")
            or fund_data.get("SHORTNAME")
            or fund_data.get("基金简称")
            or ""
        ).strip()
        value_label = "每万份收益" if fund_type == "005" else "净值"
        return {
            "ok": True,
            "code": code,
            "name": fund_name,
            "nav": nav,
            "estimate_nav": None,
            "change_pct": _safe_float(row.get("JZZZL")),
            "time": _normalise_quote_time(str(row.get("FSRQ") or "")),
            "source": "eastmoney_official_nav",
            "data_status": "official_nav",
            "message": "最新官方净值（非实时估值）",
            "value_label": value_label,
            "fund_type": fund_type,
        }
    except Exception as exc:
        return {"code": code, "ok": False, "error": str(exc), "health_outcome": "failure"}


def _record_source_result(source: str, result: dict[str, Any]) -> None:
    if result.get("ok"):
        outcome = "success"
    else:
        outcome = str(result.get("health_outcome") or "no_data")
        if outcome not in {"no_data", "failure"}:
            outcome = "failure"
    market_source_health.record(source, outcome, str(result.get("error") or "") or None)


def fetch_stock_quote(code: str) -> dict[str, Any]:
    """Fetch a mainland A-share quote using Sina's public quote endpoint."""
    clean_code = code.strip().lower()
    symbol = _stock_symbol(clean_code)
    if symbol is None:
        return {"ok": False, "code": code, "error": "请输入 6 位 A 股代码"}
    try:
        req = urllib.request.Request(
            f"https://hq.sinajs.cn/list={symbol}{clean_code[-6:]}",
            headers={**HEADERS, "Referer": "https://finance.sina.com.cn/"},
        )
        with urllib.request.urlopen(req, timeout=settings.market_request_timeout_seconds) as response:
            text = response.read().decode("gbk", errors="replace")
        raw = text.split('"')[1].split(",")
        name = raw[0].strip() if raw else ""
        price = _safe_float(raw[3] if len(raw) > 3 else None)
        previous = _safe_float(raw[2] if len(raw) > 2 else None)
        if not name or price is None or price <= 0 or previous is None or previous <= 0:
            return {"ok": False, "code": code, "error": "新浪行情未返回有效股票报价"}
        change_pct = round((price - previous) / previous * 100, 4)
        observed_at = " ".join(raw[30:32]).strip() if len(raw) > 31 else ""
        return {
            "ok": True,
            "code": clean_code[-6:],
            "name": name,
            "price": price,
            "change_pct": change_pct,
            "time": observed_at,
            "source": "sina_stock",
            "data_status": "intraday_estimate",
            "message": "盘中股票报价，仅供参考",
        }
    except Exception as exc:
        return {"ok": False, "code": code, "error": str(exc), "health_outcome": "failure"}


def _stock_symbol(code: str) -> str | None:
    clean_code = code.removeprefix("sh").removeprefix("sz").removeprefix("bj")
    if len(clean_code) != 6 or not clean_code.isdigit():
        return None
    if clean_code.startswith(("5", "6", "68")):
        return "sh"
    if clean_code.startswith(("0", "3")):
        return "sz"
    if clean_code.startswith(("4", "8")):
        return "bj"
    return None


def fetch_market_indices() -> list[dict[str, Any]]:
    indices = [
        ("s_sh000001", "上证指数"),
        ("s_sz399001", "深证成指"),
        ("s_sz399006", "创业板指"),
        ("s_sh000688", "科创50"),
        ("s_sh000300", "沪深300"),
    ]
    results: list[dict[str, Any]] = []
    for code, name in indices:
        try:
            req = urllib.request.Request(
                f"https://hq.sinajs.cn/list={code}",
                headers={**HEADERS, "Referer": "https://finance.sina.com.cn/"},
            )
            with urllib.request.urlopen(req, timeout=8) as response:
                text = response.read().decode("gbk")
            raw = text.split('"')[1].split(",")
            results.append(
                {
                    "ok": True,
                    "code": code,
                    "name": name,
                    "price": _safe_float(raw[1] if len(raw) > 1 else None),
                    "change_pct": _safe_float(raw[3] if len(raw) > 3 else None),
                    "source": "sina",
                }
            )
        except Exception as exc:
            results.append({"ok": False, "code": code, "name": name, "error": str(exc)})
    return results


def fetch_news(limit: int = 20, session=None, refresh: bool = False) -> list[dict[str, Any]]:
    """Compatibility seam for callers that historically imported news from market.py."""
    return fetch_normalized_news(limit=limit, session=session, refresh=refresh)


def trading_status(now: datetime | None = None) -> dict[str, str]:
    current = now or datetime.now()
    if current.weekday() >= 5:
        return {"status": "closed", "message": "周末休市"}
    minutes = current.hour * 60 + current.minute
    if minutes < 9 * 60 + 30:
        return {"status": "pre_open", "message": "开盘前"}
    if minutes < 11 * 60 + 30:
        return {"status": "morning", "message": "上午盘中"}
    if minutes < 13 * 60:
        return {"status": "lunch", "message": "午间休市"}
    if minutes < 15 * 60:
        return {"status": "afternoon", "message": "下午盘中"}
    return {"status": "closed", "message": "已收盘"}


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", text))).strip()


def _safe_float(value: object) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _positive_float(value: object) -> float | None:
    parsed = _safe_float(value)
    return parsed if parsed is not None and parsed > 0 else None


def _normalise_quote_time(value: str) -> str:
    cleaned = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned):
        return f"{cleaned} 15:00"
    return cleaned
