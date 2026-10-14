import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Activity, FlaskConical, History, Plus, Trash2, X } from "lucide-react";
import { PaperPosition, PaperTrade } from "../api/client";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { toast } from "sonner";
import { usePaperHistory, usePaperPortfolio, usePaperQuotes, usePaperTrade, useRefreshPaperQuotes, useRetractPaperTrade } from "../hooks/usePaperTrading";
import { formatMoney } from "../lib/utils";

const operationLabels: Record<string, string> = { buy: "模拟买入", sell: "模拟卖出" };
const assetTypeLabels: Record<string, string> = { fund: "基金", stock: "股票" };

function localDate() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
}

export function PaperTrading() {
  const portfolioQuery = usePaperPortfolio();
  const rows = portfolioQuery.data ?? [];
  const createTrade = usePaperTrade();
  const refreshQuotes = useRefreshPaperQuotes();
  const retractTrade = useRetractPaperTrade();
  const [operation, setOperation] = useState<"buy" | "sell">("buy");
  const [tradeDate, setTradeDate] = useState(localDate);
  const [units, setUnits] = useState("");
  const [price, setPrice] = useState("");
  const [fee, setFee] = useState("0.1");
  const [assetCode, setAssetCode] = useState("");
  const [assetName, setAssetName] = useState("");
  const [assetType, setAssetType] = useState<"fund" | "stock">("fund");
  const [detailId, setDetailId] = useState<number | null>(null);
  const [pendingRetraction, setPendingRetraction] = useState<PaperTrade | null>(null);
  const [tradeError, setTradeError] = useState<string | null>(null);
  const tradeErrorRef = useRef<HTMLDivElement>(null);
  const pendingTradeKey = useRef<{ signature: string; key: string } | null>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const detail = rows.find((row) => row.id === detailId) ?? null;
  const closeDetail = useCallback(() => setDetailId(null), []);
  const isSell = operation === "sell";
  const calculatedAmount = Number(units) * Number(price) + (isSell ? -1 : 1) * Number(fee || "0");
  const amountPreview = units && price && Number.isFinite(calculatedAmount) ? formatMoney(calculatedAmount) : "--";
  const summary = useMemo(() => ({
    ideaCount: rows.length,
    openCount: rows.filter((row) => row.is_open).length,
    realized: rows.reduce((total, row) => total + Number(row.realized_profit || 0), 0),
    unrealized: rows.reduce((total, row) => total + Number(row.unrealized_profit || 0), 0),
    unvaluedCount: rows.filter((row) => row.is_open && row.market_value == null).length,
  }), [rows]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (createTrade.isPending) return;
    setTradeError(null);
    const form = new FormData(event.currentTarget);
    const payload = {
      asset_code: assetCode.trim(),
      asset_name: assetName.trim(),
      asset_type: assetType,
      operation,
      trade_date: tradeDate,
      units: units.trim(),
      price: price.trim(),
      fee: fee.trim() || "0",
      reason: formValue(form, "reason").trim() || undefined,
    };
    const signature = JSON.stringify(payload);
    if (pendingTradeKey.current?.signature !== signature) {
      pendingTradeKey.current = { signature, key: crypto.randomUUID() };
    }
    try {
      await createTrade.mutateAsync({ ...payload, idempotency_key: pendingTradeKey.current.key });
      pendingTradeKey.current = null;
      formRef.current?.reset();
      setOperation("buy");
      setTradeDate(localDate());
      setUnits("");
      setPrice("");
      setFee("0.1");
      setAssetCode("");
      setAssetName("");
      setAssetType("fund");
      toast.success("模拟操作已记录，仅更新模拟盘", { className: "paperToast" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "模拟操作保存失败";
      setTradeError(message);
      window.requestAnimationFrame(() => tradeErrorRef.current?.focus());
      toast.error(message, { className: "paperToast" });
    }
  }

  async function refreshMarket() {
    try {
      const result = await refreshQuotes.mutateAsync();
      toast.success(`模拟行情已刷新：${result.updated} 个成功${result.failed ? `，${result.failed} 个暂不可用` : ""}`, { className: "paperToast" });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "行情刷新失败", { className: "paperToast" });
    }
  }

  function prepareSell(position: PaperPosition) {
    setDetailId(null);
    setOperation("sell");
    setAssetCode(position.code);
    setAssetName(position.name);
    setAssetType(position.asset_type);
    setTradeDate(localDate());
    setUnits("");
    setPrice(position.market_price ?? "");
    setFee("0.1");
    window.setTimeout(() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }), 0);
  }

  async function confirmRetraction() {
    if (!pendingRetraction || retractTrade.isPending) return;
    try {
      await retractTrade.mutateAsync(pendingRetraction.id);
      setPendingRetraction(null);
      toast.success("模拟记录已撤回，真实账本未受影响", { className: "paperToast" });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "撤回模拟记录失败", { className: "paperToast" });
    }
  }

  return (
    <section className="observatoryView paperTradingView">
      <header className="paperHero">
        <div>
          <div className="kicker"><FlaskConical size={14} aria-hidden="true" /> PAPER PORTFOLIO</div>
          <h2>模拟盘 · 投资想法观测</h2>
          <p>自由记录假设中的买卖，观察后续走势与盈亏，不设虚拟资金上限。</p>
        </div>
        <div className="paperHeroActions"><div className="paperCaution"><strong>独立模拟账本</strong><span>不改变真实持仓、操作、总览或 Agent 分析</span></div><button className="paperRefreshButton" type="button" onClick={() => void refreshMarket()} disabled={refreshQuotes.isPending || summary.openCount === 0}><Activity size={16} aria-hidden="true" />{refreshQuotes.isPending ? "刷新中…" : "刷新行情"}</button></div>
      </header>

      {portfolioQuery.isError && <div className="notice paperNotice" role="alert"><span>{portfolioQuery.error instanceof Error ? portfolioQuery.error.message : "模拟盘读取失败"}</span><button className="refreshRetryButton" onClick={() => void portfolioQuery.refetch()}>重新读取</button></div>}

      <div className="paperMetrics">
        <PaperMetric label="跟踪想法" value={`${summary.ideaCount} 个`} />
        <PaperMetric label="当前模拟持仓" value={`${summary.openCount} 个`} />
        <PaperMetric label="已实现盈亏" value={formatMoney(summary.realized)} tone={summary.realized >= 0 ? "up" : "down"} />
        <PaperMetric label="浮动盈亏" value={formatMoney(summary.unrealized)} tone={summary.unrealized >= 0 ? "up" : "down"} />
      </div>
      {summary.unvaluedCount > 0 && <p className="paperQuoteNote" role="status">{summary.unvaluedCount} 个模拟持仓暂时没有可用行情；已保留交易记录，恢复报价后会重新估值。</p>}

      <form ref={formRef} className="panel paperTradeForm" onSubmit={submit}>
        <div className="sectionHeader"><div><h2>记录一个模拟想法</h2><p>不扣减现金；模拟卖出不能超过该标的已有模拟份额。</p></div><span>所有记录只保存在模拟盘</span></div>
        {tradeError && <div ref={tradeErrorRef} className="paperTradeError" role="alert" tabIndex={-1}><strong>模拟操作没有保存</strong><span>{tradeError}</span><button type="button" onClick={() => setTradeError(null)}>知道了</button></div>}
        <div className="paperFormGrid">
          <label><span>代码 <small>必填</small></span><input name="asset_code" autoComplete="off" maxLength={32} placeholder="例如：基金或股票代码" value={assetCode} onChange={(event) => setAssetCode(event.target.value)} required /></label>
          <label><span>名称 <small>必填</small></span><input name="asset_name" maxLength={255} placeholder="例如：半导体 ETF" value={assetName} onChange={(event) => setAssetName(event.target.value)} required /></label>
          <label><span>类型</span><select name="asset_type" value={assetType} onChange={(event) => setAssetType(event.target.value as "fund" | "stock")}><option value="fund">基金 / ETF</option><option value="stock">股票</option></select></label>
          <label><span>方向</span><select name="operation" value={operation} onChange={(event) => setOperation(event.target.value as "buy" | "sell")}><option value="buy">模拟买入</option><option value="sell">模拟卖出</option></select></label>
          <label><span>模拟日期</span><input name="trade_date" type="date" value={tradeDate} onChange={(event) => setTradeDate(event.target.value)} required /></label>
          <label><span>份额 <small>必填</small></span><input name="units" type="number" min="0.01" step="0.01" inputMode="decimal" placeholder="0.00" value={units} onChange={(event) => setUnits(event.target.value)} required /></label>
          <label><span>假设价格（元） <small>必填</small></span><input name="price" type="number" min="0.000001" step="0.000001" inputMode="decimal" placeholder="0.000000" value={price} onChange={(event) => setPrice(event.target.value)} required /></label>
          <label><span>手续费（元）</span><input name="fee" type="number" min="0" step="0.01" inputMode="decimal" value={fee} onChange={(event) => setFee(event.target.value)} /></label>
          <div className="paperAmountPreview"><span>模拟{isSell ? "到账" : "支出"}</span><strong>{amountPreview}</strong><small>{isSell ? "份额 × 价格 − 手续费" : "份额 × 价格 + 手续费"}</small></div>
          <label className="paperReason"><span>当时的理由 / 复盘假设</span><textarea name="reason" maxLength={2000} placeholder="记录看好的逻辑、担忧、观察期限或想验证的问题" /></label>
        </div>
        <button className="primaryButton" type="submit" disabled={createTrade.isPending}><Plus size={15} />{createTrade.isPending ? "保存中…" : "记录模拟操作"}</button>
      </form>

      <section className="paperLedger panel">
        <div className="sectionHeader"><div><h2>模拟持仓与想法</h2><p>按标的代码独立计算模拟成本、盈亏和最新保存的行情快照。</p></div><span>{rows.length} 个标的</span></div>
        <div className="paperTableWrap" tabIndex={0} role="region" aria-label="模拟持仓表，可横向滚动">
          <table className="paperTable">
            <thead><tr><th>标的</th><th>状态</th><th className="paperNumber">模拟份额</th><th className="paperNumber">模拟成本</th><th className="paperNumber">最新价格</th><th className="paperNumber">模拟市值</th><th className="paperNumber">浮动盈亏</th><th className="paperNumber">已实现盈亏</th><th>详情</th></tr></thead>
            <tbody>{rows.map((row) => <tr key={row.id} className={!row.is_open ? "paperClosedRow" : undefined}>
              <td><strong>{row.name}</strong><small>{row.code} · {assetTypeLabels[row.asset_type]}</small></td>
              <td><span className={`paperState ${row.is_open ? "open" : "closed"}`}>{row.is_open ? "持有中" : "已结束"}</span>{row.is_open && row.quote_time && <small>{row.quote_time}</small>}{row.is_open && row.market_value == null && <small title={row.quote_message || "行情暂不可用"}>行情暂不可用</small>}</td>
              <td className="paperNumber">{Number(row.units).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
              <td className="paperNumber">{formatMoney(Number(row.cost_basis))}</td>
              <td className="paperNumber">{row.market_price == null ? "--" : formatMoney(Number(row.market_price))}<small>{row.quote_status === "official_nav" ? "官方净值" : row.is_open ? "行情参考" : "已平仓"}</small></td>
              <td className="paperNumber">{row.market_value == null ? "--" : formatMoney(Number(row.market_value))}</td>
              <td className={`paperNumber ${tone(row.unrealized_profit)}`}>{row.unrealized_profit == null ? "--" : formatMoney(Number(row.unrealized_profit))}</td>
              <td className={`paperNumber ${tone(row.realized_profit)}`}>{formatMoney(Number(row.realized_profit))}</td>
              <td><button className="iconButton compactAction" onClick={() => setDetailId(row.id)} aria-label={`查看${row.name}的模拟详情`}><History size={14} aria-hidden="true" /><span>详情</span></button></td>
            </tr>)}</tbody>
          </table>
          {!portfolioQuery.isLoading && rows.length === 0 && !portfolioQuery.isError && <div className="holdingsEmpty">还没有模拟想法。记录一笔假设中的买入，开始追踪它的表现。</div>}
          {portfolioQuery.isLoading && <div className="holdingsEmpty" role="status">正在读取模拟盘…</div>}
        </div>
        <p className="paperFooter"><Activity size={14} aria-hidden="true" />基金盘中估值和股票行情仅供复盘参考；无报价时仍保留历史流水。</p>
      </section>

      {detail && <PaperAssetDetail asset={detail} onClose={closeDetail} onSell={() => prepareSell(detail)} onRetract={setPendingRetraction} />}
      <ConfirmDialog open={Boolean(pendingRetraction)} title="撤回模拟操作" description={pendingRetraction ? `将撤回${operationLabels[pendingRetraction.operation]}记录，并重新计算模拟持仓与盈亏。真实账本不会变化。${pendingRetraction.operation === "buy" ? "若后续模拟卖出依赖这笔买入，需先撤回后续操作。" : ""}` : ""} confirmLabel="确认撤回" danger busy={retractTrade.isPending} onCancel={() => setPendingRetraction(null)} onConfirm={confirmRetraction} />
    </section>
  );
}

function PaperAssetDetail({ asset, onClose, onSell, onRetract }: { asset: PaperPosition; onClose: () => void; onSell: () => void; onRetract: (trade: PaperTrade) => void }) {
  const { data: rows = [], isLoading, isError, error, refetch } = usePaperHistory(asset.id);
  const quotesQuery = usePaperQuotes(asset.id);
  const quotes = quotesQuery.data ?? [];
  const dialogRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handleTab = (event: KeyboardEvent) => {
      if (document.querySelector(".confirmDialog")) return;
      if (event.key === "Escape") { onClose(); return; }
      if (event.key !== "Tab") return;
      const controls = dialogRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), [tabindex="0"]');
      if (!controls?.length) return;
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    const onKeyDown = (event: KeyboardEvent) => handleTab(event);
    closeRef.current?.focus();
    window.addEventListener("keydown", onKeyDown);
    return () => { window.removeEventListener("keydown", onKeyDown); document.body.style.overflow = previousOverflow; previous?.focus(); };
  }, [onClose]);

  return createPortal(
    <div className="paperDetailBackdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section ref={dialogRef} className="paperDetailDialog" role="dialog" aria-modal="true" aria-labelledby="paper-detail-title">
        <header className="paperDetailHeader"><div><span className="kicker">PAPER IDEA HISTORY</span><h2 id="paper-detail-title">{asset.name}</h2><p>{asset.code} · {asset_type(asset.asset_type)} · 独立模拟记录</p></div><div className="paperDetailHeaderActions">{asset.is_open && <button className="paperRefreshButton paperSellFromDetail" onClick={onSell}><Activity size={15} aria-hidden="true" />模拟卖出</button>}<button ref={closeRef} className="modalCloseButton" onClick={onClose} aria-label="关闭模拟详情"><X size={17} aria-hidden="true" /></button></div></header>
        <div className="paperDetailMetrics"><div><span>模拟份额</span><strong>{Number(asset.units).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong></div><div><span>模拟成本</span><strong>{formatMoney(Number(asset.cost_basis))}</strong></div><div><span>已实现盈亏</span><strong className={tone(asset.realized_profit)}>{formatMoney(Number(asset.realized_profit))}</strong></div><div><span>浮动盈亏</span><strong className={tone(asset.unrealized_profit)}>{asset.unrealized_profit == null ? "--" : formatMoney(Number(asset.unrealized_profit))}</strong></div></div>
        <p className="paperDetailNote">这里记录每次模拟操作时的价格、份额和想法。行情为手动刷新保存的参考快照，不会修改或回填成交价。</p>
        <section className="paperQuoteHistory" aria-labelledby="paper-quotes-title"><div className="paperSubheading"><h3 id="paper-quotes-title">行情观测</h3><span>{quotes.length} 个快照</span></div>{quotesQuery.isLoading ? <p role="status">正在读取行情观测…</p> : quotesQuery.isError ? <p role="alert">行情快照暂不可读</p> : quotes.length === 0 ? <p>还没有行情快照。返回模拟盘点击“刷新行情”后开始留存。</p> : <div className="paperQuoteList">{[...quotes].reverse().map((quote) => <div className="paperQuotePoint" key={quote.id}><span>{quote.quote_time || new Date(quote.captured_at).toLocaleString("zh-CN", { hour12: false })}</span><strong>¥{Number(quote.price).toFixed(4)}</strong><small>{quote.quote_status === "official_nav" ? "官方净值" : "盘中参考"} · {quote.source || "行情源"}{quote.change_pct != null ? ` · ${Number(quote.change_pct) >= 0 ? "+" : ""}${Number(quote.change_pct).toFixed(2)}%` : ""}</small></div>)}</div>}</section>
        {isLoading ? <p className="paperHistoryState" role="status">正在读取模拟流水…</p> : isError ? <div className="notice paperHistoryError" role="alert"><span>{error instanceof Error ? error.message : "模拟流水读取失败"}</span><button className="secondaryButton" onClick={() => void refetch()}>重新读取</button></div> : rows.length === 0 ? <div className="holdingsEmpty">暂无模拟操作</div> : <div className="paperHistoryWrap" tabIndex={0} role="region" aria-label="模拟操作历史，可横向滚动"><table className="paperHistoryTable"><thead><tr><th>日期</th><th>方向</th><th className="paperNumber">价格</th><th className="paperNumber">份额</th><th className="paperNumber">手续费</th><th className="paperNumber">支出 / 到账</th><th>理由与状态</th><th>操作</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id} className={row.retracted_at ? "paperRetracted" : undefined}><td>{row.trade_date}</td><td className={row.operation === "buy" ? "upText" : "downText"}>{operationLabels[row.operation]}</td><td className="paperNumber">{Number(row.price).toFixed(6)}</td><td className="paperNumber">{Number(row.units).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td><td className="paperNumber">{formatMoney(Number(row.fee))}</td><td className="paperNumber">{formatMoney(Number(row.amount))}<small>{row.operation === "buy" ? "含手续费支出" : "扣费后到账"}</small></td><td className="paperReason">{row.reason || "未填写理由"}{row.retracted_at && <small>已撤回 · {row.retraction_reason || "用户手动撤回"}</small>}</td><td>{row.retracted_at ? <span className="paperRetractedLabel">已撤回</span> : <button className="retractButton" onClick={() => onRetract(row)} aria-label={`撤回${row.trade_date}的${operationLabels[row.operation]}`}><Trash2 size={14} aria-hidden="true" /><span>撤回</span></button>}</td></tr>)}</tbody></table></div>}
      </section>
    </div>, document.body,
  );
}

function PaperMetric({ label, value, tone: color }: { label: string; value: string; tone?: "up" | "down" }) {
  return <div className="paperMetric"><span>{label}</span><strong className={color ? `${color}Text` : undefined}>{value}</strong></div>;
}

function tone(value?: string | null) {
  return value == null ? "" : Number(value) >= 0 ? "upText" : "downText";
}

function asset_type(value: string) {
  return assetTypeLabels[value] ?? value;
}

function formValue(form: FormData, key: string) {
  const value = form.get(key);
  return typeof value === "string" ? value : "";
}
