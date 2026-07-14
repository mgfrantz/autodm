import { useMemo } from 'react'
import type { SkillCheckResolution } from '../types'
import {
  getDegreeMeta,
  hasResolution,
  formatStatChanges,
  summarizeResolution,
} from '../utils/skillCheckResolution'

/* ------------------------------------------------------------------ *
 * SkillCheckResolutionCard — inline game-event card showing the
 * structured mechanical outcome the DM computed for a freeform player
 * action (DSPy tutorial pattern #5: structured skill-check resolution).
 *
 * This is the "Game Event UI Layer" piece for skill checks: it surfaces
 * the degree of success, narrative notes, stat changes, items gained,
 * and XP — the structured data the DM narration doesn't mechanically
 * apply. Rendered inline after the latest DM narration bubble and
 * dismissed by the player (or auto-cleared on the next action).
 * ------------------------------------------------------------------ */

interface SkillCheckResolutionCardProps {
  resolution: SkillCheckResolution | null | undefined
  onDismiss?: () => void
}

export default function SkillCheckResolutionCard({
  resolution,
  onDismiss,
}: SkillCheckResolutionCardProps) {
  const visible = useMemo(() => hasResolution(resolution), [resolution])

  // Pre-compute formatted pieces so render stays declarative.
  const meta = useMemo(() => getDegreeMeta(resolution?.degree), [resolution?.degree])
  const statLines = useMemo(
    () => formatStatChanges(resolution?.stat_changes),
    [resolution?.stat_changes],
  )
  const summary = useMemo(() => summarizeResolution(resolution), [resolution])

  if (!visible) return null

  const xp = resolution?.experience_gained
  const hasXp = typeof xp === 'number' && xp > 0
  const items = resolution?.items_gained
  const hasItems = Array.isArray(items) && items.length > 0
  const notes = resolution?.narrative_notes?.trim()
  const hasNotes = !!notes && notes.length > 0

  return (
    <div
      className="rounded-lg border border-parchment-700/60 bg-parchment-900/40 p-3 mt-2 animate-scale-in"
      role="status"
      aria-label={summary || 'Skill check resolution'}
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <span
          className={`inline-flex items-center gap-1.5 text-xs font-bold px-2.5 py-1 rounded-full border ${meta.badgeClass}`}
        >
          <span aria-hidden>{meta.icon}</span>
          {meta.label}
        </span>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="text-parchment-500 hover:text-parchment-200 text-xs px-1.5 py-0.5 rounded transition-colors"
            aria-label="Dismiss resolution"
            title="Dismiss"
          >
            ✕
          </button>
        )}
      </div>

      {/* Narrative notes — the DM's mechanical explanation */}
      {hasNotes && (
        <p className="text-sm text-parchment-300 italic leading-snug mb-2">
          {notes}
        </p>
      )}

      {/* Mechanical outcomes grid */}
      {(hasXp || hasItems || statLines.length > 0) && (
        <div className="flex flex-wrap gap-1.5">
          {hasXp && (
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-arcane-900/60 text-arcane-200 border border-arcane-600/40">
              ✨ +{xp} XP
            </span>
          )}
          {statLines.map((line, i) => {
            const positive = !line.includes('−')
            return (
              <span
                key={`stat-${i}`}
                className={`text-xs font-semibold px-2 py-0.5 rounded border ${
                  positive
                    ? 'bg-emerald-900/40 text-emerald-200 border-emerald-600/30'
                    : 'bg-blood-900/40 text-blood-200 border-blood-600/30'
                }`}
              >
                {line}
              </span>
            )
          })}
        </div>
      )}

      {/* Items gained */}
      {hasItems && (
        <div className="mt-2">
          <span className="text-[10px] uppercase tracking-wide text-parchment-500 font-semibold">
            Items Gained
          </span>
          <div className="flex flex-wrap gap-1.5 mt-1">
            {items.map((item, i) => (
              <span
                key={`item-${i}`}
                className="text-xs px-2 py-0.5 rounded bg-amber-900/40 text-amber-200 border border-amber-600/30"
              >
                🎁 {item}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
