"""
导出今日实时数据 -> JSON，供 agent 复盘读取（无需手动粘贴持仓）。

用法:
    python export_daily.py

首次使用先复制 watchlist.example.json 为 watchlist.json，再填写自己的标的。

数据来源:
    - 基金实时估值: 天天基金 fundgz.1234567.com.cn
    - 美元指数 DXY: 新浪 hq.sinajs.cn (list=DINIW)
输出:
    <agent_data>/exports/YYYY-MM-DD_HHMM.json
    (每次运行按当前时间生成新文件，按日期归档；agent_data 即本脚本所在目录)

扩展方式:
    编辑同目录 watchlist.json，在 items 里新增一项即可。
    { "code": "xxxxxx", "name": "名称", "type": "fund", "theme": "分组", "note": "可选" }
    type=fund 走天天基金估值；type=stock 走新浪个股行情。
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WATCHLIST_FILE = os.path.join(SCRIPT_DIR, "watchlist.json")
EXPORT_DIR = os.path.join(SCRIPT_DIR, "exports")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

FUND_ESTIMATE_URL = "https://fundgz.1234567.com.cn/js/{code}.js"
STOCK_URL = "https://hq.sinajs.cn/list={code}"
DXY_URL = "https://hq.sinajs.cn/list=DINIW"

# 内部新闻信号来源（独立抓取，不依赖后端服务）
WALLSTREETCNN_URL = "https://api-one.wallstcn.com/apiv1/content/lives?channel=global-channel&limit={limit}"
SINA_NEWS_URL = "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&k=&num={limit}&page=1"

# 新闻 -> 持仓主题 关键词映射（用于把新闻关联到你的 watchlist 分组）
NEWS_TAG_KEYWORDS = {
    "AI": ("AI", "人工智能", "大模型", "算力", "英伟达", "NVIDIA", "微软", "OpenAI", "GPT"),
    "半导体": ("半导体", "芯片", "晶圆", "光刻", "存储", "美光", "台积电", "中芯", "长鑫", "DRAM"),
    "黄金": ("黄金", "金价", "贵金属", "上海金", "避险", "伦敦金"),
    "债券": ("债券", "债市", "国债", "收益率", "利率债", "信用债"),
    "美联储": ("美联储", "降息", "加息", "鲍威尔", "沃什", "FOMC", "联邦基金利率"),
    "通胀": ("通胀", "CPI", "PPI", "PCE", "物价"),
    "美元": ("美元", "美元指数", "DXY", "汇率"),
    "红利": ("红利", "高股息", "股息", "分红"),
    "银行": ("银行", "息差", "存款", "贷款", "拨备"),
    "房地产": ("房地产", "地产", "房企", "楼市", "房贷"),
    "新能源": ("新能源", "光伏", "风电", "储能", "锂电"),
    "电池": ("电池", "锂电", "固态电池", "储能"),
    "电力": ("电力", "电网", "火电", "水电", "核电", "绿电"),
    "消费": ("消费", "食品饮料", "白酒", "零售", "餐饮"),
    "港股": ("港股", "恒生", "港交所", "南向资金"),
    "美股": ("美股", "纳指", "纳斯达克", "标普", "道指"),
    "A股": ("A股", "沪指", "上证", "深证", "创业板", "科创", "沪深", "中证"),
}
DEFAULT_TAG = "市场"


def _get(url: str, referer: str | None = None, decode: str = "utf-8") -> str:
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode(decode)


def fetch_fund_estimate(code: str) -> dict:
    """基金实时估值（天天基金）。返回含 change_pct 的字典。"""
    try:
        text = _get(FUND_ESTIMATE_URL.format(code=code),
                    referer="https://fundf10.eastmoney.com/")
        start, end = text.find("("), text.rfind(")")
        if start == -1 or end == -1:
            return {"ok": False, "error": "unexpected response"}
        data = json.loads(text[start + 1:end])
        return {
            "ok": True,
            "code": data.get("fundcode", code),
            "name": data.get("name", ""),
            "nav": _f(data.get("dwjz")),
            "estimate_nav": _f(data.get("gsz")),
            "change_pct": _f(data.get("gszzl")),
            "time": data.get("gztime", ""),
        }
    except Exception as exc:  # 网络/解析失败
        return {"ok": False, "error": str(exc)}


def fetch_stock_quote(code: str) -> dict:
    """A股个股实时行情（新浪）。code 形如 sh600519 / sz000001。"""
    try:
        text = _get(STOCK_URL.format(code=code),
                    referer="https://finance.sina.com.cn/", decode="gbk")
        raw = text.split('"')[1].split(",")
        if len(raw) < 4:
            return {"ok": False, "error": "empty quote"}
        return {
            "ok": True,
            "code": code,
            "name": raw[0],
            "price": _f(raw[1]),
            "prev_close": _f(raw[2]),
            "change_pct": _f(raw[3]),
            "time": raw[30] if len(raw) > 30 else "",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def fetch_dxy() -> dict:
    """美元指数 DXY（新浪）。"""
    try:
        text = _get(DXY_URL, referer="https://finance.sina.com.cn/", decode="gbk")
        if "DINIW" not in text:
            return {"ok": False, "error": "no DINIW field"}
        fields = text.split('"')[1].split(",")
        price = _f(fields[1])
        preclose = _f(fields[7])
        chg = round((price - preclose) / preclose * 100, 2) if price and preclose else None
        return {
            "ok": True,
            "price": price,
            "preclose": preclose,
            "change_pct": chg,
            "high": _f(fields[5]),
            "low": _f(fields[6]),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _f(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _clean_text(text: str) -> str:
    import re
    from html import unescape
    text = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s+", " ", unescape(text)).strip()


def fetch_news(limit: int = 30) -> list[dict]:
    """抓取内部新闻信号（华尔街见闻 + 新浪），独立实现，不依赖后端。"""
    items: list[dict] = []
    items.extend(_fetch_wallstreetcn(limit))
    items.extend(_fetch_sina(limit))
    seen: set[str] = set()
    unique: list[dict] = []
    for item in items:
        key = (item.get("title") or "")[:40]
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    return unique[:limit]


def _fetch_wallstreetcn(limit: int) -> list[dict]:
    try:
        url = WALLSTREETCNN_URL.format(limit=limit)
        data = json.loads(_get(url))
        out = []
        for row in data.get("data", {}).get("items", []):
            title = _clean_text(row.get("content_text", "") or row.get("title", ""))
            if title:
                out.append({"title": title, "url": "", "source": "wallstreetcn"})
        return out
    except Exception:
        return []


def _fetch_sina(limit: int) -> list[dict]:
    try:
        url = SINA_NEWS_URL.format(limit=limit)
        data = json.loads(_get(url, referer="https://finance.sina.com.cn/"))
        out = []
        for row in data.get("result", {}).get("data", []):
            title = _clean_text(row.get("title", ""))
            if title:
                out.append({"title": title, "url": row.get("url", ""), "source": "sina"})
        return out
    except Exception:
        return []


def tag_news_item(title: str, watch_themes: set[str]) -> dict:
    tags = [
        tag
        for tag, keywords in NEWS_TAG_KEYWORDS.items()
        if any(kw.lower() in title.lower() for kw in keywords)
    ]
    tags = tags or [DEFAULT_TAG]
    related = sorted(set(tags) & watch_themes)
    return {"tags": tags, "related_themes": related}


def build_internal_news(watch_themes: set[str], limit: int = 30) -> list[dict]:
    raw = fetch_news(limit=limit)
    out = []
    for item in raw:
        tagged = tag_news_item(item.get("title", ""), watch_themes)
        out.append({
            "title": item.get("title"),
            "source": item.get("source"),
            "url": item.get("url", ""),
            "tags": tagged["tags"],
            "related_themes": tagged["related_themes"],
            "note": "Internal site signal only; agent must verify importance with active web search.",
        })
    return out


def load_watchlist() -> dict:
    if not os.path.exists(WATCHLIST_FILE):
        raise FileNotFoundError(
            "缺少 agent_data/watchlist.json；请先复制 watchlist.example.json 并填写个人追踪清单"
        )
    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    now = datetime.now()
    watchlist = load_watchlist()
    items = watchlist.get("items", [])

    # 拉取宏观（DXY）
    dxy = fetch_dxy()

    # 拉取内部新闻信号，并与 watchlist 主题关联
    watch_themes = {it.get("theme", "") for it in items if it.get("theme")}
    internal_news = build_internal_news(watch_themes, limit=30)

    # 逐标的拉取实时数据
    holdings = []
    for it in items:
        code = it.get("code", "")
        typ = it.get("type", "fund")
        rec = {
            "code": code,
            "name": it.get("name", ""),
            "type": typ,
            "theme": it.get("theme", ""),
            "note": it.get("note", ""),
        }
        if typ == "stock":
            q = fetch_stock_quote(code)
            rec["price"] = q.get("price")
            rec["change_pct"] = q.get("change_pct")
            rec["updated_at"] = q.get("time")
            rec["source"] = "sina" if q.get("ok") else f"failed:{q.get('error')}"
        else:  # fund
            q = fetch_fund_estimate(code)
            rec["estimate_nav"] = q.get("estimate_nav")
            rec["change_pct"] = q.get("change_pct")
            rec["updated_at"] = q.get("time")
            rec["source"] = "fundgz.1234567.com.cn" if q.get("ok") else f"failed:{q.get('error')}"
        holdings.append(rec)
        time.sleep(0.15)  # 轻量限速，避免被封

    # 按今日涨跌排序（便于 agent 一眼看强弱）
    holdings.sort(key=lambda x: x.get("change_pct") if x.get("change_pct") is not None else -999,
                  reverse=True)

    up = sum(1 for h in holdings if h.get("change_pct") and h["change_pct"] > 0)
    down = sum(1 for h in holdings if h.get("change_pct") and h["change_pct"] < 0)
    flat = len(holdings) - up - down

    package = {
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "export_daily.py (实时抓取，非收盘保证)",
        "macro": {
            "dxy": dxy,
            "note": "黄金/美股 QDII 受 DXY 与实际利率影响，复盘时结合参考",
        },
        "summary": {"count": len(holdings), "up": up, "down": down, "flat": flat},
        "internal_news_signals": internal_news,
        "holdings": holdings,
    }

    os.makedirs(EXPORT_DIR, exist_ok=True)
    out_name = now.strftime("%Y-%m-%d_%H%M") + ".json"
    out_path = os.path.join(EXPORT_DIR, out_name)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(package, f, ensure_ascii=False, indent=2)

    print(f"已导出: {out_path}")
    print(f"标的 {len(holdings)} 支 | 涨 {up} / 跌 {down} / 平 {flat}")
    print(f"内部新闻信号 {len(internal_news)} 条")
    if not dxy.get("ok"):
        print(f"[警告] DXY 获取失败: {dxy.get('error')}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已退出")
