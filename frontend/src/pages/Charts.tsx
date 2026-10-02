import ReactECharts from "echarts-for-react";
import { AlertTriangle, Check, Database, Pencil, Plus, RefreshCw, Tags } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiGet, apiPost, HoldingFundTrend, MarketSourceHealth } from "../api/client";
import { useAddWatchlistItem, useWatchlists } from "../hooks/useWatchlists";
import { useDebounce } from "../hooks/useDebounce";
import { sampleData } from "../lib/utils";

type RefreshState = "idle" | "loading-cache" | "cached" | "refreshing" | "complete" | "partial" | "failed";

type RefreshProgress = {
  completed: number;
  total: number;
  completedBatches: number;
  totalBatches: number;
  scope: string;
};

type TrackingItemUpdated = {
  id: number;
  display_name: string;
  custom_name?: string | null;
  tags: string[];
};

const REFRESH_BATCH_SIZE = 7;

export function Charts() {
  const [watchlistId, setWatchlistId] = useState<number | null>(null);
  const [rows, setRows] = useState<HoldingFundTrend[]>([]);
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [assetType, setAssetType] = useState<"stock" | "fund">("stock");
  const [assetName, setAssetName] = useState("");
  const [refreshState, setRefreshState] = useState<RefreshState>("idle");
  const [refreshProgress, setRefreshProgress] = useState<RefreshProgress | null>(null);
  const [failedItemIds, setFailedItemIds] = useState<number[]>([]);
  const [lastRefreshAt, setLastRefreshAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<MarketSourceHealth | null>(null);
  const watchlistsQuery = useWatchlists();
  const addWatchlistItem = useAddWatchlistItem();
  const watchlists = watchlistsQuery.data ?? [];
  const adding = addWatchlistItem.isPending;
  const refreshControllerRef = useRef<{ id: number; controller: AbortController; sequence: number } | null>(null);
  const requestSequenceRef = useRef(0);

  useEffect(() => {
    setWatchlistId((current) => current ?? watchlists[0]?.id ?? null);
  }, [watchlists]);

  useEffect(() => {
    if (watchlistsQuery.error) setError(watchlistsQuery.error instanceof Error ? watchlistsQuery.error.message : "追踪列表读取失败");
  }, [watchlistsQuery.error]);

  useEffect(() => {
    if (watchlistId == null) return;
    void loadWatchlist(watchlistId);
  }, [watchlistId]);

  useEffect(() => () => {
    refreshControllerRef.current?.controller.abort();
  }, []);

  useEffect(() => {
    const onItemUpdated = (event: Event) => {
      const detail = (event as CustomEvent<TrackingItemUpdated>).detail;
      if (!detail) return;
      setRows((current) => current.map((row) => row.watchlist_item_id === detail.id
        ? { ...row, name: detail.display_name, custom_name: detail.custom_name, tags: detail.tags }
        : row));
      void watchlistsQuery.refetch();
    };
    window.addEventListener("watchlist-item-updated", onItemUpdated);
    return () => window.removeEventListener("watchlist-item-updated", onItemUpdated);
  }, []);

  const isCurrentRequest = useCallback((id: number, sequence: number) => {
    const active = refreshControllerRef.current;
    return active != null && !active.controller.signal.aborted && active.id === id && active.sequence === sequence && requestSequenceRef.current === sequence && watchlistId === id;
  }, [watchlistId]);

  const finishRequest = useCallback((id: number, sequence: number) => {
    if (refreshControllerRef.current?.id === id && refreshControllerRef.current.sequence === sequence) {
      refreshControllerRef.current = null;
    }
  }, []);

  async function loadWatchlist(id: number) {
    if (refreshControllerRef.current?.id === id && !refreshControllerRef.current.controller.signal.aborted) return;
    refreshControllerRef.current?.controller.abort();
    const sequence = ++requestSequenceRef.current;
    const controller = new AbortController();
    refreshControllerRef.current = { id, controller, sequence };
    setRows([]);
    setActiveTag(null);
    setError(null);
    setFailedItemIds([]);
    setRefreshProgress(null);
    setLastRefreshAt(null);
    setHealth(null);
    setRefreshState("loading-cache");

    // Navigation may read snapshots, but must never start a quote refresh.
    try {
      const cachedRows = normalizeTrendRows(await apiGet<HoldingFundTrend[]>(`/watchlists/${id}/trends?refresh=false`, { signal: controller.signal }));
      if (!isCurrentRequest(id, sequence)) return;
      setRows(cachedRows);
      setRefreshState(cachedRows.length ? "cached" : "idle");
    } catch (err) {
      if (!isCurrentRequest(id, sequence) || isCancelled(err)) return;
      setError(err instanceof Error ? err.message : "本地快照读取失败");
      setRefreshState("idle");
    } finally {
      finishRequest(id, sequence);
    }
  }

  async function beginRefresh(itemIds: number[], scope: string) {
    if (watchlistId == null || itemIds.length === 0) return;
    if (refreshControllerRef.current?.id === watchlistId && !refreshControllerRef.current.controller.signal.aborted) return;
    refreshControllerRef.current?.controller.abort();
    const sequence = ++requestSequenceRef.current;
    const controller = new AbortController();
    refreshControllerRef.current = { id: watchlistId, controller, sequence };
    setError(null);
    await refreshInBatches(watchlistId, itemIds, scope, sequence, controller);
  }

  async function refreshInBatches(
    id: number,
    itemIds: number[],
    scope: string,
    sequence: number,
    controller: AbortController,
  ) {
    const uniqueIds = [...new Set(itemIds)];
    const batches = chunk(uniqueIds, REFRESH_BATCH_SIZE);
    const failures = new Set<number>();
    let completed = 0;
    setFailedItemIds([]);
    setRefreshState("refreshing");
    setRefreshProgress({ completed: 0, total: uniqueIds.length, completedBatches: 0, totalBatches: batches.length, scope });

    for (let index = 0; index < batches.length; index += 1) {
      const batch = batches[index];
      try {
        const refreshedRows = normalizeTrendRows(await apiPost<HoldingFundTrend[]>(
          `/watchlists/${id}/trends/refresh`,
          { item_ids: batch },
          { signal: controller.signal },
        ));
        if (!isCurrentRequest(id, sequence)) return;
        setRows((current) => mergeTrendRows(current, refreshedRows));
        refreshedRows
          .filter((row) => row.quote_status === "unavailable")
          .forEach((row) => failures.add(row.watchlist_item_id));
      } catch (err) {
        if (!isCurrentRequest(id, sequence) || isCancelled(err)) return;
        batch.forEach((itemId) => failures.add(itemId));
      }
      completed += batch.length;
      if (!isCurrentRequest(id, sequence)) return;
      setFailedItemIds([...failures]);
      setRefreshProgress({
        completed,
        total: uniqueIds.length,
        completedBatches: index + 1,
        totalBatches: batches.length,
        scope,
      });
    }

    if (!isCurrentRequest(id, sequence)) return;
    setLastRefreshAt(new Date().toISOString());
    setRefreshState(failures.size === 0 ? "complete" : failures.size === uniqueIds.length ? "failed" : "partial");
    void apiGet<MarketSourceHealth>("/market/data-sources/health", { signal: controller.signal })
      .then((nextHealth) => { if (requestSequenceRef.current === sequence && watchlistId === id) setHealth(nextHealth); })
      .catch(() => undefined);
    finishRequest(id, sequence);
  }

  async function addTracking(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (watchlistId == null) return;
    const normalizedCode = code.trim().toLowerCase().replace(/\s/g, "").replace(/^(sh|sz|bj)/, "");
    if (!/^\d{6}$/.test(normalizedCode)) {
      setError("请输入 6 位股票或基金代码");
      return;
    }
    setError(null);
    try {
      await addWatchlistItem.mutateAsync({ watchlistId,
        asset_code: normalizedCode,
        asset_type: assetType,
        asset_name: assetName.trim() || undefined,
      });
      await watchlistsQuery.refetch();
      setCode("");
      setAssetName("");
      refreshControllerRef.current?.controller.abort();
      await loadWatchlist(watchlistId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "添加追踪失败");
    }
  }

  const tagCounts = useMemo(() => {
    const counts = new Map<string, number>();
    rows.forEach((row) => (row.tags ?? []).forEach((tag) => counts.set(tag, (counts.get(tag) ?? 0) + 1)));
    return [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0], "zh-CN"));
  }, [rows]);

  useEffect(() => {
    if (activeTag && !tagCounts.some(([tag]) => tag === activeTag)) setActiveTag(null);
  }, [activeTag, tagCounts]);

  const visibleRows = useMemo(
    () => activeTag ? rows.filter((row) => (row.tags ?? []).includes(activeTag)) : rows,
    [activeTag, rows],
  );

  const summary = useMemo(() => {
    const visible = visibleRows.filter((row) => row.latest?.change_pct != null);
    return {
      up: visible.filter((row) => Number(row.latest?.change_pct) > 0).length,
      down: visible.filter((row) => Number(row.latest?.change_pct) < 0).length,
      flat: visible.filter((row) => Number(row.latest?.change_pct) === 0).length,
      official: visibleRows.filter((row) => row.quote_status === "official_nav").length,
      unavailable: visibleRows.filter((row) => row.quote_status === "unavailable").length,
    };
  }, [visibleRows]);

  const sortedRows = useMemo(() => [...visibleRows].sort((a, b) => {
    const aHasCurve = a.points.length > 0;
    const bHasCurve = b.points.length > 0;
    if (aHasCurve !== bHasCurve) return aHasCurve ? -1 : 1;
    if (aHasCurve && bHasCurve) return changeValue(b) - changeValue(a);
    return a.name.localeCompare(b.name, "zh-CN");
  }), [visibleRows]);

  const selectedWatchlist = watchlists.find((list) => list.id === watchlistId);
  const isLoadingCache = refreshState === "loading-cache";
  const isRefreshing = refreshState === "refreshing";
  const isBusy = isLoadingCache || isRefreshing;
  const visibleIds = visibleRows.map((row) => row.watchlist_item_id);

  return (
    <section className="panel wide chartsWorkspace">
      <div className="sectionHeader chartsHeader">
        <div>
          <p className="pageKicker">OBSERVATION / LIVE TRACKING</p>
          <h2>走势观测</h2>
          <span>默认只读取本地快照；点击“刷新当前”才更新当前筛选范围内的行情。</span>
        </div>
        <div className="chartsRefreshActions">
          <button className="iconButton" onClick={() => beginRefresh(visibleIds, activeTag ? `标签：${activeTag}` : "全部标的")} disabled={isBusy || adding || visibleIds.length === 0} title="手动刷新当前筛选结果">
            <RefreshCw size={16} className={isRefreshing ? "spin" : undefined} />
            <span>{isLoadingCache ? "读取快照中" : isRefreshing ? "刷新中" : `刷新当前（${visibleIds.length}）`}</span>
          </button>
        </div>
      </div>

      <RefreshStatusStrip state={refreshState} progress={refreshProgress} failedCount={failedItemIds.length} lastRefreshAt={lastRefreshAt} />
      {error && <div className="notice">{error}</div>}
      {health && <SourceHealthStrip health={health} />}
      {rows.length === 0 && !isBusy && !error && <div className="trackingEmpty"><strong>还没有追踪标的</strong><span>在下方添加标的，再点击“刷新当前”获取行情。</span></div>}

      {rows.length > 0 && <div className="tagFilterBar" aria-label="按自定义标签筛选">
        <div className="tagFilterTitle"><Tags size={15} /><span>观察标签</span></div>
        <div className="tagFilterOptions">
          <button className={activeTag == null ? "active" : ""} onClick={() => setActiveTag(null)}>全部 <small>{rows.length}</small></button>
          {tagCounts.map(([tag, count]) => <button key={tag} className={activeTag === tag ? "active" : ""} onClick={() => setActiveTag(tag)}>{tag} <small>{count}</small></button>)}
        </div>
        {tagCounts.length === 0 && <span className="tagFilterHint">可在标的详情中添加标签</span>}
      </div>}

      {rows.length > 0 && <div className="trackingSummary">当前显示 {visibleRows.length}/{rows.length} 项 · 按可用曲线涨跌幅排序 · 上涨 {summary.up} · 下跌 {summary.down} · 持平 {summary.flat} · 官方净值 {summary.official} · 暂不可用 {summary.unavailable}</div>}

      <div className="fundTrendGrid">
        {sortedRows.map((row) => <FundTrendCard key={row.watchlist_item_id} row={row} watchlistId={watchlistId} />)}
      </div>
      {activeTag && visibleRows.length === 0 && <div className="trackingEmpty"><strong>该标签下暂无标的</strong><span>切换标签或在详情中为标的添加“{activeTag}”。</span></div>}
      {selectedWatchlist?.description && <p className="watchlistDescription">{selectedWatchlist.description}</p>}

      <form className="watchlistToolbar" onSubmit={addTracking}>
        <div className="watchlistToolbarTitle"><span>WATCHLIST</span><strong>添加追踪标的</strong></div>
        <select className="watchlistSelect" value={watchlistId ?? ""} onChange={(event) => setWatchlistId(Number(event.target.value))} aria-label="选择追踪列表">
          {watchlists.map((list) => <option key={list.id} value={list.id}>{list.name}</option>)}
        </select>
        <select value={assetType} onChange={(event) => setAssetType(event.target.value as "stock" | "fund")} aria-label="标的类型">
          <option value="stock">股票</option>
          <option value="fund">基金</option>
        </select>
        <input value={code} onChange={(event) => setCode(event.target.value)} placeholder="输入 6 位代码" inputMode="numeric" maxLength={6} aria-label="股票或基金代码" />
        <input value={assetName} onChange={(event) => setAssetName(event.target.value)} placeholder="名称自动识别，可覆盖" aria-label="标的名称（可选）" />
        <button className="primaryButton watchlistAddButton" type="submit" disabled={adding || watchlistId == null}><Plus size={16} />{adding ? "添加中" : "加入追踪"}</button>
      </form>
    </section>
  );
}

function RefreshStatusStrip({ state, progress, failedCount, lastRefreshAt }: { state: RefreshState; progress: RefreshProgress | null; failedCount: number; lastRefreshAt: string | null }) {
  if (state === "idle") return null;
  const timeLabel = lastRefreshAt ? formatTime(lastRefreshAt) : "";
  const progressLabel = progress ? `${progress.completed}/${progress.total} · 批次 ${progress.completedBatches}/${progress.totalBatches}` : "";
  const content = {
    "loading-cache": { icon: <Database size={15} />, label: "正在读取本地快照", detail: "不会自动刷新行情", tone: "cached" },
    cached: { icon: <Database size={15} />, label: "当前显示本地快照", detail: "如需最新行情，请点击“刷新当前”", tone: "cached" },
    refreshing: { icon: <RefreshCw size={15} className="spin" />, label: `${progress?.scope ?? "行情"}刷新中`, detail: progressLabel, tone: "refreshing" },
    complete: { icon: <Check size={15} />, label: `本轮刷新完成${timeLabel ? ` · ${timeLabel}` : ""}`, detail: progressLabel, tone: "complete" },
    partial: { icon: <AlertTriangle size={15} />, label: `刷新完成 · ${failedCount} 项未更新`, detail: "成功项已保留；如需重试，请点击“刷新当前”", tone: "partial" },
    failed: { icon: <AlertTriangle size={15} />, label: "本轮刷新未取得新数据", detail: "继续显示本地快照，不会自动重试；可点击“刷新当前”", tone: "failed" },
    idle: { icon: null, label: "", detail: "", tone: "" },
  }[state];
  return <div className={`refreshStatusStrip ${content.tone}`} role="status"><span className="refreshStatusIcon">{content.icon}</span><strong>{content.label}</strong>{content.detail && <span>{content.detail}</span>}</div>;
}

function isCancelled(error: unknown) {
  return error instanceof Error && "status" in error && (error as { status?: number }).status === 499;
}

function mergeTrendRows(previous: HoldingFundTrend[], next: HoldingFundTrend[]) {
  const nextById = new Map(next.map((row) => [row.watchlist_item_id, row]));
  const merged = previous.map((cached) => {
    const row = nextById.get(cached.watchlist_item_id);
    if (!row) return cached;
    nextById.delete(cached.watchlist_item_id);
    if (row.points.length > 0 || cached.points.length === 0) return row;
    return { ...row, points: cached.points, latest: row.latest ?? cached.latest, last_available: row.last_available ?? cached.last_available, is_fallback: true };
  });
  return [...merged, ...nextById.values()];
}

function FundTrendCard({ row, watchlistId }: { row: HoldingFundTrend; watchlistId: number | null }) {
  const displayPoint = row.latest ?? row.last_available;
  const displayChange = displayPoint?.change_pct;
  const tone = displayChange == null ? "flat" : displayChange > 0 ? "up" : displayChange < 0 ? "down" : "flat";
  const debouncedPoints = useDebounce(row.points, 300);
  const sampledPoints = useMemo(() => sampleData(debouncedPoints, 500), [debouncedPoints]);
  const values = sampledPoints.map((point) => point.change_pct ?? 0);
  const times = sampledPoints.map((point) => formatTime(point.time));
  const singlePoint = values.length === 1;
  const option = {
    animation: false,
    grid: { left: 6, right: 6, top: 10, bottom: 6 },
    xAxis: { type: "category", show: false, boundaryGap: false, data: singlePoint ? ["", times[0], ""] : times },
    yAxis: { type: "value", show: false, min: (value: { min: number }) => Math.min(value.min, -0.1), max: (value: { max: number }) => Math.max(value.max, 0.1) },
    series: [{
      type: "line", smooth: true, symbol: "circle", symbolSize: 5,
      lineStyle: { width: 2, color: tone === "up" ? "#0f7b4f" : tone === "down" ? "#b8323a" : "#6f7782" },
      itemStyle: { color: tone === "up" ? "#0f7b4f" : tone === "down" ? "#b8323a" : "#6f7782" },
      areaStyle: { opacity: 0.08 }, data: singlePoint ? [values[0], values[0], values[0]] : values,
    }],
    tooltip: { trigger: "axis", formatter: (params: Array<{ data: number; axisValue: string }>) => `${params[0].axisValue}<br/>${params[0].data.toFixed(2)}%` },
  };

  return (
    <article className={`fundTrendCard ${tone}`}>
      <div className="fundTrendHeader">
        <div><strong title={row.name}>{displayName(row.name)}</strong><span>{row.code} · {row.asset_type === "stock" ? "股票" : "基金"}</span></div>
        <div className="trendCardActions"><em>{displayChange == null ? "--" : `${displayChange > 0 ? "+" : ""}${displayChange.toFixed(2)}%`}</em><button className="removeWatchButton" onClick={() => { if (watchlistId != null) window.location.hash = `tracking/${watchlistId}/${row.watchlist_item_id}`; }} title="编辑追踪详情" aria-label={`编辑${row.name}`}><Pencil size={13} /></button></div>
      </div>
      <div className="fundTrendTags">{(row.tags ?? []).slice(0, 3).map((tag) => <span key={tag}>#{tag}</span>)}{(row.tags ?? []).length > 3 && <small>+{(row.tags ?? []).length - 3}</small>}</div>
      <div className="fundTrendMeta" title={row.category_note ?? undefined}><span className="fundCategoryBadge">{row.asset_type === "stock" ? "股票" : row.category_label ?? "基金"}</span><span>{row.source_label ?? "数据源未知"}</span><span>{row.freshness_label ?? "更新时间未知"}</span>{row.is_fallback && <span className="fallbackFlag">已降级</span>}</div>
      {row.points.length > 0 ? <ReactECharts option={option} style={{ height: 92 }} /> : <div className={`fundQuoteState ${row.quote_status}`}><strong>{quoteStatusLabel(row.quote_status)}</strong><span>{row.quote_message ?? "暂无行情说明"}</span></div>}
      <div className="fundTrendFooter"><span>{row.value_label ?? "价格"} {displayPoint?.price?.toFixed(4) ?? "--"}</span><span>{displayPoint ? formatQuoteTime(row.as_of ?? displayPoint.time, row.quote_status) : "暂无可用数据"}</span></div>
    </article>
  );
}

function SourceHealthStrip({ health }: { health: MarketSourceHealth }) {
  return <div className="sourceHealthStrip"><strong>数据源健康</strong><div className="sourceHealthList">{health.sources.map((source) => <span className={`sourceHealthChip ${source.status}`} key={source.source} title={source.last_error ?? undefined}><i />{source.source_label}<small>{sourceStatusLabel(source.status)}</small></span>)}</div><span className="sourceHealthNote">仅在刷新行情时更新</span></div>;
}

function sourceStatusLabel(status: MarketSourceHealth["sources"][number]["status"]) {
  if (status === "healthy") return "正常";
  if (status === "no_data") return "无此类盘中数据";
  if (status === "degraded") return "部分失败";
  if (status === "unavailable") return "不可用";
  return "未请求";
}

function quoteStatusLabel(status: HoldingFundTrend["quote_status"]) {
  if (status === "official_nav") return "最新官方净值";
  if (status === "unavailable") return "行情获取失败";
  if (status === "stale") return "最近可用快照";
  if (status === "intraday_estimate") return "盘中行情";
  return "尚未获取行情";
}

function formatQuoteTime(value: string, status: HoldingFundTrend["quote_status"]) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  if (status === "official_nav" || status === "stale") return date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
  return formatTime(value);
}

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
}

function displayName(value: string, maxLength = 12) {
  const chars = Array.from(value);
  return chars.length > maxLength ? `${chars.slice(0, maxLength).join("")}…` : value;
}

function changeValue(row: HoldingFundTrend) {
  const latest = row.latest?.change_pct;
  if (latest != null) return Number(latest);
  const lastPoint = row.points[row.points.length - 1]?.change_pct;
  return lastPoint == null ? Number.NEGATIVE_INFINITY : Number(lastPoint);
}

function chunk<T>(values: T[], size: number): T[][] {
  const result: T[][] = [];
  for (let index = 0; index < values.length; index += size) result.push(values.slice(index, index + size));
  return result;
}

function normalizeTrendRows(rows: HoldingFundTrend[]) {
  return rows.map((row) => ({ ...row, tags: Array.isArray(row.tags) ? row.tags : [] }));
}
