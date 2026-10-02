import { RefreshCw } from "lucide-react";
import { useMarketIndices, useNews, useRefreshNews } from "../hooks/useMarketData";
import { toast } from "sonner";

export function News() {
  const indicesQuery = useMarketIndices();
  const newsQuery = useNews(20);
  const refreshNews = useRefreshNews(20);
  const indices = indicesQuery.data ?? [];
  const news = newsQuery.data ?? [];
  const loading = newsQuery.isLoading || refreshNews.isPending;
  const error = indicesQuery.error ?? newsQuery.error;

  async function reloadNews() {
    try {
      await refreshNews.mutateAsync();
      toast.success("新闻已刷新");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "新闻刷新失败，请稍后重试");
    }
  }

  return (
    <section className="pageGrid">
      {error && <div className="notice observatoryNotice"><span>{error instanceof Error ? error.message : "暂时无法读取市场信号"}</span><button className="refreshRetryButton" onClick={() => void Promise.allSettled([indicesQuery.refetch(), newsQuery.refetch()])}>重新读取</button></div>}
      <section className="panel">
        <div className="sectionHeader">
          <h2>市场信号</h2>
        </div>
        <div className="denseList">
          {indices.length > 0 ? indices.map((item) => (
            <div className="listRow" key={item.code}>
              <span>{item.name}</span>
              <strong className={(item.change_pct ?? 0) >= 0 ? "upText" : "downText"}>
                {item.change_pct == null ? "--" : `${item.change_pct.toFixed(2)}%`}
              </strong>
            </div>
          )) : <div className="observatoryEmpty">暂无市场指数数据</div>}
        </div>
      </section>

      <section className="panel">
        <div className="sectionHeader">
          <div><h2>前沿资讯</h2><span>{news.length} 条 · 缓存优先</span></div>
          <button className="iconButton" onClick={() => void reloadNews()} disabled={loading} title="刷新新闻"><RefreshCw size={16} className={loading ? "spin" : ""} /></button>
        </div>
        <div className="newsList">
          {loading && news.length === 0 && <div className="observatoryEmpty">正在读取新闻…</div>}
          {!loading && news.length === 0 && <div className="observatoryEmpty">暂无新闻线索</div>}
          {news.map((item) => (
            <a className="newsListItem" key={`${item.source}-${item.content_hash ?? item.title}`} href={item.url || "#"} target="_blank" rel="noreferrer">
              <div className="newsListMeta"><span>{item.source_label ?? item.source}</span><time>{formatNewsTime(item.published_at ?? item.fetched_at)}</time>{item.quality === "stale" && <em>旧缓存</em>}</div>
              <strong>{item.title}</strong>
              {item.summary && <p>{item.summary}</p>}
            </a>
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
