import { create } from 'zustand';
import type { GameState, StoryEntry } from '../types';

interface GameStore {
  gameId: number | null;
  gameState: GameState | null;
  story: StoryEntry[];
  loading: boolean;
  error: string | null;

  setGameId: (id: number | null) => void;
  setGameState: (state: GameState | null) => void;
  addToStory: (entry: StoryEntry) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

export const useGameStore = create<GameStore>((set) => ({
  gameId: null,
  gameState: null,
  story: [],
  loading: false,
  error: null,

  setGameId: (id) => set({ gameId: id }),
  setGameState: (state) => set({ gameState: state }),
  addToStory: (entry) => set((s) => ({ story: [...s.story, entry] })),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  reset: () => set({ gameId: null, gameState: null, story: [], loading: false, error: null }),
}));
