import { useEffect, useRef, useState } from 'react'
import {
  getEnvironment,
  getEnvironmentRegistry,
  previewEnvironmentEffects,
  rollEnvironmentWeather,
  setEnvironment,
} from '../stores/api'
import type {
  EnvironmentEffects,
  EnvironmentRegistry,
  EnvironmentResponse,
  EnvironmentRollResult,
  SceneEnvironment,
} from '../types'

/* ------------------------------------------------------------------ *
 * Friendly presentation helpers — snake_case -> human label + icon.  *
 * ------------------------------------------------------------------ */

const WEATHER_ICON: Record<string, string> = {
  clear: '☀️',
  light_rain: '🌦️',
  heavy_rain: '🌧️',
  light_snow: '🌨️',
  heavy_snow: '❄️',
  blizzard: '🥶',
  fog: '🌫️',
  strong_wind: '💨',
  storm: '⛈️',
}
const LIGHT_ICON: Record<string, string> = { bright: '☀️', dim: '🌆', darkness: '🌑' }
const TIME_ICON: Record<string, string> = { dawn: '🌅', day: '🌞', dusk: '🌇', night: '🌙' }
const TEMP_ICON: Record<string, string> = {
  normal: '🌡️',
  cold: '🧊',
  extreme_cold: '🥶',
  heat: '🔥',
  extreme_heat: '🥵',
}
const TERRAIN_ICON: Record<string, string> = {
  normal: '🟫',
  difficult: '🪨',
  heavy_difficult: '🌵',
  ice: '❄️',
  rubble: '🧱',
  undergrowth: '🌿',
  water: '🌊',
  cliff: '⛰️',
}

function titleCase(id: string): string {
  return id
    .split('_')
    .map((w) => (w ? w.charAt(0).toUpperCase() + w.slice(1) : ''))
    .join(' ')
}

function iconFor(kind: 'light' | 'weather' | 'terrain' | 'temperature' | 'time', value: string): string {
  switch (kind) {
    case 'light':
      return LIGHT_ICON[value] ?? '🔆'
    case 'weather':
      return WEATHER_ICON[value] ?? '🌥️'
    case 'terrain':
      return TERRAIN_ICON[value] ?? '🗺️'
    case 'temperature':
      return TEMP_ICON[value] ?? '🌡️'
    case 'time':
      return TIME_ICON[value] ?? '🕐'
  }
}

/* ------------------------------------------------------------------ *
 * Client-side combat-modifier derivation — mirrors the backend        *
 * environment.combat_modifiers() exactly (engine/environment.py).     *
 * Derived purely from the EnvironmentEffects booleans, so the preview *
 * updates live as the draft changes with no extra round-trip.         *
 * ------------------------------------------------------------------ */

interface DerivedModifiers {
  attacker_ranged_disadvantage: boolean
  attacker_melee_disadvantage: boolean
  attacker_cannot_see_target: boolean
  target_unseen_by_attacker: boolean
  attacker_unseen_advantage: boolean
}

function deriveModifiers(e: EnvironmentEffects, ranged: boolean): DerivedModifiers {
  const heavily = e.heavily_obscured
  return {
    attacker_ranged_disadvantage: e.ranged_attack_disadvantage && ranged,
    attacker_melee_disadvantage: heavily,
    attacker_cannot_see_target: heavily,
    target_unseen_by_attacker: heavily,
    attacker_unseen_advantage: heavily,
  }
}

type AttackOutcome = 'advantage' | 'disadvantage' | 'straight' | 'normal'

function netOutcome(m: DerivedModifiers, ranged: boolean): AttackOutcome {
  const hasDis =
    (ranged && m.attacker_ranged_disadvantage) ||
    (!ranged && m.attacker_melee_disadvantage) ||
    m.attacker_cannot_see_target
  const hasAdv = m.attacker_unseen_advantage
  if (hasAdv && hasDis) return 'straight'
  if (hasAdv) return 'advantage'
  if (hasDis) return 'disadvantage'
  return 'normal'
}

const OUTCOME_META: Record<AttackOutcome, { label: string; color: string; blurb: string }> = {
  advantage: {
    label: 'Advantage',
    color: 'text-leaf-300 bg-leaf-900/40 border-leaf-700/50',
    blurb: 'Unseen attacker strikes from the gloom.',
  },
  disadvantage: {
    label: 'Disadvantage',
    color: 'text-blood-300 bg-blood-900/30 border-blood-700/50',
    blurb: 'The scene hampers the attack.',
  },
  straight: {
    label: 'Straight roll',
    color: 'text-parchment-300 bg-parchment-900/50 border-parchment-700/50',
    blurb: 'Both combatants are blind to each other — advantage & disadvantage cancel.',
  },
  normal: {
    label: 'No modifier',
    color: 'text-arcane-300 bg-arcane-900/30 border-arcane-700/40',
    blurb: 'The scene imposes no attack modifier.',
  },
}

/* ------------------------------------------------------------------ *
 * The panel.                                                          *
 * ------------------------------------------------------------------ */

interface Props {
  gameId: number
  /** Called after the scene is changed so the parent can refresh game state. */
  onChanged?: () => void
}

type DimensionKey = 'light' | 'weather' | 'terrain' | 'temperature' | 'time_of_day'

export default function EnvironmentPanel({ gameId, onChanged }: Props) {
  const [registry, setRegistry] = useState<EnvironmentRegistry | null>(null)
  const [current, setCurrent] = useState<SceneEnvironment | null>(null)
  const [currentEffects, setCurrentEffects] = useState<EnvironmentEffects | null>(null)
  const [draft, setDraft] = useState<SceneEnvironment | null>(null)
  const [preview, setPreview] = useState<EnvironmentEffects | null>(null)
  const [attackRanged, setAttackRanged] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<string | null>(null)

  // Procedural-weather roller controls.
  const [climate, setClimate] = useState('temperate')
  const [season, setSeason] = useState('summer')
  const [rollTime, setRollTime] = useState('day')
  const [seedText, setSeedText] = useState('')

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [reg, env] = await Promise.all([
        getEnvironmentRegistry(),
        getEnvironment(gameId),
      ])
      setRegistry(reg)
      setCurrent(env.environment)
      setDraft(env.environment)
      setCurrentEffects(env.effects)
    } catch {
      setError('Failed to load the scene environment')
    }
    setLoading(false)
  }

  useEffect(() => {
    load()
  }, [gameId])

  // Debounced live preview of the draft's derived effects. Only fires when
  // the draft actually differs from the saved scene.
  const previewTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (!draft || !current) return
    const same =
      draft.light === current.light &&
      draft.weather === current.weather &&
      draft.terrain === current.terrain &&
      draft.temperature === current.temperature &&
      draft.time_of_day === current.time_of_day
    if (same) {
      setPreview(null)
      return
    }
    if (previewTimer.current) clearTimeout(previewTimer.current)
    previewTimer.current = setTimeout(async () => {
      try {
        const res = await previewEnvironmentEffects(gameId, {
          light: draft.light,
          weather: draft.weather,
          terrain: draft.terrain,
          temperature: draft.temperature,
          time_of_day: draft.time_of_day,
        })
        setPreview(res.effects)
      } catch {
        // Non-fatal: keep the last preview.
      }
    }, 300)
    return () => {
      if (previewTimer.current) clearTimeout(previewTimer.current)
    }
  }, [draft, current, gameId])

  const dirty =
    !!draft &&
    !!current &&
    (draft.light !== current.light ||
      draft.weather !== current.weather ||
      draft.terrain !== current.terrain ||
      draft.temperature !== current.temperature ||
      draft.time_of_day !== current.time_of_day ||
      (draft.notes ?? '') !== (current.notes ?? ''))

  const handleField = (key: DimensionKey, value: string) => {
    setDraft((d) => (d ? { ...d, [key]: value } : d))
    setResult(null)
  }

  const handleNotes = (value: string) => {
    setDraft((d) => (d ? { ...d, notes: value } : d))
    setResult(null)
  }

  const buildUpdate = (): Partial<SceneEnvironment> => {
    if (!draft || !current) return {}
    const upd: Partial<SceneEnvironment> = {}
    if (draft.light !== current.light) upd.light = draft.light
    if (draft.weather !== current.weather) upd.weather = draft.weather
    if (draft.terrain !== current.terrain) upd.terrain = draft.terrain
    if (draft.temperature !== current.temperature) upd.temperature = draft.temperature
    if (draft.time_of_day !== current.time_of_day) upd.time_of_day = draft.time_of_day
    if ((draft.notes ?? '') !== (current.notes ?? '')) upd.notes = draft.notes ?? ''
    return upd
  }

  const apply = async () => {
    if (!dirty) return
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const res: EnvironmentResponse = await setEnvironment(gameId, buildUpdate())
      setCurrent(res.environment)
      setDraft(res.environment)
      setCurrentEffects(res.effects)
      setPreview(null)
      setResult('Scene updated. Weather and terrain now shape travel, perception, and combat.')
      onChanged?.()
    } catch {
      setError('Failed to update the scene')
    }
    setBusy(false)
  }

  const reset = () => {
    if (current) {
      setDraft(current)
      setPreview(null)
      setResult(null)
    }
  }

  const roll = async () => {
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const seedNum = seedText.trim() === '' ? undefined : Number(seedText)
      const res: EnvironmentRollResult = await rollEnvironmentWeather(
        gameId,
        climate,
        season,
        rollTime,
        Number.isFinite(seedNum) ? seedNum : undefined,
      )
      setCurrent(res.environment)
      setDraft(res.environment)
      setCurrentEffects(res.effects)
      setPreview(null)
      setResult(res.message)
      onChanged?.()
    } catch {
      setError('Failed to roll weather')
    }
    setBusy(false)
  }

  if (loading) {
    return (
      <div className="text-parchment-400 animate-pulse text-center py-12">
        Reading the lay of the land…
      </div>
    )
  }
  if (error || !registry || !current || !draft || !currentEffects) {
    return (
      <div className="text-center py-8">
        <div className="text-blood-400 mb-3">{error || 'No environment data'}</div>
        <button className="btn-primary" onClick={load}>
          Retry
        </button>
      </div>
    )
  }

  // Effects shown: live preview when dirty, otherwise the saved scene's effects.
  const shownEffects = dirty && preview ? preview : currentEffects
  const mods = deriveModifiers(shownEffects, attackRanged)
  const outcome = netOutcome(mods, attackRanged)
  const om = OUTCOME_META[outcome]

  const dims: { key: DimensionKey; label: string }[] = [
    { key: 'time_of_day', label: 'Time of Day' },
    { key: 'light', label: 'Lighting' },
    { key: 'weather', label: 'Weather' },
    { key: 'terrain', label: 'Terrain' },
    { key: 'temperature', label: 'Temperature' },
  ]

  const optionsFor = (key: DimensionKey): { value: string; label: string }[] => {
    switch (key) {
      case 'light':
        return registry.light_levels.map((r) => ({ value: r.name, label: titleCase(r.name) }))
      case 'weather':
        return registry.weather.map((r) => ({ value: r.name, label: titleCase(r.name) }))
      case 'terrain':
        return registry.terrain.map((r) => ({ value: r.name, label: titleCase(r.name) }))
      case 'temperature':
        return registry.temperature.map((r) => ({ value: r.name, label: titleCase(r.name) }))
      case 'time_of_day':
        return registry.time_of_day.map((t) => ({ value: t.name, label: titleCase(t.name) }))
    }
  }

  const kindOf = (key: DimensionKey): 'light' | 'weather' | 'terrain' | 'temperature' | 'time' => {
    if (key === 'time_of_day') return 'time'
    return key
  }

  return (
    <div className="space-y-4">
      {/* Current scene summary */}
      <div className="bg-parchment-900/60 rounded-lg p-3 border border-arcane-800/40 animate-scale-in">
        <div className="text-[10px] uppercase text-parchment-500 tracking-wide mb-2">
          Current Scene
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {dims.map((d) => (
            <div key={d.key} className="bg-parchment-900/50 rounded-md p-2">
              <div className="text-parchment-500 uppercase tracking-wide text-[10px] mb-0.5">
                {d.label}
              </div>
              <div className="text-sm text-parchment-200 font-semibold flex items-center gap-1.5">
                <span>{iconFor(kindOf(d.key), current[d.key])}</span>
                <span className="truncate">{titleCase(current[d.key])}</span>
              </div>
            </div>
          ))}
        </div>
        {current.notes ? (
          <div className="mt-2 text-xs text-parchment-400 italic bg-parchment-950/40 rounded-md p-2 border border-parchment-800/50">
            “{current.notes}”
          </div>
        ) : null}

        {/* Active mechanical effects */}
        <div className="mt-3 pt-2 border-t border-parchment-800/60">
          <div className="text-[10px] uppercase text-parchment-500 tracking-wide mb-1.5">
            Active Effects
          </div>
          {shownEffects.active_effects.length > 0 ? (
            <ul className="text-[11px] text-parchment-300 space-y-1 list-disc list-inside leading-relaxed">
              {shownEffects.active_effects.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          ) : (
            <p className="text-[11px] text-leaf-300">No environmental penalties.</p>
          )}
          {dirty && preview && (
            <p className="text-[10px] text-gold-400 mt-1.5">
              ▲ Preview of your unsaved changes — apply to make these take effect.
            </p>
          )}
        </div>
      </div>

      {/* Live combat-modifier preview */}
      <div className="bg-parchment-900/70 rounded-lg p-3 border border-blood-700/40">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[10px] uppercase text-parchment-500 tracking-wide">
            ⚔️ Attack Modifier Preview
          </span>
          <div className="flex items-center gap-1 text-[10px]">
            <button
              onClick={() => setAttackRanged(false)}
              className={`px-2 py-0.5 rounded transition-colors ${
                !attackRanged
                  ? 'bg-arcane-800/80 text-arcane-200'
                  : 'bg-parchment-900/60 text-parchment-500 hover:text-parchment-300'
              }`}
            >
              Melee
            </button>
            <button
              onClick={() => setAttackRanged(true)}
              className={`px-2 py-0.5 rounded transition-colors ${
                attackRanged
                  ? 'bg-arcane-800/80 text-arcane-200'
                  : 'bg-parchment-900/60 text-parchment-500 hover:text-parchment-300'
              }`}
            >
              Ranged
            </button>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`text-xs font-bold uppercase px-2 py-1 rounded border ${om.color}`}
          >
            {om.label}
          </span>
          <span className="text-[11px] text-parchment-400">{om.blurb}</span>
        </div>
        {(mods.attacker_cannot_see_target ||
          (attackRanged && mods.attacker_ranged_disadvantage) ||
          mods.attacker_unseen_advantage) && (
          <div className="mt-2 flex flex-wrap gap-1.5 text-[10px]">
            {mods.attacker_cannot_see_target && (
              <span className="px-1.5 py-0.5 rounded bg-blood-900/40 text-blood-300 border border-blood-700/40">
                poor visibility hampers the strike
              </span>
            )}
            {!mods.attacker_cannot_see_target &&
              attackRanged &&
              mods.attacker_ranged_disadvantage && (
                <span className="px-1.5 py-0.5 rounded bg-blood-900/40 text-blood-300 border border-blood-700/40">
                  wind disrupts the shot
                </span>
              )}
            {mods.attacker_unseen_advantage && (
              <span className="px-1.5 py-0.5 rounded bg-leaf-900/40 text-leaf-300 border border-leaf-700/40">
                unseen attacker (advantage)
              </span>
            )}
          </div>
        )}
        <p className="text-[10px] text-parchment-600 mt-2">
          Reflects {dirty && preview ? 'your unsaved draft' : 'the live scene'}. Applied scenes
          reshape combat immediately on the next attack.
        </p>
      </div>

      {/* Editor */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <div className="flex-1 h-px bg-parchment-800/60" />
          <span className="text-xs text-parchment-600 uppercase tracking-wide">
            Adjust the Scene
          </span>
          <div className="flex-1 h-px bg-parchment-800/60" />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {dims.map((d) => {
            const val = draft[d.key]
            return (
              <label key={d.key} className="block">
                <span className="text-[10px] uppercase text-parchment-500 tracking-wide flex items-center gap-1 mb-1">
                  <span>{iconFor(kindOf(d.key), val)}</span>
                  {d.label}
                </span>
                <select
                  value={val}
                  onChange={(e) => handleField(d.key, e.target.value)}
                  className="w-full bg-parchment-950/70 border border-parchment-700/50 rounded-md px-2 py-1.5 text-sm text-parchment-200 focus:outline-none focus:ring-1 focus:ring-arcane-500"
                >
                  {optionsFor(d.key).map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
            )
          })}
        </div>

        <label className="block mt-2">
          <span className="text-[10px] uppercase text-parchment-500 tracking-wide block mb-1">
            Scene Notes
          </span>
          <textarea
            value={draft.notes ?? ''}
            onChange={(e) => handleNotes(e.target.value)}
            placeholder="DM flavor: the wind howls through the pines…"
            rows={2}
            className="w-full bg-parchment-950/70 border border-parchment-700/50 rounded-md px-2 py-1.5 text-sm text-parchment-200 focus:outline-none focus:ring-1 focus:ring-arcane-500 resize-none"
          />
        </label>

        <div className="flex gap-2 mt-3">
          <button
            className="btn-primary flex-1"
            disabled={!dirty || busy}
            onClick={apply}
            title={!dirty ? 'No changes to apply' : 'Persist the scene'}
          >
            {busy ? 'Applying…' : 'Apply Changes'}
          </button>
          <button
            className="btn-primary bg-parchment-800/60 hover:bg-parchment-700/60"
            disabled={!dirty || busy}
            onClick={reset}
          >
            Reset
          </button>
        </div>
      </div>

      {/* Procedural weather roller */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <div className="flex-1 h-px bg-parchment-800/60" />
          <span className="text-xs text-parchment-600 uppercase tracking-wide">
            Roll Procedural Weather
          </span>
          <div className="flex-1 h-px bg-parchment-800/60" />
        </div>
        <div className="bg-parchment-900/50 rounded-lg p-3 border border-parchment-800/50">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            <label className="block">
              <span className="text-[10px] uppercase text-parchment-500 tracking-wide block mb-1">
                Climate
              </span>
              <select
                value={climate}
                onChange={(e) => setClimate(e.target.value)}
                className="w-full bg-parchment-950/70 border border-parchment-700/50 rounded-md px-2 py-1.5 text-sm text-parchment-200 focus:outline-none focus:ring-1 focus:ring-arcane-500"
              >
                {registry.climates.map((c) => (
                  <option key={c} value={c}>
                    {titleCase(c)}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-[10px] uppercase text-parchment-500 tracking-wide block mb-1">
                Season
              </span>
              <select
                value={season}
                onChange={(e) => setSeason(e.target.value)}
                className="w-full bg-parchment-950/70 border border-parchment-700/50 rounded-md px-2 py-1.5 text-sm text-parchment-200 focus:outline-none focus:ring-1 focus:ring-arcane-500"
              >
                {registry.seasons.map((s) => (
                  <option key={s} value={s}>
                    {titleCase(s)}
                  </option>
                ))}
              </select>
            </label>
            <label className="block col-span-2 sm:col-span-1">
              <span className="text-[10px] uppercase text-parchment-500 tracking-wide block mb-1">
                Time of Day
              </span>
              <select
                value={rollTime}
                onChange={(e) => setRollTime(e.target.value)}
                className="w-full bg-parchment-950/70 border border-parchment-700/50 rounded-md px-2 py-1.5 text-sm text-parchment-200 focus:outline-none focus:ring-1 focus:ring-arcane-500"
              >
                {registry.time_of_day.map((t) => (
                  <option key={t.name} value={t.name}>
                    {titleCase(t.name)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="block mt-2">
            <span className="text-[10px] uppercase text-parchment-500 tracking-wide block mb-1">
              Seed (optional — for reproducible rolls)
            </span>
            <input
              type="text"
              inputMode="numeric"
              value={seedText}
              onChange={(e) => setSeedText(e.target.value)}
              placeholder="random"
              className="w-full bg-parchment-950/70 border border-parchment-700/50 rounded-md px-2 py-1.5 text-sm text-parchment-200 focus:outline-none focus:ring-1 focus:ring-arcane-500"
            />
          </label>
          <button
            className="btn-primary w-full mt-3"
            disabled={busy}
            onClick={roll}
            title="Roll weather + temperature for this climate/season and apply it"
          >
            {busy ? 'Rolling…' : '🎲 Roll Weather'}
          </button>
          <p className="text-[10px] text-parchment-600 mt-1.5">
            Generates weather and temperature from weighted DnD tables. Preserves the current
            terrain and notes.
          </p>
        </div>
      </div>

      {/* Result feedback */}
      {result && (
        <div className="bg-leaf-900/40 border border-leaf-700 rounded-lg p-3 animate-scale-in">
          <span className="font-fantasy text-leaf-300 text-sm">✓ Scene Updated</span>
          <p className="text-[11px] text-parchment-400 mt-1 leading-relaxed">{result}</p>
        </div>
      )}

      {error && <p className="text-xs text-blood-400 text-center">{error}</p>}
    </div>
  )
}
