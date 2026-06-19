export interface Character {
  id: number;
  name: string;
  race: string;
  char_class: string;
  level: number;
  background: string | null;
  alignment: string | null;
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
  gold?: number;
  skill_proficiencies?: string[];
  skill_expertise?: string[];
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
    alignment?: string | null;
    background?: string | null;
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
  // Extended combat-action fields (optional for backward compatibility).
  size?: string;
  strength?: number;
  dexterity?: number;
  athletics_bonus?: number | null;
  acrobatics_bonus?: number | null;
  dodging?: boolean;
  disengaging?: boolean;
  bonus_movement?: number;
  movement_used?: number;
  grappled_by?: string | null;
}

export interface Attack {
  name: string;
  attack_bonus: number;
  damage_dice_count: number;
  damage_dice_sides: number;
  damage_bonus: number;
  damage_type: string;
}

export interface SceneEnvironment {
  light: string;
  weather: string;
  terrain: string;
  temperature: string;
  time_of_day: string;
  notes?: string;
}

export interface Encounter {
  combatants: Combatant[];
  turn_order_ids: string[];
  current_turn_index: number;
  round_number: number;
  started: boolean;
  log: string[];
  help_advantage_targets?: string[];
  /** Active scene environment driving combat situational modifiers, if any. */
  environment?: SceneEnvironment | null;
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

// === Combat Actions (DnD 5e Actions in Combat) ===

export type CombatActionKey =
  | 'grapple'
  | 'shove'
  | 'dash'
  | 'disengage'
  | 'dodge'
  | 'help'
  | 'unarmed-strike'
  | 'off-hand-attack'
  | 'escape'
  | 'opportunity-attack';

export interface CombatActionInfo {
  key: CombatActionKey;
  name: string;
  description: string;
  cost: 'one action' | 'one attack' | 'bonus action' | 'reaction';
  requires_target: boolean;
}

export interface ActionResultSummary {
  action: string;
  success: boolean;
  description: string;
  details?: Record<string, unknown>;
}

export interface CombatActionResult {
  result: ActionResultSummary;
  attack_result?: {
    hit: boolean;
    critical: boolean;
    critical_miss: boolean;
    damage: number;
    target_remaining_hp: number;
  } | null;
  encounter: Encounter;
  combat_active: boolean;
  winner?: 'player' | 'enemy' | null;
}

// === Navigation / Map Types ===

export interface TerrainVisual {
  /** Base fill color (hex). */
  fill: string;
  /** Lighter center color for the radial-gradient highlight (hex). */
  accent: string;
  /** Border color (hex). */
  stroke: string;
  /** Decorative texture pattern id ('trees' | 'peaks' | 'waves' | …). */
  pattern: string;
}

export interface RegionNode {
  id: string;
  name: string;
  description: string;
  terrain: string;
  icon: string;
  visual: TerrainVisual;
  settlements: string[];
  dangers: string[];
  coordinates: [number, number];
  connections: string[];
  /** Present in the /regions list response. */
  visited?: boolean;
  reachable?: boolean;
  current?: boolean;
  /** Fog-of-war: visible to the player (visited or adjacent to a visited region). */
  discovered?: boolean;
}

export interface WorldMapData {
  current_region_id: string;
  current_region: RegionNode;
  visited_region_ids: string[];
  /** Regions revealed by the fog-of-war (visited + their neighbours). */
  discovered_region_ids: string[];
  reachable_region_ids: string[];
  /** Route geometry per reachable region id: array of [x, y] normalized points. */
  routes: Record<string, [number, number][]>;
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

// === Rest Types ===

export interface RestInfo {
  character_id: number;
  character_name: string;
  level: number;
  primary_class: string;
  constitution_modifier: number;
  current_hp: number;
  max_hp: number;
  hit_dice_total: number;
  hit_dice_available: number;
  hit_dice_used: number;
  hit_die_size: number;
  is_caster: boolean;
}

export interface DieRoll {
  faces: number;
  roll: number;
  modifier: number;
  total: number;
}

export interface ShortRestResult {
  type: 'short_rest';
  success: boolean;
  message: string;
  hit_dice_spent: number;
  hit_dice_available_after: number;
  rolls: DieRoll[];
  hp_before: number;
  hp_healed: number;
  hp_after: number;
  max_hp: number;
  character: {
    current_hp: number;
    max_hp: number;
    hit_dice_used: number;
  };
}

export interface SpellSlotOverview {
  level: number;
  max: number;
  used: number;
  available: number;
}

export interface LongRestResult {
  type: 'long_rest';
  success: boolean;
  message: string;
  hp_before: number;
  hp_after: number;
  hp_healed: number;
  max_hp: number;
  hit_dice_recovered: number;
  hit_dice_available_after: number;
  hit_dice_used_after: number;
  slots_recovered: boolean;
  conditions_cleared: string[];
  character: {
    current_hp: number;
    max_hp: number;
    hit_dice_used: number;
  };
  conditions: string[];
  spell_slots: SpellSlotOverview[] | null;
}

// === Skill Types ===

export interface SkillInfo {
  skill: string;
  ability: string;
  ability_score: number;
  ability_modifier: number;
  proficient: boolean;
  expertise: boolean;
  proficiency_bonus: number; // 0, pb, or 2*pb
  modifier: number; // total skill modifier
}

export interface SkillsResponse {
  character_id: number;
  proficiencies: string[];
  expertise: string[];
  skills: SkillInfo[];
  passive_scores: Record<string, number>;
}

export interface SkillCheckResult {
  skill: string;
  ability: string;
  roll: string;
  rolls: number[];
  modifier: number;
  total: number;
  success: boolean;
  dc: number;
  proficient: boolean;
  expertise: boolean;
  advantage: boolean;
  disadvantage: boolean;
  description: string;
}

// === Equipment-driven combat stats ===

export interface EquipmentAttack {
  name: string;
  attack_bonus: number;
  damage_dice_count: number;
  damage_dice_sides: number;
  damage_bonus: number;
  damage_type: string;
  ranged: boolean;
}

export interface WeaponProperties {
  ranged: boolean;
  finesse: boolean;
  light: boolean;
  two_handed: boolean;
  reach: boolean;
  thrown: boolean;
  heavy: boolean;
  versatile: boolean;
  ammunition: boolean;
}

export interface EquipmentCombatStats {
  armor_class: number;
  attacks: EquipmentAttack[];
  weapon: string | null;
  body_armor: string | null;
  shield: string | null;
  weapon_properties: WeaponProperties | null;
  weapon_magic_bonus: number;
}

// === Inventory / Equipment Types ===

export interface InventoryItem {
  id: string;
  name: string;
  item_type: string; // weapon | armor | potion | scroll | misc | quest
  description: string;
  rarity: string;
  value: number;
  weight: number;
  damage_dice_count: number;
  damage_dice_sides: number;
  damage_bonus: number;
  damage_type: string;
  attack_bonus: number;
  armor_type: string | null; // light | medium | heavy | shield
  armor_bonus: number;
  dex_limit: number | null;
  uses: number;
  max_uses: number;
  quantity: number;
}

export interface InventorySlotEntry {
  item: InventoryItem;
  equipped: boolean;
}

export interface InventoryData {
  slots: InventorySlotEntry[];
  total_weight: number;
  total_value: number;
  equipped_armor: InventoryItem | null;
  equipped_weapon: InventoryItem | null;
  equipped_shield: InventoryItem | null;
}

export interface UseItemResult {
  success: boolean;
  message: string;
  current_hp: number;
  max_hp: number;
}

// === Shop / Economy Types ===

export interface ShopMerchantSummary {
  merchant_type: string;
  label: string;
  description: string;
  visited: boolean;
}

export interface ShopOverview {
  character_id: number;
  character_name: string;
  gold: number;
  settlement_tier: string;
  merchants: ShopMerchantSummary[];
}

export interface ShopItem {
  id: string;
  name: string;
  item_type: string;
  description?: string;
  rarity: string;
  value: number;
  weight?: number;
  damage_dice_count?: number;
  damage_dice_sides?: number;
  damage_bonus?: number;
  damage_type?: string;
  attack_bonus?: number;
  armor_type?: string | null;
  armor_bonus?: number;
  dex_limit?: number | null;
  uses?: number;
  max_uses?: number;
  quantity?: number;
}

export interface ShopStockEntry {
  item: ShopItem;
  quantity: number;
  buy_price: number;
}

export interface ShopSellEntry {
  item: ShopItem;
  quantity: number;
  equipped: boolean;
  merchant_buys: boolean;
  sell_price: number;
}

export interface ShopMerchant {
  name: string;
  merchant_type: string;
  label: string;
  description: string;
  settlement_tier: string;
  gold: number;
  stock: ShopStockEntry[];
  player_inventory?: ShopSellEntry[];
}

export interface ShopTransactionResult {
  success: boolean;
  message: string;
  transaction_type: 'buy' | 'sell';
  item_name: string;
  item_id: string;
  quantity: number;
  unit_price: number;
  total: number;
  gold_after: number;
  merchant_gold_after: number;
  gold: number;
  inventory?: { slots: unknown[] };
}

export interface ShopRestockResult {
  merchant_type: string;
  restocked_lines: number;
  gold_restored: boolean;
  gold: number;
  name: string;
  merchant: ShopMerchant;
}

// === Backgrounds ===

export interface BackgroundFeature {
  name: string;
  description: string;
}

export interface BackgroundEquipmentItem {
  name: string;
  item_type: string;
  description: string;
  rarity: string;
  value: number;
  weight: number;
  quantity: number;
}

export interface BackgroundToolChoice {
  count: number;
  categories: string[];
}

export interface BackgroundDetail {
  id: string;
  name: string;
  description: string;
  skill_proficiencies: string[];
  tool_proficiencies_fixed: string[];
  tool_proficiencies_choice: BackgroundToolChoice | null;
  languages: string[];
  extra_languages: number;
  equipment: BackgroundEquipmentItem[];
  equipment_gold: number;
  feature: BackgroundFeature | null;
  personality_traits: string[];
  ideals: string[];
  bonds: string[];
  flaws: string[];
  variant_of: string | null;
}

export interface BackgroundSummary {
  id: string;
  name: string;
  description: string;
  skill_proficiencies: string[];
  feature: string | null;
  variant_of: string | null;
}

export interface CharacterBackground {
  character_id: number;
  character_name: string;
  background: string | null;
  background_known: boolean;
  detail: BackgroundDetail | null;
}

export interface SetBackgroundResult {
  success: boolean;
  character_id: number;
  background: string;
  background_id: string;
  feature: string | null;
  equipment_granted: string[];
  gold_granted: number;
  total_gold: number;
}

// === Alignment ===

export interface AlignmentDetail {
  id: string;
  name: string;
  abbreviation: string;
  ethics: 'lawful' | 'neutral' | 'chaotic';
  morals: 'good' | 'neutral' | 'evil';
  description: string;
  roleplay_hooks: string[];
}

export interface AlignmentSummary {
  id: string;
  name: string;
  abbreviation: string;
  ethics: string;
  morals: string;
  description: string;
}

export interface AlignmentRelationship {
  other_id: string;
  other_name: string;
  ethics_delta: number;
  morals_delta: number;
  total_distance: number;
  disposition: 'friendly' | 'cordial' | 'wary' | 'tense' | 'hostile';
  description: string;
}

export interface AlignmentCompatibility {
  alignment_a: string | null;
  alignment_b: string | null;
  relationship: AlignmentRelationship | null;
}

export interface CharacterAlignment {
  character_id: number;
  character_name: string;
  alignment: string | null;
  alignment_known: boolean;
  detail: AlignmentDetail | null;
}

export interface SetAlignmentResult {
  success: boolean;
  character_id: number;
  alignment: string;
  name: string;
  abbreviation: string;
}

export interface SuggestedAlignments {
  character_id: number;
  race: string | null;
  char_class: string | null;
  suggested: string[];
  race_tendencies: string[];
  class_tendencies: string[];
}

// === Languages (DnD 5e language system) ===

/** Single language registry entry. */
export interface LanguageDetail {
  id: string;
  name: string;
  type: 'standard' | 'exotic' | 'secret';
  typical_speakers: string;
  script: string | null;
}

/** Full language registry grouped by type. */
export interface LanguagesResponse {
  standard: LanguageDetail[];
  exotic: LanguageDetail[];
  secret: LanguageDetail[];
  all: LanguageDetail[];
}

/** A character's language state + valid choices. */
export interface CharacterLanguageInfo {
  character_id: number;
  race: string;
  background: string | null;
  known_languages: string[];
  automatic_languages: string[]; // From race/background/class
  extra_languages: string[]; // Chosen beyond automatic
  remaining_choices: number;
  available_choices: string[];
  summary: string;
}

/** Result of validating a proposed language set (no save). */
export interface LanguageValidationResult {
  valid: boolean;
  error: string | null;
  known_languages: string[];
  automatic_languages: string[];
  extra_languages: string[];
}

// === Environment (weather / lighting / terrain / temperature / time) ===

/** All mechanical effects derived from a scene's environment. */
export interface EnvironmentEffects {
  obscurement: string;
  lightly_obscured: boolean;
  heavily_obscured: boolean;
  perception_disadvantage: boolean;
  effective_blinded: boolean;
  ranged_attack_disadvantage: boolean;
  flames_extinguished: boolean;
  listen_disadvantage: boolean;
  movement_cost_multiplier: number;
  difficult_terrain: boolean;
  slippery: boolean;
  swim_required: boolean;
  climb_required: boolean;
  exhaustion_save: {
    ability: string;
    dc: number;
    frequency: string;
    reason: string;
  } | null;
  active_effects: string[];
  summary: string;
}

/** Registry entry for a single light/weather/terrain/temperature option. */
export interface EnvironmentRule {
  name: string;
  description: string;
  obscurement?: string | null;
  ranged_attack_disadvantage?: boolean;
  flames_extinguished?: boolean;
  listen_disadvantage?: boolean;
  movement_cost?: number;
  slippery?: boolean;
  swim_required?: boolean;
  climb_required?: boolean;
  exhaustion_save?: {
    ability: string;
    dc: number;
    frequency: string;
    reason: string;
  } | null;
}

export interface TimeOfDayOption {
  name: string;
  light: string;
}

export interface EnvironmentRegistry {
  light_levels: EnvironmentRule[];
  weather: EnvironmentRule[];
  terrain: EnvironmentRule[];
  temperature: EnvironmentRule[];
  time_of_day: TimeOfDayOption[];
  climates: string[];
  seasons: string[];
}

export interface EnvironmentResponse {
  environment: SceneEnvironment;
  effects: EnvironmentEffects;
}

export interface EnvironmentRollResult {
  message: string;
  environment: SceneEnvironment;
  effects: EnvironmentEffects;
}

/** How the environment reshapes a single attack's advantage/disadvantage. */
export interface EnvironmentCombatModifiers {
  attacker_ranged_disadvantage: boolean;
  attacker_melee_disadvantage: boolean;
  attacker_cannot_see_target: boolean;
  target_unseen_by_attacker: boolean;
  attacker_unseen_advantage: boolean;
}

export interface EnvironmentModifiersResponse {
  modifiers: EnvironmentCombatModifiers;
  environment: SceneEnvironment;
}
