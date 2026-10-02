import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';
import type { Holding } from '../api/client';

interface HoldingsState {
  // State
  holdings: Holding[];
  isLoading: boolean;
  error: string | null;
  lastFetch: number | null;

  // Actions
  setHoldings: (holdings: Holding[]) => void;
  addHolding: (holding: Holding) => void;
  updateHolding: (id: number, updated: Partial<Holding>) => void;
  removeHolding: (id: number) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;

  // Computed
  getTotal: () => number;
  getProfit: () => number;
  getCount: () => number;
}

const initialState = {
  holdings: [],
  isLoading: false,
  error: null,
  lastFetch: null,
};

export const useHoldingsStore = create<HoldingsState>()(
  devtools(
    persist(
      (set, get) => ({
        ...initialState,

        // Actions
        setHoldings: (holdings) =>
          set({ holdings, lastFetch: Date.now(), error: null, isLoading: false }),

        addHolding: (holding) => set((state) => ({ holdings: [...state.holdings, holding] })),

        updateHolding: (id, updated) =>
          set((state) => ({
            holdings: state.holdings.map((h) => (h.id === id ? { ...h, ...updated } : h)),
          })),

        removeHolding: (id) =>
          set((state) => ({
            holdings: state.holdings.filter((h) => h.id !== id),
          })),

        setLoading: (isLoading) => set({ isLoading }),

        setError: (error) => set({ error, isLoading: false }),

        reset: () => set(initialState),

        // Computed
        getTotal: () => get().holdings.reduce((sum, h) => sum + Number(h.amount || 0), 0),
        getProfit: () => get().holdings.reduce((sum, h) => sum + Number(h.profit || 0), 0),
        getCount: () => get().holdings.length,
      }),
      {
        name: 'holdings-storage',
        partialize: (state) => ({ holdings: state.holdings, lastFetch: state.lastFetch }),
      }
    ),
    { name: 'holdings-store' }
  )
);
