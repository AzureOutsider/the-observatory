import {
  BarChart3,
  Bot,
  CircleDot,
  Home,
  Newspaper,
  Power,
  Repeat2,
  Rss,
  WalletCards,
  Search,
} from "lucide-react";
import type { ComponentType } from "react";
import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { requestShutdown } from "./api/client";
import { AppErrorBoundary } from "./components/AppErrorBoundary";
import { ConfirmDialog } from "./components/ConfirmDialog";
import { useSystemStatus } from "./hooks/useSystemStatus";
import { useHoldings } from "./hooks/useHoldings";
import { SearchDialog } from "./components/SearchDialog";
import { toast } from "sonner";
import observatoryLogo from "./assets/observatory-logo.webp";

const Dashboard = lazy(() => import("./pages/Dashboard").then((module) => ({ default: module.Dashboard })));
const Holdings = lazy(() => import("./pages/Holdings").then((module) => ({ default: module.Holdings })));
const Transactions = lazy(() => import("./pages/Transactions").then((module) => ({ default: module.Transactions })));
const Charts = lazy(() => import("./pages/Charts").then((module) => ({ default: module.Charts })));
const News = lazy(() => import("./pages/News").then((module) => ({ default: module.News })));
const FrontierNews = lazy(() => import("./pages/FrontierNews").then((module) => ({ default: module.FrontierNews })));
const Agent = lazy(() => import("./pages/Agent").then((module) => ({ default: module.Agent })));
const TrackingDetail = lazy(() => import("./pages/TrackingDetail").then((module) => ({ default: module.TrackingDetail })));

type PageKey = "dashboard" | "holdings" | "transactions" | "charts" | "signals" | "frontierNews" | "agent" | "trackingDetail";

const navItems: Array<{ key: PageKey; label: string; icon: ComponentType<{ size?: number }> }> = [
  { key: "dashboard", label: "总览", icon: Home },
  { key: "holdings", label: "持仓", icon: WalletCards },
  { key: "transactions", label: "操作", icon: Repeat2 },
  { key: "charts", label: "走势", icon: BarChart3 },
  { key: "signals", label: "信号", icon: Newspaper },
  { key: "frontierNews", label: "前沿新闻", icon: Rss },
  { key: "agent", label: "Agent", icon: Bot },
];

export function App() {
  const [page, setPage] = useState<PageKey>(() => readPage());
  const [shutdownState, setShutdownState] = useState<"idle" | "stopping" | "stopped">("idle");
  const [confirmShutdown, setConfirmShutdown] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const systemStatusQuery = useSystemStatus();
  const holdingsQuery = useHoldings();
  const systemStatus = systemStatusQuery.data ?? null;
  const apiState: "checking" | "online" | "offline" = systemStatusQuery.isPending
    ? "checking"
    : systemStatusQuery.error && !systemStatusQuery.data
      ? "offline"
      : "online";
  const active = navItems.find((item) => item.key === page);

  useEffect(() => {
    document.documentElement.dataset.theme = "dark";
  }, []);

  useEffect(() => {
    const onHashChange = () => setPage(readPage());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const editing = target?.matches("input, textarea, select, [contenteditable='true']");
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearchOpen(true);
        return;
      }
      if (editing || event.altKey || event.metaKey || event.ctrlKey) return;
      const shortcut = Number(event.key);
      if (shortcut >= 1 && shortcut <= navItems.length) navigate(navItems[shortcut - 1].key);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  const navigate = useCallback((nextPage: PageKey) => {
    window.location.hash = nextPage;
    setPage(nextPage);
  }, []);
  const closeSearch = useCallback(() => setSearchOpen(false), []);
  const selectHolding = useCallback(() => { setSearchOpen(false); navigate("holdings"); }, [navigate]);

  async function shutdown() {
    if (!systemStatus?.managed_by_launcher || !systemStatus.shutdown_token) {
      toast.error("当前网站不是由 Finance 启动器管理，请使用启动器或原启动终端退出。重新启动请使用桌面的 Finance 网站.exe。");
      return;
    }

    setShutdownState("stopping");
    try {
      await requestShutdown(systemStatus.shutdown_token);
      setShutdownState("stopped");
    } catch (error) {
      setShutdownState("idle");
      toast.error(error instanceof Error ? error.message : "退出失败，请检查启动器状态。");
    }
  }

  if (shutdownState === "stopped") {
    return (
      <main className="shutdownScreen">
        <Power size={34} />
        <h1>观象台已停止</h1>
        <p>前端、后端和启动器已经退出，可以关闭此页面。</p>
      </main>
    );
  }

  return (
    <div className="appShell">
      <div className="observatoryBackdrop" aria-hidden="true">
        <div className="observatoryMoon" />
        {Array.from({ length: 120 }, (_, index) => (
          <i
            key={index}
            className="observatoryStar"
            style={{
              left: `${(index * 47) % 101}%`,
              top: `${(index * 83) % 97}%`,
              opacity: index % 7 === 0 ? 0.76 : 0.38,
              width: index % 9 === 0 ? 3 : 2,
              height: index % 9 === 0 ? 3 : 2,
            }}
          />
        ))}
      </div>
      <aside className="sidebar">
        <div className="brand">
          <img className="brandLogo" src={observatoryLogo} alt="天文学家与黄铜望远镜" width={56} height={56} />
          <div>
            <strong>观象台</strong>
            <span>The Observatory</span>
          </div>
        </div>
        <nav className="nav">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.key}
                className={(page === item.key || (item.key === "charts" && page === "trackingDetail")) ? "navButton active" : "navButton"}
                onClick={() => navigate(item.key)}
                title={item.label}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
        <div className="sidebarFooter">
          <section className="sidebarNote" aria-labelledby="sidebar-note-title">
            <h2 id="sidebar-note-title">夜航札记</h2>
            <p>在看不清未来的时候，先把仪器调准。每一个数字，都是一颗等待被解释的星。</p>
          </section>
          <button className="shutdownButton" onClick={() => setConfirmShutdown(true)} disabled={shutdownState === "stopping"} title="退出观象" aria-label="退出观象">
            <Power size={18} />
            <span>{shutdownState === "stopping" ? "正在退出" : "退出观象"}</span>
          </button>
        </div>
      </aside>

      <main className="mainPanel">
        <header className="topbar">
          <div>
            <p className="eyebrow">The Observatory / Visual System</p>
            <h1>{page === "dashboard" ? "仰观天象，俯察经济。" : (active?.label ?? (page === "trackingDetail" ? "走势" : "总览"))}</h1>
            {page === "dashboard" && <p className="topbarDescription">一套以古典科学为隐喻的投资工作台：让冷静的数据拥有夜空的尺度，也让每一项判断都留下可追溯的观测痕迹。</p>}
          </div>
          <div className="topbarContext">
            <div className="statusPill">
              <CircleDot size={13} />
              <span>LOCAL API</span>
              <strong>{apiState === "online" ? "在线" : apiState === "offline" ? "离线" : "检测中"}</strong>
            </div>
            <button className="searchTrigger" type="button" onClick={() => setSearchOpen(true)} title="搜索持仓（Ctrl/Cmd + K）"><Search size={15} /><span>搜索</span><kbd>⌘K</kbd></button>
            <div className="contextDate">
              <strong>{new Date().toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" }).replace("/", ".")}</strong>
              <span>丙午年 · 八月廿八</span>
              <span>月相：盈凸月</span>
            </div>
          </div>
        </header>

        <AppErrorBoundary key={page}>
          <Suspense fallback={<section className="panel loadingPanel">页面加载中…</section>}>
            {page === "dashboard" && <Dashboard />}
            {page === "holdings" && <Holdings />}
            {page === "transactions" && <Transactions />}
            {(page === "charts" || page === "trackingDetail") && <Charts />}
            {page === "trackingDetail" && <TrackingDetail />}
            {page === "signals" && <News />}
            {page === "frontierNews" && <FrontierNews />}
            {page === "agent" && <Agent />}
          </Suspense>
        </AppErrorBoundary>
      </main>
      <ConfirmDialog open={confirmShutdown} title="退出观象" description="前端、后端和启动器都会停止，确定继续吗？" confirmLabel="退出观象" danger busy={shutdownState === "stopping"} onCancel={() => setConfirmShutdown(false)} onConfirm={async () => { await shutdown(); if (shutdownState !== "stopping") setConfirmShutdown(false); }} />
      <SearchDialog open={searchOpen} holdings={holdingsQuery.data ?? []} onClose={closeSearch} onSelectHolding={selectHolding} />
    </div>
  );
}

function readPage(): PageKey {
  const value = window.location.hash.slice(1);
  if (value.startsWith("tracking/")) return "trackingDetail";
  return navItems.some((item) => item.key === value) ? (value as PageKey) : "dashboard";
}
