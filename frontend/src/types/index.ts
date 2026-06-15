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
