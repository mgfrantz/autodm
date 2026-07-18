import { useMemo } from 'react'
import type { GameEvent } from '../types'
import {
  damageTypeColor,
  hpBarData,
  spellCastSummary,
  spellLevelLabel,
  spellSchoolColor,
} from '../utils/gameEvents'

/* ------------------------------------------------------------------ *
 * SpellCastCard — inline game-event card showing a spell-cast result
 * (DM function calling Phase 3: spell casting).
 *
 * Renders the spell name + school + level, the resolution mode
 * (attack roll vs AC / saving throw vs DC / auto-damage / healing /
 * utility), damage/healing amounts, and — when the target is an
 * encounter combatant — the target's HP bar. Colour-coded by spell
 * school. Failed casts render a muted card with the reason. Dismissible.
 * ------------------------------------------------------------------ */

interface SpellCastCardProps {
  event: GameEvent
  onDismiss?: () => void
}

export default function SpellCastCard({ event, onDismiss }: SpellCastCardProps) {
  const d = event.data
  const success = d.success ?? true
  const school = d.school ?? ''
  const spellName = d.spell_name ?? 'Unknown spell'
  const damageType = d.damage_type ?? ''
  const dmg = d.damage ?? 0
  const heal = d.healing ?? 0
  const hit = d.hit
  const madeSave = d.made_save

  const summary = useMemo(
    () => spellCastSummary(spellName, d.level, school, success, hit, madeSave,
      dmg, heal, damageType, d.half_damage, d.target, d.message),
    [spellName, d.level, school, success, hit, madeSave, dmg, heal, damageType, d.half_damage, d.target, d.message],
  )
  const schoolColors = useMemo(() => spellSchoolColor(school), [school])
  const dmgColors = useMemo(() => damageTypeColor(damageType), [damageType])
  const hp = useMemo(
    () => hpBarData(d.target_remaining_hp, d.target_max_hp),
    [d.target_remaining_hp, d.target_max_hp],
  )
  const hasHpBar = d.target_remaining_hp !== undefined && d.target_max_hp !== undefined

  // Failed cast → muted card.
  if (!success) {
    return (
      <div
        className="rounded-lg border border-parchment-700/40 bg-parchment-900/20 p-3 mt-2 animate-scale-in opacity-80"
        role="status"
        aria-label={summary}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-semibold text-parchment-300 flex items-center gap-1.5">
            <span aria-hidden>🔮</span>
            {spellName}
            <span className="text-parchment-500 font-normal">— cast failed</span>
          </span>
          {onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              className="text-parchment-500 hover:text-parchment-200 text-xs px-1.5 py-0.5 rounded transition-colors"
              aria-label="Dismiss spell cast result"
              title="Dismiss"
            >
              ✕
            </button>
          )}
        </div>
        {d.message && (
          <div className="text-xs text-parchment-400 mt-1 italic">{d.message}</div>
        )}
      </div>
    )
  }

  // AoE summary (Phase 3.5b) — one cast hits multiple targets. No single HP
  // bar (per-target HP lives in the follow-up DamageCards).
  if (d.is_aoe) {
    const targetCount = d.target_count ?? 0
    const totalDmg = d.total_damage ?? 0
    return (
      <div
        className={`rounded-lg border ${schoolColors.border} ${schoolColors.bg} p-3 mt-2 animate-scale-in`}
        role="status"
        aria-label={summary}
      >
        {/* Header: spell name + school + level */}
        <div className="flex items-center justify-between gap-2 mb-1.5">
          <span className={`text-sm font-bold ${schoolColors.text} flex items-center gap-1.5`}>
            <span aria-hidden>🎯</span>
            {spellName}
            <span className="text-parchment-400 font-normal text-xs">
              ({school} {spellLevelLabel(d.level)})
            </span>
          </span>
          {onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              className="text-parchment-500 hover:text-parchment-200 text-xs px-1.5 py-0.5 rounded transition-colors"
              aria-label="Dismiss spell cast result"
              title="Dismiss"
            >
              ✕
            </button>
          )}
        </div>

        {/* AoE badges: target count + total damage + save DC + slot */}
        <div className="flex items-center gap-2 flex-wrap">
          {targetCount > 0 && (
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-sky-900/40 text-sky-200 border border-sky-700/40">
              💥 Hits {targetCount} target{targetCount === 1 ? '' : 's'}
            </span>
          )}
          {totalDmg > 0 && (
            <span className={`text-xs font-semibold px-2 py-0.5 rounded ${dmgColors.bg} ${dmgColors.text} border ${dmgColors.border}`}>
              {totalDmg} {damageType} total damage
            </span>
          )}
          {d.save_dc !== undefined && d.save_dc !== null && (
            <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-parchment-800/60 text-parchment-200">
              DC {d.save_dc} {d.save_ability ?? ''}
            </span>
          )}
          {d.slot_level !== undefined && d.slot_level !== null && (
            <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-parchment-800/60 text-parchment-300">
              L{d.slot_level} slot
            </span>
          )}
        </div>
      </div>
    )
  }

  return (
    <div
      className={`rounded-lg border ${schoolColors.border} ${schoolColors.bg} p-3 mt-2 animate-scale-in`}
      role="status"
      aria-label={summary}
    >
      {/* Header: spell name + school + level */}
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <span className={`text-sm font-bold ${schoolColors.text} flex items-center gap-1.5`}>
          <span aria-hidden>🔮</span>
          {spellName}
          <span className="text-parchment-400 font-normal text-xs">
            ({school} {spellLevelLabel(d.level)})
          </span>
        </span>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="text-parchment-500 hover:text-parchment-200 text-xs px-1.5 py-0.5 rounded transition-colors"
            aria-label="Dismiss spell cast result"
            title="Dismiss"
          >
            ✕
          </button>
        )}
      </div>

      {/* Resolution mode */}
      <div className="flex items-center gap-2 flex-wrap mb-2">
        {/* Attack-roll spells */}
        {hit !== undefined && hit !== null && (
          <>
            <span className={`text-sm font-bold ${hit ? 'text-emerald-300' : 'text-blood-300'}`}>
              {hit ? '✅ HIT' : '❌ MISS'}
            </span>
            {d.attack_total !== undefined && (
              <span className="text-sm font-mono text-parchment-200">
                {d.attack_total} vs AC
              </span>
            )}
          </>
        )}

        {/* Saving-throw spells */}
        {madeSave !== undefined && madeSave !== null && (
          <>
            <span className={`text-sm font-bold ${madeSave ? 'text-amber-300' : 'text-emerald-300'}`}>
              {madeSave ? '🛡️ Saved' : '💫 Failed save'}
            </span>
            {d.save_dc !== undefined && d.save_dc !== null && (
              <span className="text-sm font-mono text-parchment-200">
                DC {d.save_dc} {d.save_ability ?? ''}
              </span>
            )}
          </>
        )}

        {/* Slot expended badge (leveled spells only) */}
        {d.slot_level !== undefined && d.slot_level !== null && (
          <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-parchment-800/60 text-parchment-300">
            L{d.slot_level} slot
          </span>
        )}
        {d.slot_level === null && (
          <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-parchment-800/40 text-parchment-400">
            cantrip
          </span>
        )}
      </div>

      {/* Damage */}
      {dmg > 0 && (
        <div className={`text-sm mb-1 ${dmgColors.text}`}>
          💥 {dmg} {damageType} damage{d.half_damage ? ' (half)' : ''}
        </div>
      )}

      {/* Healing */}
      {heal > 0 && (
        <div className="text-sm mb-1 text-emerald-300">
          ✨ +{heal} HP healed{d.target ? ` — ${d.target}` : ''}
        </div>
      )}

      {/* HP bar (when target is a combatant) */}
      {hasHpBar && (
        <div className="flex items-center gap-2 mt-1">
          <span className="text-xs text-parchment-400 min-w-fit">{d.target || 'Target'} HP</span>
          <div
            className="flex-1 h-2.5 rounded-full bg-parchment-800/60 overflow-hidden"
            role="progressbar"
            aria-valuenow={hp.percentage}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div className={`h-full ${hp.color} rounded-full transition-all duration-300`} style={{ width: `${hp.percentage}%` }} />
          </div>
          <span className={`text-xs font-mono min-w-fit ${hp.isDead ? 'text-blood-300' : 'text-parchment-300'}`}>
            {hp.label}
          </span>
        </div>
      )}

      {hasHpBar && hp.isDead && (
        <div className="text-xs font-bold text-blood-300 mt-1">☠️ Defeated!</div>
      )}
    </div>
  )
}
