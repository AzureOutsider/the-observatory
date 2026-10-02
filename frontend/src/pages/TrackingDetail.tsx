import ReactECharts from "echarts-for-react";
import { Plus, Save, Tag, Trash2, X } from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { useDeleteTrackingItem, useTrackingHistory, useTrackingItem, useUpdateTrackingItem } from "../hooks/useTrackingData";
import { ConfirmDialog } from "../components/ConfirmDialog";

function readTrackingRoute() {
  const parts = window.location.hash.slice(1).split("/");
  const watchlistId = Number(parts[1]);
  const itemId = Number(parts[2]);
  return Number.isInteger(watchlistId) && watchlistId > 0 && Number.isInteger(itemId) && itemId > 0
    ? { watchlistId, itemId }
    : null;
}

export function TrackingDetail() {
  const routeHash = window.location.hash;
  const route = useMemo(readTrackingRoute, [routeHash]);
  const [customName, setCustomName] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [tagDraft, setTagDraft] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const itemQuery = useTrackingItem(route?.watchlistId, route?.itemId);
  const historyQuery = useTrackingHistory(route?.watchlistId, route?.itemId);
  const updateItem = useUpdateTrackingItem();
  const deleteItemMutation = useDeleteTrackingItem();
  const item = itemQuery.data ?? null;
  const history = historyQuery.data ?? null;
  const loading = itemQuery.isLoading;
  const saving = updateItem.isPending;
  const deleting = deleteItemMutation.isPending;
  const historyLoading = historyQuery.isLoading;
  const error = !route ? "追踪详情地址无效" : itemQuery.error instanceof Error ? itemQuery.error.message : itemQuery.error ? "追踪详情获取失败" : null;
  const historyError = historyQuery.error instanceof Error ? historyQuery.error.message : historyQuery.error ? "历史走势获取失败" : null;
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") goBack();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  useEffect(() => {
    if (!loading) closeButtonRef.current?.focus();
  }, [loading]);

  useEffect(() => {
    if (!item) return;
    setCustomName(item.custom_name ?? "");
    setTags(item.tags ?? []);
  }, [item?.id, item?.custom_name, item?.tags]);

  function goBack() {
    window.location.hash = "charts";
  }

  async function saveSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!route || !item) return;
    try {
      const nextTags = normalizeTags([...tags, ...splitTags(tagDraft)]);
      const nextItem = await updateItem.mutateAsync({ watchlistId: route.watchlistId, itemId: route.itemId,
        custom_name: customName.trim() || null,
        tags: nextTags,
      });
      setCustomName(nextItem.custom_name ?? "");
      setTags(nextItem.tags ?? []);
      setTagDraft("");
      window.dispatchEvent(new CustomEvent("watchlist-item-updated", { detail: nextItem }));
      toast.success("显示名称与观察标签已更新");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "设置保存失败");
    }
  }

  function addDraftTags() {
    const next = normalizeTags([...tags, ...splitTags(tagDraft)]);
    setTags(next);
    setTagDraft("");
  }

  async function deleteItem() {
    if (!route || !item) return;
    try {
      await deleteItemMutation.mutateAsync({ watchlistId: route.watchlistId, itemId: route.itemId });
      toast.success("追踪项已删除");
      setConfirmDelete(false);
      window.location.hash = "charts";
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除追踪失败");
    }
  }

  if (loading) return <div className="trackingModalBackdrop"><section className="trackingModal trackingDetail" role="dialog" aria-modal="true" aria-label="追踪详情"><div className="loadingPanel">详情加载中…</div></section></div>;
  if (error && !item) return <div className="trackingModalBackdrop" onMouseDown={goBack}><section className="trackingModal trackingDetail" role="dialog" aria-modal="true" aria-label="追踪详情" onMouseDown={(event) => event.stopPropagation()}><div className="trackingDetailModalBar"><span>追踪详情</span><button ref={closeButtonRef} className="modalCloseButton" onClick={goBack} title="关闭详情" aria-label="关闭详情"><X size={18} /></button></div><div className="notice">{error}</div></section></div>;
  if (!item) return null;

  const typeLabel = item.asset.asset_type === "stock" ? "股票" : "基金";
  const historyPoints = history?.points ?? [];
  const historyValues = historyPoints.map((point) => point.value);
  const historyMin = historyValues.length ? Math.min(...historyValues) : 0;
  const historyMax = historyValues.length ? Math.max(...historyValues) : 1;
  const historyPadding = Math.max((historyMax - historyMin) * 0.12, historyMax * 0.002, 0.0001);
  const latestHistoryPoint = historyPoints[historyPoints.length - 1];
  const firstHistoryPoint = historyPoints[0];
  const historyChange = firstHistoryPoint && latestHistoryPoint && firstHistoryPoint.value !== 0
    ? (latestHistoryPoint.value / firstHistoryPoint.value - 1) * 100
    : null;
  // ECharts canvas does not inherit CSS colors; resolve the shared theme tokens.
  const theme = getComputedStyle(document.documentElement);
  const chartColor = theme.getPropertyValue(historyChange == null || historyChange === 0 ? "--obs-muted" : historyChange > 0 ? "--green" : "--red").trim();
  const chartMuted = theme.getPropertyValue("--obs-muted").trim();
  const chartLine = theme.getPropertyValue("--obs-blue-line").trim();
  const chartBrass = theme.getPropertyValue("--obs-brass-bright").trim();
  const historyOption = {
    animation: false,
    grid: { left: 14, right: 16, top: 18, bottom: 30, containLabel: true },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: historyPoints.map((point) => point.date),
      axisLine: { lineStyle: { color: chartLine } },
      axisTick: { show: false },
      axisLabel: { color: chartMuted, fontSize: 12, hideOverlap: true, interval: Math.max(Math.ceil(historyPoints.length / 6) - 1, 0), formatter: formatHistoryDate },
    },
    yAxis: {
      type: "value",
      min: historyMin - historyPadding,
      max: historyMax + historyPadding,
      scale: true,
      splitNumber: 4,
      splitLine: { lineStyle: { color: chartLine, type: "dashed" } },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: chartMuted, fontSize: 12, formatter: (value: number) => formatChartValue(value) },
    },
    series: [{
      type: "line",
      smooth: 0.18,
      symbol: "none",
      lineStyle: { width: 2, color: chartColor },
      itemStyle: { color: chartColor },
      areaStyle: { color: chartColor, opacity: 0.08 },
      data: historyValues,
    }],
    tooltip: {
      trigger: "axis",
      renderMode: "richText",
      confine: true,
      backgroundColor: theme.getPropertyValue("--obs-night-mid").trim(),
      borderColor: chartLine,
      textStyle: { color: theme.getPropertyValue("--obs-moon").trim(), fontSize: 13 },
      axisPointer: {
        type: "cross",
        lineStyle: { color: chartBrass, opacity: 0.55 },
        crossStyle: { color: chartBrass, opacity: 0.55 },
        label: { backgroundColor: theme.getPropertyValue("--obs-blue").trim(), color: chartMuted },
      },
      formatter: (params: Array<{ axisValue: string; data: number }>) => {
        const point = params[0];
        const match = historyPoints.find((candidate) => candidate.date === point?.axisValue);
        return match ? `${match.date}\n${history?.value_label ?? "数值"} ${formatChartValue(match.value)}${match.change_pct == null ? "" : `\n涨跌 ${formatPercent(match.change_pct)}`}` : "";
      },
    },
  };
  return (
    <div className="trackingModalBackdrop" onMouseDown={goBack}>
    <section className="trackingModal trackingDetail" role="dialog" aria-modal="true" aria-labelledby="tracking-detail-title" onMouseDown={(event) => event.stopPropagation()}>
      <div className="trackingDetailModalBar">
        <span>追踪详情</span>
        <button ref={closeButtonRef} className="modalCloseButton" onClick={goBack} title="关闭详情" aria-label="关闭详情"><X size={18} /></button>
      </div>
      <div className="trackingDetailHeader">
        <div className="trackingDetailIdentity">
          <p className="pageKicker">TRACKING / DETAIL</p>
          <h2 id="tracking-detail-title">{item.display_name}</h2>
          <span>{item.asset.code} · {typeLabel}</span>
        </div>
        <span className="trackingDetailBadge">追踪项 #{item.id}</span>
      </div>

      {error && <div className="notice">{error}</div>}

      <div className="trackingDetailGrid">
        <section className="trackingDetailSection trackingHistorySection">
          <div className="sectionHeader"><div><h2>历史走势</h2><span>近半年 · 每个交易日一条数据</span></div><span className="historyRangeBadge">近半年</span></div>
          {historyLoading && <div className="trackingHistoryEmpty"><span>HISTORY / SERIES</span><strong>正在加载历史行情</strong><p>首次打开会从行情源同步并写入本地缓存。</p></div>}
          {!historyLoading && historyError && historyPoints.length === 0 && <div className="trackingHistoryEmpty"><span>HISTORY / SERIES</span><strong>历史行情暂不可用</strong><p>{historyError}</p></div>}
          {!historyLoading && !historyError && historyPoints.length === 0 && <div className="trackingHistoryEmpty"><span>HISTORY / SERIES</span><strong>暂无近半年数据</strong><p>该标的暂时没有可绘制的历史行情。</p></div>}
          {!historyLoading && historyPoints.length > 0 && <>
            {historyError && <div className="historyInlineNotice">{historyError}，当前显示本地缓存。</div>}
            <div className="historyStats">
              <div><span>最新</span><strong>{formatChartValue(latestHistoryPoint?.value)} </strong><small>{history?.value_label}</small></div>
              <div><span>区间最高</span><strong>{formatChartValue(historyMax)}</strong></div>
              <div><span>区间最低</span><strong>{formatChartValue(historyMin)}</strong></div>
              <div><span>区间变化</span><strong className={historyChange == null || historyChange === 0 ? "flatText" : historyChange > 0 ? "upText" : "downText"}>{historyChange == null ? "--" : formatPercent(historyChange)}</strong></div>
            </div>
            <ReactECharts option={historyOption} style={{ height: 278, width: "100%" }} notMerge lazyUpdate />
            <div className="historyChartFooter"><span>{history?.start_date} 至 {history?.end_date}</span><span>{history?.source_label ?? "历史数据源未知"} · {history?.message}</span></div>
          </>}
        </section>

        <div className="trackingDetailSection">
          <div className="sectionHeader"><div><h2>显示与标签</h2><span>官方名称用于识别；标签用于筛选观察范围和局部刷新。</span></div><Tag size={17} /></div>
          <form className="trackingNameForm" onSubmit={saveSettings}>
            <label><span>官方名称</span><input value={item.official_name} readOnly /></label>
            <label><span>走势页显示名称</span><input value={customName} onChange={(event) => setCustomName(event.target.value)} placeholder="留空则显示官方名称" maxLength={255} /></label>
            <div className="trackingTagEditor">
              <span className="trackingFieldLabel">观察标签</span>
              <div className="trackingTagInputRow"><input value={tagDraft} onChange={(event) => setTagDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === "," || event.key === "，") { event.preventDefault(); addDraftTags(); } }} placeholder="例如：持仓、新能源、重点观察" maxLength={80} /><button className="iconButton" type="button" onClick={addDraftTags} disabled={!tagDraft.trim()} title="添加标签"><Plus size={15} /><span>添加</span></button></div>
              <div className="trackingTagList">{tags.map((tag) => <span key={tag}>#{tag}<button type="button" onClick={() => setTags((current) => current.filter((value) => value !== tag))} title={`移除标签 ${tag}`} aria-label={`移除标签 ${tag}`}><X size={11} /></button></span>)}{tags.length === 0 && <small>暂未设置标签</small>}</div>
            </div>
            <div className="trackingFormActions"><button className="primaryButton" type="submit" disabled={saving}><Save size={16} />{saving ? "保存中" : "保存设置"}</button>{customName && <button className="iconButton" type="button" onClick={() => setCustomName("")}>恢复官方名称</button>}</div>
          </form>
        </div>
      </div>

      <div className="trackingDangerZone"><div><strong>删除追踪项</strong><span>删除后不会影响持仓或交易记录。</span></div><button className="dangerButton" onClick={() => setConfirmDelete(true)} disabled={deleting}><Trash2 size={16} />删除追踪</button></div>
      <ConfirmDialog open={confirmDelete} title="删除追踪项" description={`确定删除“${item.display_name}”的追踪吗？删除后不会影响持仓或交易记录。`} confirmLabel="删除追踪" danger busy={deleting} onCancel={() => setConfirmDelete(false)} onConfirm={deleteItem} />
    </section>
    </div>
  );
}

function formatHistoryDate(value: string) {
  const parts = value.split("-");
  return parts.length === 3 ? `${parts[1]}-${parts[2]}` : value;
}

function formatChartValue(value: number | undefined) {
  if (value == null || Number.isNaN(value)) return "--";
  return value >= 10 ? value.toFixed(2) : value.toFixed(4);
}

function formatPercent(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function splitTags(value: string) {
  return value.split(/[,，、]/).map((tag) => tag.trim()).filter(Boolean);
}

function normalizeTags(values: string[]) {
  const result: string[] = [];
  const seen = new Set<string>();
  values.forEach((value) => {
    const tag = value.trim().replace(/^#+/, "").slice(0, 24);
    const key = tag.toLocaleLowerCase();
    if (tag && !seen.has(key) && result.length < 12) {
      seen.add(key);
      result.push(tag);
    }
  });
  return result;
}
