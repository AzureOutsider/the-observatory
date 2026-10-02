import { Check, Clipboard, Copy, ExternalLink, FilePlus2, RefreshCw, Search, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";
import { AGENT_ANALYSIS_PACKAGE_ENDPOINT, ReviewAppendResult } from "../api/client";
import { useAgentAnalysisPackage, useAppendReview } from "../hooks/useAgentData";
import { toast } from "sonner";

const skillCommand = "读取 investment-observatory-review Skill，获取今日分析包，主动检索外部新闻并追加复盘";

export function Agent() {
  const [topic, setTopic] = useState("AI");
  const [requestedTopic, setRequestedTopic] = useState("AI");
  const [review, setReview] = useState("");
  const [appendResult, setAppendResult] = useState<ReviewAppendResult | null>(null);
  const analysisQuery = useAgentAnalysisPackage(requestedTopic);
  const appendReviewMutation = useAppendReview();
  const context = analysisQuery.data ?? null;
  const loading = analysisQuery.isLoading || analysisQuery.isFetching;
  const appending = appendReviewMutation.isPending;

  function loadContext() {
    const nextTopic = topic.trim() || "AI";
    if (nextTopic === requestedTopic) {
      void analysisQuery.refetch();
      return;
    }
    setRequestedTopic(nextTopic);
  }

  const jsonText = useMemo(() => (context ? JSON.stringify(context, null, 2) : ""), [context]);
  const quality = context?.data_quality_summary;
  const history = context?.historical_review;

  async function copyText(value: string, label: string) {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      toast.success(`${label}已复制`, { className: "agentToast" });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "复制失败", { className: "agentToast" });
    }
  }

  async function appendReview() {
    if (!review.trim()) return;
    setAppendResult(null);
    try {
      const result = await appendReviewMutation.mutateAsync({
        analysis_date: context?.analysis_date ?? context?.date,
        content: review,
      });
      setAppendResult(result);
      if (result.appended) setReview("");
      toast.success(result.duplicate ? "检测到相同内容，未重复追加" : "已追加到复盘文件", { className: "agentToast" });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "追加失败", { className: "agentToast" });
    }
  }

  return (
    <section className="agentWorkbench">
      <section className="agentHero panel">
        <div><span className="eyebrow">OBSERVATORY / RESEARCH DESK</span><h2>分析工作台</h2><p>把网站事实、外部研究和复盘连续性放在同一张工作台上。</p></div>
        <div className="agentHeroActions"><label className="agentTopicField"><span>研究主题</span><input value={topic} onChange={(event) => setTopic(event.target.value)} onKeyDown={(event) => event.key === "Enter" && loadContext()} /></label><button className="primaryButton" onClick={() => loadContext()} disabled={loading}><RefreshCw size={16} className={loading ? "spin" : ""} />{loading ? "生成中" : "生成今日分析包"}</button></div>
      </section>

      {analysisQuery.error && <div className="notice agentErrorNotice" role="alert"><span>{analysisQuery.error instanceof Error ? analysisQuery.error.message : "暂时无法生成分析包"}</span><button className="refreshRetryButton" onClick={() => void analysisQuery.refetch()}>重新读取</button></div>}
      {loading && !context && <div className="notice" role="status">正在生成今日分析包…</div>}
      {context && <>
        <section className="agentMetricGrid">
          <div className="agentMetric panel"><span>持仓标的</span><strong>{context.private_portfolio.holding_count}</strong><small>总额 {context.private_portfolio.total_amount.toFixed(0)}</small></div>
          <div className="agentMetric panel"><span>内部新闻信号</span><strong>{context.internal_news_signals.length}</strong><small>仅作线索，需外部核验</small></div>
          <div className="agentMetric panel"><span>必检索方向</span><strong>{context.external_research.suggested_queries.length}</strong><small>供外部 Agent 主动检索</small></div>
          <div className="agentMetric panel"><span>不可用标的</span><strong>{quality?.status_counts?.unavailable ?? 0}</strong><small>数据质量提示</small></div>
        </section>

        <section className="agentGrid">
          <section className="panel agentControlPanel"><div className="sectionHeader"><div><span className="eyebrow">RUN CONTROL</span><h2>交付给外部 Agent</h2></div><ShieldCheck size={19} /></div><div className="agentEndpointBox"><span>分析包接口</span><code>{AGENT_ANALYSIS_PACKAGE_ENDPOINT}</code><button className="iconButton" title="复制接口地址" onClick={() => copyText(AGENT_ANALYSIS_PACKAGE_ENDPOINT, "接口地址")}><Copy size={15} /></button></div><div className="agentCommandBox"><span>Skill 工作流</span><p>{skillCommand}</p><button className="iconButton" title="复制 Skill 工作流" onClick={() => copyText(skillCommand, "工作流")}><Clipboard size={15} /></button></div><div className="agentFacts"><div><span>生成时间</span><strong>{context.generated_at ?? "-"}</strong></div><div><span>交易状态</span><strong>{context.market_snapshot.trading_status.message}</strong></div><div><span>数据规则</span><strong>{quality?.manual_refresh_required ? "以最近刷新为准" : "自动更新"}</strong></div></div></section>
          <section className="panel agentContinuityPanel"><div className="sectionHeader"><div><span className="eyebrow">REVIEW CONTINUITY</span><h2>复盘连续性</h2></div><ExternalLink size={18} /></div><div className="continuityPath">{history?.path ?? "-"}</div><div className="continuityDates">{history?.recent_dates?.length ? history.recent_dates.map((date) => <span key={date}>{date}</span>) : <span>尚无历史日期</span>}</div><div className="continuityColumns"><div><span>待验证事项</span><strong>{history?.open_items?.length ?? 0}</strong></div><div><span>后续关注 / 触发条件</span><strong>{history?.follow_up_items?.length ?? history?.triggers?.length ?? 0}</strong></div></div></section>
        </section>

        <section className="panel wide agentResearchPanel"><div className="sectionHeader"><div><span className="eyebrow">RESEARCH QUEUE</span><h2>外部检索任务</h2><span>内部新闻只是起点，重要事实请交叉验证。</span></div><Search size={19} /></div><div className="researchColumns"><div><h3>推荐检索词</h3><div className="queryList">{context.external_research.suggested_queries.map((query) => <button key={query} onClick={() => copyText(query, "检索词")}>{query}</button>)}</div></div><div><h3>来源优先级</h3><div className="denseList">{context.external_research.source_priority.map((source) => <div className="listRow stacked" key={source.type}><span>{source.type}</span><small>{source.examples.join(" / ")}</small></div>)}</div></div></div></section>

        <section className="panel wide agentAppendPanel"><div className="sectionHeader"><div><span className="eyebrow">DIRECT APPEND</span><h2>追加复盘</h2><span>外部 Agent 生成 Markdown 后，可直接写入当前复盘文件。</span></div><FilePlus2 size={19} /></div><label className="agentReviewField"><span>复盘正文 <small>Markdown 格式</small></span><textarea value={review} onChange={(event) => setReview(event.target.value)} placeholder={"# 每日复盘\n\n## " + (context.analysis_date ?? context.date) + "\n\n### 一、今日结论\n"} rows={8} /></label><div className="appendFooter"><span>{history?.path ?? "复盘路径未加载"}</span><button className="primaryButton" onClick={appendReview} disabled={appending || !review.trim()}><Check size={16} />{appending ? "写入中" : "直接追加"}</button></div>{appendResult && <div className={appendResult.duplicate ? "notice" : "successNotice"} role="status">{appendResult.duplicate ? "检测到相同内容，未重复追加。" : "已追加到复盘文件。"} <code>{appendResult.path}</code></div>}</section>

        <section className="panel wide agentPayloadPanel"><div className="sectionHeader"><div><span className="eyebrow">COMPATIBILITY</span><h2>原始载荷</h2><span>兼容仍需手动粘贴 JSON 的外部流程。</span></div><div className="buttonCluster"><button className="iconButton" onClick={() => copyText(context.agent_prompt, "Prompt")}><Copy size={15} />Prompt</button><button className="iconButton" onClick={() => copyText(jsonText, "JSON")}><Copy size={15} />JSON</button></div></div><pre className="jsonBox">{jsonText}</pre></section>
      </>}
    </section>
  );
}
