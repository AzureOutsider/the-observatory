import { FormEvent, useState } from "react";
import { createPortal } from "react-dom";
import { type CSSProperties, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Activity, Pencil, Repeat2, Trash2 } from "lucide-react";
import { Holding, Transaction } from "../api/client";
import { HoldingEditor } from "../components/HoldingEditor";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Skeleton } from "../components/ui/skeleton";
import { useHoldings } from "../hooks/useHoldings";
import { useCreateTransaction, useRetractTransaction, useTransactions } from "../hooks/useTransactions";
import { toast } from "sonner";

const operationLabels: Record<string, string> = { buy: "买入", sell: "卖出", dividend: "分红", transfer: "转入", adjustment: "调整", note: "备注" };

export function Transactions() {
  const { data: rows = [], isLoading: transactionsLoading, isError: transactionsError, error: transactionsErrorDetail, refetch: refetchTransactions } = useTransactions();
  const { data: holdings = [] } = useHoldings();
  const createTransaction = useCreateTransaction();
  const retractTransaction = useRetractTransaction();
  const [editing, setEditing] = useState<Holding | null>(null);
  const [pendingRetraction, setPendingRetraction] = useState<Transaction | null>(null);
  const tableWrapRef = useRef<HTMLDivElement>(null);
  const virtualized = rows.length > 100;
  const rowVirtualizer = useVirtualizer({
    count: virtualized ? rows.length : 0,
    getScrollElement: () => tableWrapRef.current,
    estimateSize: () => 130,
    overscan: 8,
  });

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (createTransaction.isPending) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      await createTransaction.mutateAsync({
        asset_code: readFormValue(form, "asset_code"), asset_type: readFormValue(form, "asset_type") || "fund", asset_name: readOptionalFormValue(form, "asset_name"),
        operation: readFormValue(form, "operation"), trade_date: readFormValue(form, "trade_date"), amount: readFormValue(form, "amount"), units: readOptionalFormValue(form, "units"),
        price: readOptionalFormValue(form, "price"), fee: readFormValue(form, "fee") || "0", reason: readOptionalFormValue(form, "reason"),
      });
      formElement.reset();
      toast.success("操作已记录，持仓已同步", { className: "transactionToast" });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "记录失败，请稍后重试", { className: "transactionToast" });
    }
  }

  async function confirmRetraction() {
    if (!pendingRetraction || retractTransaction.isPending) return;
    try {
      await retractTransaction.mutateAsync(pendingRetraction.id);
      toast.success("流水已撤回，持仓已同步", { className: "transactionToast" });
      setPendingRetraction(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "撤回失败，请稍后重试", { className: "transactionToast" });
    }
  }

  return (
    <section className="transactionsView">
      {transactionsError && (
        <div className="notice observatoryNotice">
          <span>{transactionsErrorDetail instanceof Error ? transactionsErrorDetail.message : "暂时无法读取操作数据"}</span>
          <button className="refreshRetryButton" onClick={() => void refetchTransactions()}>重新读取</button>
        </div>
      )}
      <div className="transactionsIntro">
        <div><div className="kicker"><Repeat2 size={14} /> ACTIVITY REGISTER</div><h2>操作与持仓维护</h2><p>记录交易事实，或在对账后直接修正当前持仓快照。</p></div>
        <div className="transactionsStamp"><Activity size={18} /><span>{rows.length} 条流水</span></div>
      </div>
      <div className="pageGrid transactionsGrid">
        <form className="panel formPanel" onSubmit={submit}>
          <div className="sectionHeader"><div><h2>快捷记录</h2></div><span>新增一条操作事实 · 标注“必填”的项目不能为空</span></div>
          <div className="formGrid">
            <label><span>标的代码 <small>必填</small></span><input name="asset_code" placeholder="例如：000001" required /></label>
            <label><span>标的名称 <small>选填</small></span><input name="asset_name" placeholder="填写标的名称" /></label>
            <label><span>标的类型</span><select name="asset_type" defaultValue="fund"><option value="fund">基金</option><option value="stock">股票</option><option value="index">指数</option></select></label>
            <label><span>操作类型</span><select name="operation" defaultValue="buy"><option value="buy">买入</option><option value="sell">卖出</option><option value="dividend">分红</option><option value="transfer">转入</option><option value="adjustment">调整</option><option value="note">备注</option></select></label>
            <label><span>交易日期 <small>必填</small></span><input name="trade_date" type="date" required /></label>
            <label><span>金额（元） <small>必填</small></span><input name="amount" type="number" min="0" step="0.01" placeholder="0.00" required /></label>
            <label><span>份额 <small>选填 · 最多两位小数</small></span><input name="units" type="number" min="0" step="0.01" placeholder="0.00" /></label>
            <label><span>价格（元） <small>选填</small></span><input name="price" type="number" min="0" step="0.000001" placeholder="0.000000" /></label>
            <label><span>手续费（元） <small>选填</small></span><input name="fee" type="number" min="0" step="0.01" placeholder="默认为 0.00" /></label>
            <label className="transactionReasonField"><span>记录与复盘 <small>选填</small></span><textarea name="reason" placeholder="记录这次操作的理由、相关信息或交易纪律" /></label>
          </div>
          <button className="primaryButton" type="submit" disabled={createTransaction.isPending}><Repeat2 size={15} />{createTransaction.isPending ? "记录中…" : "记录操作"}</button>
        </form>

        <section className="panel transactionHistoryPanel wide">
          <div className="sectionHeader"><div><h2>操作流水</h2></div><span>{rows.length} 条记录，按日期倒序</span></div>
          <div ref={tableWrapRef} className={`transactionTableWrap ${virtualized ? "virtualTableWrap" : ""}`} tabIndex={0} role="region" aria-label="操作流水表，可横向滚动查看全部列"><table className="transactionTable"><thead><tr><th>日期</th><th>标的</th><th>动作</th><th>金额</th><th>份额 / 价格</th><th>备注 / 审计</th><th aria-label="操作" /></tr></thead>{transactionsLoading ? <tbody><TransactionLoadingRows /></tbody> : virtualized ? <tbody className="virtualTableBody" style={{ height: rowVirtualizer.getTotalSize() }}>{rowVirtualizer.getVirtualItems().map((virtualRow) => <TransactionRow key={rows[virtualRow.index].id} row={rows[virtualRow.index]} onRetract={() => setPendingRetraction(rows[virtualRow.index])} disabled={retractTransaction.isPending} deleting={retractTransaction.isPending && retractTransaction.variables === rows[virtualRow.index].id} virtualStyle={{ transform: `translateY(${virtualRow.start}px)` }} measureRef={rowVirtualizer.measureElement} index={virtualRow.index} />)}</tbody> : <tbody>{rows.map((row) => <TransactionRow key={row.id} row={row} onRetract={() => setPendingRetraction(row)} disabled={retractTransaction.isPending} deleting={retractTransaction.isPending && retractTransaction.variables === row.id} />)}</tbody>}</table>{!transactionsLoading && rows.length === 0 && <div className="holdingsEmpty">暂无操作流水，可在上方记录第一条操作。</div>}</div>
        </section>

        <section className="panel correctionPanel wide">
          <div className="sectionHeader"><div><h2>持仓修正</h2></div><span>对账后快速更新</span></div>
          <div className="correctionList">
            {holdings.length > 0 ? holdings.map((holding) => <div className="correctionRow" key={holding.id}><div className="correctionIdentity"><strong title={holding.asset.name}>{holding.asset.name}</strong><small>{holding.asset.code} · 当前金额 ¥{Number(holding.amount).toFixed(2)}</small></div><button className="iconButton compactAction" type="button" onClick={() => setEditing(holding)} title={`修正${holding.asset.name}`}><Pencil size={14} /><span>编辑</span></button></div>) : <div className="observatoryEmpty">暂无持仓可修正</div>}
          </div>
          <p className="panelFootnote">修正只影响当前持仓数据，不会改变操作流水。</p>
        </section>
      </div>
      {editing && <HoldingEditor holding={editing} onClose={() => setEditing(null)} onSaved={() => setEditing(null)} />}
      {createPortal(<div className="transactionDialogScope"><ConfirmDialog open={pendingRetraction !== null} title="撤回操作流水" description={pendingRetraction ? `确定撤回这条${operationLabels[pendingRetraction.operation] ?? pendingRetraction.operation}流水吗？关联持仓会同步反向调整。` : ""} confirmLabel="撤回流水" danger busy={retractTransaction.isPending} onCancel={() => setPendingRetraction(null)} onConfirm={confirmRetraction} /></div>, document.body)}
    </section>
  );
}

function readFormValue(form: FormData, name: string) {
  const value = form.get(name);
  return typeof value === "string" ? value : "";
}

function readOptionalFormValue(form: FormData, name: string) {
  const value = readFormValue(form, name).trim();
  return value ? value : undefined;
}

function TransactionLoadingRows() {
  return Array.from({ length: 5 }, (_, index) => (
    <tr key={`transaction-loading-${index}`} aria-hidden="true">
      <td><Skeleton className="h-4 w-20" /></td>
      <td><Skeleton className="h-5 w-28" /><Skeleton className="mt-2 h-3 w-16" /></td>
      <td><Skeleton className="h-6 w-14" /></td>
      <td><Skeleton className="h-4 w-20" /></td>
      <td><Skeleton className="h-4 w-28" /></td>
      <td><Skeleton className="h-4 w-32" /></td>
      <td><Skeleton className="h-8 w-14" /></td>
    </tr>
  ));
}

function TransactionRow({ row, onRetract, disabled, deleting, virtualStyle, measureRef, index }: { row: Transaction; onRetract: () => void; disabled: boolean; deleting: boolean; virtualStyle?: CSSProperties; measureRef?: (element: Element | null) => void; index?: number }) {
  const style = virtualStyle ? { position: "absolute", top: 0, left: 0, width: "100%", display: "table", tableLayout: "fixed", ...virtualStyle } as CSSProperties : undefined;
  return <tr className={row.retracted_at ? "retractedTransaction" : undefined} ref={measureRef} data-index={index} style={style}>
    <td>{row.trade_date}</td>
    <td><strong>{row.asset.name}</strong><small>{row.asset.code}</small></td>
    <td><span className={`operationBadge ${operationLabels[row.operation] ? row.operation : ""}`}>{operationLabels[row.operation] ?? row.operation}</span></td>
    <td className="numberCell">¥{Number(row.amount).toFixed(2)}</td>
    <td className="mutedCell">{row.units == null ? "--" : Number(row.units).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}{row.price == null ? "" : ` · ¥${Number(row.price).toFixed(4)}`}</td>
    <td className="reasonCell">{row.retracted_at ? <><span className="retractedBadge">已撤回</span><small>撤回于 {formatAuditTime(row.retracted_at)}</small><small>{row.retraction_reason || "用户手动撤回"}</small><small>{formatRetractionEffect(row.retraction_effect)}</small></> : row.reason || "--"}</td>
    <td>{row.retracted_at ? <span className="retractedLabel">不可再次撤回</span> : <button className="retractButton" type="button" onClick={onRetract} disabled={disabled} title={`撤回${row.asset.name}这条流水`}><Trash2 size={14} /><span>{deleting ? "撤回中" : "撤回"}</span></button>}</td>
  </tr>;
}

function formatAuditTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
}

function formatRetractionEffect(value?: string | null) {
  if (!value) return "持仓影响：无记录";
  try {
    const effect = JSON.parse(value) as { amount_before?: string; amount_after?: string; units_before?: string | null; units_after?: string | null };
    return `持仓 ¥${Number(effect.amount_before || 0).toFixed(2)} → ¥${Number(effect.amount_after || 0).toFixed(2)}`;
  } catch {
    return "持仓影响已记录";
  }
}
