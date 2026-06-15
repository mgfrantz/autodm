import axios from 'axios';
import type { Character, World, GameState, DMResponse } from '../types';

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
