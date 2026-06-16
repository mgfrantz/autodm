import axios from 'axios';
import type { Character, World, GameState, DMResponse, CombatState, CombatResult, WorldMapData, TravelResult, SaveSlotSummary, LoadSaveResult, RestInfo, ShortRestResult, LongRestResult } from '../types';

const API = axios.create({
  baseURL: '/api',
});

// === Characters ===
export const createCharacter = async (data: {
  name: string;
  race: string;
  char_class: string;
  level?: number;
  background?: string;
  strength: number;
  dexterity: number;
  constitution: number;
  intelligence: number;
  wisdom: number;
  charisma: number;
  backstory?: string;
}) => {
  const res = await API.post<Character>('/characters/', data);
  return res.data;
};

export const listCharacters = async () => {
  const res = await API.get<Character[]>('/characters/');
  return res.data;
};

// === Worlds ===
export const generateWorld = async (data: {
  tone?: string;
  character_id?: number;
}) => {
  const res = await API.post<World>('/world/generate', data);
  return res.data;
};

export const listWorlds = async () => {
  const res = await API.get<World[]>('/world/');
  return res.data;
};

// === Game ===
export const createGame = async (data: {
  name?: string;
  character_id: number;
  world_id: number;
}) => {
  const res = await API.post('/game/create', data);
  return res.data;
};

export const startAdventure = async (gameId: number) => {
  const res = await API.post<{ narration: string }>(`/game/${gameId}/start`);
  return res.data;
};

export const playerAction = async (gameId: number, action: string) => {
  const res = await API.post<DMResponse>(`/game/${gameId}/action`, { action });
  return res.data;
};

export const getGameState = async (gameId: number) => {
  const res = await API.get<GameState>(`/game/${gameId}/state`);
  return res.data;
};

export const listGames = async () => {
  const res = await API.get('/game/');
  return res.data;
};

// === Streaming (Server-Sent Events) ===

/** A single SSE event parsed from the streaming endpoints. */
export interface StreamEvent {
  type: 'chunk' | 'done' | 'error';
  content?: string;
  message?: string;
  combat_active?: boolean;
}

/**
 * Low-level helper: read a POST endpoint that returns an SSE stream and invoke
 * callbacks for each parsed event. Returns the events for callers that need
 * the final `done`/`error` payload.
 */
async function consumeSSEStream(
  url: string,
  body: Record<string, unknown>,
  onEvent: (event: StreamEvent) => void,
): Promise<StreamEvent[]> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!res.ok || !res.body) {
    throw new Error(`Stream request failed: HTTP ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  const events: StreamEvent[] = [];
  let buffer = '';

  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE events are separated by a blank line.
    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() ?? '';
    for (const block of blocks) {
      const dataLine = block
        .split('\n')
        .find((line) => line.startsWith('data: '));
      if (!dataLine) continue;
      const payload = JSON.parse(dataLine.slice('data: '.length)) as StreamEvent;
      events.push(payload);
      onEvent(payload);
    }
  }

  return events;
}

/**
 * Stream the opening narration. Calls onChunk for each text piece and onDone
 * once the stream completes.
 */
export async function streamStartAdventure(
  gameId: number,
  onChunk: (text: string) => void,
  onDone: () => void,
): Promise<void> {
  await consumeSSEStream(`/api/game/${gameId}/start/stream`, {}, (event) => {
    if (event.type === 'chunk' && event.content !== undefined) {
      onChunk(event.content);
    } else if (event.type === 'done') {
      onDone();
    } else if (event.type === 'error') {
      throw new Error(event.message ?? 'Streaming error');
    }
  });
}

/**
 * Stream the DM's response to a player action. Calls onChunk for each text
 * piece and onDone (with combat state) once the stream completes.
 */
export async function streamPlayerAction(
  gameId: number,
  action: string,
  onChunk: (text: string) => void,
  onDone: (combatActive: boolean) => void,
): Promise<void> {
  await consumeSSEStream(
    `/api/game/${gameId}/action/stream`,
    { action },
    (event) => {
      if (event.type === 'chunk' && event.content !== undefined) {
        onChunk(event.content);
      } else if (event.type === 'done') {
        onDone(event.combat_active ?? false);
      } else if (event.type === 'error') {
        throw new Error(event.message ?? 'Streaming error');
      }
    },
  );
}

// === Combat ===

export const startCombat = async (gameId: number, enemies: Array<{
  name: string;
  max_hp: number;
  armor_class: number;
  initiative_bonus?: number;
  speed?: number;
  attacks: Array<{
    name: string;
    attack_bonus: number;
    damage_dice_count: number;
    damage_dice_sides: number;
    damage_bonus: number;
    damage_type: string;
  }>;
}>) => {
  const res = await API.post(`/game/${gameId}/combat/start`, { enemies });
  return res.data;
};

export const getCombatState = async (gameId: number): Promise<CombatState> => {
  const res = await API.get<CombatState>(`/game/${gameId}/combat/state`);
  return res.data;
};

export const nextTurn = async (gameId: number) => {
  const res = await API.post(`/game/${gameId}/combat/next-turn`);
  return res.data;
};

export const makeAttack = async (
  gameId: number,
  attackerId: string,
  targetId: string,
  attackName: string,
  advantage = false,
  disadvantage = false,
): Promise<CombatResult> => {
  const res = await API.post(`/game/${gameId}/combat/attack`, {
    attacker_id: attackerId,
    target_id: targetId,
    attack_name: attackName,
    advantage,
    disadvantage,
  });
  return res.data;
};

export const endCombat = async (gameId: number) => {
  const res = await API.post(`/game/${gameId}/combat/end`);
  return res.data;
};

// === Navigation / Map ===

export const getWorldMap = async (gameId: number): Promise<WorldMapData> => {
  const res = await API.get<WorldMapData>(`/navigation/${gameId}/map`);
  return res.data;
};

export const travelToRegion = async (gameId: number, regionId: string): Promise<TravelResult> => {
  const res = await API.post<TravelResult>(`/navigation/${gameId}/travel`, { region_id: regionId });
  return res.data;
};

// === Save / Load ===

export const createSaveSlot = async (gameId: number, slotName: string): Promise<SaveSlotSummary> => {
  const res = await API.post<SaveSlotSummary>(`/game/${gameId}/save`, { slot_name: slotName });
  return res.data;
};

export const listSaveSlots = async (gameId: number): Promise<SaveSlotSummary[]> => {
  const res = await API.get<SaveSlotSummary[]>(`/game/${gameId}/saves`);
  return res.data;
};

export const loadSaveSlot = async (gameId: number, slotId: number): Promise<LoadSaveResult> => {
  const res = await API.post<LoadSaveResult>(`/game/${gameId}/load/${slotId}`);
  return res.data;
};

export const deleteSaveSlot = async (gameId: number, slotId: number): Promise<void> => {
  await API.delete(`/game/${gameId}/saves/${slotId}`);
};

// === Rest ===

export const getRestInfo = async (gameId: number): Promise<RestInfo> => {
  const res = await API.get<RestInfo>(`/game/${gameId}/rest`);
  return res.data;
};

export const shortRest = async (gameId: number, numDice?: number): Promise<ShortRestResult> => {
  const res = await API.post<ShortRestResult>(`/game/${gameId}/short-rest`, numDice != null ? { num_dice: numDice } : {});
  return res.data;
};

export const longRest = async (gameId: number): Promise<LongRestResult> => {
  const res = await API.post<LongRestResult>(`/game/${gameId}/long-rest`);
  return res.data;
};
