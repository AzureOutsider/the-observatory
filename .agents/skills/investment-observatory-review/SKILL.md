---
name: investment-observatory-review
description: Produce a disciplined daily investment review from The Observatory's live analysis package and external research. Use when reviewing a portfolio, generating a daily market note, or writing to the configured local review file.
---

# Investment Observatory Review

## Quick start

1. Confirm the local Observatory API is running.
2. Fetch `http://127.0.0.1:8000/api/agent/analysis-package/today` (add `?topic=...` when useful).
3. Read the package before forming any conclusion. It is the source of private portfolio facts, timestamps, freshness, and historical review continuity.
4. Search the public web before writing. Internal news signals are leads only and never imply complete coverage.
5. Write the Markdown review using the structure below, then append it with `POST /api/agent/reviews/append`.

## Required research

Search beyond the supplied news for all of these that apply:

- China A-share indices, policy, liquidity, and market style.
- Industries and themes represented in the portfolio.
- Each material stock, ETF, or fund announcement and corporate event.
- Overnight US/HK markets, rates, FX, commodities, and other cross-market drivers.
- Obvious but easy-to-miss risks, policy changes, and contradictory evidence.

Prefer official institutions, exchange filings, issuer/fund disclosures, reputable financial media, and institutional research. Cross-check important claims with two credible sources when possible. Label each claim as a confirmed fact, institution opinion, unverified report, or analyst inference; include source and publication time.

## Analysis rules

- Explain the impact on relevant holdings and whether the market may have priced it in.
- Include bull and bear cases, uncertainty, risk signals, and invalidation/observation triggers.
- Do not add a `今日建议` section. When a decision implication matters, express it as a conditional observation or follow-up trigger instead of an unconditional buy/sell command.
- Treat official NAV, stale, fallback, and QDII cross-market values according to their status. Never call them today's real-time move.
- Do not repeat the complete holdings table; the website package remains the canonical source.
- `fund_monitor.py` is retired. Never mention, run, or recommend it.

## Review format

Use the following structure. Do not replace the news section with a summary table as the primary format. Each news item needs a headline with a one-to-five-star importance marker and a short body.

```markdown
# 每日复盘

## YYYY-MM-DD

> 记录时间：YYYY-MM-DD HH:MM（注明收盘/盘中和数据口径）
> 数据性质：简述行情、基金净值、QDII、新闻的时间差和可靠性。

### 一、今日盘面涨跌情况（重点：我的持仓）
### 二、今日关键新闻
1. **新闻概况标题** ★★★★☆
   - 性质：已确认事实 / 机构观点 / 市场传闻 / 我的推断
   - 影响板块：板块、指数、相关持仓代码
   - 分析：为什么重要、是否已经被市场定价（可选）
### 三、AI 分析（今日股市为什么这样）
### 四、后续需留意的关键新闻 / 时点
| 时点 | 事件/指标 | 为什么重要或观察阈值 | 对应持仓 |
| --- | --- | --- | --- |
### 五、风险与触发条件
### 六、数据来源与限制
```

In the analysis section, explain market causes while distinguishing facts from inference. Use the knowledge base, portfolio exposure, capital flows, and macro variables when relevant. The upcoming-events table must contain concrete, verifiable dates or thresholds.

Keep the note concise and decision-oriented. Do not repeat the complete holdings table; the website package remains canonical. Use the `historical_review` section to carry forward unresolved items and previous triggers. There is no `今日建议` section; ask the Agent separately for personalized suggestions when needed.

## Append

Send JSON to `POST http://127.0.0.1:8000/api/agent/reviews/append`:

```json
{"analysis_date":"YYYY-MM-DD","content":"<markdown review>","run_id":"optional-run-id"}
```

The API writes UTF-8 directly to the configured current review file and rejects exact duplicate content. Report the returned path and whether the append was new or deduplicated.
