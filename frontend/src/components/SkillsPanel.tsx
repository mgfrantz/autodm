import { useEffect, useState } from 'react'
import { getSkills, rollSkillCheck } from '../stores/api'
import type { SkillsResponse, SkillCheckResult } from '../types'

/** Abilities in display order with short labels. */
const ABILITY_ORDER: { key: string; label: string }[] = [
  { key: 'strength', label: 'Strength' },
  { key: 'dexterity', label: 'Dexterity' },
  { key: 'intelligence', label: 'Intelligence' },
  { key: 'wisdom', label: 'Wisdom' },
  { key: 'charisma', label: 'Charisma' },
]

const formatMod = (n: number) => (n >= 0 ? `+${n}` : `${n}`)
const titleCase = (s: string) => s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

/** Common skill-check DCs (PHB p.58). */
const DC_PRESETS = [
  { label: 'Easy', dc: 10 },
  { label: 'Medium', dc: 15 },
  { label: 'Hard', dc: 20 },
  { label: 'V. Hard', dc: 25 },
]

interface Props {
  characterId: number
}

export default function SkillsPanel({ characterId }: Props) {
  const [data, setData] = useState<SkillsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Roll state
  const [activeSkill, setActiveSkill] = useState<string | null>(null)
  const [dc, setDc] = useState(15)
  const [advantage, setAdvantage] = useState(false)
  const [disadvantage, setDisadvantage] = useState(false)
  const [lastResult, setLastResult] = useState<SkillCheckResult | null>(null)
  const [rolling, setRolling] = useState(false)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const skills = await getSkills(characterId)
      setData(skills)
    } catch {
      setError('Failed to load skills')
    }
    setLoading(false)
  }

  useEffect(() => {
    load()
  }, [characterId])

  const handleRoll = async (skill: string) => {
    setActiveSkill(skill)
    setLastResult(null)
    setRolling(true)
    try {
      const result = await rollSkillCheck(characterId, skill, dc, advantage, disadvantage)
      setLastResult(result)
    } catch {
      setError('Skill check failed')
    }
    setRolling(false)
  }

  if (loading) {
    return <div className="text-parchment-400 animate-pulse text-center py-12">Consulting your training…</div>
  }
  if (error || !data) {
    return (
      <div className="text-center py-8">
        <div className="text-blood-400 mb-3">{error || 'No skill data'}</div>
        <button className="btn-primary" onClick={load}>Retry</button>
      </div>
    )
  }

  return (
    <div>
      {/* Passive scores */}
      <div className="grid grid-cols-3 gap-2 mb-4">
        {(['perception', 'investigation', 'insight'] as const).map((key) => (
          <div key={key} className="bg-parchment-900/60 rounded-lg p-2 text-center">
            <div className="text-[10px] uppercase text-parchment-500 tracking-wide">{titleCase(key)}</div>
            <div className="text-lg font-fantasy text-arcane-300">{data.passive_scores[key] ?? 10}</div>
            <div className="text-[10px] text-parchment-600">passive</div>
          </div>
        ))}
      </div>

      {/* Skills grouped by ability */}
      <div className="space-y-3 mb-4">
        {ABILITY_ORDER.map(({ key, label }) => {
          const group = data.skills.filter((s) => s.ability === key)
          if (group.length === 0) return null
          return (
            <div key={key} className="bg-parchment-900/40 rounded-lg p-2">
              <div className="text-xs font-semibold text-parchment-400 uppercase tracking-wide mb-1 px-1">
                {label}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-1">
                {group.map((s) => {
                  const isActive = activeSkill === s.skill
                  return (
                    <button
                      key={s.skill}
                      onClick={() => setActiveSkill(s.skill)}
                      className={`flex items-center justify-between rounded-md px-2 py-1.5 text-sm transition-all duration-150 hover:-translate-y-0.5 active:scale-95 ${
                        isActive
                          ? 'bg-arcane-800/70 ring-1 ring-arcane-500'
                          : 'bg-parchment-900/60 hover:bg-parchment-800/60'
                      }`}
                      title={`${titleCase(s.skill)} (${s.ability.slice(0, 3).toUpperCase()}) — click to roll${
                        s.feat_sources.length ? ` · feat: ${s.feat_sources.join(', ')}` : ''
                      }`}
                    >
                      <span className="flex items-center gap-1.5 min-w-0">
                        <span className="w-4 text-center shrink-0">
                          {s.expertise ? (
                            <span className="text-gold-400 text-xs font-bold" title="Expertise">✦✦</span>
                          ) : s.proficient ? (
                            <span className="text-leaf-400 text-xs" title="Proficient">●</span>
                          ) : (
                            <span className="text-parchment-700 text-xs">○</span>
                          )}
                        </span>
                        <span className={`truncate ${s.proficient ? 'text-parchment-200' : 'text-parchment-400'}`}>
                          {titleCase(s.skill)}
                        </span>
                        {s.feat_granted && (
                          <span
                            className="shrink-0 text-[9px] font-semibold uppercase tracking-wide text-gold-300 bg-gold-900/40 border border-gold-700/50 rounded px-1 leading-tight"
                            title={`Granted by feat: ${s.feat_sources.join(', ')}`}
                          >
                            ✦ {s.feat_sources[0]}
                          </span>
                        )}
                      </span>
                      <span className={`font-mono shrink-0 ml-2 ${s.proficient ? 'text-arcane-300' : 'text-parchment-400'}`}>
                        {formatMod(s.modifier)}
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>

      {/* Roll controls for the active skill */}
      {activeSkill && (
        <div className="bg-parchment-900/70 rounded-lg p-3 border border-arcane-800/50 animate-scale-in">
          <div className="flex items-center justify-between mb-2">
            <span className="font-fantasy text-parchment-200">🎲 {titleCase(activeSkill)} Check</span>
            <button
              className="text-parchment-500 hover:text-parchment-300 text-lg leading-none"
              onClick={() => { setActiveSkill(null); setLastResult(null) }}
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
              max={40}
              value={dc}
              onChange={(e) => setDc(Math.max(1, Math.min(40, parseInt(e.target.value) || 1)))}
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

          <button
            className="btn-primary w-full"
            onClick={() => handleRoll(activeSkill)}
            disabled={rolling}
          >
            {rolling ? 'Rolling…' : `Roll ${titleCase(activeSkill)} (DC ${dc})`}
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
                  {lastResult.success ? '✓ Success' : '✗ Failure'}
                </span>
              </div>
              <div className="text-xs text-parchment-400 mt-1 font-mono">
                Roll: {lastResult.rolls.join(' & ')} {lastResult.modifier >= 0 ? '+' : ''}{lastResult.modifier} = <span className="text-parchment-200 font-bold">{lastResult.total}</span>
                <span className="text-parchment-600"> vs DC {lastResult.dc}</span>
                {lastResult.advantage && <span className="ml-2 text-leaf-400">(advantage)</span>}
                {lastResult.disadvantage && <span className="ml-2 text-blood-400">(disadvantage)</span>}
              </div>
            </div>
          )}
        </div>
      )}

      <p className="text-xs text-parchment-600 mt-3 text-center">
        ● Proficient &nbsp; ✦✦ Expertise &nbsp; <span className="text-gold-300">✦ badge</span> = feat-granted &nbsp; — Click a skill to roll a check.
      </p>
    </div>
  )
}
