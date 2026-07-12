import { create } from 'zustand';
import type { GameState, StoryEntry, CombatState } from '../types';

// Persisted user preference: whether to auto-narrate each new DM narration as
// it arrives. Stored outside of game state because it's a cross-game UI
// preference (it should survive game resets and reloads). localStorage access
// is wrapped so restricted environments (jsdom / SSR) don't blow up.
const AUTO_NARRATE_KEY = 'dnd-auto-narrate';
function readAutoNarrate(): boolean {
  try {
    return typeof localStorage !== 'undefined' && localStorage.getItem(AUTO_NARRATE_KEY) === '1';
  } catch {
    return false;
  }
}

interface GameStore {
  gameId: number | null;
  gameState: GameState | null;
  story: StoryEntry[];
  combatState: CombatState | null;
  loading: boolean;
  error: string | null;
  /** Whether new DM narrations should be spoken aloud automatically (TTS). */
  autoNarrate: boolean;

  setGameId: (id: number | null) => void;
  setGameState: (state: GameState | null) => void;
  setCombatState: (state: CombatState | null) => void;
  addToStory: (entry: StoryEntry) => void;
  setStory: (entries: StoryEntry[]) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setAutoNarrate: (v: boolean) => void;
  reset: () => void;
}

export const useGameStore = create<GameStore>((set) => ({
  gameId: null,
  gameState: null,
  story: [],
  combatState: null,
  loading: false,
  error: null,
  autoNarrate: readAutoNarrate(),

  setGameId: (id) => set({ gameId: id }),
  setGameState: (state) => set({ gameState: state }),
  setCombatState: (state) => set({ combatState: state }),
  addToStory: (entry) => set((s) => ({ story: [...s.story, entry] })),
  setStory: (entries) => set({ story: entries }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  setAutoNarrate: (v) => {
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem(AUTO_NARRATE_KEY, v ? '1' : '0');
      }
    } catch {
      /* ignore quota / disabled storage */
    }
    set({ autoNarrate: v });
  },
  // Note: reset() deliberately keeps `autoNarrate` — it's a UI preference, not
  // per-game state, so it persists across games and page reloads.
  reset: () => set({ gameId: null, gameState: null, story: [], combatState: null, loading: false, error: null }),
}));
