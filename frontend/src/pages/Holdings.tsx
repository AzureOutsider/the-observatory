import { Pencil, WalletCards } from "lucide-react";
import { type CSSProperties, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Holding } from "../api/client";
import { HoldingEditor } from "../components/HoldingEditor";
import { Skeleton } from "../components/ui/skeleton";
import { useHoldings } from "../hooks/useHoldings";
import { formatMoney } from "../lib/utils";

const typeLabels: Record<string, string> = { fund: "基金", stock: "股票", index: "指数" };

export function Holdings() {
  const { data: rows = [], isLoading, isError, error, refetch } = useHoldings();
  const [editing, setEditing] = useState<Holding | null>(null);
  const tableWrapRef = useRef<HTMLDivElement>(null);

  const summary = useMemo(() => {
    const total = rows.reduce((sum, row) => sum + Number(row.amount || 0), 0);
    const profit = rows.reduce((sum, row) => sum + Number(row.profit || 0), 0);
    const largest = rows.reduce((max, row) => Math.max(max, Number(row.amount || 0)), 0);
    return { total, profit, largestWeight: total > 0 ? largest / total : 0 };
  }, [rows]);
  const virtualized = rows.length > 100;
  const rowVirtualizer = useVirtualizer({
    count: virtualized ? rows.length : 0,
    getScrollElement: () => tableWrapRef.current,
    estimateSize: () => 150,
    overscan: 8,
  });

  return (
    <section className="observatoryView holdingsView">
      {isError && (
        <div className="notice observatoryNotice">
          <span>{error instanceof Error ? error.message : "暂时无法读取持仓"}</span>
          <button className="refreshRetryButton" onClick={() => void refetch()}>重新读取</button>
        </div>
      )}
      <div className="holdingsMasthead">
        <div>
          <div className="kicker"><WalletCards size={14} /> PORTFOLIO REGISTER</div>
          <h2>当前持仓档案</h2>
          <p>以最新人工核对的数据为准，集中查看组合规模与风险暴露。</p>
        </div>
        <div className="holdingsStamp"><span>BOOK</span><strong>{String(rows.length).padStart(2, "0")}</strong></div>
      </div>

      <div className="holdingsMetrics">
        <Metric label="组合市值" value={formatMoney(summary.total)} />
        <Metric label="累计盈亏" value={formatMoney(summary.profit)} tone={summary.profit >= 0 ? "up" : "down"} />
        <Metric label="持仓标的" value={`${rows.length} 个`} />
        <Metric label="最大单项权重" value={`${(summary.largestWeight * 100).toFixed(1)}%`} />
      </div>

      <div className="holdingsRule"><span>POSITION LEDGER</span><div /></div>
      <div ref={tableWrapRef} className={`holdingsTableWrap ${virtualized ? "virtualTableWrap" : ""}`} tabIndex={0} role="region" aria-label="持仓明细表，可横向滚动查看全部列">
        <table className="holdingsTable">
          <thead><tr><th>标的</th><th>类型</th><th>组合权重</th><th>当前金额</th><th>持有份额</th><th>成本金额</th><th>当前盈亏</th><th aria-label="操作" /></tr></thead>
          {isLoading ? <tbody><LoadingRows /></tbody> : virtualized ? <tbody className="virtualTableBody" style={{ height: rowVirtualizer.getTotalSize() }}>{rowVirtualizer.getVirtualItems().map((virtualRow) => <HoldingRow key={rows[virtualRow.index].id} row={rows[virtualRow.index]} summaryTotal={summary.total} onEdit={() => setEditing(rows[virtualRow.index])} virtualStyle={{ transform: `translateY(${virtualRow.start}px)` }} measureRef={rowVirtualizer.measureElement} index={virtualRow.index} />)}</tbody> : <tbody>{rows.map((row) => <HoldingRow key={row.id} row={row} summaryTotal={summary.total} onEdit={() => setEditing(row)} />)}</tbody>}
        </table>
        {!isLoading && rows.length === 0 && <div className="holdingsEmpty">暂无持仓记录，请先在“操作”页记录或导入持仓。</div>}
      </div>
      <div className="holdingsFooter">最后读取：{new Date().toLocaleString("zh-CN", { hour12: false })}<span>金额与盈亏可在此页或操作页直接修正</span></div>
      {editing && <HoldingEditor holding={editing} onClose={() => setEditing(null)} onSaved={() => setEditing(null)} />}
    </section>
  );
}

function HoldingRow({ row, summaryTotal, onEdit, virtualStyle, measureRef, index }: { row: Holding; summaryTotal: number; onEdit: () => void; virtualStyle?: CSSProperties; measureRef?: (element: Element | null) => void; index?: number }) {
  const amount = Number(row.amount || 0);
  const weight = summaryTotal > 0 ? amount / summaryTotal : 0;
  const profit = row.profit == null ? null : Number(row.profit);
  const style = virtualStyle ? { position: "absolute", top: 0, left: 0, width: "100%", display: "table", tableLayout: "fixed", ...virtualStyle } as CSSProperties : undefined;
  return <tr ref={measureRef} data-index={index} style={style} key={row.id}>
    <td><div className="holdingIdentity"><strong title={row.asset.name}>{row.asset.name}</strong><small>{row.asset.code}</small><small className="holdingAudit">收盘估值：{formatAuditTime(row.last_valuation_at)} · {row.last_valuation_source || "暂无记录"}</small><small className={`holdingAudit ${row.manual_adjusted ? "manual" : ""}`}>{row.manual_adjusted ? `手动修正：${formatAuditTime(row.last_manual_adjustment_at)}` : "未手动修正"}</small></div></td>
    <td><span className="assetTypeBadge">{typeLabels[row.asset.asset_type] ?? row.asset.asset_type}</span></td>
    <td><div className="weightCell"><span>{(weight * 100).toFixed(1)}%</span><i><b style={{ width: `${Math.min(weight * 100, 100)}%` }} /></i></div></td>
    <td className="numberCell">{formatMoney(amount)}</td>
    <td className="numberCell">{row.units == null ? "--" : Number(row.units).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
    <td className="numberCell">{row.cost_basis == null ? "--" : formatMoney(Number(row.cost_basis))}</td>
    <td className={`holdingProfit numberCell ${profit == null ? "flatText" : profit >= 0 ? "upText" : "downText"}`}>{profit == null ? "--" : <><strong>{formatMoney(profit)}</strong><small>{formatProfitRate(row, amount, profit)}</small></>}</td>
    <td><button className="iconButton compactAction" onClick={onEdit} title={`修正${row.asset.name}`}><Pencil size={14} /><span>修正</span></button></td>
  </tr>;
}

function LoadingRows() {
  return Array.from({ length: 5 }, (_, index) => (
    <tr key={`holding-loading-${index}`} aria-hidden="true">
      <td><Skeleton className="h-5 w-44" /><Skeleton className="mt-2 h-3 w-20" /></td>
      <td><Skeleton className="h-6 w-12" /></td>
      <td><Skeleton className="h-4 w-24" /></td>
      <td><Skeleton className="h-4 w-24" /></td>
      <td><Skeleton className="h-4 w-20" /></td>
      <td><Skeleton className="h-4 w-24" /></td>
      <td><Skeleton className="h-4 w-20" /></td>
      <td><Skeleton className="h-8 w-14" /></td>
    </tr>
  ));
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: "up" | "down" }) {
  return <div className="holdingsMetric"><span>{label}</span><strong className={tone === "up" ? "upText" : tone === "down" ? "downText" : ""}>{value}</strong></div>;
}

function formatProfitRate(row: Holding, amount: number, profit: number) {
  const explicitCost = row.cost_basis == null ? null : Number(row.cost_basis);
  const estimatedCost = explicitCost != null && explicitCost > 0 ? explicitCost : amount - profit;
  if (!Number.isFinite(estimatedCost) || estimatedCost <= 0) return "比例待补充";
  return `${profit >= 0 ? "+" : ""}${((profit / estimatedCost) * 100).toFixed(2)}%`;
}

function formatAuditTime(value?: string | null) {
  if (!value) return "暂无";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
}
