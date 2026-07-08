import { useEffect, useState } from 'react'
import { getSavingThrowProficiencies, rollSavingThrow } from '../stores/api'
import type { SavingThrowProficienciesResponse, SavingThrowRollResult } from '../types'

/** The six abilities in display order with short labels. */
const ABILITY_ORDER: { key: string; label: string; abbr: string }[] = [
  { key: 'strength', label: 'Strength', abbr: 'STR' },
  { key: 'dexterity', label: 'Dexterity', abbr: 'DEX' },
  { key: 'constitution', label: 'Constitution', abbr: 'CON' },
  { key: 'intelligence', label: 'Intelligence', abbr: 'INT' },
  { key: 'wisdom', label: 'Wisdom', abbr: 'WIS' },
  { key: 'charisma', label: 'Charisma', abbr: 'CHA' },
]

const formatMod = (n: number) => (n >= 0 ? `+${n}` : `${n}`)

/** Common save DCs (mirrors the spell DC band; PHB traps/spells sit here). */
const DC_PRESETS = [
  { label: 'Easy', dc: 10 },
  { label: 'Medium', dc: 13 },
  { label: 'Hard', dc: 16 },
  { label: 'V. Hard', dc: 19 },
]

interface Props {
  characterId: number
  /** Active conditions to enforce on the roll (e.g. paralyzed auto-fails Str/Dex). */
  conditions?: string[]
}

export default function SavingThrowsPanel({ characterId, conditions = [] }: Props) {
  const [data, setData] = useState<SavingThrowProficienciesResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Roll state
  const [activeAbility, setActiveAbility] = useState<string | null>(null)
  const [dc, setDc] = useState(13)
  const [advantage, setAdvantage] = useState(false)
  const [disadvantage, setDisadvantage] = useState(false)
  const [lastResult, setLastResult] = useState<SavingThrowRollResult | null>(null)
  const [rolling, setRolling] = useState(false)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const profs = await getSavingThrowProficiencies(characterId)
      setData(profs)
    } catch {
      setError('Failed to load saving throws')
    }
    setLoading(false)
  }

  useEffect(() => {
    load()
  }, [characterId])

  const handleRoll = async (ability: string) => {
    setActiveAbility(ability)
    setLastResult(null)
    setRolling(true)
    try {
      const result = await rollSavingThrow(characterId, ability, dc, advantage, disadvantage, conditions)
      setLastResult(result)
    } catch {
      setError('Saving throw failed')
    }
    setRolling(false)
  }

  if (loading) {
    return <div className="text-parchment-400 animate-pulse text-center py-12">Steadying your resolve…</div>
  }
  if (error || !data) {
    return (
      <div className="text-center py-8">
        <div className="text-blood-400 mb-3">{error || 'No save data'}</div>
        <button className="btn-primary" onClick={load}>Retry</button>
      </div>
    )
  }

  return (
    <div>
      {/* Summary band: how many saves are proficient */}
      <div className="mb-3 text-center">
        <span className="text-xs text-parchment-500">
          Proficient in <span className="text-leaf-400 font-semibold">{data.proficiencies.length}</span> of 6 saves
        </span>
      </div>

      {/* Saves grid */}
      <div className="space-y-1.5 mb-4">
        {ABILITY_ORDER.map(({ key, label, abbr }) => {
          const proficient = data.proficiencies.includes(key)
          const bonus = data.bonus_by_ability[key] ?? 0
          const featName = data.feat_sources[key]
          const isActive = activeAbility === key
          return (
            <button
              key={key}
              onClick={() => setActiveAbility(key)}
              className={`flex items-center justify-between w-full rounded-md px-3 py-2 text-sm transition-all duration-150 hover:-translate-y-0.5 active:scale-95 ${
                isActive
                  ? 'bg-arcane-800/70 ring-1 ring-arcane-500'
                  : 'bg-parchment-900/60 hover:bg-parchment-800/60'
              }`}
              title={`${label} save — click to roll${featName ? ` · feat: ${featName}` : ''}`}
            >
              <span className="flex items-center gap-2 min-w-0">
                <span className="w-4 text-center shrink-0">
                  {proficient ? (
                    <span className="text-leaf-400 text-xs" title="Proficient">●</span>
                  ) : (
                    <span className="text-parchment-700 text-xs">○</span>
                  )}
                </span>
                <span className={`font-medium ${proficient ? 'text-parchment-200' : 'text-parchment-400'}`}>
                  {label}
                </span>
                <span className="text-[10px] text-parchment-600 font-mono">{abbr}</span>
                {featName && (
                  <span
                    className="shrink-0 text-[9px] font-semibold uppercase tracking-wide text-gold-300 bg-gold-900/40 border border-gold-700/50 rounded px-1 leading-tight"
                    title={`Save proficiency granted by feat: ${featName}`}
                  >
                    ✦ {featName}
                  </span>
                )}
              </span>
              <span className={`font-mono shrink-0 ml-2 ${proficient ? 'text-arcane-300' : 'text-parchment-400'}`}>
                {formatMod(bonus)}
              </span>
            </button>
          )
        })}
      </div>

      {/* Roll controls for the active save */}
      {activeAbility && (
        <div className="bg-parchment-900/70 rounded-lg p-3 border border-arcane-800/50 animate-scale-in">
          <div className="flex items-center justify-between mb-2">
            <span className="font-fantasy text-parchment-200">
              🛡️ {ABILITY_ORDER.find((a) => a.key === activeAbility)?.label} Save
            </span>
            <button
              className="text-parchment-500 hover:text-parchment-300 text-lg leading-none"
              onClick={() => { setActiveAbility(null); setLastResult(null) }}
            >×</button>
          </div>

          {/* DC presets + custom */}
          <div className="flex items-center gap-1 mb-2 flex-wrap">
            <span className="text-xs text-parchment-500 mr-1">DC:</span>
            {DC_PRESETS.map((p) => (
              <button
                key={p.dc}
                onClick={() => setDc(p.dc)}
                className={`text-xs px-2 py-1 rounded transition-colors ${
                  dc === p.dc ? 'bg-arcane-700 text-parchment-100' : 'bg-parchment-800/60 text-parchment-400 hover:bg-parchment-700/60'
                }`}
              >
                {p.label} ({p.dc})
              </button>
            ))}
            <input
              type="number"
              min={1}
              max={30}
              value={dc}
              onChange={(e) => setDc(Math.max(1, Math.min(30, parseInt(e.target.value) || 1)))}
              className="w-16 input-field text-xs px-2 py-1"
            />
          </div>

          {/* Advantage toggles */}
          <div className="flex gap-2 mb-3">
            <button
              onClick={() => { setAdvantage(!advantage); if (!advantage) setDisadvantage(false) }}
              className={`text-xs px-3 py-1 rounded transition-colors ${
                advantage ? 'bg-leaf-700 text-parchment-100' : 'bg-parchment-800/60 text-parchment-400 hover:bg-parchment-700/60'
              }`}
            >
              ▲ Advantage
            </button>
            <button
              onClick={() => { setDisadvantage(!disadvantage); if (!disadvantage) setAdvantage(false) }}
              className={`text-xs px-3 py-1 rounded transition-colors ${
                disadvantage ? 'bg-blood-700 text-parchment-100' : 'bg-parchment-800/60 text-parchment-400 hover:bg-parchment-700/60'
              }`}
            >
              ▼ Disadvantage
            </button>
          </div>

          {conditions.length > 0 && (
            <p className="text-[11px] text-amber-400/80 mb-2">
              ⚠ Active conditions enforced: {conditions.join(', ')}
            </p>
          )}

          <button
            className="btn-primary w-full"
            onClick={() => handleRoll(activeAbility)}
            disabled={rolling}
          >
            {rolling ? 'Rolling…' : `Roll ${ABILITY_ORDER.find((a) => a.key === activeAbility)?.label} Save (DC ${dc})`}
          </button>

          {/* Result */}
          {lastResult && (
            <div className={`mt-3 rounded-lg p-3 border animate-scale-in ${
              lastResult.success
                ? 'bg-leaf-900/40 border-leaf-700'
                : 'bg-blood-900/40 border-blood-700'
            }`}>
              <div className="flex items-center justify-between">
                <span className="text-sm text-parchment-300">{lastResult.description}</span>
                <span className={`font-fantasy text-xl ${lastResult.success ? 'text-leaf-300' : 'text-blood-300'}`}>
                  {lastResult.auto_failed ? '✗ Auto-fail' : lastResult.success ? '✓ Success' : '✗ Failure'}
                </span>
              </div>
              <div className="text-xs text-parchment-400 mt-1 font-mono">
                {!lastResult.auto_failed && (
                  <>
                    Roll: {lastResult.rolls.join(' & ')} {lastResult.modifier >= 0 ? '+' : ''}{lastResult.modifier} = <span className="text-parchment-200 font-bold">{lastResult.total}</span>
                    <span className="text-parchment-600"> vs DC {lastResult.dc}</span>
                  </>
                )}
                {lastResult.advantage && <span className="ml-2 text-leaf-400">(advantage)</span>}
                {lastResult.disadvantage && <span className="ml-2 text-blood-400">(disadvantage)</span>}
              </div>
            </div>
          )}
        </div>
      )}

      <p className="text-xs text-parchment-600 mt-3 text-center">
        ● Proficient &nbsp; <span className="text-gold-300">✦ badge</span> = feat-granted save &nbsp; — Click a save to roll.
      </p>
    </div>
  )
}
