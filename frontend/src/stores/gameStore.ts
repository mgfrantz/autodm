import { create } from 'zustand';
import type { GameState, StoryEntry, CombatState } from '../types';

interface GameStore {
  gameId: number | null;
  gameState: GameState | null;
  story: StoryEntry[];
  combatState: CombatState | null;
  loading: boolean;
  error: string | null;

  setGameId: (id: number | null) => void;
  setGameState: (state: GameState | null) => void;
  setCombatState: (state: CombatState | null) => void;
  addToStory: (entry: StoryEntry) => void;
  setStory: (entries: StoryEntry[]) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

export const useGameStore = create<GameStore>((set) => ({
  gameId: null,
  gameState: null,
  story: [],
  combatState: null,
  loading: false,
  error: null,

  setGameId: (id) => set({ gameId: id }),
  setGameState: (state) => set({ gameState: state }),
  setCombatState: (state) => set({ combatState: state }),
  addToStory: (entry) => set((s) => ({ story: [...s.story, entry] })),
  setStory: (entries) => set({ story: entries }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  reset: () => set({ gameId: null, gameState: null, story: [], combatState: null, loading: false, error: null }),
}));
