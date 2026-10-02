import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';
import { App } from "./App";
import "./styles/globals.css";
import "./styles/app.css";
import "./styles/charts.css";
import "./styles/tracking-detail.css";
import "./styles/frontier-news.css";
import "./styles/holdings.css";
import "./styles/transactions.css";
import "./styles/agent.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5分钟
      gcTime: 1000 * 60 * 30, // 30分钟
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
      <Toaster position="top-right" richColors />
    </QueryClientProvider>
  </React.StrictMode>,
);
