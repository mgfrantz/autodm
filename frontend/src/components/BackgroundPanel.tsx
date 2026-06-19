import { useEffect, useState } from 'react'
import {
  getCharacterBackground,
  getBackground,
  listBackgrounds,
  setCharacterBackground,
} from '../stores/api'
import type {
  CharacterBackground,
  BackgroundSummary,
  BackgroundDetail,
  SetBackgroundResult,
} from '../types'

const titleCase = (s: string) =>
  s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

/** Rarity → badge color (consistent with InventoryPanel). */
const rarityColor = (rarity: string): string => {
  const r = rarity.toLowerCase()
  if (r.includes('legendary')) return 'text-amber-400'
  if (r.includes('very rare') || r.includes('rare')) return 'text-arcane-300'
  if (r.includes('uncommon')) return 'text-leaf-400'
  return 'text-parchment-500'
}

interface Props {
  characterId: number
  /** Called after a background is applied so the parent can refresh game state. */
  onChanged?: () => void
}

export default function BackgroundPanel({ characterId, onChanged }: Props) {
  const [charBg, setCharBg] = useState<CharacterBackground | null>(null)
  const [backgrounds, setBackgrounds] = useState<BackgroundSummary[]>([])
  const [preview, setPreview] = useState<BackgroundDetail | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [applyEquipment, setApplyEquipment] = useState(true)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<SetBackgroundResult | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [bg, list] = await Promise.all([
        getCharacterBackground(characterId),
        listBackgrounds(),
      ])
      setCharBg(bg)
      setBackgrounds(list)
    } catch {
      setError('Failed to load background data')
    }
    setLoading(false)
  }

  useEffect(() => {
    load()
  }, [characterId])

  // Load full detail when a background is selected for preview.
  useEffect(() => {
    if (!selected) {
      setPreview(null)
      return
    }
    let cancelled = false
    getBackground(selected)
      .then((detail) => {
        if (!cancelled) setPreview(detail)
      })
      .catch(() => {
        if (!cancelled) setError('Failed to load background detail')
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
      const res = await setCharacterBackground(characterId, selected, applyEquipment)
      setResult(res)
      // Refresh the resolved background + clear selection.
      const bg = await getCharacterBackground(characterId)
      setCharBg(bg)
      setSelected(null)
      setPreview(null)
      onChanged?.()
    } catch {
      setError('Failed to apply background')
    }
    setBusy(false)
  }

  if (loading) {
    return (
      <div className="text-parchment-400 animate-pulse text-center py-12">
        Recalling your origins…
      </div>
    )
  }
  if (error || !charBg) {
    return (
      <div className="text-center py-8">
        <div className="text-blood-400 mb-3">{error || 'No background data'}</div>
        <button className="btn-primary" onClick={load}>
          Retry
        </button>
      </div>
    )
  }

  const current = charBg.detail
  const isChanging = selected !== null && selected !== charBg.background
  // The chosen background's name in the summary list.
  const chosenSummary = backgrounds.find((b) => b.id === selected)

  return (
    <div className="space-y-4">
      {/* Current background summary card */}
      {current ? (
        <div className="bg-parchment-900/60 rounded-lg p-3 border border-arcane-800/40 animate-scale-in">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] uppercase text-parchment-500 tracking-wide">
              Current Background
            </span>
            {current.variant_of && (
              <span className="text-[10px] text-parchment-600">
                variant of {current.variant_of}
              </span>
            )}
          </div>
          <h3 className="font-fantasy text-xl text-parchment-100">{current.name}</h3>
          <p className="text-sm text-parchment-400 mt-1 leading-relaxed">
            {current.description}
          </p>

          {/* Feature */}
          {current.feature && (
            <div className="mt-3 bg-arcane-900/30 rounded-md p-2.5 border border-arcane-800/40">
              <div className="text-xs font-semibold text-gold-400 mb-0.5">
                ⭐ Feature: {current.feature.name}
              </div>
              <p className="text-xs text-parchment-300 leading-relaxed">
                {current.feature.description}
              </p>
            </div>
          )}

          {/* Skills + tools + languages */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-3 text-xs">
            <div className="bg-parchment-900/50 rounded-md p-2">
              <div className="text-parchment-500 uppercase tracking-wide mb-1">
                Skills
              </div>
              {current.skill_proficiencies.length > 0 ? (
                <div className="flex flex-wrap gap-1">
                  {current.skill_proficiencies.map((s) => (
                    <span
                      key={s}
                      className="px-1.5 py-0.5 bg-leaf-900/50 text-leaf-300 rounded"
                    >
                      {titleCase(s)}
                    </span>
                  ))}
                </div>
              ) : (
                <span className="text-parchment-600">—</span>
              )}
            </div>
            <div className="bg-parchment-900/50 rounded-md p-2">
              <div className="text-parchment-500 uppercase tracking-wide mb-1">
                Tools
              </div>
              {current.tool_proficiencies_fixed.length > 0 ||
              current.tool_proficiencies_choice ? (
                <div className="flex flex-wrap gap-1">
                  {current.tool_proficiencies_fixed.map((t) => (
                    <span
                      key={t}
                      className="px-1.5 py-0.5 bg-arcane-900/50 text-arcane-300 rounded"
                    >
                      {titleCase(t)}
                    </span>
                  ))}
                  {current.tool_proficiencies_choice &&
                    current.tool_proficiencies_choice.count > 0 && (
                      <span className="px-1.5 py-0.5 bg-arcane-900/50 text-arcane-300 rounded">
                        +{current.tool_proficiencies_choice.count} choice
                        {current.tool_proficiencies_choice.count > 1 ? 's' : ''}
                      </span>
                    )}
                </div>
              ) : (
                <span className="text-parchment-600">—</span>
              )}
            </div>
            <div className="bg-parchment-900/50 rounded-md p-2">
              <div className="text-parchment-500 uppercase tracking-wide mb-1">
                Languages
              </div>
              {current.languages.length > 0 || current.extra_languages > 0 ? (
                <div className="flex flex-wrap gap-1">
                  {current.languages.map((l) => (
                    <span
                      key={l}
                      className="px-1.5 py-0.5 bg-blood-900/30 text-blood-200 rounded"
                    >
                      {titleCase(l)}
                    </span>
                  ))}
                  {current.extra_languages > 0 && (
                    <span className="px-1.5 py-0.5 bg-blood-900/30 text-blood-200 rounded">
                      +{current.extra_languages} extra
                    </span>
                  )}
                </div>
              ) : (
                <span className="text-parchment-600">Common only</span>
              )}
            </div>
          </div>

          {/* Equipment + gold */}
          {(current.equipment.length > 0 || current.equipment_gold > 0) && (
            <div className="mt-3 pt-2 border-t border-parchment-800/60">
              <div className="text-xs text-parchment-500 uppercase tracking-wide mb-1">
                Starting Equipment
              </div>
              <div className="flex flex-wrap gap-1.5">
                {current.equipment.map((it, i) => (
                  <span
                    key={i}
                    className="text-xs px-1.5 py-0.5 bg-parchment-900/50 rounded"
                    title={`${it.item_type} · ${it.rarity} · ${it.value}gp`}
                  >
                    {it.quantity > 1 ? `${it.quantity}× ` : ''}
                    {it.name}
                    <span className={`ml-1 ${rarityColor(it.rarity)}`}>●</span>
                  </span>
                ))}
                {current.equipment_gold > 0 && (
                  <span className="text-xs px-1.5 py-0.5 bg-gold-900/30 text-gold-300 rounded font-semibold">
                    {current.equipment_gold} gp
                  </span>
                )}
              </div>
              <p className="text-[11px] text-parchment-600 mt-1.5">
                Already granted during character creation. Changing backgrounds re-grants the new set.
              </p>
            </div>
          )}

          {/* Characteristics for roleplay inspiration */}
          {(current.personality_traits.length > 0 ||
            current.ideals.length > 0 ||
            current.bonds.length > 0 ||
            current.flaws.length > 0) && (
            <div className="mt-3 pt-2 border-t border-parchment-800/60">
              <details className="group">
                <summary className="text-xs text-parchment-500 cursor-pointer hover:text-parchment-300 select-none">
                  📖 Suggested characteristics (personality, ideals, bonds, flaws)
                </summary>
                <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {[
                    ['Personality Traits', current.personality_traits, 'text-arcane-300'],
                    ['Ideals', current.ideals, 'text-leaf-300'],
                    ['Bonds', current.bonds, 'text-gold-300'],
                    ['Flaws', current.flaws, 'text-blood-300'],
                  ].map(([label, items, color]) => {
                    const arr = items as string[]
                    if (arr.length === 0) return null
                    return (
                      <div key={label as string} className="bg-parchment-900/40 rounded-md p-2">
                        <div className={`text-[10px] uppercase tracking-wide mb-1 ${color}`}>
                          {label}
                        </div>
                        <ul className="text-[11px] text-parchment-400 space-y-0.5 list-disc list-inside">
                          {arr.slice(0, 6).map((t, i) => (
                            <li key={i}>{t}</li>
                          ))}
                        </ul>
                      </div>
                    )
                  })}
                </div>
              </details>
            </div>
          )}
        </div>
      ) : (
        <div className="bg-parchment-900/60 rounded-lg p-3 border border-blood-700/40">
          <p className="text-sm text-parchment-300">
            No background set. Choose one below to gain skill proficiencies, a
            feature, equipment, and roleplay hooks.
          </p>
        </div>
      )}

      {/* Divider + change background */}
      <div className="flex items-center gap-2">
        <div className="flex-1 h-px bg-parchment-800/60" />
        <span className="text-xs text-parchment-600 uppercase tracking-wide">
          {current ? 'Change Background' : 'Choose a Background'}
        </span>
        <div className="flex-1 h-px bg-parchment-800/60" />
      </div>

      {/* Selectable background grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 max-h-48 overflow-y-auto pr-1">
        {backgrounds.map((b) => {
          const isCurrent = b.id === charBg.background
          const isSelected = b.id === selected
          return (
            <button
              key={b.id}
              onClick={() => setSelected(isSelected ? null : b.id)}
              className={`text-left rounded-md px-2.5 py-2 text-sm transition-all duration-150 hover:-translate-y-0.5 active:scale-95 ${
                isSelected
                  ? 'bg-arcane-800/70 ring-1 ring-arcane-500'
                  : 'bg-parchment-900/60 hover:bg-parchment-800/60'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold text-parchment-200 truncate">
                  {b.name}
                </span>
                {isCurrent && (
                  <span className="text-[10px] text-leaf-400 shrink-0">current</span>
                )}
                {b.variant_of && (
                  <span className="text-[10px] text-parchment-600 shrink-0">
                    ({b.variant_of})
                  </span>
                )}
              </div>
              {b.feature && (
                <div className="text-[11px] text-gold-400 mt-0.5 truncate">
                  ⭐ {b.feature}
                </div>
              )}
            </button>
          )
        })}
      </div>

      {/* Preview of the selected background */}
      {preview && chosenSummary && (
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

          {preview.feature && (
            <div className="text-xs mb-2">
              <span className="text-gold-400 font-semibold">
                ⭐ {preview.feature.name}:
              </span>{' '}
              <span className="text-parchment-300">{preview.feature.description}</span>
            </div>
          )}

          <div className="flex flex-wrap gap-1 mb-2">
            {preview.skill_proficiencies.map((s) => (
              <span
                key={s}
                className="text-[11px] px-1.5 py-0.5 bg-leaf-900/50 text-leaf-300 rounded"
              >
                {titleCase(s)}
              </span>
            ))}
          </div>

          {preview.equipment.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-2">
              {preview.equipment.map((it, i) => (
                <span
                  key={i}
                  className="text-[11px] px-1.5 py-0.5 bg-parchment-900/50 rounded"
                >
                  {it.quantity > 1 ? `${it.quantity}× ` : ''}
                  {it.name}
                </span>
              ))}
              {preview.equipment_gold > 0 && (
                <span className="text-[11px] px-1.5 py-0.5 bg-gold-900/30 text-gold-300 rounded font-semibold">
                  {preview.equipment_gold} gp
                </span>
              )}
            </div>
          )}

          {/* Apply controls */}
          <div className="mt-3 pt-2 border-t border-parchment-800/60">
            <label className="flex items-center gap-2 text-xs text-parchment-300 mb-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={applyEquipment}
                onChange={(e) => setApplyEquipment(e.target.checked)}
                className="accent-arcane-500"
              />
              Claim starting equipment{' '}
              {preview.equipment_gold > 0 && (
                <span className="text-gold-400">+ {preview.equipment_gold} gp</span>
              )}
            </label>
            <button
              className="btn-primary w-full"
              disabled={!isChanging || busy}
              onClick={handleApply}
              title={
                !isChanging
                  ? 'This is already your current background'
                  : `Set background to ${preview.name}`
              }
            >
              {busy
                ? 'Applying…'
                : `Set Background${applyEquipment ? ' & Claim Gear' : ''}`}
            </button>
            {!isChanging && (
              <p className="text-[11px] text-parchment-600 mt-1 text-center">
                This is already your background.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Result feedback */}
      {result && (
        <div className="bg-leaf-900/40 border border-leaf-700 rounded-lg p-3 animate-scale-in">
          <div className="flex items-center justify-between mb-1">
            <span className="font-fantasy text-leaf-300">
              ✓ {result.background}
            </span>
            <span className="text-xs text-gold-400 font-semibold">
              {result.total_gold} gp total
            </span>
          </div>
          {result.feature && (
            <div className="text-xs text-parchment-400 mb-1">
              Feature: <span className="text-gold-400">{result.feature}</span>
            </div>
          )}
          {result.equipment_granted.length > 0 ? (
            <div className="text-xs text-parchment-400">
              Granted:{' '}
              <span className="text-parchment-200">
                {result.equipment_granted.join(', ')}
                {result.gold_granted > 0 && ` + ${result.gold_granted} gp`}
              </span>
            </div>
          ) : (
            <div className="text-xs text-parchment-500">
              Background updated. Starting equipment not re-granted (idempotent).
            </div>
          )}
        </div>
      )}

      {error && <p className="text-xs text-blood-400 text-center">{error}</p>}
    </div>
  )
}
