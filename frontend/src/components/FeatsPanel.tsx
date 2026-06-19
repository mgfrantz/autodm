import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  listFeats,
  getCharacterFeats,
  getAvailableFeats,
  learnFeat,
} from '../stores/api'
import type {
  FeatInfo,
  CharacterFeatsResponse,
  LearnFeatResult,
} from '../types'

/* ------------------------------------------------------------------ *
 * Ability display helpers.                                            *
 * ------------------------------------------------------------------ */
const ABILITY_LABELS: Record<string, string> = {
  strength: 'Strength',
  dexterity: 'Dexterity',
  constitution: 'Constitution',
  intelligence: 'Intelligence',
  wisdom: 'Wisdom',
  charisma: 'Charisma',
}

const ABILITY_ABBR: Record<string, string> = {
  strength: 'STR',
  dexterity: 'DEX',
  constitution: 'CON',
  intelligence: 'INT',
  wisdom: 'WIS',
  charisma: 'CHA',
}

type Tone = 'arcane' | 'gold' | 'leaf' | 'blood' | 'parchment'

const TONE_BADGE: Record<Tone, string> = {
  arcane: 'bg-arcane-900/50 text-arcane-300 border-arcane-700/40',
  gold: 'bg-gold-900/40 text-gold-300 border-gold-700/40',
  leaf: 'bg-leaf-900/40 text-leaf-300 border-leaf-700/40',
  blood: 'bg-blood-900/40 text-blood-300 border-blood-700/40',
  parchment: 'bg-parchment-900/60 text-parchment-300 border-parchment-700/40',
}

/** Build readable effect chips for a feat definition. */
function featEffectChips(feat: FeatInfo): { label: string; tone: Tone }[] {
  const chips: { label: string; tone: Tone }[] = []
  for (const [ability, amount] of Object.entries(feat.ability_bonus)) {
    chips.push({ label: `${ABILITY_ABBR[ability] ?? ability} +${amount}`, tone: 'gold' })
  }
  if (feat.ability_bonus_choices.length > 0) {
    const names = feat.ability_bonus_choices.map((a) => ABILITY_ABBR[a] ?? a)
    chips.push({ label: `+1 ${names.join(' or ')}`, tone: 'gold' })
  }
  if (feat.hp_per_level) {
    chips.push({ label: `+${feat.hp_per_level} HP / lvl`, tone: 'leaf' })
  }
  if (feat.initiative_bonus) {
    chips.push({ label: `Initiative +${feat.initiative_bonus}`, tone: 'arcane' })
  }
  if (feat.speed_bonus) {
    chips.push({ label: `Speed +${feat.speed_bonus} ft`, tone: 'arcane' })
  }
  if (feat.ac_bonus) {
    chips.push({ label: `AC +${feat.ac_bonus}`, tone: 'arcane' })
  }
  if (feat.saving_throw_proficiency) {
    const ab = ABILITY_ABBR[feat.saving_throw_proficiency] ?? feat.saving_throw_proficiency
    chips.push({ label: `${ab} save prof`, tone: 'arcane' })
  }
  for (const skill of feat.skill_proficiencies) {
    chips.push({ label: `${skill} skill`, tone: 'leaf' })
  }
  for (const key of Object.keys(feat.combat_modifiers)) {
    chips.push({ label: key.replace(/_/g, ' '), tone: 'blood' })
  }
  return chips
}

/** Human-readable prerequisite string, or null. */
function prerequisiteText(feat: FeatInfo): string | null {
  const pre = feat.prerequisite
  if (!pre) return null
  if (
    pre.min_level <= 1 &&
    Object.keys(pre.min_abilities).length === 0 &&
    !pre.requires_caster &&
    !pre.requires_class &&
    !pre.requires_armor_proficiency
  ) {
    return null
  }
  const parts: string[] = []
  if (pre.min_level > 1) parts.push(`Level ${pre.min_level}+`)
  for (const [ability, min] of Object.entries(pre.min_abilities)) {
    parts.push(`${ABILITY_ABBR[ability] ?? ability} ${min}+`)
  }
  if (pre.requires_caster) parts.push('Spellcasting')
  if (pre.requires_class) parts.push(`${capitalize(pre.requires_class)} class`)
  if (pre.requires_armor_proficiency) {
    parts.push(`${capitalize(pre.requires_armor_proficiency)} armor prof`)
  }
  return parts.join(' · ')
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1)
}

/** Summarize the effects_applied dict on a learned feat into readable chips. */
function learnedEffectChips(effects: Record<string, unknown>): { label: string; tone: Tone }[] {
  const chips: { label: string; tone: Tone }[] = []
  if (effects.initiative_bonus != null) {
    chips.push({ label: `Initiative +${effects.initiative_bonus}`, tone: 'arcane' })
  }
  if (effects.speed_bonus != null) {
    chips.push({ label: `Speed +${effects.speed_bonus} ft`, tone: 'arcane' })
  }
  if (effects.ac_bonus != null) {
    chips.push({ label: `AC +${effects.ac_bonus}`, tone: 'arcane' })
  }
  if (effects.hp_per_level != null) {
    chips.push({ label: `+${effects.hp_per_level} HP / lvl`, tone: 'leaf' })
  }
  if (effects.saving_throw_proficiency) {
    const ab = ABILITY_ABBR[effects.saving_throw_proficiency as string] ?? (effects.saving_throw_proficiency as string)
    chips.push({ label: `${ab} save prof`, tone: 'arcane' })
  }
  const skills = effects.skill_proficiencies
  if (Array.isArray(skills)) {
    for (const skill of skills) chips.push({ label: `${skill} skill`, tone: 'leaf' })
  }
  const notes = effects.notes
  if (Array.isArray(notes)) {
    for (const note of notes) chips.push({ label: String(note), tone: 'parchment' })
  }
  return chips
}

interface Props {
  characterId: number
  /** Called after a feat is learned so the parent can refresh game state. */
  onChanged?: () => void
}

export default function FeatsPanel({ characterId, onChanged }: Props) {
  const [charFeats, setCharFeats] = useState<CharacterFeatsResponse | null>(null)
  const [available, setAvailable] = useState<FeatInfo[]>([])
  const [registry, setRegistry] = useState<FeatInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Available-feats search filter.
  const [availFilter, setAvailFilter] = useState('')
  // Registry browser.
  const [showRegistry, setShowRegistry] = useState(false)
  const [registryFilter, setRegistryFilter] = useState('')

  // Learn flow state.
  const [learningFeat, setLearningFeat] = useState<FeatInfo | null>(null)
  const [chosenAbility, setChosenAbility] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [learnResult, setLearnResult] = useState<LearnFeatResult | null>(null)
  const [learnError, setLearnError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [cf, avail, reg] = await Promise.all([
        getCharacterFeats(characterId),
        getAvailableFeats(characterId),
        listFeats(),
      ])
      setCharFeats(cf)
      setAvailable(avail)
      setRegistry(reg)
    } catch {
      setError('Failed to load feat data')
    }
    setLoading(false)
  }, [characterId])

  useEffect(() => {
    load()
  }, [load])

  const knownNames = useMemo(
    () => new Set((charFeats?.feats ?? []).map((f) => f.name.toLowerCase())),
    [charFeats],
  )

  // The ASI budget drives whether the learn flow is available at all.
  const asiAvailable = charFeats?.asi_available ?? 0

  const openLearn = (feat: FeatInfo) => {
    setLearningFeat(feat)
    setChosenAbility(feat.ability_bonus_choices[0] ?? null)
    setLearnResult(null)
    setLearnError(null)
  }

  const cancelLearn = () => {
    setLearningFeat(null)
    setChosenAbility(null)
    setLearnResult(null)
    setLearnError(null)
  }

  const handleLearn = async () => {
    if (!learningFeat) return
    setBusy(true)
    setLearnError(null)
    setLearnResult(null)
    try {
      const result = await learnFeat(
        characterId,
        learningFeat.name,
        learningFeat.ability_bonus_choices.length > 0 ? chosenAbility ?? undefined : undefined,
      )
      setLearnResult(result)
      // Refresh available + character feats so the UI reflects the new state.
      const [cf, avail] = await Promise.all([
        getCharacterFeats(characterId),
        getAvailableFeats(characterId),
      ])
      setCharFeats(cf)
      setAvailable(avail)
      onChanged?.()
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Failed to learn feat'
      setLearnError(detail)
    }
    setBusy(false)
  }

  if (loading) {
    return (
      <div className="text-parchment-400 animate-pulse text-center py-12">
        Consulting the annals of heroes and legends…
      </div>
    )
  }
  if (error && !charFeats) {
    return (
      <div className="text-center py-8">
        <div className="text-blood-400 mb-3">{error}</div>
        <button className="btn-primary" onClick={load}>
          Retry
        </button>
      </div>
    )
  }
  if (!charFeats) {
    return <div className="text-center py-8 text-parchment-500">No feat data</div>
  }

  // Filtered available feats (respecting the search box).
  const filteredAvailable = available.filter((f) => {
    if (!availFilter.trim()) return true
    const q = availFilter.toLowerCase()
    return (
      f.name.toLowerCase().includes(q) ||
      f.description.toLowerCase().includes(q) ||
      f.source.toLowerCase().includes(q)
    )
  })

  const filteredRegistry = registry.filter((f) => {
    if (!registryFilter.trim()) return true
    const q = registryFilter.toLowerCase()
    return (
      f.name.toLowerCase().includes(q) ||
      f.description.toLowerCase().includes(q) ||
      f.source.toLowerCase().includes(q)
    )
  })

  /* ----------------------------- ASI status ----------------------------- */
  const earned = charFeats.asi_earned
  const used = charFeats.asi_used

  return (
    <div className="space-y-4">
      {/* ASI status card */}
      <div className="bg-parchment-900/60 rounded-lg p-3 border border-gold-800/40 animate-scale-in">
        <div className="flex items-center justify-between mb-1">
          <span className="text-[10px] uppercase text-parchment-500 tracking-wide">
            Ability Score Improvements
          </span>
          <span className="text-[10px] text-gold-300 font-mono font-semibold">
            Level {charFeats.level}
          </span>
        </div>

        <div className="flex items-end gap-2 mb-2">
          <span
            className={`font-fantasy text-3xl leading-none ${
              asiAvailable > 0 ? 'text-gold-300' : 'text-parchment-400'
            }`}
          >
            {asiAvailable}
          </span>
          <span className="text-xs text-parchment-500 mb-0.5">
            ASI{asiAvailable === 1 ? '' : 's'} available to spend
          </span>
        </div>

        {/* Used / earned progress bar */}
        <div className="h-1.5 bg-parchment-900 rounded-full overflow-hidden mb-2">
          <div
            className="h-full bg-gold-500 transition-all duration-300"
            style={{ width: `${earned > 0 ? (used / earned) * 100 : 0}%` }}
          />
        </div>
        <div className="flex items-center justify-between text-[11px] text-parchment-500">
          <span>
            <span className="text-parchment-300 font-semibold">{used}</span> spent of{' '}
            <span className="text-parchment-300 font-semibold">{earned}</span> earned
          </span>
          <span>
            {charFeats.next_asi_level
              ? `Next ASI at level ${charFeats.next_asi_level}`
              : 'No further ASIs'}
          </span>
        </div>

        {asiAvailable > 0 ? (
          <div className="mt-2 bg-gold-900/20 border border-gold-700/30 rounded-md px-2 py-1.5">
            <p className="text-[11px] text-gold-300">
              ✦ You may spend an ASI on a feat (or an ability boost) — choose a
              feat below.
            </p>
          </div>
        ) : (
          <div className="mt-2 bg-parchment-900/40 border border-parchment-800/60 rounded-md px-2 py-1.5">
            <p className="text-[11px] text-parchment-500">
              No ASI available. {charFeats.next_asi_level
                ? `Reach level ${charFeats.next_asi_level} to earn another.`
                : 'Your class grants no further ASIs.'}
            </p>
          </div>
        )}
      </div>

      {/* Learned feats */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs uppercase text-parchment-500 tracking-wide">
            Learned Feats
          </span>
          <span className="text-[10px] text-arcane-300 font-mono font-semibold">
            {charFeats.feats.length}
          </span>
        </div>

        {charFeats.feats.length === 0 ? (
          <div className="bg-parchment-950/40 rounded-lg p-3 border border-parchment-800/60 text-center">
            <p className="text-sm text-parchment-500 italic">
              No feats learned yet.
            </p>
            <p className="text-[11px] text-parchment-600 mt-1">
              Spend an ASI on a feat below to gain new abilities.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {charFeats.feats.map((feat) => {
              const chips = learnedEffectChips(feat.effects_applied)
              const def = registry.find((r) => r.name.toLowerCase() === feat.name.toLowerCase())
              return (
                <div
                  key={feat.name}
                  className="bg-parchment-900/40 rounded-lg p-3 border border-leaf-800/30 animate-slide-up"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-fantasy text-base text-leaf-200">
                      {feat.name}
                    </span>
                    {feat.learned_at_level != null && (
                      <span className="text-[10px] text-parchment-500 font-mono">
                        learned @ L{feat.learned_at_level}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-parchment-400 leading-relaxed mb-2">
                    {feat.description}
                  </p>
                  {chips.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {chips.map((c, i) => (
                        <span
                          key={i}
                          className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] ${TONE_BADGE[c.tone]}`}
                        >
                          {c.label}
                        </span>
                      ))}
                    </div>
                  )}
                  {def && def.notes.length > 0 && (
                    <ul className="mt-2 space-y-0.5">
                      {def.notes.map((note, i) => (
                        <li key={i} className="text-[10px] text-parchment-500">
                          • {note}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Available feats (learn flow) */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs uppercase text-parchment-500 tracking-wide">
            Available Feats
            {asiAvailable === 0 && (
              <span className="text-parchment-600 normal-case ml-1">
                (no ASI to spend)
              </span>
            )}
          </span>
          <input
            type="text"
            value={availFilter}
            onChange={(e) => setAvailFilter(e.target.value)}
            placeholder="Search…"
            className="text-xs bg-parchment-950/60 border border-parchment-800 rounded-md px-2 py-1 text-parchment-200 placeholder:text-parchment-600 focus:outline-none focus:border-arcane-500 w-32 sm:w-40"
          />
        </div>

        {available.length === 0 ? (
          <div className="bg-parchment-950/40 rounded-lg p-3 border border-parchment-800/60 text-center">
            <p className="text-sm text-parchment-500 italic">
              {knownNames.size === registry.length
                ? 'You have mastered every known feat!'
                : 'No feats are currently available to you.'}
            </p>
            <p className="text-[11px] text-parchment-600 mt-1">
              Some feats require minimum ability scores, level, or class features.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {filteredAvailable.map((feat) => (
              <FeatCard
                key={feat.name}
                feat={feat}
                known={false}
                available={asiAvailable > 0}
                onLearn={() => openLearn(feat)}
              />
            ))}
            {filteredAvailable.length === 0 && available.length > 0 && (
              <p className="text-xs text-parchment-600 italic text-center py-2">
                No feats match "{availFilter}".
              </p>
            )}
          </div>
        )}
      </div>

      {/* Learn confirmation flow (inline modal) */}
      {learningFeat && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/80 p-4 animate-overlay-in"
          onClick={cancelLearn}
        >
          <div
            className="panel max-w-md w-full animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-fantasy text-xl text-gold-200">
                Learn: {learningFeat.name}
              </h3>
              <button
                className="text-parchment-400 hover:text-parchment-200 text-2xl leading-none"
                onClick={cancelLearn}
              >
                ×
              </button>
            </div>

            {learnResult ? (
              /* Success result view */
              <div className="space-y-3">
                <div className="bg-leaf-900/30 border border-leaf-700/50 rounded-lg p-3">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="font-fantasy text-leaf-300 text-lg">
                      ✓ {learnResult.feat_name} Learned
                    </span>
                  </div>
                  <p className="text-xs text-parchment-400 mb-2">
                    {learnResult.message}
                  </p>
                  <div className="grid grid-cols-2 gap-2 text-[11px]">
                    {Object.entries(learnResult.ability_changes).length > 0 && (
                      <div className="bg-gold-900/20 border border-gold-700/30 rounded px-2 py-1">
                        <span className="text-parchment-500">Ability: </span>
                        <span className="text-gold-300 font-mono">
                          {Object.entries(learnResult.ability_changes)
                            .map(([a, d]) => `${ABILITY_ABBR[a] ?? a} ${d > 0 ? '+' : ''}${d}`)
                            .join(', ')}
                        </span>
                      </div>
                    )}
                    {learnResult.max_hp_change !== 0 && (
                      <div className="bg-leaf-900/20 border border-leaf-700/30 rounded px-2 py-1">
                        <span className="text-parchment-500">Max HP: </span>
                        <span className="text-leaf-300 font-mono">
                          {learnResult.max_hp > 0 ? '+' : ''}
                          {learnResult.max_hp_change} → {learnResult.max_hp}
                        </span>
                      </div>
                    )}
                    <div className="bg-arcane-900/20 border border-arcane-700/30 rounded px-2 py-1">
                      <span className="text-parchment-500">ASI left: </span>
                      <span className="text-arcane-300 font-mono">
                        {learnResult.asi_available}
                      </span>
                    </div>
                  </div>
                </div>
                <button className="btn-primary w-full" onClick={cancelLearn}>
                  Done
                </button>
              </div>
            ) : (
              /* Confirmation / ability-pick view */
              <div className="space-y-3">
                <p className="text-xs text-parchment-400 leading-relaxed">
                  {learningFeat.description}
                </p>

                {/* Effect chips preview */}
                <div className="flex flex-wrap gap-1">
                  {featEffectChips(learningFeat).map((c, i) => (
                    <span
                      key={i}
                      className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] ${TONE_BADGE[c.tone]}`}
                    >
                      {c.label}
                    </span>
                  ))}
                </div>

                {/* Ability choice for half-feats */}
                {learningFeat.ability_bonus_choices.length > 0 && (
                  <div>
                    <p className="text-[11px] text-parchment-500 uppercase tracking-wide mb-1.5">
                      Choose an ability to increase (+1):
                    </p>
                    <div className="grid grid-cols-2 gap-1.5">
                      {learningFeat.ability_bonus_choices.map((ability) => (
                        <button
                          key={ability}
                          onClick={() => setChosenAbility(ability)}
                          className={`text-sm rounded-md border px-2 py-1.5 transition-all duration-150 ${
                            chosenAbility === ability
                              ? 'border-gold-500 bg-gold-900/50 text-gold-200'
                              : 'border-parchment-700 bg-parchment-900/60 text-parchment-300 hover:border-arcane-500'
                          }`}
                        >
                          {ABILITY_LABELS[ability] ?? ability}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Prerequisite reminder */}
                {prerequisiteText(learningFeat) && (
                  <p className="text-[10px] text-arcane-400/70">
                    Requires: {prerequisiteText(learningFeat)}
                  </p>
                )}

                {learnError && (
                  <div className="bg-blood-900/30 border border-blood-700/50 rounded-md p-2">
                    <p className="text-[11px] text-blood-300">⚠ {learnError}</p>
                  </div>
                )}

                <div className="flex gap-2 pt-1">
                  <button
                    className="btn-primary flex-1"
                    disabled={
                      busy ||
                      (learningFeat.ability_bonus_choices.length > 0 && !chosenAbility)
                    }
                    onClick={handleLearn}
                    title={
                      learningFeat.ability_bonus_choices.length > 0 && !chosenAbility
                        ? 'Choose an ability first'
                        : 'Learn this feat (spends 1 ASI)'
                    }
                  >
                    {busy ? 'Learning…' : 'Learn Feat (−1 ASI)'}
                  </button>
                  <button
                    className="px-3 py-1.5 text-sm rounded-lg border border-parchment-700 text-parchment-400 hover:text-parchment-200 hover:border-parchment-500 transition-colors"
                    onClick={cancelLearn}
                    disabled={busy}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Registry browser */}
      <div className="flex items-center gap-2">
        <div className="flex-1 h-px bg-parchment-800/60" />
        <button
          className="text-xs text-arcane-300/80 hover:text-arcane-200 uppercase tracking-wide transition-colors"
          onClick={() => setShowRegistry((s) => !s)}
        >
          {showRegistry ? '▾ Hide' : '▸ Show'} Feat Compendium
        </button>
        <div className="flex-1 h-px bg-parchment-800/60" />
      </div>

      {showRegistry && (
        <div className="space-y-3 animate-overlay-in">
          <input
            type="text"
            value={registryFilter}
            onChange={(e) => setRegistryFilter(e.target.value)}
            placeholder="Search the compendium…"
            className="w-full text-xs bg-parchment-950/60 border border-parchment-800 rounded-md px-2 py-1.5 text-parchment-200 placeholder:text-parchment-600 focus:outline-none focus:border-arcane-500"
          />
          <div className="space-y-2">
            {filteredRegistry.map((feat) => {
              const known = knownNames.has(feat.name.toLowerCase())
              const isAvailable = available.some(
                (a) => a.name.toLowerCase() === feat.name.toLowerCase(),
              )
              return (
                <FeatCard
                  key={feat.name}
                  feat={feat}
                  known={known}
                  available={isAvailable && asiAvailable > 0}
                  badge={
                    known
                      ? { label: '✓ known', tone: 'leaf' }
                      : isAvailable
                      ? { label: '✦ available', tone: 'gold' }
                      : null
                  }
                  onLearn={() => openLearn(feat)}
                />
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ *
 * Reusable feat card.                                                 *
 * ------------------------------------------------------------------ */
interface FeatCardProps {
  feat: FeatInfo
  known: boolean
  available: boolean
  badge?: { label: string; tone: Tone } | null
  onLearn?: () => void
}

function FeatCard({ feat, known, available, badge, onLearn }: FeatCardProps) {
  const [expanded, setExpanded] = useState(false)
  const chips = featEffectChips(feat)
  const pre = prerequisiteText(feat)

  return (
    <div
      className={`rounded-lg p-3 border transition-colors ${
        known
          ? 'border-leaf-700/40 bg-leaf-900/10'
          : 'border-parchment-800/60 bg-parchment-900/40'
      }`}
    >
      <div className="flex items-start justify-between gap-2 mb-1">
        <button
          onClick={() => setExpanded((e) => !e)}
          className="text-left flex-1 min-w-0"
        >
          <span className="font-fantasy text-sm text-parchment-200 hover:text-arcane-200 transition-colors">
            {feat.name}
          </span>
          <span className="text-[10px] text-parchment-600 ml-1.5">
            {feat.source}
          </span>
        </button>
        {badge && (
          <span
            className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[9px] font-bold uppercase shrink-0 ${TONE_BADGE[badge.tone]}`}
          >
            {badge.label}
          </span>
        )}
      </div>

      <p
        className={`text-xs text-parchment-400 leading-relaxed ${
          expanded ? '' : 'line-clamp-2'
        }`}
      >
        {feat.description}
      </p>

      {expanded && (
        <div className="mt-2 space-y-2 animate-overlay-in">
          {chips.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {chips.map((c, i) => (
                <span
                  key={i}
                  className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] ${TONE_BADGE[c.tone]}`}
                >
                  {c.label}
                </span>
              ))}
            </div>
          )}
          {feat.notes.length > 0 && (
            <ul className="space-y-0.5">
              {feat.notes.map((note, i) => (
                <li key={i} className="text-[10px] text-parchment-500">
                  • {note}
                </li>
              ))}
            </ul>
          )}
          {pre && (
            <p className="text-[10px] text-arcane-400/70">
              Requires: {pre}
            </p>
          )}
        </div>
      )}

      <div className="flex items-center justify-between mt-2 pt-2 border-t border-parchment-800/60">
        <button
          onClick={() => setExpanded((e) => !e)}
          className="text-[10px] text-parchment-500 hover:text-parchment-300 transition-colors"
        >
          {expanded ? '▾ less' : '▸ more'}
        </button>
        {!known && onLearn && (
          <button
            onClick={onLearn}
            disabled={!available}
            className={`text-[11px] px-2 py-0.5 rounded-md border transition-all ${
              available
                ? 'border-gold-600 bg-gold-900/40 text-gold-200 hover:-translate-y-0.5 hover:bg-gold-900/60'
                : 'border-parchment-800 text-parchment-600 cursor-not-allowed'
            }`}
            title={
              available
                ? 'Learn this feat (spends 1 ASI)'
                : 'No ASI available to spend'
            }
          >
            + Learn
          </button>
        )}
      </div>
    </div>
  )
}
