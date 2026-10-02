---
name: investment-research-analysis
description: Analyze markets, sectors, themes, stocks, ETFs, and funds with sourced data/news research, scenario-based outlooks, and a structured Markdown report. Use for requests about any market or sector such as grain, commercial aerospace, technology, energy, or healthcare; do not use for unattended trade execution.
---

# Investment Research Analysis

Produce a decision-oriented research note for the requested market, sector/theme, instruments, and time horizon. The report is research support, not personalized financial advice. Never turn an LLM opinion into an automatic order.

## Workflow

1. Clarify the scope from the request. Record the market/region, sector or theme, named securities or ETFs, analysis date, and horizon. If an item is missing, state a reasonable assumption in the report.
2. Search current information before drawing conclusions. Prefer primary sources relevant to the subject: statistical agencies, regulators, exchanges, company filings, fund/ETF issuer disclosures, industry associations, international organisations, and official product or policy documents. Use reputable financial media only as secondary coverage.
3. Build a timestamped evidence set. For every material number or event, record publication time, observation period, source URL, and whether it is a fact, institution view, market report, or analyst inference. Cross-check important claims with two independent credible sources when practical.
4. Analyze the market, sector, or theme in layers:
   - **Macro and policy:** relevant regulation, fiscal/industrial policy, inflation, rates, FX, energy, commodities, and geopolitics.
   - **Industry economics:** demand, capacity, pricing power, competition, supply chain, technology cycle, and relevant operating indicators.
   - **Price and positioning:** spot/futures or market-price structure, seasonality, volatility, open interest or fund flows where available, and relative performance versus broad indices.
   - **Equities and funds:** earnings sensitivity, margins, inventory cycle, balance-sheet risk, index methodology, holdings concentration, tracking error, fees, liquidity, premium/discount to NAV, and trading rules.
5. Produce an outlook for the requested horizon using three conditional scenarios (base, upside, downside). Use directional language and probability ranges only when supported by evidence. State the assumptions, leading indicators, invalidation conditions, and what is already priced in. Do not give an unconditional buy/sell command or a precise price target without a defensible valuation method.
6. Perform a quality and risk pass: flag stale or revised data, mixed units/currencies, different industry taxonomies, survivorship/look-ahead bias, source scraping instability, ETF NAV lag, and material event uncertainty.
7. Write the result as UTF-8 Markdown. Default path: `reports/investment-research/YYYY-MM-DD-<topic>-analysis.md`; use a filesystem-safe topic slug. Create the directory if needed. Do not overwrite an existing report without explicit instruction; use a versioned filename such as `-v2` when a same-day rerun is required.

## Required report sections

Read [references/report-template.md](references/report-template.md) before writing the report. Keep the report concise but complete and include:

- Executive conclusion and data cutoff
- Market/sector snapshot with comparable metrics
- Supply-demand and policy drivers
- News and event table with source, time, classification, and relevance
- Stock/ETF/fund analysis for each requested instrument
- Base/upside/downside scenarios and forecast horizon
- Risks, invalidation conditions, and watchlist triggers
- Data limitations and full source list

Use tables for comparable metrics and event timelines. Every forward-looking statement must identify its assumption and a measurable observation trigger.
