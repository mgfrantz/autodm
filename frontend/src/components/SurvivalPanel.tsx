import { useCallback, useEffect, useState } from 'react'
import { getSurvival, advanceSurvival, resetSurvival } from '../stores/api'
import type { SurvivalStatus, SurvivalAdvanceResult, StoryEntry } from '../types'

/* ------------------------------------------------------------------ *
 * Survival panel — DnD 5e starvation & dehydration (PHB ch.8 "Food
 * and Water"). A character needs 1 lb of food and 1 gal of water per
 * day (2 gal in hot weather). Going without food beyond a grace period
 * (3 + CON mod days), or drinking too little water, inflicts exhaustion.
 *
 * This panel is a thin UI over the existing, already-tested backend
 * survival API (`/api/game/{id}/survival`). Exhaustion itself is owned
 * by the exhaustion system; this panel only tracks the *drivers* (the
 * consecutive-day deprivation counters) and resolves a day's intake.
 * ------------------------------------------------------------------ */

/**
 * Build a one-line, story-log-worthy narration of a survival day, or
 * ``null`` when nothing worth narrating happened. Surfacing this in the DM
 * bubble (via ``onNarration``) means a trek through the desert or a stretch
 * of famine reads like a world event, not a silent counter increment.
 */
function survivalNarration(result: SurvivalAdvanceResult): string | null {
  if (result.died) {
    return `☠️ Deprivation proves fatal — the character collapses and dies of starvation (exhaustion level ${result.exhaustion_after}).`
  }
  if (result.exhaustion_added > 0) {
    const cause = [
      result.exhaustion_from_food > 0 ? 'starvation' : null,
      result.exhaustion_from_water > 0 ? 'dehydration' : null,
    ].filter(Boolean).join(' + ')
    return `🥵 A day without enough ${cause || 'sustenance'} takes its toll — exhaustion ${result.exhaustion_before} → ${result.exhaustion_after}.`
  }
  // Only narrate a "clean" day if the player was previously in deficit and is
  // now recovering (avoid spamming "ate well" every day).
  if (result.exhaustion_before > 0 && result.food_intake_ok && result.water_intake_ok) {
    return `🍽️ A full day's food and water sustains the character — exhaustion holds at ${result.exhaustion_after}.`
  }
  return null
}

interface SurvivalPanelProps {
  gameId: number
  onChanged?: () => void | Promise<void>
  /** Narrate a survival day into the DM story bubble. Called with a system
   *  story entry only when something meaningful happened (exhaustion gained,
   *  death, or recovering from prior deficit); uneventful days stay silent. */
  onNarration?: (entry: StoryEntry) => void
}

export default function SurvivalPanel({ gameId, onChanged, onNarration }: SurvivalPanelProps) {
  const [status, setStatus] = useState<SurvivalStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [flash, setFlash] = useState<SurvivalAdvanceResult | null>(null)

  // Day-intake controls. Defaults reflect a healthy day's worth.
  const [foodLbs, setFoodLbs] = useState(1)
  const [waterGal, setWaterGal] = useState(1)
  const [hot, setHot] = useState<boolean | null>(null) // null = auto-detect

  const refresh = useCallback(async () => {
    try {
      const data = await getSurvival(gameId)
      setStatus(data)
      setError(null)
      // Seed the intake sliders from the day's needs; remember the auto-detected
      // hot flag so the toggle shows the effective climate.
      setHot(data.deficit.hot)
    } catch {
      setError('Failed to load survival status.')
    } finally {
      setLoading(false)
    }
  }, [gameId])

  useEffect(() => {
    setLoading(true)
    refresh()
  }, [refresh])

  const showFlash = (msg: SurvivalAdvanceResult | null) => {
    setFlash(msg)
    if (msg) window.setTimeout(() => setFlash(null), 5000)
  }

  const advance = async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await advanceSurvival(
        gameId,
        foodLbs,
        waterGal,
        hot === null ? undefined : hot,
      )
      // Refresh the underlying status so the counters + deficit update.
      await refresh()
      showFlash(result)
      // Surface the day's outcome in the DM story bubble (only when meaningful).
      const line = survivalNarration(result)
      if (line && onNarration) {
        onNarration({ role: 'system', content: line, timestamp: new Date().toISOString() })
      }
      if (onChanged) await onChanged()
    } catch {
      setError('Could not advance the survival day (it cannot be done mid-combat).')
    } finally {
      setBusy(false)
    }
  }

  const reset = async () => {
    setBusy(true)
    setError(null)
    try {
      const data = await resetSurvival(gameId)
      setStatus(data)
      showFlash(null)
      if (onChanged) await onChanged()
    } catch {
      setError('Could not reset the survival counters.')
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return <div className="text-parchment-400 animate-pulse text-center py-8">Assessing sustenance…</div>
  }

  if (error && !status) {
    return <div className="text-blood-500 text-sm text-center py-8">{error}</div>
  }

  if (!status) return null

  const { state, deficit, daily_needs } = status
  const inCombat = false // survival is out-of-combat; backend guards the advance
  const waterNeed = daily_needs.water
  const effectiveHot = hot ?? deficit.hot

  // How urgent is each deficit? Food uses grace; water has no grace (any miss stacks).
  const foodUrgent = deficit.starving
  const foodWarn = !foodUrgent && state.days_without_food > 0
  const waterMiss = state.days_without_water > 0

  return (
    <div className="space-y-4">
      {/* In-combat note */}
      {inCombat && (
        <div className="bg-blood-900/40 border border-blood-700 rounded-lg p-3 text-sm text-blood-300">
          ⚔️ You are in combat. Resolve the fight before tracking a survival day.
        </div>
      )}

      {/* Current status readout */}
      <div className="rounded-lg p-4 border bg-parchment-900/60 border-parchment-700/40">
        <div className="flex items-baseline justify-between mb-3">
          <span className="text-parchment-500 text-sm font-semibold uppercase tracking-wide">
            Sustenance
          </span>
          <span className="text-xs text-parchment-600">
            Needs: {daily_needs.food} lb food · {waterNeed} gal water{effectiveHot ? ' 🌡️' : ''}/day
          </span>
        </div>

        <div className="grid grid-cols-2 gap-3">
          {/* Food */}
          <div className={`rounded-md p-3 border ${
            foodUrgent
              ? 'bg-blood-900/30 border-blood-700/50'
              : foodWarn
              ? 'bg-amber-900/30 border-amber-700/40'
              : 'bg-leaf-900/20 border-leaf-700/30'
          }`}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-semibold text-parchment-400 uppercase tracking-wide">🍖 Food</span>
              <span className={`text-lg font-bold font-fantasy ${
                foodUrgent ? 'text-blood-300' : foodWarn ? 'text-amber-300' : 'text-leaf-300'
              }`}>
                {state.days_without_food}
                <span className="text-parchment-600 text-xs font-normal"> days short</span>
              </span>
            </div>
            <div className="text-xs text-parchment-500">
              {foodUrgent ? (
                <span className="text-blood-300">Starving — grace ({deficit.food_grace_days}) exceeded.</span>
              ) : foodWarn ? (
                <span>{deficit.food_days_until_exhaustion} day(s) of grace left (of {deficit.food_grace_days}).</span>
              ) : (
                <span className="text-leaf-300">Well-fed today.</span>
              )}
            </div>
          </div>

          {/* Water */}
          <div className={`rounded-md p-3 border ${
            waterMiss
              ? 'bg-blood-900/30 border-blood-700/50'
              : 'bg-leaf-900/20 border-leaf-700/30'
          }`}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-semibold text-parchment-400 uppercase tracking-wide">💧 Water</span>
              <span className={`text-lg font-bold font-fantasy ${
                waterMiss ? 'text-blood-300' : 'text-leaf-300'
              }`}>
                {state.days_without_water}
                <span className="text-parchment-600 text-xs font-normal"> days short</span>
              </span>
            </div>
            <div className="text-xs text-parchment-500">
              {waterMiss ? (
                <span className="text-blood-300">Dehydrated — thirst threatens exhaustion.</span>
              ) : (
                <span className="text-leaf-300">Well-watered today.</span>
              )}
            </div>
          </div>
        </div>

        {/* Exhaustion link */}
        <div className="mt-3 pt-3 border-t border-parchment-800/60 flex items-center justify-between text-sm">
          <span className="text-parchment-500">Exhaustion driven in part by these:</span>
          <span className={`font-bold ${status.exhaustion >= 5 ? 'text-blood-400' : status.exhaustion >= 3 ? 'text-amber-300' : status.exhaustion > 0 ? 'text-gold-300' : 'text-leaf-300'}`}>
            {status.exhaustion}/6
          </span>
        </div>
      </div>

      {/* Rules summary */}
      <p className="text-xs text-parchment-600 leading-relaxed">
        A character needs <span className="text-parchment-400">{daily_needs.food} lb of food</span> and{' '}
        <span className="text-parchment-400">{waterNeed} gal of water</span> each day
        {effectiveHot && <span className="text-amber-300"> (doubled in hot weather)</span>}.
        Beyond a grace of <span className="text-parchment-400">{deficit.food_grace_days} days</span> without food, or
        on too little water, the character suffers exhaustion.
      </p>

      {/* Result flash */}
      {flash && (
        <div className={`rounded-lg p-3 border text-sm animate-fade-in ${
          flash.died
            ? 'bg-blood-900/50 border-blood-600 text-blood-200'
            : flash.exhaustion_added > 0
            ? 'bg-amber-900/40 border-amber-700 text-amber-200'
            : 'bg-arcane-900/40 border-arcane-700 text-parchment-200'
        }`}>
          <div className="font-semibold mb-1">
            {flash.died
              ? '☠️ Death by deprivation.'
              : flash.exhaustion_added > 0
              ? `🥵 +${flash.exhaustion_added} exhaustion (now level ${flash.exhaustion_after}).`
              : '🍽️ The day passes without ill effect.'}
          </div>
          {flash.thirst_save_success !== null && (
            <div className="text-xs text-parchment-300">
              Thirst save: d20({flash.thirst_save_roll}) +{flash.thirst_save_bonus} vs DC {flash.thirst_save_dc} →{' '}
              <span className={flash.thirst_save_success ? 'text-leaf-300' : 'text-blood-300'}>
                {flash.thirst_save_success ? 'success' : 'failure'}
              </span>
            </div>
          )}
          {flash.messages.length > 0 && (
            <ul className="mt-1 space-y-0.5 text-xs text-parchment-400 list-disc list-inside">
              {flash.messages.map((m, i) => <li key={i}>{m}</li>)}
            </ul>
          )}
        </div>
      )}
      {error && (
        <div className="text-blood-500 text-sm">{error}</div>
      )}

      {/* Advance-a-day controls */}
      <div className="bg-parchment-900/60 rounded-lg p-3">
        <h3 className="text-xs text-parchment-500 font-semibold uppercase tracking-wide mb-2">
          Advance a Day
        </h3>
        <p className="text-xs text-parchment-600 mb-3">
          Record what the character consumed today, then resolve the day's survival check.
        </p>

        {/* Food slider */}
        <div className="mb-3">
          <div className="flex items-center justify-between text-xs mb-1">
            <label className="text-parchment-400">🍖 Food (lb)</label>
            <span className={`font-semibold ${foodLbs >= daily_needs.food ? 'text-leaf-300' : 'text-amber-300'}`}>
              {foodLbs.toFixed(2)} lb{foodLbs >= daily_needs.food ? ' ✓' : ''}
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={Math.max(2, +(daily_needs.food * 2).toFixed(2))}
            step={0.25}
            value={foodLbs}
            onChange={(e) => setFoodLbs(Number(e.target.value))}
            disabled={busy}
            className="w-full accent-gold-500"
          />
        </div>

        {/* Water slider */}
        <div className="mb-3">
          <div className="flex items-center justify-between text-xs mb-1">
            <label className="text-parchment-400">💧 Water (gal)</label>
            <span className={`font-semibold ${waterGal >= waterNeed ? 'text-leaf-300' : waterGal >= waterNeed / 2 ? 'text-amber-300' : 'text-blood-300'}`}>
              {waterGal.toFixed(2)} gal{waterGal >= waterNeed ? ' ✓' : waterGal >= waterNeed / 2 ? ' (half)' : ' (< half)'}
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={Math.max(2, +(waterNeed * 2).toFixed(2))}
            step={0.25}
            value={waterGal}
            onChange={(e) => setWaterGal(Number(e.target.value))}
            disabled={busy}
            className="w-full accent-arcane-400"
          />
        </div>

        {/* Hot toggle */}
        <div className="flex items-center gap-2 mb-3 text-xs">
          <label className="text-parchment-400">🌡️ Hot weather</label>
          <button
            type="button"
            onClick={() => setHot(effectiveHot ? false : true)}
            disabled={busy}
            className={`px-2 py-0.5 rounded border text-xs ${
              effectiveHot
                ? 'bg-amber-900/40 border-amber-700 text-amber-300'
                : 'bg-parchment-800/50 border-parchment-700 text-parchment-400'
            }`}
          >
            {effectiveHot ? 'On (2 gal/day)' : 'Off (1 gal/day)'}
          </button>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <button
            className="btn-primary text-sm"
            onClick={advance}
            disabled={busy}
            title="Resolve one day of food/water intake"
          >
            📅 Resolve day
          </button>
          <button
            className="btn-primary text-sm bg-leaf-700 hover:bg-leaf-600"
            onClick={reset}
            disabled={busy}
            title="Restock — reset the deprivation counters to zero"
          >
            🎒 Restock
          </button>
        </div>
      </div>
    </div>
  )
}
