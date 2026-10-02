# Agent 分析工作流

观象台采用“网站提供事实，外部 Agent 负责研究和判断”的半自动流程。Skill 只保存分析方法与输出约束，不保存动态持仓、行情或新闻。

## 1. 获取分析包

```text
GET http://127.0.0.1:8000/api/agent/analysis-package/today
```

可选 `topic` 查询参数。返回包包含：

- `private_portfolio`：持仓事实、权重、最近交易和知识片段。
- `market_snapshot`：行情、交易状态、来源和时间。
- `internal_news_signals`：网站新闻接口提供的线索，不代表完整覆盖。
- `historical_review`：当前复盘文件最近日期、待验证事项和触发条件摘要。
- `external_research`：必须主动检索的方向、来源优先级、检索词和核验规则。
- `data_quality_summary`：行情状态统计和刷新限制。
- `analysis_contract`：输出章节与风险护栏。

旧的 `GET /api/agent/research-context/today` 保留用于兼容。

新闻接口默认使用本地 SQLite 缓存，只有用户或调用方显式传 `refresh=true` 才请求上游。当前适配器包括新浪财经、华尔街见闻和美联储公开 Press Releases RSS，每条新闻包含来源、发布时间、抓取时间、重要度、摘要（若来源提供）和质量状态；外部 Agent 仍必须主动检索完整新闻。

## 2. 外部研究与写作

可使用项目 Skill [investment-observatory-review](../.agents/skills/investment-observatory-review/SKILL.md)。Agent 必须搜索 A 股与政策、持仓行业和标的事件、隔夜美港市场及利率汇率商品等外部信息，并区分事实、观点、未证实消息与推断。复盘不重复完整持仓表。

复盘 Markdown 采用以下结构。新闻使用“概况标题 + 星级 + 正文标签”，而不是只输出一张摘要表：

```markdown
# 每日复盘
## YYYY-MM-DD
### 一、今日盘面涨跌情况（重点：我的持仓）
### 二、今日关键新闻
1. **新闻概况标题** ★★★★☆
   - 性质：已确认事实 / 机构观点 / 市场传闻 / 我的推断
   - 影响板块：板块、指数、相关持仓代码
   - 分析：可选
### 三、AI 分析（今日股市为什么这样）
### 四、后续需留意的关键新闻 / 时点
| 时点 | 事件/指标 | 为什么重要或观察阈值 | 对应持仓 |
| --- | --- | --- | --- |
### 五、风险与触发条件
### 六、数据来源与限制
```

不再生成“今日建议”章节；需要具体建议时，单独向 Agent 追问。

## 3. 直接追加

```text
POST http://127.0.0.1:8000/api/agent/reviews/append
Content-Type: application/json
```

```json
{
  "analysis_date": "YYYY-MM-DD",
  "content": "<markdown review>",
  "run_id": "optional-run-id"
}
```

接口以 UTF-8 追加到 `FINANCE_REVIEW_PATH` 指向的文件，自动创建目录和文件。返回 `appended`、`duplicate`、`path` 和内容指纹；完全相同内容的重试不会重复写入。这里没有人工审核队列或副本，便于外部 Agent 直接完成每日记录。
