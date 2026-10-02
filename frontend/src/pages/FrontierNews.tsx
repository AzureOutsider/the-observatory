import { RefreshCw, Tags } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { useFrontierNews, useFrontierNewsTags, useRefreshFrontierNews } from "../hooks/useFrontierNews";

const ALL_TAG = "全部";

export function FrontierNews() {
  const [activeTag, setActiveTag] = useState(ALL_TAG);
  const [sourceFilter, setSourceFilter] = useState("");
  const [importanceFilter, setImportanceFilter] = useState(0);
  const [relatedOnly, setRelatedOnly] = useState(false);
  const tagsQuery = useFrontierNewsTags();
  const newsQuery = useFrontierNews();
  const refreshNews = useRefreshFrontierNews();
  const tags = tagsQuery.data ?? [ALL_TAG];
  const allItems = newsQuery.data ?? [];
  const loading = newsQuery.isLoading || refreshNews.isPending;
  const error = tagsQuery.error ?? newsQuery.error;

  async function loadNews() {
    try {
      await refreshNews.mutateAsync();
      toast.success("前沿新闻已刷新", { className: "frontierToast" });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "新闻刷新失败，请稍后重试", { className: "frontierToast" });
    }
  }

  const tagCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of allItems) {
      for (const tag of item.tags ?? []) {
        counts.set(tag, (counts.get(tag) ?? 0) + 1);
      }
    }
    return counts;
  }, [allItems]);

  const sourceOptions = useMemo(
    () => Array.from(new Map(allItems.map((item) => [item.source, item.source_label ?? item.source])).entries()),
    [allItems],
  );

  const visibleItems = useMemo(() => {
    return allItems.filter((item) => {
      const matchesTag = activeTag === ALL_TAG || (item.tags ?? []).includes(activeTag);
      const matchesSource = !sourceFilter || item.source === sourceFilter;
      const matchesImportance = (item.importance ?? 0) >= importanceFilter;
      const matchesHolding = !relatedOnly || (item.related_holdings?.length ?? 0) > 0;
      return matchesTag && matchesSource && matchesImportance && matchesHolding;
    });
  }, [activeTag, allItems, importanceFilter, relatedOnly, sourceFilter]);

  const impactRows = useMemo(() => {
    const impacts = new Map<string, { newsCount: number; holdings: Map<string, string> }>();
    for (const item of allItems) {
      for (const tag of item.tags ?? []) {
        const row = impacts.get(tag) ?? { newsCount: 0, holdings: new Map<string, string>() };
        row.newsCount += 1;
        for (const holding of item.related_holdings ?? []) {
          if (holding.matched_tags.includes(tag)) {
            row.holdings.set(holding.code, holding.name);
          }
        }
        impacts.set(tag, row);
      }
    }
    return Array.from(impacts.entries())
      .map(([tag, value]) => ({
        tag,
        newsCount: value.newsCount,
        holdingCount: value.holdings.size,
      }))
      .filter((row) => row.holdingCount > 0)
      .sort((a, b) => b.newsCount + b.holdingCount - (a.newsCount + a.holdingCount))
      .slice(0, 8);
  }, [allItems]);

  return (
    <section className="frontierLayout">
      <aside className="panel tagPanel">
        <div className="sectionHeader">
          <h2>标签筛选</h2>
          <Tags size={16} />
        </div>
        <div className="tagRail">
          {tags.map((tag) => (
            <button
              key={tag}
              className={activeTag === tag ? "tagFilter active" : "tagFilter"}
              aria-pressed={activeTag === tag}
              onClick={() => setActiveTag(tag)}
            >
              <span>{tag}</span>
              {tag !== ALL_TAG && <em>{tagCounts.get(tag) ?? 0}</em>}
            </button>
          ))}
        </div>
      </aside>

      <section className="panel frontierNewsPanel">
        <div className="sectionHeader">
          <div>
            <p className="pageKicker">NEWSROOM / MARKET DISPATCH</p>
            <h2>前沿新闻</h2>
            <span>
              {activeTag === ALL_TAG ? "全部标签" : activeTag} · {visibleItems.length} 条
            </span>
          </div>
          <button className="iconButton" onClick={() => void loadNews()} disabled={loading} title="刷新新闻">
            <RefreshCw size={16} className={loading ? "spin" : ""} />
            <span>{loading ? "刷新中" : "刷新"}</span>
          </button>
        </div>

        {error && <div className="notice"><span>{error instanceof Error ? error.message : "暂时无法读取前沿新闻"}</span><button className="refreshRetryButton" onClick={() => void Promise.allSettled([tagsQuery.refetch(), newsQuery.refetch()])}>重新读取</button></div>}

        {impactRows.length > 0 && (
          <div className="impactStrip">
            {impactRows.map((row) => (
              <button key={row.tag} aria-pressed={activeTag === row.tag} onClick={() => setActiveTag(row.tag)}>
                <strong>{row.tag}</strong>
                <span>
                  {row.newsCount} 条新闻 · {row.holdingCount} 个持仓
                </span>
              </button>
            ))}
          </div>
        )}

        <div className="newsFilterBar">
          <label><span>来源</span><select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}><option value="">全部来源</option>{sourceOptions.map(([source, label]) => <option key={source} value={source}>{label}</option>)}</select></label>
          <label><span>重要度</span><select value={importanceFilter} onChange={(event) => setImportanceFilter(Number(event.target.value))}><option value={0}>全部</option><option value={4}>★★★★ 及以上</option><option value={5}>★★★★★</option></select></label>
          <label className="newsToggle"><input type="checkbox" checked={relatedOnly} onChange={(event) => setRelatedOnly(event.target.checked)} /><span>仅看关联持仓</span></label>
        </div>

        <div className="frontierNewsList">
          {loading && allItems.length === 0 && <div className="trackingEmpty"><strong>正在读取前沿新闻</strong><span>正在加载标签和新闻数据。</span></div>}
          {!loading && visibleItems.length === 0 && <div className="trackingEmpty"><strong>暂无符合条件的新闻</strong><span>调整筛选条件或刷新新闻源。</span></div>}
          {visibleItems.map((item) => (
            <article className="frontierNewsItem" key={`${item.source}-${item.title}`}>
              <div className="newsMeta">
                <span>{item.source_label ?? item.source}</span>
                <time>{formatNewsTime(item.published_at ?? item.fetched_at)}</time>
                <em className={`importanceStars importance-${Math.min(5, Math.max(1, item.importance ?? 1))}`} aria-label={`重要度 ${Math.min(5, Math.max(1, item.importance ?? 1))} 星`}>{renderStars(item.importance ?? 1)}</em>
                {item.quality === "stale" && <small>旧缓存</small>}
                <div className="newsTags">
                  {(item.tags ?? ["市场"]).map((tag) => (
                    <button key={tag} aria-pressed={activeTag === tag} onClick={() => setActiveTag(tag)}>
                      {tag}
                    </button>
                  ))}
                </div>
              </div>
              {item.url ? (
                <a href={item.url} target="_blank" rel="noreferrer">
                  {item.title}
                </a>
              ) : (
                <strong>{item.title}</strong>
              )}
              {item.summary && <p className="frontierNewsSummary">{item.summary}</p>}
              {(item.related_holdings?.length ?? 0) > 0 && (
                <div className="relatedHoldings">
                  {item.related_holdings!.slice(0, 6).map((holding) => (
                    <span key={`${item.title}-${holding.code}`}>
                      {holding.name}
                      {holding.latest_change_pct != null && <em className={holding.latest_change_pct > 0 ? "upText" : holding.latest_change_pct < 0 ? "downText" : "flatText"}>{formatPct(holding.latest_change_pct)}</em>}
                    </span>
                  ))}
                </div>
              )}
            </article>
          ))}
        </div>
      </section>
    </section>
  );
}

function formatNewsTime(value?: string | null) {
  if (!value) return "时间未知";
  return value.replace("T", " ").slice(0, 16);
}

function renderStars(value: number) {
  return "★".repeat(Math.min(5, Math.max(1, value)));
}

function formatPct(value: number) {
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}
