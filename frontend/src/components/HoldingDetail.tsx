import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { Holding } from "../api/client";
import { useHoldingTransactions } from "../hooks/useHoldings";
import { formatMoney } from "../lib/utils";

const operationLabels: Record<string, string> = { buy: "买入", sell: "卖出", dividend: "分红", transfer: "转入", adjustment: "调整", note: "备注" };

export function HoldingDetail({ holding, onClose }: { holding: Holding; onClose: () => void }) {
  const { data: rows = [], isLoading, isError, error, refetch } = useHoldingTransactions(holding.id);
  const dialogRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key !== "Tab") return;
      const controls = dialogRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), [tabindex="0"]');
      if (!controls?.length) return;
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, [onClose]);

  const activeRows = rows.filter((row) => !row.retracted_at);
  const buyTotal = activeRows.filter((row) => row.operation === "buy").reduce((sum, row) => sum + Number(row.amount), 0);
  const sellTotal = activeRows.filter((row) => row.operation === "sell").reduce((sum, row) => sum + Number(row.amount), 0);

  return createPortal(
    <div className="holdingEditorBackdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section ref={dialogRef} className="holdingEditor holdingDetail" role="dialog" aria-modal="true" aria-labelledby="holding-detail-title" aria-describedby="holding-detail-note">
        <div className="holdingEditorHeader">
          <div><span className="kicker">POSITION HISTORY</span><h2 id="holding-detail-title">{holding.asset.custom_name || holding.asset.name}</h2><p>{holding.asset.code} · 持仓操作详情</p></div>
          <button ref={closeRef} className="modalCloseButton" onClick={onClose} aria-label="关闭持仓详情"><X size={17} aria-hidden="true" /></button>
        </div>
        <div className="holdingDetailSummary">
          <div><span>持有份额</span><strong>{number(holding.units, 2)}</strong></div>
          <div><span>当前成本</span><strong>{holding.cost_basis == null ? "--" : formatMoney(Number(holding.cost_basis))}</strong></div>
        </div>
        <p id="holding-detail-note" className="holdingEditorNotice">按交易日期从近到远显示已记录的操作，包含撤回记录。导入持仓和手动修正不生成买卖流水。</p>
        {holding.last_manual_adjustment_at && <p className="holdingDetailAudit">最近持仓修正：{holding.last_manual_adjustment_at.replace("T", " ")} · {holding.last_manual_adjustment_reason || "未注明原因"}</p>}
        {isLoading ? <p role="status">正在读取操作记录…</p> : isError ? <div className="notice holdingDetailError" role="alert"><span>{error instanceof Error ? error.message : "操作记录读取失败"}</span><button className="secondaryButton" onClick={() => void refetch()}>重新读取</button></div> : rows.length === 0 ? <div className="holdingsEmpty">暂无该标的的操作记录。在“操作”页录入后会显示在这里。</div> : <>
          <p className="holdingDetailTotals">已记录 {activeRows.length} 笔有效操作 · 买入支出 {formatMoney(buyTotal)} · 卖出到账 {formatMoney(sellTotal)}（不含撤回记录）</p>
          <div className="holdingDetailTableWrap" tabIndex={0} role="region" aria-label="该标的操作记录，可横向滚动">
            <table className="holdingDetailTable">
              <thead><tr><th>交易日期</th><th>操作</th><th className="numberCell">价格（元）</th><th className="numberCell">份额</th><th className="numberCell">手续费（元）</th><th className="numberCell">金额（元）</th><th>记录与复盘</th></tr></thead>
              <tbody>{rows.map((row) => <tr key={row.id} className={row.retracted_at ? "holdingDetailRetracted" : ""}>
                <td>{row.trade_date}</td><td><span className={`holdingDetailOperation ${row.operation}`}>{operationLabels[row.operation] || row.operation}</span>{row.retracted_at && <small>已撤回</small>}</td>
                <td className="numberCell">{number(row.price, 6)}</td><td className="numberCell">{number(row.units, 2)}</td><td className="numberCell">{number(row.fee, 4)}</td>
                <td className="numberCell">{number(row.amount, 4)}<small>{row.operation === "sell" ? "扣费后到账" : row.operation === "buy" ? "含手续费支出" : "记录金额"}</small></td>
                <td className="holdingDetailReason">{row.reason || "--"}{row.retracted_at && <small>撤回时间：{row.retracted_at.replace("T", " ")} · {row.retraction_reason || "未注明原因"}</small>}</td>
              </tr>)}</tbody>
            </table>
          </div>
        </>}
      </section>
    </div>, document.body,
  );
}

function number(value: string | null | undefined, precision: number) {
  return value == null ? "--" : Number(value).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: precision });
}
