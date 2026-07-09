import { useCallback, useEffect, useState } from 'react'
import {
  getTrapRegistry, getGameTraps, placeTrap, detectTrap, disarmTrap,
  triggerGameTrap, removeTrap,
} from '../stores/api'
import type { Trap, TrapInstance, StoryEntry } from '../types'

/* ------------------------------------------------------------------ *
 * Traps & Hazards panel — DnD 5e DMG ch.5 ("Traps").
 *
 * A DM/player console over the existing, already-tested trap API
 * (`/api/game/{id}/traps` and `/api/game/traps/registry`).
 *
 * Flow: place a trap from the registry → discover it (active Perception
 * check) → disarm it (thieves' tools / ability check) → or trigger it
 * (damage + conditions with a save-for-half). Every action mutates the
 * backend (persisted in game_state["traps"]) and logs to the story.
 * ------------------------------------------------------------------ */

type Severity = 'setback' | 'dangerous' | 'deadly'
type TrapType = 'mechanical' | 'magical'

const SEVERITY_STYLES: Record<Severity, string> = {
  setback: 'bg-leaf-900/40 border-leaf-700/50 text-leaf-300',
  dangerous: 'bg-amber-900/40 border-amber-700/50 text-amber-300',
  deadly: 'bg-blood-900/50 border-blood-700/50 text-blood-300',
}

const SEVERITY_ICON: Record<Severity, string> = {
  setback: '⚠️',
  dangerous: '☠️',
  deadly: '💀',
}

/** A brief, story-log-worthy narration of a trap action, or null for a no-op. */
function trapNarration(kind: 'place' | 'detect' | 'disarm' | 'trigger' | 'remove', name: string, detail?: string): string {
  switch (kind) {
    case 'place':
      return `🪤 A ${name} lies in wait${detail ? ` at ${detail}` : ''}.`
    case 'detect':
      return detail ? `🔍 ${detail}` : `🔍 You examine the area around the ${name}.`
    case 'disarm':
      return detail ? `🔧 ${detail}` : `🔧 You attempt to disarm the ${name}.`
    case 'trigger':
      return detail ? `💥 ${detail}` : `💥 The ${name} is triggered!`
    case 'remove':
      return `🧹 The ${name} is cleared away.`
  }
}

interface TrapsPanelProps {
  gameId: number
  inCombat?: boolean
  onChanged?: () => void | Promise<void>
  /** Narrate a trap action into the DM story bubble. Called only when the
   *  action produces a meaningful result (discovery, disarm, trigger). */
  onNarration?: (entry: StoryEntry) => void
}

export default function TrapsPanel({ gameId, inCombat = false, onChanged, onNarration }: TrapsPanelProps) {
  const [registry, setRegistry] = useState<Trap[]>([])
  const [instances, setInstances] = useState<TrapInstance[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{ kind: 'detect' | 'disarm' | 'trigger'; narrative: string; tone: 'good' | 'bad' | 'neutral' } | null>(null)

  // Registry filters
  const [typeFilter, setTypeFilter] = useState<TrapType | 'all'>('all')
  const [severityFilter, setSeverityFilter] = useState<Severity | 'all'>('all')
  const [selectedTrapId, setSelectedTrapId] = useState<string | null>(null)
  const [placeLocation, setPlaceLocation] = useState('')

  // Check modifiers for the active trap
  const [perceptionTotal, setPerceptionTotal] = useState(10)
  const [disarmTotal, setDisarmTotal] = useState(10)
  const [disarmMethod, setDisarmMethod] = useState('thieves_tools')
  const [saveRoll, setSaveRoll] = useState<number | ''>(10)
  const [saveModifier, setSaveModifier] = useState(0)

  const refresh = useCallback(async () => {
    try {
      const [reg, inst] = await Promise.all([
        getTrapRegistry(
          typeFilter === 'all' ? undefined : typeFilter,
          severityFilter === 'all' ? undefined : severityFilter,
        ),
        getGameTraps(gameId),
      ])
      setRegistry(reg)
      setInstances(inst)
      setError(null)
    } catch {
      setError('Failed to load traps.')
    } finally {
      setLoading(false)
    }
  }, [gameId, typeFilter, severityFilter])

  useEffect(() => {
    setLoading(true)
    refresh()
  }, [refresh])

  const showFlash = (r: { kind: 'detect' | 'disarm' | 'trigger'; narrative: string; tone: 'good' | 'bad' | 'neutral' }) => {
    setResult(r)
    if (r.narrative) window.setTimeout(() => setResult(null), 6000)
  }

  const handlePlace = async () => {
    if (!selectedTrapId) return
    setBusy(true)
    setError(null)
    try {
      const inst = await placeTrap(gameId, selectedTrapId, placeLocation)
      setInstances((prev) => [...prev, inst])
      setPlaceLocation('')
      if (onNarration) {
        onNarration({ role: 'system', content: trapNarration('place', inst.trap.name, inst.location || undefined), timestamp: new Date().toISOString() })
      }
      if (onChanged) await onChanged()
    } catch {
      setError('Could not place the trap.')
    } finally {
      setBusy(false)
    }
  }

  const handleDetect = async (index: number) => {
    setBusy(true)
    setError(null)
    try {
      const r = await detectTrap(gameId, index, perceptionTotal)
      await refresh()
      showFlash({
        kind: 'detect',
        narrative: r.narrative,
        tone: r.success ? 'good' : 'neutral',
      })
      if (r.success && onNarration) {
        onNarration({ role: 'system', content: trapNarration('detect', '', r.narrative), timestamp: new Date().toISOString() })
      }
      if (onChanged) await onChanged()
    } catch {
      setError('Could not attempt detection.')
    } finally {
      setBusy(false)
    }
  }

  const handleDisarm = async (index: number) => {
    setBusy(true)
    setError(null)
    try {
      const r = await disarmTrap(gameId, index, disarmTotal, disarmMethod)
      await refresh()
      const tone: 'good' | 'bad' | 'neutral' = r.success ? 'good' : r.triggered ? 'bad' : 'neutral'
      let narrative = r.narrative
      if (r.triggered) {
        narrative += ' ' + r.triggered.narrative
      }
      showFlash({ kind: 'disarm', narrative, tone })
      if (onNarration) {
        onNarration({ role: 'system', content: trapNarration('disarm', '', narrative), timestamp: new Date().toISOString() })
      }
      if (onChanged) await onChanged()
    } catch {
      setError('Could not attempt to disarm.')
    } finally {
      setBusy(false)
    }
  }

  const handleTrigger = async (index: number) => {
    setBusy(true)
    setError(null)
    try {
      const r = await triggerGameTrap(
        gameId,
        index,
        saveRoll === '' ? undefined : saveRoll,
        saveModifier,
      )
      await refresh()
      showFlash({
        kind: 'trigger',
        narrative: r.narrative,
        tone: r.damage > 0 ? 'bad' : 'neutral',
      })
      if (onNarration) {
        onNarration({ role: 'system', content: trapNarration('trigger', '', r.narrative), timestamp: new Date().toISOString() })
      }
      if (onChanged) await onChanged()
    } catch {
      setError('Could not trigger the trap.')
    } finally {
      setBusy(false)
    }
  }

  const handleRemove = async (index: number) => {
    setBusy(true)
    setError(null)
    try {
      const inst = instances[index]
      await removeTrap(gameId, index)
      await refresh()
      if (onNarration && inst) {
        onNarration({ role: 'system', content: trapNarration('remove', inst.trap.name), timestamp: new Date().toISOString() })
      }
      if (onChanged) await onChanged()
    } catch {
      setError('Could not remove the trap.')
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return <div className="text-parchment-400 animate-pulse text-center py-8">Scanning for traps…</div>
  }

  if (error && registry.length === 0 && instances.length === 0) {
    return <div className="text-blood-500 text-sm text-center py-8">{error}</div>
  }

  return (
    <div className="space-y-4">
      {/* In-combat note */}
      {inCombat && (
        <div className="bg-blood-900/40 border border-blood-700 rounded-lg p-3 text-sm text-blood-300">
          ⚔️ You are in combat. Traps can still be triggered, but detection and disarm checks typically happen out of combat.
        </div>
      )}

      {/* Result flash */}
      {result && result.narrative && (
        <div className={`rounded-lg p-3 border text-sm animate-fade-in ${
          result.tone === 'good'
            ? 'bg-leaf-900/40 border-leaf-700 text-leaf-200'
            : result.tone === 'bad'
            ? 'bg-blood-900/50 border-blood-600 text-blood-200'
            : 'bg-arcane-900/40 border-arcane-700 text-parchment-200'
        }`}>
          {result.narrative}
        </div>
      )}
      {error && <div className="text-blood-500 text-sm">{error}</div>}

      {/* Placed traps in this game */}
      <div>
        <div className="flex items-baseline justify-between mb-2">
          <h3 className="text-xs text-parchment-500 font-semibold uppercase tracking-wide">
            Traps in this Area
          </h3>
          <span className="text-xs text-parchment-600">{instances.length} placed</span>
        </div>

        {instances.length === 0 ? (
          <p className="text-xs text-parchment-600 italic px-1">No traps placed yet. Choose one from the registry below.</p>
        ) : (
          <div className="space-y-2">
            {instances.map((inst, i) => {
              const sev = inst.trap.severity as Severity
              const status = inst.disarmed
                ? { label: 'Disarmed', cls: 'text-leaf-300 bg-leaf-900/40 border-leaf-700/40' }
                : inst.triggered
                ? { label: `Triggered ×${inst.trigger_count}`, cls: 'text-blood-300 bg-blood-900/40 border-blood-700/40' }
                : inst.discovered
                ? { label: 'Discovered', cls: 'text-amber-300 bg-amber-900/40 border-amber-700/40' }
                : { label: 'Hidden', cls: 'text-parchment-400 bg-parchment-800/40 border-parchment-700/40' }
              return (
                <div key={i} className="rounded-lg p-3 border bg-parchment-900/60 border-parchment-700/40">
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-semibold text-parchment-200 font-fantasy">
                          {SEVERITY_ICON[sev]} {inst.trap.name}
                        </span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded border uppercase tracking-wide ${status.cls}`}>
                          {status.label}
                        </span>
                        {inst.location && (
                          <span className="text-[10px] text-parchment-500">📍 {inst.location}</span>
                        )}
                      </div>
                      <p className="text-xs text-parchment-500 mt-1 line-clamp-2">{inst.trap.description}</p>
                    </div>
                  </div>

                  {/* Stat chips */}
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${SEVERITY_STYLES[sev]}`}>
                      {inst.trap.severity}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded border bg-parchment-800/50 border-parchment-700 text-parchment-400 capitalize">
                      {inst.trap.trap_type}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded border bg-parchment-800/50 border-parchment-700 text-parchment-400">
                      👁 DC {inst.trap.detection_dc}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded border bg-parchment-800/50 border-parchment-700 text-parchment-400">
                      🔧 DC {inst.trap.disarm_dc}
                    </span>
                  </div>

                  {/* Effects summary (only when discovered) */}
                  {inst.discovered && inst.trap.effects.length > 0 && (
                    <ul className="mb-2 space-y-0.5 text-[11px] text-parchment-400 list-disc list-inside">
                      {inst.trap.effects.map((e, j) => (
                        <li key={j}>
                          {e.type === 'damage' && (
                            <>
                              💥 {e.damage_dice} {e.damage_type}
                              {e.save_ability && ` — ${e.save_ability} save DC ${e.save_dc} (${e.save_result} on success)`}
                            </>
                          )}
                          {e.type === 'condition' && (
                            <>
                              ⛓ {e.condition}
                              {e.condition_duration ? ` (${e.condition_duration} rds)` : ''}
                              {e.save_ability && ` — ${e.save_ability} save DC ${e.save_dc}`}
                            </>
                          )}
                          {(e.type === 'teleport' || e.type === 'summon' || e.type === 'telekinesis') && (
                            <>✨ {e.description || e.type}</>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}

                  {/* Action buttons */}
                  <div className="flex flex-wrap gap-1.5">
                    <button
                      className="px-2 py-1 rounded text-[11px] font-medium bg-arcane-800/60 hover:bg-arcane-700/60 border border-arcane-600/40 text-arcane-200 disabled:opacity-40"
                      onClick={() => handleDetect(i)}
                      disabled={busy || inst.discovered || inst.disarmed}
                      title="Active Perception check vs detection DC"
                    >
                      🔍 Detect
                    </button>
                    <button
                      className="px-2 py-1 rounded text-[11px] font-medium bg-leaf-800/60 hover:bg-leaf-700/60 border border-leaf-600/40 text-leaf-200 disabled:opacity-40"
                      onClick={() => handleDisarm(i)}
                      disabled={busy || !inst.discovered || inst.disarmed}
                      title="Disarm check vs disarm DC (requires discovery)"
                    >
                      🔧 Disarm
                    </button>
                    <button
                      className="px-2 py-1 rounded text-[11px] font-medium bg-blood-800/60 hover:bg-blood-700/60 border border-blood-600/40 text-blood-200 disabled:opacity-40"
                      onClick={() => handleTrigger(i)}
                      disabled={busy || inst.disarmed}
                      title="Trigger the trap (damage + conditions)"
                    >
                      💥 Trigger
                    </button>
                    <button
                      className="px-2 py-1 rounded text-[11px] font-medium bg-parchment-800/60 hover:bg-parchment-700/60 border border-parchment-600/40 text-parchment-400 disabled:opacity-40"
                      onClick={() => handleRemove(i)}
                      disabled={busy}
                      title="Remove this trap (GM action)"
                    >
                      🧹 Clear
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Check modifiers */}
      <div className="bg-parchment-900/60 rounded-lg p-3 border border-parchment-700/30">
        <h3 className="text-xs text-parchment-500 font-semibold uppercase tracking-wide mb-2">
          Check Roll Inputs
        </h3>
        <p className="text-[11px] text-parchment-600 mb-2">
          These totals feed the Detect / Disarm / Trigger actions above. Enter the full check result (roll + modifier).
        </p>
        <div className="grid grid-cols-2 gap-2">
          <label className="text-[11px] text-parchment-400">
            👁 Perception total
            <input
              type="number"
              min={1}
              value={perceptionTotal}
              onChange={(e) => setPerceptionTotal(Number(e.target.value))}
              disabled={busy}
              className="w-full mt-0.5 bg-parchment-950/60 border border-parchment-700/50 rounded px-2 py-1 text-parchment-200 text-sm"
            />
          </label>
          <label className="text-[11px] text-parchment-400">
            🔧 Disarm total
            <input
              type="number"
              min={1}
              value={disarmTotal}
              onChange={(e) => setDisarmTotal(Number(e.target.value))}
              disabled={busy}
              className="w-full mt-0.5 bg-parchment-950/60 border border-parchment-700/50 rounded px-2 py-1 text-parchment-200 text-sm"
            />
          </label>
          <label className="text-[11px] text-parchment-400">
            🎲 Save roll (d20)
            <input
              type="number"
              min={1}
              max={20}
              value={saveRoll}
              onChange={(e) => setSaveRoll(e.target.value === '' ? '' : Number(e.target.value))}
              disabled={busy}
              className="w-full mt-0.5 bg-parchment-950/60 border border-parchment-700/50 rounded px-2 py-1 text-parchment-200 text-sm"
            />
          </label>
          <label className="text-[11px] text-parchment-400">
            ➕ Save modifier
            <input
              type="number"
              value={saveModifier}
              onChange={(e) => setSaveModifier(Number(e.target.value))}
              disabled={busy}
              className="w-full mt-0.5 bg-parchment-950/60 border border-parchment-700/50 rounded px-2 py-1 text-parchment-200 text-sm"
            />
          </label>
        </div>
        <label className="block text-[11px] text-parchment-400 mt-2">
          Disarm method
          <select
            value={disarmMethod}
            onChange={(e) => setDisarmMethod(e.target.value)}
            disabled={busy}
            className="w-full mt-0.5 bg-parchment-950/60 border border-parchment-700/50 rounded px-2 py-1 text-parchment-200 text-sm"
          >
            <option value="thieves_tools">Thieves' Tools (Dex)</option>
            <option value="strength">Strength (force)</option>
            <option value="arcana">Arcana (magical)</option>
            <option value="dexterity">Dexterity (nimble fingers)</option>
            <option value="investigation">Investigation (figure it out)</option>
          </select>
        </label>
      </div>

      {/* Trap registry — place new traps */}
      <div className="bg-parchment-900/60 rounded-lg p-3 border border-parchment-700/30">
        <h3 className="text-xs text-parchment-500 font-semibold uppercase tracking-wide mb-2">
          Place a Trap
        </h3>

        {/* Filters */}
        <div className="flex flex-wrap gap-2 mb-3">
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value as TrapType | 'all')}
            disabled={busy}
            className="text-[11px] bg-parchment-950/60 border border-parchment-700/50 rounded px-2 py-1 text-parchment-300"
          >
            <option value="all">All types</option>
            <option value="mechanical">⚙️ Mechanical</option>
            <option value="magical">🔮 Magical</option>
          </select>
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value as Severity | 'all')}
            disabled={busy}
            className="text-[11px] bg-parchment-950/60 border border-parchment-700/50 rounded px-2 py-1 text-parchment-300"
          >
            <option value="all">All severities</option>
            <option value="setback">⚠️ Setback</option>
            <option value="dangerous">☠️ Dangerous</option>
            <option value="deadly">💀 Deadly</option>
          </select>
        </div>

        <div className="grid grid-cols-2 gap-1.5 mb-2 max-h-48 overflow-y-auto">
          {registry.map((t) => {
            const sev = t.severity as Severity
            const active = selectedTrapId === t.id
            return (
              <button
                key={t.id}
                onClick={() => setSelectedTrapId(active ? null : t.id)}
                disabled={busy}
                className={`text-left rounded px-2 py-1.5 border text-xs transition-colors ${
                  active
                    ? 'bg-gold-900/40 border-gold-600/50 text-gold-200'
                    : 'bg-parchment-800/40 border-parchment-700/30 text-parchment-300 hover:bg-parchment-800/70'
                }`}
              >
                <div className="flex items-center gap-1">
                  <span>{SEVERITY_ICON[sev]}</span>
                  <span className="font-medium truncate">{t.name}</span>
                </div>
                <div className="text-[10px] text-parchment-500 mt-0.5">
                  {t.trap_type} · {t.severity} · DC {t.detection_dc}/{t.disarm_dc}
                </div>
              </button>
            )
          })}
          {registry.length === 0 && (
            <p className="col-span-2 text-xs text-parchment-600 italic">No traps match these filters.</p>
          )}
        </div>

        <label className="block text-[11px] text-parchment-400 mb-2">
          Location (optional)
          <input
            type="text"
            value={placeLocation}
            onChange={(e) => setPlaceLocation(e.target.value)}
            disabled={busy}
            placeholder="e.g. corridor, chest, doorway"
            className="w-full mt-0.5 bg-parchment-950/60 border border-parchment-700/50 rounded px-2 py-1 text-parchment-200 text-sm"
          />
        </label>

        <button
          className="btn-primary text-sm w-full"
          onClick={handlePlace}
          disabled={busy || !selectedTrapId}
          title={selectedTrapId ? 'Place this trap in the area' : 'Select a trap from the list first'}
        >
          🪤 Place {selectedTrapId ? registry.find((t) => t.id === selectedTrapId)?.name : 'Trap'}
        </button>
      </div>

      <p className="text-[11px] text-parchment-600 leading-relaxed">
        DnD 5e trap mechanics follow the DMG ch.5: detect via Perception (active or passive), disarm via thieves' tools
        or an ability check, or trigger it for damage and conditions. A failed disarm by 5+ may spring the trap.
        Severity (setback / dangerous / deadly) scales DCs and damage per the DMG guidelines.
      </p>
    </div>
  )
}
