import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import type { SystemStatus } from '../api/client';

export type PageKey =
  | 'dashboard'
  | 'holdings'
  | 'transactions'
  | 'charts'
  | 'signals'
  | 'frontierNews'
  | 'agent'
  | 'trackingDetail';

interface AppState {
  // State
  currentPage: PageKey;
  apiStatus: 'checking' | 'online' | 'offline';
  systemStatus: SystemStatus | null;

  // Actions
  setCurrentPage: (page: PageKey) => void;
  navigate: (page: PageKey) => void;
  setApiStatus: (status: AppState['apiStatus']) => void;
  setSystemStatus: (status: SystemStatus | null) => void;
}

export const useAppStore = create<AppState>()(
  devtools(
    (set) => ({
      // Initial State
      currentPage: 'dashboard',
      apiStatus: 'checking',
      systemStatus: null,

      // Actions
      setCurrentPage: (page) => set({ currentPage: page }),

      navigate: (page) => {
        window.location.hash = page;
        set({ currentPage: page });
      },

      setApiStatus: (status) => set({ apiStatus: status }),

      setSystemStatus: (status) => set({ systemStatus: status }),

    }),
    { name: 'app-store' }
  )
);
