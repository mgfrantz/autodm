export interface Character {
  id: number;
  name: string;
  race: string;
  char_class: string;
  level: number;
  background: string | null;
  strength: number;
  dexterity: number;
  constitution: number;
  intelligence: number;
  wisdom: number;
  charisma: number;
  max_hp: number;
  current_hp: number;
  armor_class: number;
  speed: number;
  backstory: string | null;
}

export interface World {
  id: number;
  name: string;
  description: string;
  tone: string;
}

export interface StoryEntry {
  role: 'player' | 'dm' | 'system';
  content: string;
  timestamp: string;
}

export interface GameState {
  game_id: number;
  name: string;
  character: {
    id: number;
    name: string;
    race: string;
    char_class: string;
    level: number;
    hp: number;
    max_hp: number;
  };
  world: {
    id: number;
    name: string;
  };
  game_state: {
    location: string;
    visited_locations: string[];
    active_quests: string[];
    conditions: string[];
    in_combat: boolean;
  };
  story_log: StoryEntry[];
  current_act: number;
  xp: number;
}

export interface DMResponse {
  narration: string;
  choices: string[] | null;
  combat_active: boolean;
  roll_requested: boolean;
}

// === Combat Types ===

export interface Combatant {
  id: string;
  name: string;
  side: 'player' | 'enemy';
  max_hp: number;
  current_hp: number;
  armor_class: number;
  initiative: number;
  initiative_bonus: number;
  speed: number;
  conditions: string[];
  attacks: Attack[];
}

export interface Attack {
  name: string;
  attack_bonus: number;
  damage_dice_count: number;
  damage_dice_sides: number;
  damage_bonus: number;
  damage_type: string;
}

export interface Encounter {
  combatants: Combatant[];
  turn_order_ids: string[];
  current_turn_index: number;
  round_number: number;
  started: boolean;
  log: string[];
}

export interface CombatState {
  in_combat: boolean;
  is_active?: boolean;
  winner?: 'player' | 'enemy' | null;
  round?: number;
  current_turn?: string;
  current_turn_id?: string;
  encounter?: Encounter;
}

export interface CombatResult {
  result: {
    attacker: string;
    target: string;
    attack: string;
    hit: boolean;
    critical: boolean;
    critical_miss: boolean;
    damage: number;
    target_remaining_hp: number;
    description: string;
  };
  encounter: Encounter;
  combat_active: boolean;
  winner?: 'player' | 'enemy' | null;
}

// === Navigation / Map Types ===

export interface RegionNode {
  id: string;
  name: string;
  description: string;
  terrain: string;
  icon: string;
  settlements: string[];
  dangers: string[];
  coordinates: [number, number];
  connections: string[];
  /** Present in the /regions list response. */
  visited?: boolean;
  reachable?: boolean;
  current?: boolean;
}

export interface WorldMapData {
  current_region_id: string;
  current_region: RegionNode;
  visited_region_ids: string[];
  reachable_region_ids: string[];
  regions: RegionNode[];
}

export interface TravelResult {
  success: boolean;
  message: string;
  from_region_id: string | null;
  to_region: RegionNode | null;
  travel_hours: number;
  encounter_triggered: boolean;
  encounter_danger: string | null;
}

// === Save / Load Types ===

export interface SaveSlotSummary {
  id: number;
  game_save_id: number;
  slot_name: string;
  created_at: string | null;
  current_act: number;
  character_level: number | null;
  character_hp: number | null;
  character_max_hp: number | null;
  xp: number;
}

export interface LoadSaveResult {
  message: string;
  slot_name: string;
  restored_character: {
    level: number | null;
    current_hp: number | null;
    max_hp: number | null;
    xp: number | null;
  };
  story_log_entries: number;
}
