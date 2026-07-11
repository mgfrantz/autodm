import axios from 'axios';
import type { Character, World, GameState, DMResponse, CombatState, CombatResult, WorldMapData, TravelResult, SaveSlotSummary, LoadSaveResult, RestInfo, ShortRestResult, LongRestResult, SkillsResponse, SkillCheckResult, CombatActionInfo, CombatActionResult, CombatActionKey, EquipmentCombatStats, InventoryData, UseItemResult, ShopOverview, ShopMerchant, ShopTransactionResult, ShopRestockResult, BackgroundSummary, BackgroundDetail, CharacterBackground, SetBackgroundResult, AlignmentSummary, AlignmentDetail, AlignmentCompatibility, CharacterAlignment, SetAlignmentResult, SuggestedAlignments, LanguageDetail, LanguagesResponse, CharacterLanguageInfo, LanguageValidationResult, EnvironmentRegistry, EnvironmentResponse, EnvironmentRollResult, EnvironmentModifiersResponse, SpellbookResponse, SpellDetail, CastSpellResult, SpellRegistryResponse, FeatInfo, CharacterFeatsResponse, LearnFeatResult, ExhaustionStatus, ExhaustionModifyResult, SurvivalStatus, SurvivalAdvanceResult, SavingThrowProficienciesResponse, SavingThrowRollResult, Trap, TrapInstance, DetectionResult, DisarmResult, TriggerResult, PassiveDetectResult, TrapDmSummary, SocialNPC, ReactionResult, InfluenceResult, InsightResult, DowntimeActivity, DowntimeResolveResult, SubclassInfo, CharacterSubclassResponse, AvailableSubclassesResponse, ChooseSubclassResult, Mount, MountStatusResponse, MountAcquireResult, MountSimpleResult, MountDamageResult, MountHealResult, MountCombatResult, MountTravelResult, ImageGenerationStatus, ImageGenerationResult, ImageGallery, GeneratedImage, TTSStatus, NarrateResult, TTSListResponse, DeleteAudioResult, LegendaryCreaturePreset, LegendaryCombatantView, EncounterLegendaryResponse, LairStateResponse, UseLegendaryActionResult, FireLairActionResult } from '../types';

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
  alignment?: string;
  strength: number;
  dexterity: number;
  constitution: number;
  intelligence: number;
  wisdom: number;
  charisma: number;
  backstory?: string;
  personality_traits?: string[];
  ideal?: string;
  bond?: string;
  flaw?: string;
}) => {
  const res = await API.post<Character>('/characters/', data);
  return res.data;
};

export const listCharacters = async () => {
  const res = await API.get<Character[]>('/characters/');
  return res.data;
};

export const getCharacter = async (characterId: number): Promise<Character> => {
  const res = await API.get<Character>(`/characters/${characterId}`);
  return res.data;
};

export const generateCharacterFlavor = async (data: {
  race: string;
  char_class: string;
  background?: string;
  alignment?: string;
  level?: number;
  strength: number;
  dexterity: number;
  constitution: number;
  intelligence: number;
  wisdom: number;
  charisma: number;
}) => {
  const res = await API.post('/characters/generate-flavor', data);
  return res.data as {
    name: string;
    backstory: string;
    personality_traits: string[];
    ideal: string;
    bond: string;
    flaw: string;
  };
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

// === Combat Actions (Grapple, Shove, Dash, Disengage, Dodge, Help, etc.) ===

export const listCombatActions = async (gameId: number): Promise<CombatActionInfo[]> => {
  const res = await API.get<{ actions: CombatActionInfo[] }>(`/game/${gameId}/combat/actions`);
  return res.data.actions;
};

export const performCombatAction = async (
  gameId: number,
  combatantId: string,
  action: CombatActionKey,
  targetId?: string,
  option?: string,
): Promise<CombatActionResult> => {
  const res = await API.post<CombatActionResult>(`/game/${gameId}/combat/action`, {
    combatant_id: combatantId,
    action,
    target_id: targetId ?? null,
    option: option ?? null,
  });
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

// === Skills ===

export const getSkills = async (characterId: number): Promise<SkillsResponse> => {
  const res = await API.get<SkillsResponse>(`/characters/${characterId}/skills`);
  return res.data;
};

export const rollSkillCheck = async (
  characterId: number,
  skill: string,
  dc: number,
  advantage = false,
  disadvantage = false,
  conditions: string[] = [],
): Promise<SkillCheckResult> => {
  const res = await API.post<SkillCheckResult>(`/characters/${characterId}/skills/check`, {
    skill,
    dc,
    advantage,
    disadvantage,
    conditions,
  });
  return res.data;
};

// === Saving Throws ===

export const getSavingThrowProficiencies = async (
  characterId: number,
): Promise<SavingThrowProficienciesResponse> => {
  const res = await API.get<SavingThrowProficienciesResponse>(
    `/characters/${characterId}/saving-throws/proficiencies`,
  );
  return res.data;
};

export const rollSavingThrow = async (
  characterId: number,
  ability: string,
  dc: number,
  advantage = false,
  disadvantage = false,
  conditions: string[] = [],
): Promise<SavingThrowRollResult> => {
  const res = await API.post<SavingThrowRollResult>(
    `/characters/${characterId}/saving-throws/roll`,
    { ability, dc, advantage, disadvantage, conditions },
  );
  return res.data;
};

// === Equipment-driven combat stats ===

export const getEquipmentCombatStats = async (characterId: number): Promise<EquipmentCombatStats> => {
  const res = await API.get<EquipmentCombatStats>(`/characters/${characterId}/combat-stats`);
  return res.data;
};

// === Inventory / Equipment Management ===

export const getInventory = async (characterId: number): Promise<InventoryData> => {
  const res = await API.get<InventoryData>(`/characters/${characterId}/inventory`);
  return res.data;
};

export const equipItem = async (characterId: number, itemId: string): Promise<InventoryData> => {
  const res = await API.post<InventoryData>(`/characters/${characterId}/equip/${itemId}`);
  return res.data;
};

export const unequipItem = async (characterId: number, itemId: string): Promise<InventoryData> => {
  const res = await API.post<InventoryData>(`/characters/${characterId}/unequip/${itemId}`);
  return res.data;
};

export const useInventoryItem = async (characterId: number, itemId: string): Promise<UseItemResult> => {
  const res = await API.post<UseItemResult>(`/characters/${characterId}/use/${itemId}`);
  return res.data;
};

export const removeInventoryItem = async (characterId: number, itemId: string, quantity = 1): Promise<InventoryData> => {
  const res = await API.delete<InventoryData>(`/characters/${characterId}/items/${itemId}`, {
    params: { quantity },
  });
  return res.data;
};

// === Shop / Economy ===

export const getShopOverview = async (gameId: number): Promise<ShopOverview> => {
  const res = await API.get<ShopOverview>(`/game/${gameId}/shop`);
  return res.data;
};

export const getMerchant = async (gameId: number, merchantType: string): Promise<ShopMerchant> => {
  const res = await API.get<ShopMerchant>(`/game/${gameId}/shop/${merchantType}`);
  return res.data;
};

export const buyFromMerchant = async (
  gameId: number,
  merchantType: string,
  itemId: string,
  quantity = 1,
): Promise<ShopTransactionResult> => {
  const res = await API.post<ShopTransactionResult>(`/game/${gameId}/shop/${merchantType}/buy`, {
    item_id: itemId,
    quantity,
  });
  return res.data;
};

export const sellToMerchant = async (
  gameId: number,
  merchantType: string,
  itemId: string,
  quantity = 1,
): Promise<ShopTransactionResult> => {
  const res = await API.post<ShopTransactionResult>(`/game/${gameId}/shop/${merchantType}/sell`, {
    item_id: itemId,
    quantity,
  });
  return res.data;
};

export const restockMerchant = async (gameId: number, merchantType: string): Promise<ShopRestockResult> => {
  const res = await API.post<ShopRestockResult>(`/game/${gameId}/shop/${merchantType}/restock`);
  return res.data;
};

// === Backgrounds ===

export const listBackgrounds = async (): Promise<BackgroundSummary[]> => {
  const res = await API.get<BackgroundSummary[]>('/backgrounds');
  return res.data;
};

export const getBackground = async (name: string): Promise<BackgroundDetail> => {
  const res = await API.get<BackgroundDetail>(`/backgrounds/${encodeURIComponent(name)}`);
  return res.data;
};

export const getCharacterBackground = async (characterId: number): Promise<CharacterBackground> => {
  const res = await API.get<CharacterBackground>(`/characters/${characterId}/background`);
  return res.data;
};

export const setCharacterBackground = async (
  characterId: number,
  background: string,
  applyEquipment = true,
): Promise<SetBackgroundResult> => {
  const res = await API.post<SetBackgroundResult>(`/characters/${characterId}/background`, {
    background,
    apply_equipment: applyEquipment,
  });
  return res.data;
};

// === Alignment ===

export const listAlignments = async (): Promise<AlignmentSummary[]> => {
  const res = await API.get<AlignmentSummary[]>('/alignment');
  return res.data;
};

export const getAlignment = async (name: string): Promise<AlignmentDetail> => {
  const res = await API.get<AlignmentDetail>(`/alignment/${encodeURIComponent(name)}`);
  return res.data;
};

export const getAlignmentCompatibility = async (a: string, b: string): Promise<AlignmentCompatibility> => {
  const res = await API.get<AlignmentCompatibility>('/alignment/compatibility', { params: { a, b } });
  return res.data;
};

export const getCharacterAlignment = async (characterId: number): Promise<CharacterAlignment> => {
  const res = await API.get<CharacterAlignment>(`/characters/${characterId}/alignment`);
  return res.data;
};

export const setCharacterAlignment = async (
  characterId: number,
  alignment: string,
): Promise<SetAlignmentResult> => {
  const res = await API.post<SetAlignmentResult>(`/characters/${characterId}/alignment`, { alignment });
  return res.data;
};

export const getSuggestedAlignments = async (characterId: number): Promise<SuggestedAlignments> => {
  const res = await API.get<SuggestedAlignments>(`/characters/${characterId}/alignment/suggested`);
  return res.data;
};

// === Languages ===

export const getLanguagesRegistry = async (): Promise<LanguagesResponse> => {
  const res = await API.get<LanguagesResponse>('/languages/registry');
  return res.data;
};

export const getLanguageInfo = async (languageId: string): Promise<LanguageDetail> => {
  const res = await API.get<LanguageDetail>(`/languages/info/${encodeURIComponent(languageId)}`);
  return res.data;
};

export const getCharacterLanguages = async (characterId: number): Promise<CharacterLanguageInfo> => {
  const res = await API.get<CharacterLanguageInfo>(`/characters/${characterId}/languages/choices`);
  return res.data;
};

export const setCharacterLanguages = async (
  characterId: number,
  languages: string[],
): Promise<CharacterLanguageInfo> => {
  const res = await API.post<CharacterLanguageInfo>(`/characters/${characterId}/languages`, { languages });
  return res.data;
};

export const validateCharacterLanguages = async (
  characterId: number,
  languages: string[],
): Promise<LanguageValidationResult> => {
  const res = await API.post<LanguageValidationResult>(
    `/characters/${characterId}/languages/validate`,
    { languages },
  );
  return res.data;
};

// === Environment ===

export const getEnvironmentRegistry = async (): Promise<EnvironmentRegistry> => {
  const res = await API.get<EnvironmentRegistry>('/game/environment/registry');
  return res.data;
};

export const getEnvironment = async (gameId: number): Promise<EnvironmentResponse> => {
  const res = await API.get<EnvironmentResponse>(`/game/${gameId}/environment`);
  return res.data;
};

export const setEnvironment = async (
  gameId: number,
  update: Partial<{
    light: string;
    weather: string;
    terrain: string;
    temperature: string;
    time_of_day: string;
    notes: string;
  }>,
): Promise<EnvironmentResponse> => {
  const res = await API.put<EnvironmentResponse>(`/game/${gameId}/environment`, update);
  return res.data;
};

export const previewEnvironmentEffects = async (
  gameId: number,
  probe: { light: string; weather: string; terrain: string; temperature: string; time_of_day: string },
): Promise<EnvironmentResponse> => {
  const res = await API.post<EnvironmentResponse>(`/game/${gameId}/environment/effects`, probe);
  return res.data;
};

export const rollEnvironmentWeather = async (
  gameId: number,
  climate: string,
  season: string,
  timeOfDay: string,
  seed?: number,
): Promise<EnvironmentRollResult> => {
  const res = await API.post<EnvironmentRollResult>(`/game/${gameId}/environment/roll`, {
    climate,
    season,
    time_of_day: timeOfDay,
    ...(seed != null ? { seed } : {}),
  });
  return res.data;
};

export const getEnvironmentCombatModifiers = async (
  gameId: number,
  attackIsRanged = false,
): Promise<EnvironmentModifiersResponse> => {
  const res = await API.post<EnvironmentModifiersResponse>(
    `/game/${gameId}/environment/combat-modifiers`,
    {},
    { params: { attack_is_ranged: attackIsRanged } },
  );
  return res.data;
};

// === Spells ===

export const getSpellbook = async (characterId: number): Promise<SpellbookResponse> => {
  const res = await API.get<SpellbookResponse>(`/characters/${characterId}/spells`);
  return res.data;
};

export const initializeSpellbook = async (characterId: number): Promise<SpellbookResponse> => {
  const res = await API.post<SpellbookResponse>(`/characters/${characterId}/spells/initialize`);
  return res.data;
};

export const learnSpell = async (characterId: number, spellId: string): Promise<SpellbookResponse> => {
  const res = await API.post<SpellbookResponse>(`/characters/${characterId}/spells/learn`, {
    spell_id: spellId,
  });
  return res.data;
};

/** Toggle a spell's prepared state (prepared casters). */
export const togglePrepareSpell = async (characterId: number, spellId: string): Promise<SpellbookResponse> => {
  const res = await API.post<SpellbookResponse>(`/characters/${characterId}/spells/prepare`, {
    spell_id: spellId,
  });
  return res.data;
};

export interface CastSpellPayload {
  spell_id: string;
  slot_level?: number;
  caster_mod: number;
  target_ac?: number;
  target_save_total?: number;
  active_conditions?: string[];
}

export const castSpell = async (characterId: number, payload: CastSpellPayload): Promise<CastSpellResult> => {
  const res = await API.post<CastSpellResult>(`/characters/${characterId}/spells/cast`, payload);
  return res.data;
};

export const getSpellRegistry = async (): Promise<SpellDetail[]> => {
  const res = await API.get<SpellRegistryResponse>('/characters/spells/registry');
  return res.data.spells;
};

// === Feats ===

/** List all feats in the registry (full definitions). */
export const listFeats = async (): Promise<FeatInfo[]> => {
  const res = await API.get<FeatInfo[]>('/characters/feats/list');
  return res.data;
};

/** A character's learned feats + ASI (Ability Score Improvement) status. */
export const getCharacterFeats = async (characterId: number): Promise<CharacterFeatsResponse> => {
  const res = await API.get<CharacterFeatsResponse>(`/characters/feats/${characterId}`);
  return res.data;
};

/** Feats a character can learn right now (not known, prerequisites met). */
export const getAvailableFeats = async (characterId: number): Promise<FeatInfo[]> => {
  const res = await API.get<FeatInfo[]>(`/characters/feats/${characterId}/available`);
  return res.data;
};

/** Learn a feat, consuming one ASI instance. `chosenAbility` is required for
 *  half-feats (those with ability_bonus_choices). */
export const learnFeat = async (
  characterId: number,
  featName: string,
  chosenAbility?: string,
): Promise<LearnFeatResult> => {
  const res = await API.post<LearnFeatResult>(`/characters/feats/${characterId}/learn`, {
    feat_name: featName,
    chosen_ability: chosenAbility ?? null,
  });
  return res.data;
};

// === Subclasses (DnD 5e archetypes) ===

/** List all subclasses in the registry, optionally filtered by class. */
export const listSubclasses = async (className?: string): Promise<SubclassInfo[]> => {
  const res = await API.get<SubclassInfo[]>('/characters/subclasses/list', {
    params: className ? { class_name: className } : {},
  });
  return res.data;
};

/** A specific subclass's definition. */
export const getSubclassDetail = async (subclassId: string): Promise<SubclassInfo> => {
  const res = await API.get<SubclassInfo>(`/characters/subclasses/list/${subclassId}`);
  return res.data;
};

/** A character's subclass state + merged class/subclass feature timeline. */
export const getCharacterSubclass = async (
  characterId: number,
): Promise<CharacterSubclassResponse> => {
  const res = await API.get<CharacterSubclassResponse>(
    `/characters/subclasses/${characterId}`,
  );
  return res.data;
};

/** Subclasses a character can choose right now (one set per eligible class). */
export const getAvailableSubclasses = async (
  characterId: number,
): Promise<AvailableSubclassesResponse> => {
  const res = await API.get<AvailableSubclassesResponse>(
    `/characters/subclasses/${characterId}/available`,
  );
  return res.data;
};

/** Permanently choose a subclass. `className` defaults to the primary class. */
export const chooseSubclass = async (
  characterId: number,
  subclassId: string,
  className?: string,
): Promise<ChooseSubclassResult> => {
  const res = await API.post<ChooseSubclassResult>(
    `/characters/subclasses/${characterId}/choose`,
    { subclass_id: subclassId, class_name: className ?? null },
  );
  return res.data;
};

// === Exhaustion (DnD 5e special state, 0–6 levels, 6 = death) ===

/** The character's current exhaustion level + cumulative-effects breakdown. */
export const getExhaustion = async (gameId: number): Promise<ExhaustionStatus> => {
  const res = await API.get<ExhaustionStatus>(`/game/${gameId}/exhaustion`);
  return res.data;
};

/** Modify the character's out-of-combat exhaustion.
 *  `mode` is 'set' (absolute), 'add' (stack levels), or 'reduce'. */
export const modifyExhaustion = async (
  gameId: number,
  mode: 'set' | 'add' | 'reduce',
  levels: number,
): Promise<ExhaustionModifyResult> => {
  const res = await API.post<ExhaustionModifyResult>(`/game/${gameId}/exhaustion`, {
    mode,
    levels,
  });
  return res.data;
};

// === Survival (DnD 5e starvation & dehydration — daily food/water tracking) ===

/** The character's current survival drivers, deficit summary, and exhaustion. */
export const getSurvival = async (gameId: number): Promise<SurvivalStatus> => {
  const res = await API.get<SurvivalStatus>(`/game/${gameId}/survival`);
  return res.data;
};

/** Resolve one day of food/water intake; applies any exhaustion inflicted. */
export const advanceSurvival = async (
  gameId: number,
  foodLbs: number,
  waterGal: number,
  hot?: boolean,
  saveRoll?: number,
): Promise<SurvivalAdvanceResult> => {
  const res = await API.post<SurvivalAdvanceResult>(`/game/${gameId}/survival/advance`, {
    food_lbs: foodLbs,
    water_gal: waterGal,
    ...(hot !== undefined ? { hot } : {}),
    ...(saveRoll !== undefined ? { save_roll: saveRoll } : {}),
  });
  return res.data;
};

/** Reset the food/water deprivation counters to zero (character has restocked). */
export const resetSurvival = async (gameId: number): Promise<SurvivalStatus> => {
  const res = await API.post<SurvivalStatus>(`/game/${gameId}/survival/reset`);
  return res.data;
};

// === Traps & Hazards (DMG ch.5 — registry, place, detect, disarm, trigger) ===

/** List all trap templates, optionally filtered by type and/or severity. */
export const getTrapRegistry = async (
  trapType?: 'mechanical' | 'magical',
  severity?: 'setback' | 'dangerous' | 'deadly',
): Promise<Trap[]> => {
  const res = await API.get<Trap[]>('/game/traps/registry', {
    params: {
      ...(trapType ? { trap_type: trapType } : {}),
      ...(severity ? { severity } : {}),
    },
  });
  return res.data;
};

/** Get details for a specific trap template. */
export const getTrapDetail = async (trapId: string): Promise<Trap> => {
  const res = await API.get<Trap>(`/game/traps/registry/${encodeURIComponent(trapId)}`);
  return res.data;
};

/** List all trap instances placed in a game. */
export const getGameTraps = async (gameId: number): Promise<TrapInstance[]> => {
  const res = await API.get<TrapInstance[]>(`/game/${gameId}/traps`);
  return res.data;
};

/** Place a trap (from the registry) into the game world. */
export const placeTrap = async (
  gameId: number,
  trapId: string,
  location = '',
): Promise<TrapInstance> => {
  const res = await API.post<TrapInstance>(`/game/${gameId}/traps`, { trap_id: trapId, location });
  return res.data;
};

/** Attempt to detect a trap with an active Perception check. */
export const detectTrap = async (
  gameId: number,
  trapIndex: number,
  perceptionTotal: number,
  roll = 0,
): Promise<DetectionResult> => {
  const res = await API.post<DetectionResult>(
    `/game/${gameId}/traps/${trapIndex}/detect`,
    { perception_total: perceptionTotal, roll },
  );
  return res.data;
};

/** Check passive Perception against a trap. */
export const passiveDetectTrap = async (
  gameId: number,
  trapIndex: number,
  passivePerception: number,
): Promise<PassiveDetectResult> => {
  const res = await API.post<PassiveDetectResult>(
    `/game/${gameId}/traps/${trapIndex}/passive-detect`,
    { passive_perception: passivePerception },
  );
  return res.data;
};

/** Attempt to disarm a trap. A critical failure (by 5+) can spring the trap. */
export const disarmTrap = async (
  gameId: number,
  trapIndex: number,
  checkTotal: number,
  method = 'thieves_tools',
  roll = 0,
): Promise<DisarmResult> => {
  const res = await API.post<DisarmResult>(
    `/game/${gameId}/traps/${trapIndex}/disarm`,
    { check_total: checkTotal, roll, method },
  );
  return res.data;
};

/** Trigger a trap (e.g. by walking into it). Applies damage/conditions. */
export const triggerGameTrap = async (
  gameId: number,
  trapIndex: number,
  saveRoll?: number,
  saveModifier = 0,
): Promise<TriggerResult> => {
  const res = await API.post<TriggerResult>(
    `/game/${gameId}/traps/${trapIndex}/trigger`,
    {
      ...(saveRoll !== undefined ? { save_roll: saveRoll } : {}),
      save_modifier: saveModifier,
    },
  );
  return res.data;
};

/** Remove a placed trap from the game (GM/admin action). */
export const removeTrap = async (
  gameId: number,
  trapIndex: number,
): Promise<{ status: string; trap_id: string }> => {
  const res = await API.delete(`/game/${gameId}/traps/${trapIndex}`);
  return res.data;
};

/** Get a DM-friendly summary of traps in the current area. */
export const getTrapsDmSummary = async (gameId: number): Promise<TrapDmSummary> => {
  const res = await API.get<TrapDmSummary>(`/game/${gameId}/traps/dm-summary`);
  return res.data;
};

// === Social Interaction (DMG ch.4/ch.8 — reaction, influence, insight) ===

/** List known NPCs with their DMG attitude, trust, and influence-DC. */
export const getSocialNPCs = async (gameId: number): Promise<SocialNPC[]> => {
  const res = await API.get<{ npcs: SocialNPC[] }>(`/game/${gameId}/social/npcs`);
  return res.data.npcs;
};

/** Get a single NPC's interaction summary (defaults to indifferent if unknown). */
export const getSocialNPC = async (gameId: number, npcName: string): Promise<SocialNPC> => {
  const res = await API.get<SocialNPC>(`/game/${gameId}/social/npcs/${encodeURIComponent(npcName)}`);
  return res.data;
};

/** Roll an initial-reaction (2d6 + CHA) for a newly-met NPC. */
export const rollSocialReaction = async (
  gameId: number,
  npcName: string,
  charismaModifier?: number,
  reactionDice?: [number, number],
): Promise<ReactionResult> => {
  const res = await API.post<ReactionResult>(`/game/${gameId}/social/reaction`, {
    npc_name: npcName,
    ...(charismaModifier !== undefined ? { charisma_modifier: charismaModifier } : {}),
    ...(reactionDice ? { reaction_dice: reactionDice } : {}),
  });
  return res.data;
};

/** Make a Charisma check to shift an NPC's attitude one step. */
export const influenceNPC = async (
  gameId: number,
  npcName: string,
  skill: string,
  opts: {
    skillModifier?: number;
    conditions?: string[];
    forcedAdvantage?: boolean;
    forcedDisadvantage?: boolean;
    roll?: number;
    failMarginForWorsen?: number;
  } = {},
): Promise<InfluenceResult> => {
  const res = await API.post<InfluenceResult>(`/game/${gameId}/social/influence`, {
    npc_name: npcName,
    skill,
    ...(opts.skillModifier !== undefined ? { skill_modifier: opts.skillModifier } : {}),
    ...(opts.conditions !== undefined ? { conditions: opts.conditions } : {}),
    ...(opts.forcedAdvantage ? { forced_advantage: true } : {}),
    ...(opts.forcedDisadvantage ? { forced_disadvantage: true } : {}),
    ...(opts.roll !== undefined ? { roll: opts.roll } : {}),
    ...(opts.failMarginForWorsen !== undefined ? { fail_margin_for_worsen: opts.failMarginForWorsen } : {}),
  });
  return res.data;
};

/** An Insight check against an NPC's (passive or rolled) Deception. */
export const insightNPC = async (
  gameId: number,
  npcName: string,
  opts: {
    insightModifier?: number;
    npcDeceptionTotal?: number;
    npcPassiveDeception?: number;
    insightRoll?: number;
  } = {},
): Promise<InsightResult> => {
  const res = await API.post<InsightResult>(`/game/${gameId}/social/insight`, {
    npc_name: npcName,
    ...(opts.insightModifier !== undefined ? { insight_modifier: opts.insightModifier } : {}),
    ...(opts.npcDeceptionTotal !== undefined ? { npc_deception_total: opts.npcDeceptionTotal } : {}),
    ...(opts.npcPassiveDeception !== undefined ? { npc_passive_deception: opts.npcPassiveDeception } : {}),
    ...(opts.insightRoll !== undefined ? { insight_roll: opts.insightRoll } : {}),
  });
  return res.data;
};

// === Downtime Activities (PHB ch.8 + XGE ch.2 — between-adventures system) ===

/** All available downtime activities (carousing, crime, gambling, ...). */
export const getDowntimeActivities = async (
  gameId: number,
): Promise<DowntimeActivity[]> => {
  const res = await API.get<{ activities: DowntimeActivity[] }>(`/game/${gameId}/downtime/activities`);
  return res.data.activities;
};

/** Optional knobs for a downtime resolution; all are passed straight through. */
export interface DowntimeResolveOptions {
  activity: string;
  modifier?: number;
  dc?: number;
  days?: number;
  workweeks?: number;
  roll?: number;
  rolls?: number[];
  d6?: number;
  complication_d20?: number;
  save_roll?: number;
  tier?: 'lower' | 'middle' | 'upper';
  wager?: number;
  games?: number;
  casing_dc?: number;
  heist_dc?: number;
  heist_checks?: number;
  casing_modifier?: number;
  heist_modifier?: number;
  casing_roll?: number;
  heist_rolls?: number[];
  item_value?: number;
  progress_before?: number;
  has_proficiency?: boolean;
  target?: string;
  target_kind?: 'tool' | 'language';
  tool_proficiency?: boolean;
  conditions?: string[];
}

/** Resolve one downtime activity, applying gold/exhaustion/training effects. */
export const resolveDowntime = async (
  gameId: number,
  opts: DowntimeResolveOptions,
): Promise<DowntimeResolveResult> => {
  const res = await API.post<DowntimeResolveResult>(`/game/${gameId}/downtime/resolve`, opts);
  return res.data;
};

// === Legendary Actions & Lair Actions — boss-monster combat (MM p.11) ===

/** All ready-to-use legendary creature presets (dragons, liches, beholders...). */
export const listLegendaryCreatures = async (): Promise<LegendaryCreaturePreset[]> => {
  const res = await API.get<{ creatures: LegendaryCreaturePreset[] }>('/game/legendary/creatures');
  return res.data.creatures;
};

/** Look up a single legendary creature preset by id. */
export const getLegendaryCreature = async (creatureId: string): Promise<LegendaryCreaturePreset> => {
  const res = await API.get<LegendaryCreaturePreset>(`/game/legendary/creatures/${creatureId}`);
  return res.data;
};

/** Every legendary creature in the active encounter with its action budget. */
export const getEncounterLegendary = async (gameId: number): Promise<EncounterLegendaryResponse> => {
  const res = await API.get<EncounterLegendaryResponse>(`/game/${gameId}/legendary`);
  return res.data;
};

/** A single combatant's legendary-action budget + available actions. */
export const getLegendaryState = async (
  gameId: number,
  combatantId: string,
): Promise<LegendaryCombatantView> => {
  const res = await API.get<LegendaryCombatantView>(`/game/${gameId}/legendary/${combatantId}`);
  return res.data;
};

/** Spend a legendary action off-turn (attack-kind actions need a targetId). */
export const useLegendaryAction = async (
  gameId: number,
  combatantId: string,
  actionId: string,
  targetId?: string,
): Promise<UseLegendaryActionResult> => {
  const res = await API.post<UseLegendaryActionResult>(`/game/${gameId}/legendary/use`, {
    combatant_id: combatantId,
    action_id: actionId,
    target_id: targetId,
  });
  return res.data;
};

/** The encounter's lair-action state (initiative 20 actions + last fired round). */
export const getLairState = async (gameId: number): Promise<LairStateResponse> => {
  const res = await API.get<LairStateResponse>(`/game/${gameId}/lair`);
  return res.data;
};

/** Fire the lair action due this round (initiative count 20). */
export const fireLairAction = async (gameId: number): Promise<FireLairActionResult> => {
  const res = await API.post<FireLairActionResult>(`/game/${gameId}/lair/action`);
  return res.data;
};

// === Mounts & Vehicles (DnD 5e mounted travel + mounted combat — PHB ch.5/8/9) ===

/** List all registered mount/vehicle definitions, optionally filtered by type. */
export const getMountRegistry = async (
  gameId: number,
  type?: 'land' | 'flying' | 'aquatic' | 'vehicle',
): Promise<Mount[]> => {
  const res = await API.get<Mount[]>(`/game/${gameId}/mounts/registry`, {
    params: type ? { type } : {},
  });
  return res.data;
};

/** Get a single mount definition from the registry. */
export const getMountRegistryMount = async (
  gameId: number,
  mountId: string,
): Promise<Mount> => {
  const res = await API.get<Mount>(`/game/${gameId}/mounts/${mountId}`);
  return res.data;
};

/** The character's current mount state + readable summary. */
export const getMountState = async (gameId: number): Promise<MountStatusResponse> => {
  const res = await API.get<MountStatusResponse>(`/game/${gameId}/mount`);
  return res.data;
};

/** Acquire a fresh, fully-healthy mount (optionally paying its cost). */
export const acquireMount = async (
  gameId: number,
  mountId: string,
  mounted = true,
  pay = false,
): Promise<MountAcquireResult> => {
  const res = await API.post<MountAcquireResult>(`/game/${gameId}/mount/acquire`, {
    mount_id: mountId,
    mounted,
    pay,
  });
  return res.data;
};

/** Climb into the saddle (costs half your movement in combat). */
export const mountUp = async (gameId: number): Promise<MountSimpleResult> => {
  const res = await API.post<MountSimpleResult>(`/game/${gameId}/mount/mount-up`);
  return res.data;
};

/** Dismount but keep leading the mount. */
export const dismount = async (gameId: number): Promise<MountSimpleResult> => {
  const res = await API.post<MountSimpleResult>(`/game/${gameId}/mount/dismount`);
  return res.data;
};

/** Set the overland travel pace (slow/normal/fast) and gallop-burst toggle. */
export const setMountPace = async (
  gameId: number,
  pace: 'slow' | 'normal' | 'fast',
  galloping = false,
): Promise<MountSimpleResult> => {
  const res = await API.post<MountSimpleResult>(`/game/${gameId}/mount/pace`, {
    pace,
    galloping,
  });
  return res.data;
};

/** Apply damage to the mount (may throw the rider at 0 HP). */
export const damageMount = async (
  gameId: number,
  amount: number,
  saveTotal?: number,
): Promise<MountDamageResult> => {
  const res = await API.post<MountDamageResult>(`/game/${gameId}/mount/damage`, {
    amount,
    ...(saveTotal !== undefined ? { save_total: saveTotal } : {}),
  });
  return res.data;
};

/** Heal the active mount (clamped to its max HP). */
export const healMount = async (
  gameId: number,
  amount: number,
): Promise<MountHealResult> => {
  const res = await API.post<MountHealResult>(`/game/${gameId}/mount/heal`, { amount });
  return res.data;
};

/** Mounted-combat modifiers for the rider against a given target. */
export const getMountCombat = async (
  gameId: number,
  targetSize = 'medium',
  targetMounted = false,
): Promise<MountCombatResult> => {
  const res = await API.post<MountCombatResult>(`/game/${gameId}/mount/combat`, {
    target_size: targetSize,
    target_mounted: targetMounted,
  });
  return res.data;
};

/** Preview adjusted travel hours for a trip given the current mount + pace. */
export const previewMountTravel = async (
  gameId: number,
  baseHours: number,
  pace?: 'slow' | 'normal' | 'fast',
  galloping?: boolean,
): Promise<MountTravelResult> => {
  const res = await API.post<MountTravelResult>(`/game/${gameId}/mount/travel`, {
    base_hours: baseHours,
    ...(pace ? { pace } : {}),
    ...(galloping !== undefined ? { galloping } : {}),
  });
  return res.data;
};

// --------------------------------------------------------------------------- //
// Image Generation
// --------------------------------------------------------------------------- //

/** Check whether image generation is configured. */
export const getImageStatus = async (
  gameId: number,
): Promise<ImageGenerationStatus> => {
  const res = await API.get<ImageGenerationStatus>(`/game/${gameId}/images/status`);
  return res.data;
};

/** Generate a scene illustration from the latest DM narration. */
export const generateSceneImage = async (
  gameId: number,
): Promise<ImageGenerationResult> => {
  const res = await API.post<ImageGenerationResult>(`/game/${gameId}/images/scene`);
  return res.data;
};

/** Generate an NPC or character portrait. */
export const generatePortraitImage = async (
  gameId: number,
  name: string,
  description = '',
  race = '',
  charClass = '',
): Promise<ImageGenerationResult> => {
  const res = await API.post<ImageGenerationResult>(`/game/${gameId}/images/portrait`, {
    name,
    description,
    race,
    char_class: charClass,
  });
  return res.data;
};

/** List all cached images for this game (gallery). */
export const getGameImages = async (
  gameId: number,
): Promise<ImageGallery> => {
  const res = await API.get<ImageGallery>(`/game/${gameId}/images`);
  return res.data;
};

/** Remove a cached image from the gallery by index. */
export const deleteGameImage = async (
  gameId: number,
  index: number,
): Promise<{ removed: GeneratedImage; remaining_count: number }> => {
  const res = await API.delete(`/game/${gameId}/images/${index}`);
  return res.data;
};

// ---------------------------------------------------------------------------
// Voice Narration (TTS) — AI-generated DM voice (provider-agnostic TTS API)
// ---------------------------------------------------------------------------

/** Check whether voice narration (TTS) is configured. */
export const getTTSStatus = async (
  gameId: number,
): Promise<TTSStatus> => {
  const res = await API.get<TTSStatus>(`/game/${gameId}/tts/status`);
  return res.data;
};

/**
 * Synthesize arbitrary text to speech (one-shot, NOT cached). Returns a
 * playable object URL for the raw audio bytes. Caller must revoke the URL
 * when done to avoid memory leaks.
 */
export const synthesizeSpeech = async (
  gameId: number,
  text: string,
  voice?: string,
): Promise<string> => {
  const res = await API.post(`/game/${gameId}/tts/synthesize`, { text, voice }, {
    responseType: 'blob',
  });
  return URL.createObjectURL(res.data);
};

/**
 * Synthesize (and cache) the latest DM narration — or explicit text. Returns
 * the cached narration metadata; the audio bytes are served by
 * `cachedAudioUrl()`.
 */
export const narrateLatest = async (
  gameId: number,
  voice?: string,
  text?: string,
): Promise<NarrateResult> => {
  const res = await API.post<NarrateResult>(`/game/${gameId}/tts/narrate`, {
    voice,
    text,
  });
  return res.data;
};

/** Build the playable audio URL for a cached narration by its id. */
export const cachedAudioUrl = (gameId: number, audioId: string): string =>
  `/api/game/${gameId}/tts/audio/${audioId}`;

/** List all cached narrations for this game (metadata only). */
export const listCachedAudio = async (
  gameId: number,
): Promise<TTSListResponse> => {
  const res = await API.get<TTSListResponse>(`/game/${gameId}/tts`);
  return res.data;
};

/** Remove a cached narration by its id. */
export const deleteCachedAudio = async (
  gameId: number,
  audioId: string,
): Promise<DeleteAudioResult> => {
  const res = await API.delete<DeleteAudioResult>(`/game/${gameId}/tts/${audioId}`);
  return res.data;
};

