import { useCallback, useEffect, useState } from 'react'
import {
  getMountState,
  getMountRegistry,
  acquireMount,
  mountUp,
  dismount,
  setMountPace,
  damageMount,
  healMount,
  getMountCombat,
  previewMountTravel,
} from '../stores/api'
import type {
  Mount,
  MountStatusResponse,
  MountCombatResult,
  MountTravelResult,
  StoryEntry,
} from '../types'

/* ------------------------------------------------------------------ *
 * Mounts panel — DnD 5e mounted travel & mounted combat (PHB ch.5/8/9).
 *
 * The mounts engine + API are fully built and tested on the backend; this
 * panel surfaces them to the player. A character owns at most one *active*
 * mount (ridden or led), persisted in ``game_state["mount"]``. The panel
 * lets the player:
 *   - browse the 18-mount registry and acquire one (optionally paying gold)
 *   - mount up / dismount
 *   - set the overland travel pace (slow/normal/fast) + gallop burst
 *   - damage / heal the mount (a mount dropped to 0 HP throws the rider)
 *   - preview mounted-combat modifiers (advantage vs smaller unmounted
 *     creatures, the Mounted Combatant feat benefits, lance rules)
 *   - preview adjusted travel hours for a trip
 * ------------------------------------------------------------------ */

const TYPE_ICON: Record<string, string> = {
  land: '🐎',
  flying: '🦅',
  aquatic: '⛵',
  vehicle: '🛞',
}

const PACE_OPTIONS: { value: 'slow' | 'normal' | 'fast'; label: string; note: string }[] = [
  { value: 'slow', label: 'Slow', note: 'Can travel Stealthily' },
  { value: 'normal', label: 'Normal', note: 'No modifiers' },
  { value: 'fast', label: 'Fast', note: '−5 passive Perception' },
]

const SIZES = ['tiny', 'small', 'medium', 'large', 'huge', 'gargantuan']

interface MountsPanelProps {
  gameId: number
  characterGold?: number
  onChanged?: () => void | Promise<void>
  /** Narrate a mount event (acquire, damage, dismount-throw) into the DM bubble. */
  onNarration?: (entry: StoryEntry) => void
}

export default function MountsPanel({ gameId, characterGold, onChanged, onNarration }: MountsPanelProps) {
  const [status, setStatus] = useState<MountStatusResponse | null>(null)
  const [registry, setRegistry] = useState<Mount[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [flash, setFlash] = useState<string | null>(null)

  // Registry browser controls.
  const [registryFilter, setRegistryFilter] = useState<string>('all')
  const [payForMount, setPayForMount] = useState(false)

  // Mount-management controls.
  const [dmgAmount, setDmgAmount] = useState(5)
  const [healAmount, setHealAmount] = useState(5)

  // Combat + travel previews.
  const [showCombat, setShowCombat] = useState(false)
  const [targetSize, setTargetSize] = useState('medium')
  const [combatResult, setCombatResult] = useState<MountCombatResult | null>(null)
  const [showTravel, setShowTravel] = useState(false)
  const [travelHours, setTravelHours] = useState(8)
  const [travelResult, setTravelResult] = useState<MountTravelResult | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [st, reg] = await Promise.all([
        getMountState(gameId),
        getMountRegistry(gameId),
      ])
      setStatus(st)
      setRegistry(reg)
      setError(null)
    } catch {
      setError('Failed to load mount status.')
    } finally {
      setLoading(false)
    }
  }, [gameId])

  useEffect(() => {
    setLoading(true)
    refresh()
  }, [refresh])

  const showFlash = (msg: string | null) => {
    setFlash(msg)
    if (msg) window.setTimeout(() => setFlash(null), 5000)
  }

  const narrate = (line: string) => {
    if (onNarration) {
      onNarration({ role: 'system', content: line, timestamp: new Date().toISOString() })
    }
  }

  const wrap = async (fn: () => Promise<unknown>, errMsg: string, successMsg?: string) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
      await refresh()
      showFlash(successMsg ?? null)
      if (onChanged) await onChanged()
    } catch {
      setError(errMsg)
    } finally {
      setBusy(false)
    }
  }

  const handleAcquire = async (mount: Mount) => {
    await wrap(
      async () => {
        const res = await acquireMount(gameId, mount.id, true, payForMount)
        showFlash(
          payForMount && res.paid_gp > 0
            ? `Acquired a ${mount.name} for ${res.paid_gp} gp.`
            : `Acquired a ${mount.name}.`,
        )
        narrate(`🐎 Acquired a ${mount.name}${payForMount && mount.cost_gp > 0 ? ` (paid ${mount.cost_gp} gp)` : ''}.`)
      },
      payForMount
        ? 'Could not acquire the mount (insufficient gold or unknown mount).'
        : 'Could not acquire the mount.',
    )
  }

  const handleMountUp = async () => {
    await wrap(
      () => mountUp(gameId),
      'Could not mount up.',
      'You climb into the saddle.',
    )
  }

  const handleDismount = async () => {
    await wrap(
      () => dismount(gameId),
      'Could not dismount.',
      'You dismount, leading the mount by the reins.',
    )
  }

  const handlePace = async (pace: 'slow' | 'normal' | 'fast', galloping: boolean) => {
    await wrap(
      async () => {
        const res = await setMountPace(gameId, pace, galloping)
        showFlash(res.pace_note ?? `Pace set to ${pace}.`)
      },
      'Could not set the pace.',
    )
  }

  const handleDamage = async () => {
    await wrap(
      async () => {
        const res = await damageMount(gameId, dmgAmount)
        narrate(res.outcome.message)
        if (res.outcome.forced_dismount && res.state.current_hp === 0) {
          showFlash('💀 Your mount collapses — you are thrown and land prone!')
        } else {
          showFlash(res.outcome.message)
        }
      },
      'Could not damage the mount.',
    )
  }

  const handleHeal = async () => {
    await wrap(
      async () => {
        const res = await healMount(gameId, healAmount)
        showFlash(`Healed ${res.healed} HP (${res.state.current_hp}/${res.state.max_hp}).`)
      },
      'Could not heal the mount.',
    )
  }

  const handleCombat = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await getMountCombat(gameId, targetSize, false)
      setCombatResult(res)
    } catch {
      setError('Could not compute combat modifiers.')
    } finally {
      setBusy(false)
    }
  }

  const handleTravel = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await previewMountTravel(gameId, travelHours)
      setTravelResult(res)
    } catch {
      setError('Could not preview travel time.')
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return <div className="text-parchment-400 animate-pulse text-center py-8">Saddling up…</div>
  }

  if (error && !status) {
    return <div className="text-blood-500 text-sm text-center py-8">{error}</div>
  }

  if (!status) return null

  const { state, summary, has_mounted_combatant } = status
  const mount = summary.mount
  const hpPct = state.max_hp > 0 ? Math.round((state.current_hp / state.max_hp) * 100) : 0
  const hpColor = hpPct > 50 ? 'bg-leaf-600' : hpPct > 25 ? 'bg-amber-500' : 'bg-blood-600'

  // Filter the registry for the browser.
  const filteredRegistry =
    registryFilter === 'all'
      ? registry
      : registry.filter((m) => m.type === registryFilter)

  const canAfford = (m: Mount) => characterGold === undefined || characterGold >= m.cost_gp

  return (
    <div className="space-y-4">
      {/* Mounted Combatant feat badge */}
      {has_mounted_combatant && (
        <div className="bg-gold-900/30 border border-gold-700/50 rounded-lg p-2.5 text-sm text-gold-200 flex items-center gap-2">
          <span className="text-lg">✦</span>
          <span><span className="font-semibold">Mounted Combatant</span> feat active — Dex-save advantage, evasion & attack redirect on your mount.</span>
        </div>
      )}

      {/* Current mount card */}
      {summary.has_mount && mount ? (
        <div className="rounded-lg p-4 border bg-parchment-900/60 border-parchment-700/40">
          <div className="flex items-start justify-between mb-3">
            <div className="flex items-center gap-3">
              <span className="text-3xl">{TYPE_ICON[mount.type] ?? '🐎'}</span>
              <div>
                <div className="font-fantasy text-xl text-parchment-100">{mount.name}</div>
                <div className="text-xs text-parchment-500 capitalize">
                  {mount.type} · {mount.size} · {mount.control_type} control
                  {mount.can_fly && ' · 🪽 flying'}
                  {mount.can_swim && ' · 🌊 swim'}
                </div>
              </div>
            </div>
            <span className={`px-2 py-0.5 rounded-full text-xs font-semibold border ${
              state.mounted
                ? 'bg-leaf-900/40 border-leaf-700 text-leaf-300'
                : state.current_hp > 0 ? 'bg-parchment-800/60 border-parchment-600 text-parchment-400'
                : 'bg-blood-900/40 border-blood-700 text-blood-300'
            }`}>
              {state.current_hp === 0 ? '☠️ Downed' : state.mounted ? '🐴 Mounted' : '🚶 Leading'}
            </span>
          </div>

          {/* HP bar */}
          <div className="mb-3">
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="text-parchment-400">Mount HP</span>
              <span className="font-semibold text-parchment-200">
                {state.current_hp}/{state.max_hp}
                {state.conditions.length > 0 && (
                  <span className="ml-2 text-blood-300">[{state.conditions.join(', ')}]</span>
                )}
              </span>
            </div>
            <div className="h-2.5 rounded-full bg-parchment-800/70 overflow-hidden">
              <div className={`h-full ${hpColor} transition-all duration-300`} style={{ width: `${hpPct}%` }} />
            </div>
          </div>

          {/* Stat chips */}
          <div className="grid grid-cols-3 gap-2 text-center text-xs mb-3">
            <div className="bg-parchment-800/40 rounded p-2">
              <div className="text-parchment-500 uppercase tracking-wide">Speed</div>
              <div className="font-semibold text-arcane-300">{mount.effective_speed} ft</div>
            </div>
            <div className="bg-parchment-800/40 rounded p-2">
              <div className="text-parchment-500 uppercase tracking-wide">Carry</div>
              <div className="font-semibold text-leaf-300">{mount.carrying_capacity_lbs} lb</div>
            </div>
            <div className="bg-parchment-800/40 rounded p-2">
              <div className="text-parchment-500 uppercase tracking-wide">Travel</div>
              <div className="font-semibold text-gold-300">×{summary.travel_multiplier?.toFixed(2) ?? mount.speed_multiplier.toFixed(2)}</div>
            </div>
          </div>

          {/* Mount-up / Dismount */}
          <div className="grid grid-cols-2 gap-2 mb-3">
            <button
              className="btn-primary text-sm"
              onClick={handleMountUp}
              disabled={busy || state.mounted || state.current_hp === 0}
              title="Climb into the saddle (half your movement in combat)"
            >
              🐴 Mount up
            </button>
            <button
              className="btn-primary text-sm bg-parchment-700 hover:bg-parchment-600"
              onClick={handleDismount}
              disabled={busy || !state.mounted}
              title="Dismount but keep leading the mount"
            >
              🚶 Dismount
            </button>
          </div>

          {/* Pace selector */}
          <div className="bg-parchment-800/30 rounded-md p-3 mb-3">
            <div className="text-xs text-parchment-500 font-semibold uppercase tracking-wide mb-2">
              Travel Pace
            </div>
            <div className="grid grid-cols-3 gap-2 mb-2">
              {PACE_OPTIONS.map((p) => (
                <button
                  key={p.value}
                  className={`text-xs py-1.5 rounded border transition-colors ${
                    state.pace === p.value
                      ? 'bg-arcane-900/50 border-arcane-600 text-arcane-200'
                      : 'bg-parchment-800/40 border-parchment-700 text-parchment-400 hover:text-parchment-200'
                  }`}
                  onClick={() => handlePace(p.value, state.galloping)}
                  disabled={busy}
                  title={p.note}
                >
                  {p.label}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2 text-xs">
              <label className="text-parchment-400">🏇 Gallop burst</label>
              <button
                type="button"
                onClick={() => handlePace(state.pace as 'slow' | 'normal' | 'fast', !state.galloping)}
                disabled={busy || mount.is_vehicle}
                className={`px-2 py-0.5 rounded border text-xs ${
                  state.galloping
                    ? 'bg-gold-900/40 border-gold-700 text-gold-300'
                    : 'bg-parchment-800/50 border-parchment-700 text-parchment-400'
                }`}
                title={mount.is_vehicle ? 'Vehicles cannot gallop' : '~2× distance for the first hour/day'}
              >
                {state.galloping ? 'On' : 'Off'}
              </button>
              <span className="text-parchment-600">· {summary.pace_note}</span>
            </div>
          </div>

          {/* Damage / Heal */}
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-blood-900/20 rounded-md p-2.5 border border-blood-800/40">
              <div className="flex items-center justify-between text-xs mb-1.5">
                <label className="text-blood-300 font-semibold">⚔️ Damage</label>
                <input
                  type="number"
                  min={0}
                  value={dmgAmount}
                  onChange={(e) => setDmgAmount(Math.max(0, Number(e.target.value)))}
                  disabled={busy}
                  className="w-14 bg-parchment-900/60 border border-parchment-700 rounded px-1.5 py-0.5 text-parchment-200 text-xs text-right"
                />
              </div>
              <button
                className="w-full btn-primary text-xs bg-blood-800 hover:bg-blood-700"
                onClick={handleDamage}
                disabled={busy || state.current_hp === 0}
              >
                Apply
              </button>
            </div>
            <div className="bg-leaf-900/20 rounded-md p-2.5 border border-leaf-800/40">
              <div className="flex items-center justify-between text-xs mb-1.5">
                <label className="text-leaf-300 font-semibold">✨ Heal</label>
                <input
                  type="number"
                  min={0}
                  value={healAmount}
                  onChange={(e) => setHealAmount(Math.max(0, Number(e.target.value)))}
                  disabled={busy}
                  className="w-14 bg-parchment-900/60 border border-parchment-700 rounded px-1.5 py-0.5 text-parchment-200 text-xs text-right"
                />
              </div>
              <button
                className="w-full btn-primary text-xs bg-leaf-800 hover:bg-leaf-700"
                onClick={handleHeal}
                disabled={busy || state.current_hp >= state.max_hp}
              >
                Apply
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="rounded-lg p-4 border bg-parchment-900/40 border-parchment-700/40 text-center">
          <div className="text-4xl mb-2">🚶</div>
          <p className="text-parchment-400 text-sm">You are on foot. Acquire a mount below to travel faster and gain mounted-combat options.</p>
        </div>
      )}

      {/* Result flash */}
      {flash && (
        <div className="rounded-lg p-3 border text-sm animate-fade-in bg-arcane-900/40 border-arcane-700 text-parchment-200">
          {flash}
        </div>
      )}
      {error && <div className="text-blood-500 text-sm">{error}</div>}

      {/* Combat modifiers preview */}
      <div className="bg-parchment-900/60 rounded-lg p-3">
        <button
          className="w-full flex items-center justify-between text-left"
          onClick={() => setShowCombat((s) => !s)}
        >
          <span className="text-xs text-parchment-500 font-semibold uppercase tracking-wide">
            ⚔️ Mounted Combat Modifiers
          </span>
          <span className="text-parchment-500 text-xs">{showCombat ? '▲' : '▼'}</span>
        </button>
        {showCombat && (
          <div className="mt-3 space-y-2">
            <div className="flex items-center gap-2 text-xs">
              <label className="text-parchment-400">Target size</label>
              <select
                value={targetSize}
                onChange={(e) => setTargetSize(e.target.value)}
                disabled={busy}
                className="bg-parchment-900/60 border border-parchment-700 rounded px-2 py-1 text-parchment-200 text-xs capitalize"
              >
                {SIZES.map((s) => (
                  <option key={s} value={s} className="capitalize">{s}</option>
                ))}
              </select>
              <button className="btn-primary text-xs px-2 py-1" onClick={handleCombat} disabled={busy}>
                Compute
              </button>
            </div>
            {combatResult && (
              <div className="rounded-md border border-parchment-700/50 bg-parchment-800/30 p-2.5 space-y-1.5 text-xs">
                {combatResult.modifiers.mounted ? (
                  <>
                    <div className="flex flex-wrap gap-1.5">
                      {combatResult.modifiers.melee_advantage && combatResult.melee_advantage_vs_target && (
                        <span className="px-1.5 py-0.5 rounded bg-leaf-900/40 border border-leaf-700/50 text-leaf-300">
                          ⬆ Advantage vs smaller unmounted
                        </span>
                      )}
                      {combatResult.modifiers.has_mounted_combatant_feat && (
                        <span className="px-1.5 py-0.5 rounded bg-gold-900/40 border border-gold-700/50 text-gold-300">
                          ✦ Dex-save adv · evasion · redirect
                        </span>
                      )}
                    </div>
                    {!combatResult.melee_advantage_vs_target && combatResult.modifiers.melee_advantage && (
                      <p className="text-parchment-500">
                        No advantage vs this target (not smaller than the mount).
                      </p>
                    )}
                    <ul className="space-y-0.5 text-parchment-400 list-disc list-inside">
                      {combatResult.modifiers.notes.map((n, i) => (
                        <li key={i}>{n}</li>
                      ))}
                    </ul>
                  </>
                ) : (
                  <p className="text-parchment-500">
                    {combatResult.modifiers.notes[0] ?? 'You are not currently mounted.'}
                  </p>
                )}
                {combatResult.weapon_rules.lance?.notes && (
                  <p className="text-parchment-500 italic border-t border-parchment-700/40 pt-1.5">
                    {combatResult.weapon_rules.lance.notes}
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Travel preview */}
      <div className="bg-parchment-900/60 rounded-lg p-3">
        <button
          className="w-full flex items-center justify-between text-left"
          onClick={() => setShowTravel((s) => !s)}
        >
          <span className="text-xs text-parchment-500 font-semibold uppercase tracking-wide">
            🗺️ Travel-Time Preview
          </span>
          <span className="text-parchment-500 text-xs">{showTravel ? '▲' : '▼'}</span>
        </button>
        {showTravel && (
          <div className="mt-3 space-y-2">
            <div className="flex items-center gap-2 text-xs">
              <label className="text-parchment-400">On-foot hours</label>
              <input
                type="number"
                min={0}
                value={travelHours}
                onChange={(e) => setTravelHours(Math.max(0, Number(e.target.value)))}
                disabled={busy}
                className="w-16 bg-parchment-900/60 border border-parchment-700 rounded px-1.5 py-1 text-parchment-200 text-xs text-right"
              />
              <button className="btn-primary text-xs px-2 py-1" onClick={handleTravel} disabled={busy}>
                Preview
              </button>
            </div>
            {travelResult && (
              <div className="rounded-md border border-parchment-700/50 bg-parchment-800/30 p-2.5 text-xs space-y-1">
                <div className="flex items-baseline gap-2">
                  <span className="text-parchment-500 line-through">{travelResult.speed.base_hours}h on foot</span>
                  <span className="text-arcane-300 text-lg font-bold">→ {travelResult.speed.adjusted_hours}h</span>
                  {travelResult.speed.galloping && <span className="text-gold-300">🏇 galloping</span>}
                </div>
                <div className="text-parchment-500">
                  Pace ×{travelResult.speed.pace_multiplier.toFixed(2)} · Mount ×{travelResult.speed.mount_multiplier.toFixed(2)} · Total ×{travelResult.speed.total_multiplier.toFixed(2)}
                </div>
                <ul className="text-parchment-500 list-disc list-inside space-y-0.5">
                  {travelResult.speed.notes.map((n, i) => (
                    <li key={i}>{n}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Registry browser */}
      <div className="bg-parchment-900/60 rounded-lg p-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-parchment-500 font-semibold uppercase tracking-wide">
            🐎 Mounts & Vehicles
          </span>
          {characterGold !== undefined && (
            <span className="text-xs text-gold-300">💰 {characterGold} gp</span>
          )}
        </div>

        {/* Pay toggle */}
        <div className="flex items-center gap-2 mb-3 text-xs">
          <label className="text-parchment-400">Pay gold on acquire</label>
          <button
            type="button"
            onClick={() => setPayForMount((p) => !p)}
            disabled={busy}
            className={`px-2 py-0.5 rounded border text-xs ${
              payForMount
                ? 'bg-gold-900/40 border-gold-700 text-gold-300'
                : 'bg-parchment-800/50 border-parchment-700 text-parchment-400'
            }`}
          >
            {payForMount ? 'On' : 'Off'}
          </button>
          <span className="text-parchment-600">· {payForMount ? 'deducts cost, fails if broke' : 'free acquisition'}</span>
        </div>

        {/* Type filter */}
        <div className="flex flex-wrap gap-1.5 mb-3">
          {['all', 'land', 'flying', 'aquatic', 'vehicle'].map((t) => (
            <button
              key={t}
              className={`text-xs px-2 py-0.5 rounded-full border capitalize transition-colors ${
                registryFilter === t
                  ? 'bg-arcane-900/50 border-arcane-600 text-arcane-200'
                  : 'bg-parchment-800/40 border-parchment-700 text-parchment-400 hover:text-parchment-200'
              }`}
              onClick={() => setRegistryFilter(t)}
            >
              {TYPE_ICON[t] ?? '📦'} {t}
            </button>
          ))}
        </div>

        {/* Mount grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-72 overflow-y-auto pr-1">
          {filteredRegistry.map((m) => {
            const affordable = canAfford(m)
            const isCurrent = m.id === state.mount_id
            return (
              <div
                key={m.id}
                className={`rounded-md border p-2.5 text-xs transition-colors ${
                  isCurrent
                    ? 'border-gold-600/60 bg-gold-900/20'
                    : 'border-parchment-700/50 bg-parchment-800/30'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="font-semibold text-parchment-200 flex items-center gap-1">
                      <span>{TYPE_ICON[m.type] ?? '🐎'}</span>
                      {m.name}
                      {isCurrent && <span className="text-gold-400">●</span>}
                    </div>
                    <div className="text-parchment-500 capitalize">
                      {m.size} · {m.type} · {m.effective_speed} ft
                      {m.can_fly && ' 🪽'}
                      {m.can_swim && ' 🌊'}
                    </div>
                    <div className="text-parchment-600 mt-0.5 leading-snug">{m.description}</div>
                    {m.notes && <div className="text-arcane-300 mt-0.5">⚙ {m.notes}</div>}
                  </div>
                  <div className="text-right shrink-0">
                    <div className={`font-bold ${m.cost_gp > 0 ? 'text-gold-300' : 'text-leaf-300'}`}>
                      {m.cost_gp > 0 ? `${m.cost_gp} gp` : 'free'}
                    </div>
                    <button
                      className="mt-1 btn-primary text-xs px-2 py-0.5"
                      onClick={() => handleAcquire(m)}
                      disabled={busy || isCurrent || (payForMount && !affordable)}
                      title={
                        isCurrent
                          ? 'Currently owned'
                          : payForMount && !affordable
                          ? 'Cannot afford'
                          : `Acquire a ${m.name}`
                      }
                    >
                      {isCurrent ? 'Owned' : 'Acquire'}
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
        <p className="text-xs text-parchment-600 mt-2 leading-relaxed">
          Acquiring replaces your current mount. Mounts persist in your game state and round-trip through save/load.
        </p>
      </div>
    </div>
  )
}
