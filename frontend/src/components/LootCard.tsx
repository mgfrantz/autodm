import { useMemo } from 'react'
import type { GameEvent } from '../types'
import {
  itemRarityColor,
  lootIcon,
  lootSummary,
} from '../utils/gameEvents'

/* ------------------------------------------------------------------ *
 * LootCard — inline game-event card showing an inventory operation
 * (DM function calling Phase 4: inventory operations).
 *
 * Renders the item name + type + rarity, the operation (gained /
 * removed / equipped / used), operation-specific indicators
 * (quantity badge, healing, new AC, uses remaining), and an optional
 * provenance source. Colour-coded by rarity tier. Failed operations
 * render a muted card with the reason. Dismissible.
 * ------------------------------------------------------------------ */

interface LootCardProps {
  event: GameEvent
  onDismiss?: () => void
}

export default function LootCard({ event, onDismiss }: LootCardProps) {
  const d = event.data
  const success = d.success ?? true
  const operation = (d.operation ?? 'gained').toLowerCase()
  const itemName = d.item_name ?? 'Unknown item'
  const itemType = d.item_type ?? ''
  const rarity = d.rarity ?? 'common'
  const quantity = d.quantity ?? 1
  const healing = d.healing
  const acAfter = d.ac_after
  const usesRemaining = d.uses_remaining

  const summary = useMemo(
    () => lootSummary(
      d.operation, d.item_name, d.item_type, d.quantity, d.success,
      d.healing, d.ac_after, d.uses_remaining, d.message, d.source,
    ),
    [d.operation, d.item_name, d.item_type, d.quantity, d.success,
      d.healing, d.ac_after, d.uses_remaining, d.message, d.source],
  )
  const colors = useMemo(() => itemRarityColor(rarity), [rarity])
  const icon = useMemo(() => lootIcon(itemType), [itemType])

  // Operation badge (verb + glyph).
  const opBadge = useMemo(() => {
    switch (operation) {
      case 'gained':   return { glyph: '🎁', label: 'Acquired', tone: 'text-emerald-300' }
      case 'removed':  return { glyph: '📤', label: 'Removed', tone: 'text-rose-300' }
      case 'equipped': return { glyph: '⚔️', label: 'Equipped', tone: 'text-sky-300' }
      case 'used':     return { glyph: '🧪', label: 'Used', tone: 'text-amber-300' }
      default:         return { glyph: '🎒', label: operation, tone: 'text-parchment-300' }
    }
  }, [operation])

  // Failed operation → muted card.
  if (!success) {
    return (
      <div
        className="rounded-lg border border-parchment-700/40 bg-parchment-900/20 p-3 mt-2 animate-scale-in opacity-80"
        role="status"
        aria-label={summary}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-semibold text-parchment-300 flex items-center gap-1.5">
            <span aria-hidden>{icon}</span>
            {itemName}
            <span className="text-parchment-500 font-normal">— {opBadge.label.toLowerCase()} failed</span>
          </span>
          {onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              className="text-parchment-500 hover:text-parchment-200 text-xs px-1.5 py-0.5 rounded transition-colors"
              aria-label="Dismiss loot event"
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

  return (
    <div
      className={`rounded-lg border ${colors.border} ${colors.bg} p-3 mt-2 animate-scale-in`}
      role="status"
      aria-label={summary}
    >
      {/* Header: item icon + name + rarity */}
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <span className={`text-sm font-bold ${colors.text} flex items-center gap-1.5`}>
          <span aria-hidden>{icon}</span>
          {itemName}
          {rarity !== 'common' && (
            <span className="text-parchment-400 font-normal text-xs capitalize">
              ({rarity.replace('_', ' ')})
            </span>
          )}
        </span>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="text-parchment-500 hover:text-parchment-200 text-xs px-1.5 py-0.5 rounded transition-colors"
            aria-label="Dismiss loot event"
            title="Dismiss"
          >
            ✕
          </button>
        )}
      </div>

      {/* Operation + indicators */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`text-sm font-semibold ${opBadge.tone} flex items-center gap-1`}>
          <span aria-hidden>{opBadge.glyph}</span>
          {opBadge.label}
        </span>

        {/* Quantity badge for stackable gains/removals > 1 */}
        {quantity > 1 && (operation === 'gained' || operation === 'removed') && (
          <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-parchment-800/60 text-parchment-300">
            ×{quantity}
          </span>
        )}

        {/* Value badge (gold) when present */}
        {typeof d.value === 'number' && d.value > 0 && (operation === 'gained' || operation === 'removed') && (
          <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-amber-900/30 text-amber-200">
            {d.value} gp
          </span>
        )}

        {/* Healing indicator (used: healing potion) */}
        {healing !== null && healing !== undefined && healing > 0 && (
          <span className="text-sm font-semibold text-emerald-300">
            ✨ +{healing} HP
          </span>
        )}

        {/* AC indicator (equipped) */}
        {acAfter !== null && acAfter !== undefined && (
          <span className="text-sm font-semibold text-sky-300 flex items-center gap-1">
            <span aria-hidden>🛡️</span> AC {acAfter}
          </span>
        )}

        {/* Uses remaining (used: consumable) */}
        {usesRemaining !== null && usesRemaining !== undefined && (
          <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${usesRemaining > 0 ? 'bg-parchment-800/60 text-parchment-300' : 'bg-parchment-800/40 text-parchment-500'}`}>
            {usesRemaining > 0 ? `${usesRemaining} use${usesRemaining === 1 ? '' : 's'} left` : 'consumed'}
          </span>
        )}
      </div>

      {/* Source provenance */}
      {d.source && (
        <div className="text-xs text-parchment-400 mt-1.5 italic">
          From: {d.source}
        </div>
      )}
    </div>
  )
}
