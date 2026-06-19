import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getCharacter,
  getSpellbook,
  initializeSpellbook,
  learnSpell,
  togglePrepareSpell,
  castSpell,
  getSpellRegistry,
} from '../stores/api'
import type {
  Character,
  SpellDetail,
  SpellbookResponse,
  CastSpellResult,
} from '../types'

/* ------------------------------------------------------------------ *
 * Static helpers                                                      *
 * ------------------------------------------------------------------ */

const ABILITY_SCORE: Record<string, keyof Character> = {
  str: 'strength',
  dex: 'dexterity',
  con: 'constitution',
  int: 'intelligence',
  wis: 'wisdom',
  cha: 'charisma',
}

const ABILITY_LABEL: Record<string, string> = {
  str: 'STR',
  dex: 'DEX',
  con: 'CON',
  int: 'INT',
  wis: 'WIS',
  cha: 'CHA',
}

const CASTER_TYPE_LABEL: Record<string, string> = {
  full: 'Full Caster',
  half: 'Half Caster',
  third: 'Third Caster',
  none: 'Non-Caster',
}

/** Per-school badge styling. */
const SCHOOL_BADGE: Record<string, string> = {
  abjuration: 'bg-sky-900/40 text-sky-300 border-sky-700/40',
  conjuration: 'bg-amber-900/40 text-amber-300 border-amber-700/40',
  divination: 'bg-violet-900/40 text-violet-300 border-violet-700/40',
  enchantment: 'bg-rose-900/40 text-rose-300 border-rose-700/40',
  evocation: 'bg-blood-900/40 text-blood-300 border-blood-700/40',
  illusion: 'bg-fuchsia-900/40 text-fuchsia-300 border-fuchsia-700/40',
  necromancy: 'bg-emerald-900/40 text-emerald-300 border-emerald-700/40',
  transmutation: 'bg-leaf-900/40 text-leaf-300 border-leaf-700/40',
}

const schoolBadge = (school: string): string =>
  SCHOOL_BADGE[school] ?? 'bg-parchment-900/50 text-parchment-300 border-parchment-700/40'

const abilityMod = (score: number): number => Math.floor((score - 10) / 2)
const profBonus = (level: number): number => Math.floor((level - 1) / 4) + 2

/** "Cantrip" | "Level N" label for a spell level. */
const levelLabel = (level: number): string => (level === 0 ? 'Cantrip' : `Level ${level}`)

/** Short ordinal-ish level tag e.g. "0" / "1st" / "2nd" / "3rd". */
const levelTag = (level: number): string => {
  if (level === 0) return 'Cantrip'
  if (level === 1) return '1st'
  if (level === 2) return '2nd'
  if (level === 3) return '3rd'
  return `${level}th`
}

/** One-line mechanical summary of a spell's effect. */
function effectSummary(spell: SpellDetail): string {
  const parts: string[] = []
  if (spell.damage_dice_count > 0 && spell.damage_dice_sides > 0) {
    const dmg = `${spell.damage_dice_count}d${spell.damage_dice_sides}`
    parts.push(spell.damage_bonus
      ? `${dmg}${spell.damage_bonus > 0 ? '+' : ''}${spell.damage_bonus} ${spell.damage_type}`
      : `${dmg} ${spell.damage_type}`)
  }
  if (spell.healing_dice_count > 0 && spell.healing_dice_sides > 0) {
    parts.push(`heal ${spell.healing_dice_count}d${spell.healing_dice_sides}`)
  }
  if (spell.requires_attack_roll) parts.push('spell attack')
  if (spell.save_ability) parts.push(`${spell.save_ability.toUpperCase()} save`)
  if (parts.length === 0) return 'Utility'
  return parts.join(' · ')
}

/** Component-icons string (V/S/M) for compact display. */
const componentChips = (spell: SpellDetail): string[] => {
  const out: string[] = []
  if (spell.parsed_components.verbal) out.push('V')
  if (spell.parsed_components.somatic) out.push('S')
  if (spell.parsed_components.material) out.push('M')
  return out
}

interface Props {
  characterId: number
  /** Active conditions (e.g. from the scene) that may block spell components. */
  activeConditions?: string[]
  /** Called after a cast / learn / prepare so the parent can refresh game state. */
  onChanged?: () => void
}

interface CastConfig {
  spell: SpellDetail
  slotLevel: number
  targetAc: number
  targetSaveTotal: number
}

export default function SpellsPanel({ characterId, activeConditions = [], onChanged }: Props) {
  const [spellbook, setSpellbook] = useState<SpellbookResponse | null>(null)
  const [character, setCharacter] = useState<Character | null>(null)
  const [registry, setRegistry] = useState<SpellDetail[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [castConfig, setCastConfig] = useState<CastConfig | null>(null)
  const [castResult, setCastResult] = useState<CastSpellResult | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [showLearn, setShowLearn] = useState(false)
  const [levelFilter, setLevelFilter] = useState<number | 'all'>('all')
  const [schoolFilter, setSchoolFilter] = useState<string>('all')
  const [search, setSearch] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [book, char, reg] = await Promise.all([
        getSpellbook(characterId),
        getCharacter(characterId),
        getSpellRegistry(),
      ])
      setSpellbook(book)
      setCharacter(char)
      setRegistry(reg)
    } catch {
      setError('Failed to load spellbook')
    }
    setLoading(false)
  }, [characterId])

  useEffect(() => {
    load()
  }, [load])

  // Casting-derived stats, computed client-side to mirror the backend engine.
  const castingMod = useMemo(() => {
    if (!character || !spellbook) return 0
    const field = ABILITY_SCORE[spellbook.casting_ability]
    if (!field) return 0
    return abilityMod((character[field] as number) ?? 10)
  }, [character, spellbook])

  const spellAttackBonus = useMemo(
    () => (spellbook ? profBonus(spellbook.level) + castingMod : 0),
    [spellbook, castingMod],
  )
  const spellSaveDc = useMemo(() => 8 + spellAttackBonus, [spellAttackBonus])

  // id -> detail lookup across the whole registry (for known-but-unprepared).
  const byId = useMemo<Record<string, SpellDetail>>(() => {
    const map: Record<string, SpellDetail> = {}
    for (const s of registry) map[s.id] = s
    return map
  }, [registry])

  const isCaster = spellbook ? spellbook.caster_type !== 'none' : false

  // Slot levels (1-9) that have any capacity, for the slot tracker.
  const activeSlots = useMemo(
    () => (spellbook ? spellbook.slots.filter((s) => s.max > 0) : []),
    [spellbook],
  )

  const hasAnySlots = activeSlots.some((s) => s.available > 0)

  // Castable spells grouped by level (cantrips, then 1..9).
  const groupedCastable = useMemo(() => {
    const groups = new Map<number, SpellDetail[]>()
    if (!spellbook) return groups
    for (const s of spellbook.castable_spells) {
      const arr = groups.get(s.level) ?? []
      arr.push(s)
      groups.set(s.level, arr)
    }
    return groups
  }, [spellbook])

  const groupLevels = useMemo(
    () => Array.from(groupedCastable.keys()).sort((a, b) => a - b),
    [groupedCastable],
  )

  /** Known spells that are NOT currently castable (prepared casters' unprepared). */
  const unpreparedKnown = useMemo<SpellDetail[]>(() => {
    if (!spellbook || spellbook.casting_style !== 'prepared') return []
    const castableIds = new Set(spellbook.castable_spells.map((s) => s.id))
    return spellbook.known_spells
      .map((id) => byId[id])
      .filter((s): s is SpellDetail => Boolean(s) && !castableIds.has(s.id))
  }, [spellbook, byId])

  // --- Actions ----------------------------------------------------------

  const refreshBook = async () => {
    const book = await getSpellbook(characterId)
    setSpellbook(book)
  }

  const openCast = (spell: SpellDetail) => {
    setCastResult(null)
    let slot = spell.level
    if (!spell.level) {
      slot = 0
    } else {
      // Default to the lowest available slot at or above the spell's level.
      const avail = activeSlots.find(
        (s) => s.level >= spell.level && s.available > 0,
      )
      slot = avail ? avail.level : spell.level
    }
    setCastConfig({ spell, slotLevel: slot, targetAc: 12, targetSaveTotal: 10 })
  }

  const cancelCast = () => {
    setCastConfig(null)
    setCastResult(null)
  }

  const handleCast = async () => {
    if (!castConfig) return
    const { spell } = castConfig
    setBusy(true)
    setError(null)
    setCastResult(null)
    try {
      const payload: Parameters<typeof castSpell>[1] = {
        spell_id: spell.id,
        caster_mod: castingMod,
        active_conditions: activeConditions,
      }
      if (spell.level > 0) payload.slot_level = castConfig.slotLevel
      if (spell.requires_attack_roll) payload.target_ac = castConfig.targetAc
      if (spell.save_ability) payload.target_save_total = castConfig.targetSaveTotal

      const result = await castSpell(characterId, payload)
      setCastResult(result)
      await refreshBook()
      onChanged?.()
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Failed to cast spell'
      setError(detail)
    }
    setBusy(false)
  }

  const handleInitialize = async () => {
    setBusy(true)
    setError(null)
    try {
      const book = await initializeSpellbook(characterId)
      setSpellbook(book)
      setNotice('Spellbook initialized with starting spells for your class.')
      onChanged?.()
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Failed to initialize spellbook'
      setError(detail)
    }
    setBusy(false)
  }

  const handleTogglePrepare = async (spellId: string) => {
    setBusy(true)
    setError(null)
    try {
      const book = await togglePrepareSpell(characterId, spellId)
      setSpellbook(book)
      onChanged?.()
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Failed to change preparation'
      setError(detail)
    }
    setBusy(false)
  }

  const handleLearn = async (spellId: string) => {
    setBusy(true)
    setError(null)
    try {
      const book = await learnSpell(characterId, spellId)
      setSpellbook(book)
      const name = byId[spellId]?.name ?? spellId
      setNotice(`Learned ${name}.`)
      onChanged?.()
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Failed to learn spell'
      setError(detail)
    }
    setBusy(false)
  }

  // --- Render: states ---------------------------------------------------

  if (loading) {
    return (
      <div className="text-parchment-400 animate-pulse text-center py-12">
        Gathering arcane sigils and incantations…
      </div>
    )
  }
  if (error && !spellbook) {
    return (
      <div className="text-center py-8">
        <div className="text-blood-400 mb-3">{error}</div>
        <button className="btn-primary" onClick={load}>Retry</button>
      </div>
    )
  }
  if (!spellbook) {
    return <div className="text-center py-8 text-parchment-500">No spellbook data</div>
  }

  // Non-caster class.
  if (!isCaster) {
    return (
      <div className="space-y-4">
        <div className="bg-parchment-900/60 rounded-lg p-4 border border-parchment-800/60 text-center animate-scale-in">
          <div className="text-4xl mb-2">⚔️</div>
          <p className="text-parchment-200 font-semibold">
            {spellbook.char_class.charAt(0).toUpperCase() + spellbook.char_class.slice(1)}s don&apos;t cast spells.
          </p>
          <p className="text-xs text-parchment-500 mt-1 leading-relaxed">
            This class relies on martial prowess, not magic. multiclass into a
            caster or create a new arcane/divine character to weave spells.
          </p>
        </div>
        <LearnableRegistry
          show={showLearn}
          setShow={setShowLearn}
          registry={registry}
          knownIds={new Set(spellbook.known_spells)}
          levelFilter={levelFilter}
          setLevelFilter={setLevelFilter}
          schoolFilter={schoolFilter}
          setSchoolFilter={setSchoolFilter}
          search={search}
          setSearch={setSearch}
          busy={busy}
          onLearn={handleLearn}
        />
      </div>
    )
  }

  // Caster with an empty spellbook — offer initialization.
  const isEmpty = spellbook.known_spells.length === 0 && spellbook.prepared_spells.length === 0

  return (
    <div className="space-y-4">
      {/* Overview card */}
      <div className="bg-parchment-900/60 rounded-lg p-3 border border-arcane-800/40 animate-scale-in">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
          <div className="flex items-center gap-2">
            <span className="font-fantasy text-arcane-200 text-lg">
              {CASTER_TYPE_LABEL[spellbook.caster_type] ?? 'Caster'}
            </span>
            <span className="text-[10px] uppercase text-parchment-500 tracking-wide border border-parchment-700/60 rounded px-1.5 py-0.5">
              {spellbook.casting_style === 'prepared' ? 'Prepared' : spellbook.casting_style === 'known' ? 'Known' : ''}
            </span>
          </div>
          <span className="text-[10px] text-parchment-500">
            Spell attack <span className="text-arcane-300 font-mono font-semibold">+{spellAttackBonus}</span>
            {' · '}
            Save DC <span className="text-arcane-300 font-mono font-semibold">{spellSaveDc}</span>
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-parchment-500">
          <span>Casting ability <span className="text-parchment-300 font-semibold">{ABILITY_LABEL[spellbook.casting_ability] ?? spellbook.casting_ability.toUpperCase()}</span> ({castingMod >= 0 ? '+' : ''}{castingMod})</span>
          <span>Level <span className="text-parchment-300 font-semibold">{spellbook.level}</span></span>
          <span>{spellbook.known_spells.length} known</span>
          {spellbook.casting_style === 'prepared' && (
            <span>{spellbook.prepared_spells.length} prepared</span>
          )}
        </div>
      </div>

      {/* Spell slots tracker */}
      {activeSlots.length > 0 && (
        <div className="bg-parchment-950/40 rounded-lg p-3 border border-parchment-800/60">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs uppercase text-parchment-500 tracking-wide">Spell Slots</span>
            <span className={`text-[10px] font-mono font-semibold ${hasAnySlots ? 'text-arcane-300' : 'text-blood-400'}`}>
              {hasAnySlots ? 'slots available' : 'all expended — rest to recover'}
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
            {activeSlots.map((s) => {
              const pips = Array.from({ length: s.max }, (_, i) => i < s.available)
              return (
                <div key={s.level} className="flex items-center gap-2">
                  <span className="text-[10px] text-parchment-500 w-8 shrink-0">{levelTag(s.level)}</span>
                  <div className="flex gap-1 flex-1">
                    {pips.map((filled, i) => (
                      <span
                        key={i}
                        title={filled ? 'Available' : 'Expended'}
                        className={`w-3.5 h-3.5 rounded-sm border transition-colors ${
                          filled
                            ? 'bg-arcane-500 border-arcane-400 shadow-[0_0_4px] shadow-arcane-500/50'
                            : 'bg-parchment-900 border-parchment-700/60'
                        }`}
                      />
                    ))}
                    <span className="text-[10px] text-parchment-500 ml-1 font-mono">
                      {s.available}/{s.max}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {notice && (
        <div className="bg-arcane-900/30 border border-arcane-700/50 rounded-md p-2 text-[11px] text-arcane-200 animate-scale-in">
          ✦ {notice}
        </div>
      )}
      {error && (
        <div className="bg-blood-900/30 border border-blood-700/50 rounded-md p-2 text-[11px] text-blood-300">
          ⚠ {error}
        </div>
      )}

      {/* Empty spellbook */}
      {isEmpty ? (
        <div className="bg-parchment-900/40 rounded-lg p-4 border border-parchment-800/60 text-center">
          <p className="text-parchment-300 mb-1">Your spellbook is empty.</p>
          <p className="text-xs text-parchment-500 mb-3">
            Initialize the starting spells granted to a level {spellbook.level} {spellbook.char_class}.
          </p>
          <button className="btn-primary" disabled={busy} onClick={handleInitialize}>
            {busy ? 'Initializing…' : '✦ Initialize Starting Spells'}
          </button>
        </div>
      ) : (
        <>
          {/* Cast console */}
          {castConfig && (
            <CastConsole
              config={castConfig}
              setConfig={setCastConfig}
              activeSlots={activeSlots}
              saveDc={spellSaveDc}
              attackBonus={spellAttackBonus}
              busy={busy}
              result={castResult}
              onCast={handleCast}
              onCancel={cancelCast}
            />
          )}

          {/* Castable spells, grouped by level */}
          <div className="space-y-4">
            {groupLevels.map((lvl) => (
              <div key={lvl}>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs uppercase text-arcane-300/80 tracking-wide font-semibold">
                    {levelLabel(lvl)}
                  </span>
                  <div className="flex-1 h-px bg-arcane-800/40" />
                  <span className="text-[10px] text-parchment-600">
                    {groupedCastable.get(lvl)!.length}
                  </span>
                </div>
                <div className="grid grid-cols-1 gap-2">
                  {groupedCastable.get(lvl)!.map((spell) => (
                    <SpellCard
                      key={spell.id}
                      spell={spell}
                      expanded={expandedId === spell.id}
                      onToggleExpand={() => setExpandedId((p) => (p === spell.id ? null : spell.id))}
                      isPrepared={spellbook.casting_style === 'prepared' && spell.level > 0
                        ? spellbook.prepared_spells.includes(spell.id)
                        : null}
                      canCast={
                        spell.level === 0
                          ? true
                          : activeSlots.some((s) => s.level >= spell.level && s.available > 0)
                      }
                      busy={busy}
                      onCast={() => openCast(spell)}
                      onTogglePrepare={() => handleTogglePrepare(spell.id)}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Prepared-spell management for prepared casters */}
          {unpreparedKnown.length > 0 && (
            <div className="bg-parchment-950/40 rounded-lg p-3 border border-parchment-800/60">
              <div className="text-xs uppercase text-parchment-500 tracking-wide mb-2">
                Known but Unprepared
              </div>
              <div className="flex flex-wrap gap-1.5">
                {unpreparedKnown.map((spell) => (
                  <button
                    key={spell.id}
                    disabled={busy}
                    onClick={() => handleTogglePrepare(spell.id)}
                    title={`${spell.name} — click to prepare`}
                    className="inline-flex items-center gap-1 rounded-md border border-parchment-700 bg-parchment-900/60 px-2 py-1 text-xs text-parchment-300 hover:border-arcane-500 hover:-translate-y-0.5 transition-all disabled:opacity-40"
                  >
                    + {spell.name}
                  </button>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* Learnable registry */}
      <LearnableRegistry
        show={showLearn}
        setShow={setShowLearn}
        registry={registry}
        knownIds={new Set([...spellbook.known_spells, ...spellbook.prepared_spells])}
        levelFilter={levelFilter}
        setLevelFilter={setLevelFilter}
        schoolFilter={schoolFilter}
        setSchoolFilter={setSchoolFilter}
        search={search}
        setSearch={setSearch}
        busy={busy}
        onLearn={handleLearn}
      />
    </div>
  )
}

/* ------------------------------------------------------------------ *
 * SpellCard sub-component                                             *
 * ------------------------------------------------------------------ */

interface SpellCardProps {
  spell: SpellDetail
  expanded: boolean
  onToggleExpand: () => void
  isPrepared: boolean | null
  canCast: boolean
  busy: boolean
  onCast: () => void
  onTogglePrepare: () => void
}

function SpellCard({
  spell,
  expanded,
  onToggleExpand,
  isPrepared,
  canCast,
  busy,
  onCast,
  onTogglePrepare,
}: SpellCardProps) {
  return (
    <div
      className={`rounded-lg p-2.5 border transition-colors ${
        isPrepared === false
          ? 'border-parchment-800/60 bg-parchment-900/30'
          : 'border-arcane-800/40 bg-parchment-900/50'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <button
          onClick={onToggleExpand}
          className="flex-1 min-w-0 text-left"
          title={expanded ? 'Collapse' : 'Expand details'}
        >
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-sm font-semibold text-parchment-100">{spell.name}</span>
            <span className={`text-[9px] uppercase rounded border px-1 py-0.5 ${schoolBadge(spell.school)}`}>
              {spell.school}
            </span>
            {spell.concentration && (
              <span className="text-[9px] text-arcane-400 uppercase" title="Concentration">◉ conc</span>
            )}
            {spell.ritual && (
              <span className="text-[9px] text-gold-400 uppercase" title="Ritual">✦ ritual</span>
            )}
          </div>
          <div className="text-[11px] text-parchment-500 mt-0.5">
            {effectSummary(spell)} · {spell.range} · {spell.casting_time}
          </div>
        </button>
        <div className="flex items-center gap-1.5 shrink-0">
          {isPrepared !== null && spell.level > 0 && (
            <button
              onClick={onTogglePrepare}
              disabled={busy}
              title={isPrepared ? 'Unprepare' : 'Prepare'}
              className={`text-[10px] px-1.5 py-1 rounded border transition-colors disabled:opacity-40 ${
                isPrepared
                  ? 'border-leaf-700/50 bg-leaf-900/40 text-leaf-300'
                  : 'border-parchment-700 bg-parchment-900/60 text-parchment-400 hover:border-arcane-500'
              }`}
            >
              {isPrepared ? '✓ prep' : '+ prep'}
            </button>
          )}
          <button
            onClick={onCast}
            disabled={busy || !canCast}
            title={canCast ? 'Cast this spell' : 'No slots available — rest to recover'}
            className="text-xs px-2.5 py-1 rounded-md border border-arcane-500 bg-arcane-900/50 text-arcane-200 hover:bg-arcane-800/60 hover:-translate-y-0.5 transition-all disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:translate-y-0"
          >
            Cast
          </button>
        </div>
      </div>

      {expanded && (
        <div className="mt-2 pt-2 border-t border-parchment-800/60 space-y-1.5 animate-overlay-in">
          <p className="text-[11px] text-parchment-400 leading-relaxed">{spell.description}</p>
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-parchment-500">
            <span>Duration: <span className="text-parchment-300">{spell.duration}</span></span>
            <span>
              Components:{' '}
              <span className="text-parchment-300">
                {componentChips(spell).join(', ') || 'none'}
              </span>
            </span>
            {spell.parsed_components.material && spell.material_description && (
              <span className="text-gold-400/80">M: {spell.material_description}</span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ *
 * CastConsole sub-component                                           *
 * ------------------------------------------------------------------ */

interface CastConsoleProps {
  config: CastConfig
  setConfig: React.Dispatch<React.SetStateAction<CastConfig | null>>
  activeSlots: { level: number; available: number; max: number }[]
  saveDc: number
  attackBonus: number
  busy: boolean
  result: CastSpellResult | null
  onCast: () => void
  onCancel: () => void
}

function CastConsole({
  config,
  setConfig,
  activeSlots,
  saveDc,
  attackBonus,
  busy,
  result,
  onCast,
  onCancel,
}: CastConsoleProps) {
  const { spell } = config
  const isCantrip = spell.level === 0

  // Valid slot levels for upcasting this spell (>= base level, with availability).
  const upcastLevels = activeSlots
    .filter((s) => s.level >= spell.level && s.available > 0)
    .map((s) => s.level)

  const needsAttack = spell.requires_attack_roll
  const needsSave = Boolean(spell.save_ability)

  return (
    <div className="bg-arcane-950/40 rounded-lg p-3 border border-arcane-700/50 animate-scale-in">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-fantasy text-arcane-200">
          ✦ Casting: {spell.name}
        </span>
        <button
          onClick={onCancel}
          className="text-parchment-500 hover:text-parchment-300 text-lg leading-none"
          title="Cancel"
        >
          ×
        </button>
      </div>

      <div className="space-y-2">
        {/* Slot level (leveled spells only) */}
        {!isCantrip && (
          <div>
            <label className="text-[10px] uppercase text-parchment-500 tracking-wide block mb-1">
              Spell Slot Level
            </label>
            {upcastLevels.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {upcastLevels.map((lvl) => (
                  <button
                    key={lvl}
                    onClick={() => setConfig((p) => (p ? { ...p, slotLevel: lvl } : p))}
                    className={`text-xs px-2 py-1 rounded-md border transition-colors ${
                      config.slotLevel === lvl
                        ? 'border-arcane-400 bg-arcane-800/60 text-arcane-100'
                        : 'border-parchment-700 bg-parchment-900/60 text-parchment-300 hover:border-arcane-500'
                    }`}
                  >
                    {levelTag(lvl)}
                    {lvl > spell.level && <span className="text-gold-400 text-[9px] ml-1">↑</span>}
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-blood-400">
                No slots of level {levelTag(spell.level)} or higher remain. Rest to recover slots.
              </p>
            )}
          </div>
        )}

        {/* Attack-roll target AC */}
        {needsAttack && (
          <div className="flex items-center justify-between">
            <label className="text-[11px] text-parchment-400">
              Target AC{' '}
              <span className="text-parchment-600">(attack +{attackBonus})</span>
            </label>
            <input
              type="number"
              min={1}
              max={35}
              value={config.targetAc}
              onChange={(e) => setConfig((p) => (p ? { ...p, targetAc: Number(e.target.value) } : p))}
              className="w-16 bg-parchment-900 border border-parchment-700 rounded px-2 py-1 text-sm text-parchment-100 text-center focus:border-arcane-500 focus:outline-none"
            />
          </div>
        )}

        {/* Saving-throw target total */}
        {needsSave && (
          <div className="flex items-center justify-between">
            <label className="text-[11px] text-parchment-400">
              Target {spell.save_ability!.toUpperCase()} Save{' '}
              <span className="text-parchment-600">(DC {saveDc})</span>
            </label>
            <input
              type="number"
              min={1}
              max={40}
              value={config.targetSaveTotal}
              onChange={(e) => setConfig((p) => (p ? { ...p, targetSaveTotal: Number(e.target.value) } : p))}
              className="w-16 bg-parchment-900 border border-parchment-700 rounded px-2 py-1 text-sm text-parchment-100 text-center focus:border-arcane-500 focus:outline-none"
            />
          </div>
        )}

        {/* Cast / result */}
        <div className="flex gap-2 pt-1">
          <button
            className="btn-primary flex-1"
            disabled={busy || (!isCantrip && upcastLevels.length === 0)}
            onClick={onCast}
          >
            {busy ? 'Casting…' : `Cast ${spell.name}`}
          </button>
        </div>

        {result && <CastResultBox result={result} saveDc={saveDc} targetAc={config.targetAc} />}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ *
 * CastResultBox sub-component                                         *
 * ------------------------------------------------------------------ */

function CastResultBox({
  result,
  saveDc,
  targetAc,
}: {
  result: CastSpellResult
  saveDc: number
  targetAc: number
}) {
  if (!result.success) {
    return (
      <div className="bg-blood-900/30 border border-blood-700/50 rounded-md p-2 text-[11px] text-blood-300">
        ⚠ {result.message}
      </div>
    )
  }
  const lines: string[] = []
  if (result.rolled_attack !== null && result.hit !== null) {
    lines.push(`Attack roll ${result.rolled_attack} vs AC ${targetAc} → ${result.hit ? '✅ HIT' : '❌ MISS'}`)
  }
  if (result.made_save !== null) {
    lines.push(`Target save vs DC ${saveDc} → ${result.made_save ? 'made (half damage)' : 'failed (full damage)'}`)
  }
  if (result.damage > 0) {
    lines.push(`💥 ${result.damage} ${result.damage_type} damage`)
  }
  if (result.healing > 0) {
    lines.push(`✨ ${result.healing} HP restored`)
  }
  if (lines.length === 0) {
    lines.push(result.message || 'The spell takes effect.')
  }
  return (
    <div className="bg-arcane-900/30 border border-arcane-700/40 rounded-md p-2 space-y-0.5 animate-scale-in">
      {lines.map((l, i) => (
        <p key={i} className="text-[11px] text-arcane-100 leading-relaxed">{l}</p>
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ *
 * LearnableRegistry sub-component                                     *
 * ------------------------------------------------------------------ */

interface LearnableRegistryProps {
  show: boolean
  setShow: (v: boolean) => void
  registry: SpellDetail[]
  knownIds: Set<string>
  levelFilter: number | 'all'
  setLevelFilter: (v: number | 'all') => void
  schoolFilter: string
  setSchoolFilter: (v: string) => void
  search: string
  setSearch: (v: string) => void
  busy: boolean
  onLearn: (id: string) => void
}

function LearnableRegistry({
  show,
  setShow,
  registry,
  knownIds,
  levelFilter,
  setLevelFilter,
  schoolFilter,
  setSchoolFilter,
  search,
  setSearch,
  busy,
  onLearn,
}: LearnableRegistryProps) {
  const schools = useMemo(
    () => Array.from(new Set(registry.map((s) => s.school))).sort(),
    [registry],
  )

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return registry.filter((s) => {
      if (levelFilter !== 'all' && s.level !== levelFilter) return false
      if (schoolFilter !== 'all' && s.school !== schoolFilter) return false
      if (q && !s.name.toLowerCase().includes(q) && !s.description.toLowerCase().includes(q)) return false
      return true
    })
  }, [registry, levelFilter, schoolFilter, search])

  return (
    <>
      <div className="flex items-center gap-2">
        <div className="flex-1 h-px bg-parchment-800/60" />
        <button
          className="text-xs text-arcane-300/80 hover:text-arcane-200 uppercase tracking-wide transition-colors"
          onClick={() => setShow(!show)}
        >
          {show ? '▾ Hide' : '▸ Show'} Spell Library ({registry.length})
        </button>
        <div className="flex-1 h-px bg-parchment-800/60" />
      </div>

      {show && (
        <div className="space-y-3 animate-overlay-in">
          {/* Filters */}
          <div className="flex flex-wrap gap-2">
            <select
              value={String(levelFilter)}
              onChange={(e) =>
                setLevelFilter(e.target.value === 'all' ? 'all' : Number(e.target.value))
              }
              className="bg-parchment-900 border border-parchment-700 rounded px-2 py-1 text-xs text-parchment-200 focus:border-arcane-500 focus:outline-none"
            >
              <option value="all">All Levels</option>
              <option value="0">Cantrips</option>
              {Array.from({ length: 9 }, (_, i) => i + 1).map((lvl) => (
                <option key={lvl} value={lvl}>{levelTag(lvl)} Level</option>
              ))}
            </select>
            <select
              value={schoolFilter}
              onChange={(e) => setSchoolFilter(e.target.value)}
              className="bg-parchment-900 border border-parchment-700 rounded px-2 py-1 text-xs text-parchment-200 focus:border-arcane-500 focus:outline-none"
            >
              <option value="all">All Schools</option>
              {schools.map((sc) => (
                <option key={sc} value={sc} className="capitalize">{sc}</option>
              ))}
            </select>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search spells…"
              className="flex-1 min-w-[120px] bg-parchment-900 border border-parchment-700 rounded px-2 py-1 text-xs text-parchment-200 placeholder:text-parchment-600 focus:border-arcane-500 focus:outline-none"
            />
          </div>

          {/* Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-[320px] overflow-y-auto pr-1">
            {filtered.length === 0 ? (
              <p className="text-xs text-parchment-500 italic col-span-full text-center py-4">
                No spells match your filters.
              </p>
            ) : (
              filtered.map((s) => {
                const known = knownIds.has(s.id)
                return (
                  <div
                    key={s.id}
                    className={`rounded-lg p-2 border ${
                      known
                        ? 'border-leaf-700/40 bg-leaf-900/15'
                        : 'border-parchment-800/60 bg-parchment-900/40'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 mb-0.5">
                      <span className="text-xs font-semibold text-parchment-200 truncate">{s.name}</span>
                      <div className="flex items-center gap-1 shrink-0">
                        <span className="text-[9px] text-parchment-500">{levelTag(s.level)}</span>
                        <span className={`text-[9px] uppercase rounded border px-1 ${schoolBadge(s.school)}`}>
                          {s.school}
                        </span>
                      </div>
                    </div>
                    <p className="text-[10px] text-parchment-500 leading-snug line-clamp-2 mb-1.5">
                      {effectSummary(s)} · {s.range}
                    </p>
                    {known ? (
                      <span className="text-[10px] text-leaf-400 font-semibold uppercase">✓ Known</span>
                    ) : (
                      <button
                        onClick={() => onLearn(s.id)}
                        disabled={busy}
                        className="text-[10px] px-2 py-0.5 rounded border border-gold-600/50 bg-gold-900/30 text-gold-300 hover:bg-gold-800/40 transition-colors disabled:opacity-40"
                      >
                        + Learn
                      </button>
                    )}
                  </div>
                )
              })
            )}
          </div>
        </div>
      )}
    </>
  )
}
