import { ExternalLink, ScanEye, Telescope } from "lucide-react";
import { useMemo } from "react";
import { useHoldings } from "../hooks/useHoldings";
import { useMarketIndices, useNews } from "../hooks/useMarketData";

export function Dashboard() {
  const holdingsQuery = useHoldings();
  const indicesQuery = useMarketIndices();
  const newsQuery = useNews(8);
  const holdings = holdingsQuery.data ?? [];
  const indices = indicesQuery.data ?? [];
  const news = newsQuery.data ?? [];
  const isLoading = holdingsQuery.isLoading || indicesQuery.isLoading || newsQuery.isLoading;
  const error = holdingsQuery.error ?? indicesQuery.error ?? newsQuery.error;

  function retry() {
    void Promise.allSettled([holdingsQuery.refetch(), indicesQuery.refetch(), newsQuery.refetch()]);
  }

  const orderedHoldings = useMemo(
    () => [...holdings].sort((a, b) => Number(b.amount || 0) - Number(a.amount || 0)),
    [holdings],
  );
  const total = useMemo(() => holdings.reduce((sum, row) => sum + Number(row.amount || 0), 0), [holdings]);
  const profit = useMemo(() => holdings.reduce((sum, row) => sum + Number(row.profit || 0), 0), [holdings]);

  return (
    <section className="observatoryView ledgerView">
      {isLoading && <div className="notice observatoryNotice">正在读取观测数据…</div>}
      {error && <div className="notice observatoryNotice"><span>{error instanceof Error ? error.message : "暂时无法读取观测数据"}</span><button className="refreshRetryButton" onClick={retry}>重新读取</button></div>}
      <div className="observatoryHero">
        <div className="observatoryMasthead">
          <div>
            <div className="kicker"><ScanEye size={14} /> 01 / INSTRUMENT</div>
            <h2>黄铜观测镜</h2>
            <p>暖光不是装饰，它标记了人的手：调焦、记录、复核，再把视线放回漫长的时间线上。</p>
          </div>
          <Telescope className="dashboardInstrument" aria-hidden="true" />
        </div>
        <aside className="fieldNote">
          <div className="fieldNoteOrbit" aria-hidden="true" />
          <p className="fieldNoteKicker">观测手记 · {observationDate()}</p>
          <h3>今日组合摘要</h3>
          <p>{holdingsQuery.data ? `当前记录 ${holdings.length} 项持仓。${orderedHoldings[0] ? `金额最大的持仓为${orderedHoldings[0].asset.name}。` : "可前往持仓页建立第一份档案。"}` : "等待持仓数据，暂不生成组合摘要。"}</p>
          <a href="#holdings">查看完整持仓档案</a>
          <span>数据状态 · {error ? "部分数据读取失败" : isLoading ? "读取中" : "本次读取完成"}</span>
        </aside>
      </div>

      <div className="ledgerMetrics">
        <Metric label="组合市值" value={`¥${total.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}`} />
        <Metric label="累计盈亏" value={`¥${profit.toFixed(2)}`} tone={profit >= 0 ? "up" : "down"} />
        <Metric label="观察中的资产" value={String(holdings.length)} />
        <Metric label="今日信号" value={String(news.length)} />
      </div>

      <div className="ledgerRule"><span>MARKET PULSE</span><div /></div>
      <div className="marketTape" aria-label="市场指数">
        {indices.length > 0 ? indices.map((item) => (
          <div className="marketTapeItem" key={item.code}>
            <span>{item.name}</span>
            <strong>{item.price?.toFixed(2) ?? "--"}</strong>
            <em className={tone(item.change_pct)}>{pct(item.change_pct)}</em>
          </div>
        )) : <div className="observatoryEmpty">暂无市场指数数据</div>}
      </div>

      <div className="ledgerColumns">
        <section className="ledgerBlock">
          <Heading index="01" label="PORTFOLIO" title="持仓档案" note="按当前金额排序" />
          <div className="ledgerTable">
            {orderedHoldings.length > 0 ? orderedHoldings.slice(0, 8).map((row, index) => (
              <div className="ledgerRow" key={row.id}>
                <span className="ledgerIndex">{String(index + 1).padStart(2, "0")}</span>
                <div className="ledgerAsset">
                  <strong>{row.asset.name}</strong>
                  <small>{row.asset.code} · {row.asset.asset_type}</small>
                </div>
                <strong className="ledgerAmount">¥{Number(row.amount).toFixed(2)}</strong>
                <span className={tone(row.profit == null ? null : Number(row.profit))}>{row.profit == null ? "--" : `¥${Number(row.profit).toFixed(2)}`}</span>
              </div>
            )) : <div className="observatoryEmpty">暂无持仓记录</div>}
          </div>
        </section>

        <section className="ledgerBlock">
          <Heading index="02" label="SIGNALS" title="外部线索" note="仅作研究入口" />
          <div className="ledgerNewsList">
            {news.length > 0 ? news.slice(0, 6).map((item) => (
              <a key={`${item.source}-${item.title}`} href={item.url || "#"} target="_blank" rel="noreferrer">
                <span>{item.source}</span>
                <strong>{item.title}</strong>
                <ExternalLink size={13} />
              </a>
            )) : <div className="observatoryEmpty">暂无新闻线索</div>}
          </div>
        </section>
      </div>
    </section>
  );
}

function Heading({ index, label, title, note }: { index: string; label: string; title: string; note: string }) {
  return <div className="blockHeading"><span>{index} / {label}</span><strong>{title}</strong><small>{note}</small></div>;
}

function Metric({ label, value, tone: color }: { label: string; value: string; tone?: "up" | "down" }) {
  return <div className="ledgerMetric"><span>{label}</span><strong className={color === "up" ? "upText" : color === "down" ? "downText" : ""}>{value}</strong></div>;
}

function observationDate() {
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" })
    .format(new Date())
    .replace(/\//g, ".");
}

function pct(value?: number | null) {
  return value == null ? "--" : `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function tone(value?: number | null) {
  return value == null ? "flatText" : value >= 0 ? "upText" : "downText";
}
