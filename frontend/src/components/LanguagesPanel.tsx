import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  getLanguagesRegistry,
  getCharacterLanguages,
  setCharacterLanguages,
  validateCharacterLanguages,
} from '../stores/api'
import type {
  LanguageDetail,
  LanguagesResponse,
  CharacterLanguageInfo,
  LanguageValidationResult,
} from '../types'

/* ------------------------------------------------------------------ *
 * Type badge colour/label per language category.                      *
 * ------------------------------------------------------------------ */
const TYPE_META: Record<
  LanguageDetail['type'],
  { label: string; badge: string; dot: string }
> = {
  standard: {
    label: 'Standard',
    badge: 'bg-arcane-900/50 text-arcane-300 border-arcane-700/40',
    dot: 'bg-arcane-400',
  },
  exotic: {
    label: 'Exotic',
    badge: 'bg-gold-900/40 text-gold-300 border-gold-700/40',
    dot: 'bg-gold-400',
  },
  secret: {
    label: 'Secret',
    badge: 'bg-blood-900/40 text-blood-300 border-blood-700/40',
    dot: 'bg-blood-400',
  },
}

interface Props {
  characterId: number
  /** Called after languages are saved so the parent can refresh game state. */
  onChanged?: () => void
}

export default function LanguagesPanel({ characterId, onChanged }: Props) {
  const [registry, setRegistry] = useState<LanguagesResponse | null>(null)
  const [info, setInfo] = useState<CharacterLanguageInfo | null>(null)
  const [selectedExtras, setSelectedExtras] = useState<Set<string>>(new Set())
  const [validation, setValidation] = useState<LanguageValidationResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [savedSummary, setSavedSummary] = useState<string | null>(null)
  const [showRegistry, setShowRegistry] = useState(false)
  const [typeFilter, setTypeFilter] = useState<'all' | LanguageDetail['type']>('all')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [reg, charInfo] = await Promise.all([
        getLanguagesRegistry(),
        getCharacterLanguages(characterId),
      ])
      setRegistry(reg)
      setInfo(charInfo)
      setSelectedExtras(new Set(charInfo.extra_languages))
    } catch {
      setError('Failed to load language data')
    }
    setLoading(false)
  }, [characterId])

  useEffect(() => {
    load()
  }, [load])

  // Language-id -> detail lookup for names / scripts / speakers.
  const byId = useMemo<Record<string, LanguageDetail>>(() => {
    const map: Record<string, LanguageDetail> = {}
    if (registry) {
      for (const l of registry.all) map[l.id] = l
    }
    return map
  }, [registry])

  // Total extra-language budget the race/background grants (extras already
  // taken + slots still free). This mirrors the backend's budget check
  // (extra_count may not exceed the racial allotment).
  const budget = useMemo(() => {
    if (!info) return 0
    return info.remaining_choices + info.extra_languages.length
  }, [info])

  // Selectable pool: the union of currently-chosen extras and the backend's
  // available_choices, so the user can both add new extras and toggle off an
  // existing one in favour of another.
  const selectablePool = useMemo<string[]>(() => {
    if (!info) return []
    const pool = new Set<string>([...info.extra_languages, ...info.available_choices])
    return Array.from(pool).sort((a, b) => {
      const na = byId[a]?.name ?? a
      const nb = byId[b]?.name ?? b
      return na.localeCompare(nb)
    })
  }, [info, byId])

  // Candidate language set to validate/save = automatic grants + chosen extras.
  const candidate = useMemo<string[]>(() => {
    if (!info) return []
    const set = new Set<string>([...info.automatic_languages, ...selectedExtras])
    return Array.from(set)
  }, [info, selectedExtras])

  const usedSlots = selectedExtras.size
  const freeSlots = Math.max(0, budget - usedSlots)

  const hasChange = useMemo(() => {
    if (!info) return false
    const orig = new Set(info.extra_languages)
    if (orig.size !== selectedExtras.size) return true
    for (const id of selectedExtras) if (!orig.has(id)) return true
    return false
  }, [info, selectedExtras])

  // Debounced live validation against the authoritative backend rules.
  const validateTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (!info) return
    if (validateTimer.current) clearTimeout(validateTimer.current)
    validateTimer.current = setTimeout(async () => {
      try {
        const res = await validateCharacterLanguages(characterId, candidate)
        setValidation(res)
      } catch {
        // Network/validation probe failure is non-fatal; apply still
        // validates authoritatively.
      }
    }, 300)
    return () => {
      if (validateTimer.current) clearTimeout(validateTimer.current)
    }
  }, [candidate, characterId, info])

  const toggleExtra = (id: string) => {
    setSelectedExtras((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        // Enforce budget client-side so the UI can't get into an invalid state.
        if (next.size >= budget) return prev
        next.add(id)
      }
      return next
    })
  }

  const handleReset = () => {
    if (info) setSelectedExtras(new Set(info.extra_languages))
    setValidation(null)
  }

  const handleApply = async () => {
    if (!info || !hasChange) return
    setBusy(true)
    setError(null)
    setSavedSummary(null)
    try {
      const updated = await setCharacterLanguages(characterId, candidate)
      setInfo(updated)
      setSelectedExtras(new Set(updated.extra_languages))
      setSavedSummary(updated.summary)
      onChanged?.()
    } catch (e: unknown) {
      // The backend returns 400 with a detail message on invalid sets.
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? 'Failed to save languages'
      setError(detail)
    }
    setBusy(false)
  }

  if (loading) {
    return (
      <div className="text-parchment-400 animate-pulse text-center py-12">
        Consulting ancient tongues and scripts…
      </div>
    )
  }
  if (error && !info) {
    return (
      <div className="text-center py-8">
        <div className="text-blood-400 mb-3">{error}</div>
        <button className="btn-primary" onClick={load}>
          Retry
        </button>
      </div>
    )
  }
  if (!info || !registry) {
    return (
      <div className="text-center py-8 text-parchment-500">No language data</div>
    )
  }

  // Categorise known languages for display.
  const automaticDetails = info.automatic_languages
    .map((id) => byId[id])
    .filter((d): d is LanguageDetail => Boolean(d))
  const extraDetails = info.extra_languages
    .map((id) => byId[id])
    .filter((d): d is LanguageDetail => Boolean(d))

  // Registry list filtered by the active type filter.
  const filteredRegistry: LanguageDetail[] =
    typeFilter === 'all' ? registry.all : registry[typeFilter]

  const LanguageChip = ({ detail }: { detail: LanguageDetail }) => {
    const meta = TYPE_META[detail.type]
    return (
      <span
        className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] ${meta.badge}`}
        title={detail.typical_speakers}
      >
        <span className={`inline-block w-1.5 h-1.5 rounded-full ${meta.dot}`} />
        {detail.name}
      </span>
    )
  }

  return (
    <div className="space-y-4">
      {/* Current state card */}
      <div className="bg-parchment-900/60 rounded-lg p-3 border border-arcane-800/40 animate-scale-in">
        <div className="flex items-center justify-between mb-1">
          <span className="text-[10px] uppercase text-parchment-500 tracking-wide">
            Known Tongues
          </span>
          <span className="text-[10px] text-arcane-300 font-mono font-semibold">
            {info.known_languages.length} language
            {info.known_languages.length === 1 ? '' : 's'}
          </span>
        </div>
        <div className="text-xs text-parchment-500 mb-2">
          {info.race}
          {info.background ? ` · ${info.background}` : ''}
        </div>

        {/* Automatic languages */}
        {automaticDetails.length > 0 && (
          <div className="mb-2">
            <div className="text-[10px] uppercase text-parchment-600 tracking-wide mb-1">
              Automatic (race / background / class)
            </div>
            <div className="flex flex-wrap gap-1.5">
              {automaticDetails.map((d) => (
                <span
                  key={d.id}
                  className="inline-flex items-center gap-1 rounded-md border border-leaf-700/50 bg-leaf-900/40 px-2 py-0.5 text-[11px] text-leaf-200"
                  title={`${d.typical_speakers}${d.script ? ` · ${d.script} script` : ''}`}
                >
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-leaf-400" />
                  {d.name}
                  <span className="text-leaf-500/70 text-[9px]" title="Locked — granted automatically">
                    🔒
                  </span>
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Extra (chosen) languages */}
        {extraDetails.length > 0 && (
          <div className="mb-2">
            <div className="text-[10px] uppercase text-parchment-600 tracking-wide mb-1">
              Chosen Extras
            </div>
            <div className="flex flex-wrap gap-1.5">
              {extraDetails.map((d) => (
                <LanguageChip key={d.id} detail={d} />
              ))}
            </div>
          </div>
        )}

        {/* Remaining choices summary */}
        <div className="mt-2 pt-2 border-t border-parchment-800/60 flex items-center justify-between">
          <span className="text-[11px] text-parchment-400">
            {info.remaining_choices > 0 ? (
              <>
                <span className="text-gold-300 font-semibold">{info.remaining_choices}</span>{' '}
                language choice{info.remaining_choices === 1 ? '' : 's'} remaining
              </>
            ) : budget > 0 ? (
              'All language choices spent'
            ) : (
              'No extra language choices available'
            )}
          </span>
          {info.remaining_choices > 0 && (
            <span className="text-[10px] text-gold-400 uppercase tracking-wide animate-pulse">
              ✦ choose below
            </span>
          )}
        </div>
      </div>

      {/* Extra-language editor */}
      {budget > 0 && (
        <div className="bg-parchment-950/40 rounded-lg p-3 border border-parchment-800/60">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs uppercase text-parchment-500 tracking-wide">
              Choose Extra Languages
            </span>
            <span
              className={`text-[11px] font-mono font-semibold ${
                freeSlots === 0 ? 'text-gold-400' : 'text-arcane-300'
              }`}
            >
              {usedSlots}/{budget} slots
            </span>
          </div>

          {/* Budget progress bar */}
          <div className="h-1.5 bg-parchment-900 rounded-full overflow-hidden mb-3">
            <div
              className="h-full bg-gold-500 transition-all duration-300"
              style={{ width: `${budget > 0 ? (usedSlots / budget) * 100 : 0}%` }}
            />
          </div>

          {/* Selectable chips */}
          {selectablePool.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {selectablePool.map((id) => {
                const d = byId[id]
                const isOn = selectedExtras.has(id)
                const disabled = !isOn && freeSlots <= 0
                const name = d?.name ?? id
                const meta = d ? TYPE_META[d.type] : null
                return (
                  <button
                    key={id}
                    onClick={() => toggleExtra(id)}
                    disabled={disabled}
                    title={
                      d
                        ? `${d.typical_speakers}${d.script ? ` · ${d.script} script` : ''}`
                        : id
                    }
                    className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs transition-all duration-150 ${
                      disabled
                        ? 'opacity-40 cursor-not-allowed border-parchment-800 text-parchment-600'
                        : isOn
                        ? 'border-gold-500 bg-gold-900/50 text-gold-200 hover:-translate-y-0.5'
                        : 'border-parchment-700 bg-parchment-900/60 text-parchment-300 hover:border-arcane-500 hover:-translate-y-0.5 active:scale-95'
                    }`}
                  >
                    {meta && (
                      <span className={`inline-block w-1.5 h-1.5 rounded-full ${meta.dot}`} />
                    )}
                    {name}
                    {isOn && <span className="text-gold-400">✓</span>}
                  </button>
                )
              })}
            </div>
          ) : (
            <p className="text-xs text-parchment-500 italic">
              No additional languages are available to choose from.
            </p>
          )}

          {/* Live validation feedback */}
          {validation && !validation.valid && (
            <div className="mt-3 bg-blood-900/30 border border-blood-700/50 rounded-md p-2">
              <p className="text-[11px] text-blood-300 leading-relaxed">
                ⚠ {validation.error}
              </p>
            </div>
          )}
          {validation && validation.valid && (
            <div className="mt-3 bg-leaf-900/20 border border-leaf-700/30 rounded-md p-2">
              <p className="text-[11px] text-leaf-300">
                ✓ Valid selection — {validation.known_languages.length} language
                {validation.known_languages.length === 1 ? '' : 's'} known.
              </p>
            </div>
          )}

          {/* Apply / reset controls */}
          <div className="flex gap-2 mt-3 pt-2 border-t border-parchment-800/60">
            <button
              className="btn-primary flex-1"
              disabled={!hasChange || busy || (validation !== null && !validation.valid)}
              onClick={handleApply}
              title={
                !hasChange
                  ? 'No changes to save'
                  : validation !== null && !validation.valid
                  ? 'Resolve validation errors first'
                  : 'Save language choices'
              }
            >
              {busy ? 'Saving…' : hasChange ? 'Save Languages' : 'No Changes'}
            </button>
            <button
              className="px-3 py-1.5 text-sm rounded-lg border border-parchment-700 text-parchment-400 hover:text-parchment-200 hover:border-parchment-500 transition-colors disabled:opacity-40"
              onClick={handleReset}
              disabled={!hasChange || busy}
            >
              Reset
            </button>
          </div>
        </div>
      )}

      {/* Saved feedback */}
      {savedSummary && (
        <div className="bg-leaf-900/40 border border-leaf-700 rounded-lg p-3 animate-scale-in">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-fantasy text-leaf-300">✓ Languages Saved</span>
          </div>
          <p className="text-[11px] text-parchment-400 leading-relaxed">
            {savedSummary}
          </p>
          <p className="text-[10px] text-parchment-600 mt-1">
            The DM will now recognise these tongues in narration, dialogue, and
            when you encounter inscriptions or foreign speakers.
          </p>
        </div>
      )}

      {/* Registry browser */}
      <div className="flex items-center gap-2">
        <div className="flex-1 h-px bg-parchment-800/60" />
        <button
          className="text-xs text-arcane-300/80 hover:text-arcane-200 uppercase tracking-wide transition-colors"
          onClick={() => setShowRegistry((s) => !s)}
        >
          {showRegistry ? '▾ Hide' : '▸ Show'} Language Reference
        </button>
        <div className="flex-1 h-px bg-parchment-800/60" />
      </div>

      {showRegistry && (
        <div className="space-y-3 animate-overlay-in">
          {/* Type filter */}
          <div className="flex flex-wrap gap-1.5">
            {(['all', 'standard', 'exotic', 'secret'] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTypeFilter(t)}
                className={`text-[11px] px-2 py-0.5 rounded-md border transition-colors ${
                  typeFilter === t
                    ? 'border-arcane-500 bg-arcane-900/50 text-arcane-200'
                    : 'border-parchment-800 bg-parchment-900/40 text-parchment-500 hover:text-parchment-300'
                }`}
              >
                {t === 'all'
                  ? `All (${registry.all.length})`
                  : `${TYPE_META[t].label} (${
                      t === 'standard'
                        ? registry.standard.length
                        : t === 'exotic'
                        ? registry.exotic.length
                        : registry.secret.length
                    })`}
              </button>
            ))}
          </div>

          {/* Registry grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {filteredRegistry.map((d) => {
              const meta = TYPE_META[d.type]
              const isKnown = info.known_languages.includes(d.id)
              return (
                <div
                  key={d.id}
                  className={`rounded-lg p-2 border ${
                    isKnown
                      ? 'border-leaf-700/40 bg-leaf-900/15'
                      : 'border-parchment-800/60 bg-parchment-900/40'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-semibold text-parchment-200">
                      {d.name}
                    </span>
                    <div className="flex items-center gap-1">
                      {isKnown && (
                        <span
                          className="text-[9px] text-leaf-400 font-bold uppercase"
                          title="You know this language"
                        >
                          ✓ known
                        </span>
                      )}
                      <span
                        className={`text-[9px] uppercase px-1 py-0.5 rounded border ${meta.badge}`}
                      >
                        {meta.label}
                      </span>
                    </div>
                  </div>
                  <div className="text-[11px] text-parchment-400 leading-relaxed">
                    {d.typical_speakers}
                  </div>
                  <div className="text-[10px] text-parchment-600 mt-0.5">
                    Script: {d.script ?? 'None (unwritten)'}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Legend */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-parchment-600">
            {(['standard', 'exotic', 'secret'] as const).map((t) => (
              <span key={t} className="flex items-center gap-1">
                <span className={`inline-block w-2 h-2 rounded-full ${TYPE_META[t].dot}`} />
                {TYPE_META[t].label}
              </span>
            ))}
            <span className="flex items-center gap-1">
              <span className="inline-block w-2 h-2 rounded-full bg-leaf-500" /> known
            </span>
          </div>
        </div>
      )}

      {error && <p className="text-xs text-blood-400 text-center">{error}</p>}
    </div>
  )
}
