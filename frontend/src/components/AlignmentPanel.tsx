import { useEffect, useState } from 'react'
import {
  getCharacterAlignment,
  getAlignment,
  listAlignments,
  getSuggestedAlignments,
  setCharacterAlignment,
} from '../stores/api'
import type {
  CharacterAlignment,
  AlignmentSummary,
  AlignmentDetail,
  SetAlignmentResult,
  SuggestedAlignments,
} from '../types'

/* ------------------------------------------------------------------ *
 * Client-side relationship math — mirrors the backend engine exactly  *
 * (engine/alignment.py: ETHICS_VALUES / MORALS_VALUES / _disposition).*
 * Computing it locally avoids a network round-trip on every hover.    *
 * ------------------------------------------------------------------ */

const ETHICS_INDEX: Record<string, number> = { lawful: 0, neutral: 1, chaotic: 2 }
const MORALS_INDEX: Record<string, number> = { good: 0, neutral: 1, evil: 2 }

/** disposition label + colour for a given total grid distance (0-4). */
function dispositionFor(totalDistance: number): { label: string; description: string; color: string } {
  if (totalDistance <= 0)
    return {
      label: 'friendly',
      description: 'Shares the same worldview — natural allies who see eye to eye.',
      color: 'text-leaf-400',
    }
  if (totalDistance === 1)
    return {
      label: 'cordial',
      description: 'Close in outlook; minor friction but broadly compatible.',
      color: 'text-leaf-300',
    }
  if (totalDistance === 2)
    return {
      label: 'wary',
      description: 'Differ on at least one axis — tension and mutual suspicion.',
      color: 'text-gold-400',
    }
  if (totalDistance === 3)
    return {
      label: 'tense',
      description: 'Strongly opposed; cooperation requires extraordinary cause.',
      color: 'text-blood-300',
    }
  return {
    label: 'hostile',
    description: 'Diametrically opposed worldviews — outright hostility is likely.',
    color: 'text-blood-400',
  }
}

interface Relationship {
  ethics_delta: number
  morals_delta: number
  total_distance: number
  label: string
  description: string
  color: string
}

function relationshipBetween(aEthics: string, aMorals: string, bEthics: string, bMorals: string): Relationship {
  const eDelta = Math.abs((ETHICS_INDEX[aEthics] ?? 1) - (ETHICS_INDEX[bEthics] ?? 1))
  const mDelta = Math.abs((MORALS_INDEX[aMorals] ?? 1) - (MORALS_INDEX[bMorals] ?? 1))
  const total = eDelta + mDelta
  const d = dispositionFor(total)
  return {
    ethics_delta: eDelta,
    morals_delta: mDelta,
    total_distance: total,
    label: d.label,
    description: d.description,
    color: d.color,
  }
}

/** Stable 3x3 grid order: rows = morals (good→evil), cols = ethics (lawful→chaotic). */
const GRID_ORDER: string[][] = [
  ['lawful_good', 'neutral_good', 'chaotic_good'],
  ['lawful_neutral', 'neutral', 'chaotic_neutral'],
  ['lawful_evil', 'neutral_evil', 'chaotic_evil'],
]

const AXIS_LABEL = (v: string): string =>
  v.charAt(0).toUpperCase() + v.slice(1)

interface Props {
  characterId: number
  /** Called after an alignment is applied so the parent can refresh game state. */
  onChanged?: () => void
}

export default function AlignmentPanel({ characterId, onChanged }: Props) {
  const [charAlign, setCharAlign] = useState<CharacterAlignment | null>(null)
  const [alignments, setAlignments] = useState<AlignmentSummary[]>([])
  const [suggested, setSuggested] = useState<SuggestedAlignments | null>(null)
  const [preview, setPreview] = useState<AlignmentDetail | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<SetAlignmentResult | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [ca, list, sug] = await Promise.all([
        getCharacterAlignment(characterId),
        listAlignments(),
        getSuggestedAlignments(characterId),
      ])
      setCharAlign(ca)
      setAlignments(list)
      setSuggested(sug)
    } catch {
      setError('Failed to load alignment data')
    }
    setLoading(false)
  }

  useEffect(() => {
    load()
  }, [characterId])

  // Fetch full detail (with roleplay hooks) when an alignment is selected.
  useEffect(() => {
    if (!selected) {
      setPreview(null)
      return
    }
    let cancelled = false
    getAlignment(selected)
      .then((detail) => {
        if (!cancelled) setPreview(detail)
      })
      .catch(() => {
        if (!cancelled) setError('Failed to load alignment detail')
      })
    return () => {
      cancelled = true
    }
  }, [selected])

  const handleApply = async () => {
    if (!selected) return
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const res = await setCharacterAlignment(characterId, selected)
      setResult(res)
      const ca = await getCharacterAlignment(characterId)
      setCharAlign(ca)
      const sug = await getSuggestedAlignments(characterId)
      setSuggested(sug)
      setSelected(null)
      setPreview(null)
      onChanged?.()
    } catch {
      setError('Failed to apply alignment')
    }
    setBusy(false)
  }

  if (loading) {
    return (
      <div className="text-parchment-400 animate-pulse text-center py-12">
        Consulting the scales of morality…
      </div>
    )
  }
  if (error || !charAlign) {
    return (
      <div className="text-center py-8">
        <div className="text-blood-400 mb-3">{error || 'No alignment data'}</div>
        <button className="btn-primary" onClick={load}>
          Retry
        </button>
      </div>
    )
  }

  const current = charAlign.detail
  const currentId = charAlign.alignment
  const isChanging = selected !== null && selected !== currentId
  const byId: Record<string, AlignmentSummary> = Object.fromEntries(
    alignments.map((a) => [a.id, a]),
  )
  // Sets of suggested ids for quick lookups / grid badges.
  const suggestedSet = new Set(suggested?.suggested ?? [])
  const raceTendSet = new Set(suggested?.race_tendencies ?? [])
  const classTendSet = new Set(suggested?.class_tendencies ?? [])

  return (
    <div className="space-y-4">
      {/* Current alignment summary card */}
      {current ? (
        <div className="bg-parchment-900/60 rounded-lg p-3 border border-arcane-800/40 animate-scale-in">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] uppercase text-parchment-500 tracking-wide">
              Current Alignment
            </span>
            <span className="text-[10px] text-arcane-300 font-mono font-semibold">
              {current.abbreviation}
            </span>
          </div>
          <h3 className="font-fantasy text-xl text-parchment-100">{current.name}</h3>
          <p className="text-sm text-parchment-400 mt-1 leading-relaxed">
            {current.description}
          </p>

          {/* Ethics & Morals axes */}
          <div className="grid grid-cols-2 gap-2 mt-3">
            <div className="bg-parchment-900/50 rounded-md p-2">
              <div className="text-parchment-500 uppercase tracking-wide text-[10px] mb-1">
                Ethics
              </div>
              <span className="text-sm text-arcane-300 font-semibold">
                {AXIS_LABEL(current.ethics)}
              </span>
              <span className="text-[10px] text-parchment-600 ml-1">
                {current.ethics === 'lawful'
                  ? 'order & tradition'
                  : current.ethics === 'chaotic'
                  ? 'freedom & whim'
                  : 'balanced'}
              </span>
            </div>
            <div className="bg-parchment-900/50 rounded-md p-2">
              <div className="text-parchment-500 uppercase tracking-wide text-[10px] mb-1">
                Morals
              </div>
              <span className="text-sm text-gold-300 font-semibold">
                {AXIS_LABEL(current.morals)}
              </span>
              <span className="text-[10px] text-parchment-600 ml-1">
                {current.morals === 'good'
                  ? 'altruistic'
                  : current.morals === 'evil'
                  ? 'selfish'
                  : 'indifferent'}
              </span>
            </div>
          </div>

          {/* Roleplay hooks */}
          {current.roleplay_hooks.length > 0 && (
            <div className="mt-3 pt-2 border-t border-parchment-800/60">
              <div className="text-[10px] uppercase text-parchment-500 tracking-wide mb-1.5">
                ⚔️ Roleplay Hooks
              </div>
              <ul className="text-[11px] text-parchment-300 space-y-1 list-disc list-inside leading-relaxed">
                {current.roleplay_hooks.map((h, i) => (
                  <li key={i}>{h}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Suggested alignments for this race/class */}
          {suggested && (suggested.suggested.length > 0) && (
            <div className="mt-3 pt-2 border-t border-parchment-800/60">
              <div className="text-[10px] uppercase text-parchment-500 tracking-wide mb-1.5">
                Typical for {suggested.race ?? 'your race'} {suggested.char_class ?? 'your class'}
              </div>
              <div className="flex flex-wrap gap-1">
                {suggested.suggested.map((id) => {
                  const a = byId[id]
                  if (!a) return null
                  return (
                    <span
                      key={id}
                      className="text-[11px] px-1.5 py-0.5 bg-arcane-900/40 text-arcane-300 rounded border border-arcane-800/40"
                    >
                      {a.name}
                    </span>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="bg-parchment-900/60 rounded-lg p-3 border border-blood-700/40">
          <p className="text-sm text-parchment-300">
            No alignment set. Pick one from the grid below to define how your
            character sees the world.
          </p>
        </div>
      )}

      {/* Divider + change alignment */}
      <div className="flex items-center gap-2">
        <div className="flex-1 h-px bg-parchment-800/60" />
        <span className="text-xs text-parchment-600 uppercase tracking-wide">
          {current ? 'Change Alignment' : 'Choose an Alignment'}
        </span>
        <div className="flex-1 h-px bg-parchment-800/60" />
      </div>

      {/* The classic 3x3 alignment grid */}
      <div className="select-none">
        {/* Column headers: Lawful / Neutral / Chaotic */}
        <div className="grid grid-cols-[auto_1fr_1fr_1fr] gap-1.5 mb-1.5">
          <div />
          {['Lawful', 'Neutral', 'Chaotic'].map((c) => (
            <div
              key={c}
              className="text-[10px] uppercase tracking-wide text-arcane-300/70 text-center font-semibold"
            >
              {c}
            </div>
          ))}
        </div>

        {/* Rows: Good / Neutral / Evil */}
        {GRID_ORDER.map((row, rowIdx) => {
          const rowLabel = ['Good', 'Neutral', 'Evil'][rowIdx]
          const rowColor =
            rowIdx === 0
              ? 'text-leaf-300/80'
              : rowIdx === 1
              ? 'text-parchment-400'
              : 'text-blood-300/80'
          return (
            <div
              key={rowIdx}
              className="grid grid-cols-[auto_1fr_1fr_1fr] gap-1.5 mb-1.5"
            >
              <div
                className={`flex items-center justify-end pr-1 text-[10px] uppercase tracking-wide font-semibold ${rowColor}`}
              >
                {rowLabel}
              </div>
              {row.map((id) => {
                const a = byId[id]
                if (!a) {
                  return <div key={id} />
                }
                const isCurrent = id === currentId
                const isSelected = id === selected
                const isSuggested = suggestedSet.has(id)
                const fromRace = raceTendSet.has(id)
                const fromClass = classTendSet.has(id)
                return (
                  <button
                    key={id}
                    onClick={() => setSelected(isSelected ? null : id)}
                    title={a.name}
                    className={`relative rounded-md px-1.5 py-2 text-center transition-all duration-150 hover:-translate-y-0.5 active:scale-95 ${
                      isSelected
                        ? 'bg-arcane-800/80 ring-1 ring-arcane-500'
                        : isCurrent
                        ? 'bg-leaf-900/40 ring-1 ring-leaf-600/60'
                        : 'bg-parchment-900/60 hover:bg-parchment-800/60'
                    }`}
                  >
                    <div
                      className={`text-sm font-bold ${
                        isSelected
                          ? 'text-arcane-200'
                          : isCurrent
                          ? 'text-leaf-200'
                          : 'text-parchment-200'
                      }`}
                    >
                      {a.abbreviation}
                    </div>
                    <div className="text-[9px] text-parchment-500 leading-tight mt-0.5 truncate">
                      {a.name.replace(/ (Good|Neutral|Evil)/, '')}
                    </div>
                    {/* Badges: current / suggested */}
                    {isCurrent && (
                      <span className="absolute -top-1 -right-1 text-[8px] bg-leaf-600 text-parchment-950 rounded-full px-1 font-bold">
                        ✓
                      </span>
                    )}
                    {!isCurrent && isSuggested && (
                      <span
                        className="absolute -top-1 -right-1 text-[8px] bg-gold-500 text-parchment-950 rounded-full px-1 font-bold"
                        title={`Typical${fromRace && fromClass ? ' (race & class)' : fromRace ? ' (race)' : ' (class)'}`}
                      >
                        ★
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          )
        })}

        {/* Legend */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-parchment-600 mt-1">
          <span className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-full bg-leaf-500" /> current
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-full bg-gold-500" /> typical for race/class
          </span>
        </div>
      </div>

      {/* Preview + relationship to current alignment */}
      {preview && current && (
        <div className="bg-parchment-900/70 rounded-lg p-3 border border-arcane-700/50 animate-scale-in">
          <div className="flex items-center justify-between mb-2">
            <span className="font-fantasy text-lg text-parchment-100">
              {preview.name}
            </span>
            <button
              className="text-parchment-500 hover:text-parchment-300 text-lg leading-none"
              onClick={() => setSelected(null)}
            >
              ×
            </button>
          </div>
          <p className="text-xs text-parchment-400 leading-relaxed mb-2">
            {preview.description}
          </p>

          {/* Relationship to the CURRENT alignment */}
          {selected !== currentId ? (
            (() => {
              const rel = relationshipBetween(
                current.ethics,
                current.morals,
                preview.ethics,
                preview.morals,
              )
              const axisWord = (e: number, m: number): string => {
                const parts: string[] = []
                if (e > 0) parts.push(`${e} step${e > 1 ? 's' : ''} on law↔chaos`)
                if (m > 0) parts.push(`${m} step${m > 1 ? 's' : ''} on good↔evil`)
                return parts.join(' + ') || 'identical'
              }
              return (
                <div className="bg-parchment-950/50 rounded-md p-2 border border-parchment-800/60 mb-2">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] uppercase tracking-wide text-parchment-500">
                      Shift from {current.name}
                    </span>
                    <span className={`text-xs font-bold uppercase ${rel.color}`}>
                      {rel.label}
                    </span>
                  </div>
                  <p className="text-[11px] text-parchment-300 leading-relaxed mb-1">
                    {rel.description}
                  </p>
                  <div className="flex items-center gap-2 text-[10px] text-parchment-500">
                    <span className="font-mono">{axisWord(rel.ethics_delta, rel.morals_delta)}</span>
                    <span>·</span>
                    <span>grid distance {rel.total_distance}/4</span>
                  </div>
                </div>
              )
            })()
          ) : null}

          {/* Roleplay hooks for the candidate */}
          {preview.roleplay_hooks.length > 0 && (
            <div className="mb-2">
              <div className="text-[10px] uppercase text-parchment-500 tracking-wide mb-1">
                Roleplay Hooks
              </div>
              <ul className="text-[11px] text-parchment-300 space-y-0.5 list-disc list-inside leading-relaxed">
                {preview.roleplay_hooks.map((h, i) => (
                  <li key={i}>{h}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Apply controls */}
          <div className="mt-2 pt-2 border-t border-parchment-800/60">
            <button
              className="btn-primary w-full"
              disabled={!isChanging || busy}
              onClick={handleApply}
              title={
                !isChanging
                  ? 'This is already your current alignment'
                  : `Set alignment to ${preview.name}`
              }
            >
              {busy ? 'Applying…' : `Set Alignment to ${preview.name}`}
            </button>
            {!isChanging && (
              <p className="text-[11px] text-parchment-600 mt-1 text-center">
                This is already your alignment.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Result feedback */}
      {result && (
        <div className="bg-leaf-900/40 border border-leaf-700 rounded-lg p-3 animate-scale-in">
          <div className="flex items-center justify-between">
            <span className="font-fantasy text-leaf-300">
              ✓ {result.name}
            </span>
            <span className="text-xs text-arcane-300 font-mono font-semibold">
              {result.abbreviation}
            </span>
          </div>
          <p className="text-[11px] text-parchment-500 mt-1">
            Alignment updated. The DM will now tailor narration and NPC
            reactions to your new moral compass.
          </p>
        </div>
      )}

      {error && <p className="text-xs text-blood-400 text-center">{error}</p>}
    </div>
  )
}
