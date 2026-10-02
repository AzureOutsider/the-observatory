const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000/api";
const REQUEST_TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS ?? 15000);
export const AGENT_ANALYSIS_PACKAGE_ENDPOINT = `${API_BASE}/agent/analysis-package/today`;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly requestId?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export type Asset = {
  id: number;
  code: string;
  name: string;
  official_name?: string | null;
  custom_name?: string | null;
  asset_type: string;
  market?: string | null;
  theme?: string | null;
};

export type Holding = {
  id: number;
  asset: Asset;
  amount: string;
  units?: string | null;
  cost_basis?: string | null;
  profit?: string | null;
  last_valuation_at?: string | null;
  last_valuation_source?: string | null;
  last_manual_adjustment_at?: string | null;
  last_manual_adjustment_reason?: string | null;
  last_update_type?: "manual_correction" | "close_valuation" | "transaction" | "transaction_retraction" | "import" | string | null;
  manual_adjusted?: boolean;
};

export type Transaction = {
  id: number;
  asset: Asset;
  operation: string;
  trade_date: string;
  amount: string;
  units?: string | null;
  price?: string | null;
  fee: string;
  reason?: string | null;
  created_at: string;
  retracted_at?: string | null;
  retraction_reason?: string | null;
  retraction_effect?: string | null;
};

export type MarketIndex = {
  ok: boolean;
  code: string;
  name: string;
  price?: number | null;
  change_pct?: number | null;
  error?: string;
};

export type NewsItem = {
  title: string;
  summary?: string | null;
  url?: string;
  source: string;
  source_label?: string;
  published_at?: string | null;
  fetched_at?: string | null;
  importance?: number;
  quality?: "full" | "headline_only" | "stale" | string;
  content_hash?: string | null;
  tags?: string[];
  related_holdings?: RelatedHolding[];
};

export type RelatedHolding = {
  code: string;
  name: string;
  amount: number;
  tags: string[];
  matched_tags: string[];
  latest_change_pct?: number | null;
};

export type TrendPoint = {
  time: string;
  price?: number | null;
  change_pct?: number | null;
  source: string;
};

export type HoldingFundTrend = {
  watchlist_item_id: number;
  tags?: string[];
  code: string;
  name: string;
  official_name?: string | null;
  custom_name?: string | null;
  asset_type: string;
  amount: number;
  profit?: number | null;
  latest?: TrendPoint | null;
  last_available?: TrendPoint | null;
  points: TrendPoint[];
  quote_status: "intraday_estimate" | "official_nav" | "unavailable" | "stale" | "not_loaded";
  quote_message?: string | null;
  value_label?: string | null;
  quote_source?: string | null;
  source_label?: string | null;
  as_of?: string | null;
  freshness?: "fresh" | "delayed" | "stale" | "official" | "unavailable" | "not_loaded" | "unknown";
  freshness_label?: string | null;
  is_fallback?: boolean;
  fund_category?: "equity" | "bond" | "money" | "qdii" | "other";
  category_label?: string | null;
  category_note?: string | null;
};

export type HistoricalPoint = {
  date: string;
  value: number;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  change_pct?: number | null;
};

export type TrackingHistory = {
  watchlist_item_id: number;
  code: string;
  name: string;
  official_name: string;
  custom_name?: string | null;
  asset_type: string;
  value_label: string;
  range: "6m";
  range_label: string;
  start_date: string;
  end_date: string;
  source?: string | null;
  source_label?: string | null;
  cache_status: "fresh" | "cached" | "unavailable";
  message?: string | null;
  points: HistoricalPoint[];
};

export type Watchlist = {
  id: number;
  name: string;
  description?: string | null;
  items: Array<{
    id: number;
    tags?: string[];
    asset: Asset;
  }>;
};

export type MarketSourceHealth = {
  generated_at: string;
  sources: Array<{
    source: string;
    source_label: string;
    attempts: number;
    successes: number;
    no_datas: number;
    failures: number;
    last_attempt?: string | null;
    last_success?: string | null;
    last_error?: string | null;
    last_outcome?: "success" | "no_data" | "failure" | null;
    success_rate?: number | null;
    availability_rate?: number | null;
    status: "idle" | "healthy" | "no_data" | "degraded" | "unavailable";
  }>;
};

export type AgentContext = {
  date: string;
  trading_status: { status: string; message: string };
  market_indices: MarketIndex[];
  holdings: Array<{
    code: string;
    name: string;
    asset_type: string;
    theme?: string | null;
    amount: string;
    profit?: string | null;
  }>;
  recent_transactions: Array<{
    code: string;
    name: string;
    operation: string;
    trade_date: string;
    amount: string;
    reason?: string | null;
  }>;
  knowledge: Array<{ title: string; content: string; source_path: string }>;
};

export type AgentResearchContext = {
  schema_version?: string;
  generated_at?: string;
  analysis_date?: string;
  date: string;
  topic?: string | null;
  private_portfolio: {
    total_amount: number;
    holding_count: number;
    theme_exposure: Array<{
      tag: string;
      amount: number;
      weight_pct: number;
      holdings: Array<{ code: string; name: string }>;
    }>;
    holdings: Array<{
      code: string;
      name: string;
      asset_type: string;
      theme?: string | null;
      tags: string[];
      amount: number;
      profit?: number | null;
      weight_pct: number;
      today: {
        price?: number | null;
        change_pct?: number | null;
        updated_at?: string | null;
        source?: string | null;
        source_label?: string | null;
        status?: string | null;
        freshness?: string | null;
        freshness_note?: string | null;
        observed_at?: string | null;
        value_label?: string | null;
        is_intraday?: boolean;
        is_fallback?: boolean;
        fund_category?: string | null;
        category_label?: string | null;
      };
    }>;
    recent_transactions: Array<{
      code: string;
      name: string;
      operation: string;
      trade_date: string;
      amount: number;
      reason?: string | null;
    }>;
    knowledge: Array<{ title: string; content: string; source_path: string }>;
  };
  market_snapshot: {
    trading_status: { status: string; message: string };
    market_indices: MarketIndex[];
    holding_today_changes: Array<{
      code: string;
      name: string;
      change_pct?: number | null;
      latest_price?: number | null;
      updated_at?: string | null;
      status?: string | null;
      source?: string | null;
      source_label?: string | null;
      freshness?: string | null;
      is_intraday?: boolean;
      is_fallback?: boolean;
    }>;
  };
  data_source_health: MarketSourceHealth;
  data_quality_summary: {
    holding_count: number;
    status_counts: Record<string, number>;
    manual_refresh_required: boolean;
    note: string;
  };
  internal_news_signals: Array<{
    title?: string;
    summary?: string | null;
    source?: string;
    source_label?: string;
    url?: string;
    published_at?: string | null;
    fetched_at?: string | null;
    importance?: number;
    quality?: string;
    tags?: string[];
    related_holdings?: RelatedHolding[];
    note?: string;
  }>;
  external_research: {
    required: boolean;
    instruction: string;
    source_priority: Array<{ type: string; examples: string[] }>;
    verification_rules: string[];
    suggested_queries: string[];
  };
  analysis_contract: {
    required_output_sections: string[];
    guardrails: string[];
  };
  historical_review?: {
    path: string;
    exists: boolean;
    recent_dates: string[];
    open_items: string[];
    triggers: string[];
    follow_up_items?: string[];
    note?: string;
    error?: string;
  };
  agent_prompt: string;
};

export type ReviewAppendResult = {
  appended: boolean;
  duplicate: boolean;
  path: string;
  fingerprint: string;
  analysis_date?: string;
  run_id?: string | null;
  bytes_written?: number;
};

export type SystemStatus = {
  managed_by_launcher: boolean;
  shutdown_token?: string | null;
  message: string;
};

export type ApiRequestOptions = {
  signal?: AbortSignal;
  timeoutMs?: number;
};

export async function apiGet<T>(path: string, options?: ApiRequestOptions): Promise<T> {
  return apiRequest<T>(path, { method: "GET" }, options);
}

export async function apiPost<T>(path: string, body: unknown, options?: ApiRequestOptions): Promise<T> {
  return apiRequest<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }, options);
}

export async function apiDelete<T = unknown>(path: string, options?: ApiRequestOptions): Promise<T> {
  return apiRequest<T>(path, { method: "DELETE" }, options);
}

export async function apiPatch<T>(path: string, body: unknown, options?: ApiRequestOptions): Promise<T> {
  return apiRequest<T>(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }, options);
}

async function apiRequest<T>(path: string, init: RequestInit, options: ApiRequestOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timeoutMs = options.timeoutMs ?? REQUEST_TIMEOUT_MS;
  let cancelledByCaller = false;
  const onAbort = () => {
    cancelledByCaller = true;
    controller.abort();
  };
  if (options.signal) {
    if (options.signal.aborted) onAbort();
    else options.signal.addEventListener("abort", onAbort, { once: true });
  }
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const requestId = crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { ...init.headers, "X-Request-ID": requestId },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      const detail = typeof payload?.detail === "string" ? payload.detail : `请求失败（${response.status}）`;
      throw new ApiError(detail, response.status, response.headers.get("X-Request-ID") ?? requestId);
    }
    return response.json() as Promise<T>;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      if (cancelledByCaller || options.signal?.aborted) {
        throw new ApiError("请求已取消", 499, requestId);
      }
      throw new ApiError(`请求超时（${timeoutMs / 1000} 秒）`, 408, requestId);
    }
    throw new ApiError(error instanceof Error ? error.message : "网络请求失败", 0, requestId);
  } finally {
    window.clearTimeout(timeout);
    options.signal?.removeEventListener("abort", onAbort);
  }
}

export async function requestShutdown(token: string): Promise<{ status: string; message: string }> {
  return apiRequest<{ status: string; message: string }>("/system/shutdown", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Finance-Shutdown-Token": token,
    },
    body: "{}",
  });
}
