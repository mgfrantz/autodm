import { useEffect, useState } from 'react'
import {
  getInventory,
  equipItem,
  unequipItem,
  useInventoryItem,
  removeInventoryItem,
} from '../stores/api'
import type { InventoryData, InventoryItem, InventorySlotEntry } from '../types'

// ---------------------------------------------------------------- helpers ---- #

const titleCase = (s: string) =>
  s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

const RARITY_COLOR: Record<string, string> = {
  common: 'text-parchment-300',
  uncommon: 'text-leaf-300',
  rare: 'text-arcane-300',
  very_rare: 'text-purple-300',
  legendary: 'text-gold-300',
}

const TYPE_ICON: Record<string, string> = {
  weapon: '🗡️',
  armor: '🛡️',
  potion: '🧪',
  scroll: '📜',
  misc: '🎒',
  quest: '❗',
}

/** Whether an item can be equipped (weapon or armor/shield). */
const isEquippable = (item: InventoryItem) =>
  item.item_type === 'weapon' || item.item_type === 'armor'

/** Whether an item can be consumed (potion or scroll). */
const isConsumable = (item: InventoryItem) =>
  item.item_type === 'potion' || item.item_type === 'scroll'

/** A short stats line for an item (damage / AC / uses). */
function statLine(item: InventoryItem): string {
  const parts: string[] = []
  if (item.item_type === 'weapon' && item.damage_dice_count > 0) {
    parts.push(`${item.damage_dice_count}d${item.damage_dice_sides}${item.damage_type ? ` ${item.damage_type}` : ''}`)
    if (item.attack_bonus) parts.push(`+${item.attack_bonus} atk`)
    if (item.damage_bonus) parts.push(`+${item.damage_bonus} dmg`)
  } else if (item.item_type === 'armor') {
    if (item.armor_type) parts.push(titleCase(item.armor_type))
    if (item.armor_bonus) parts.push(`+${item.armor_bonus} AC`)
    if (item.dex_limit != null) parts.push(`Dex ≤ ${item.dex_limit}`)
  } else if (isConsumable(item)) {
    parts.push(`${item.uses}/${item.max_uses} uses`)
  }
  if (item.value) parts.push(`${item.value} gp`)
  if (item.weight) parts.push(`${item.weight} lb`)
  return parts.join(' · ')
}

// --------------------------------------------------------------- component ---- #

interface Props {
  characterId: number
  /** Optional callback when HP changes (e.g. from drinking a healing potion). */
  onHpChange?: (hp: number, maxHp: number) => void
}

export default function InventoryPanel({ characterId, onHpChange }: Props) {
  const [inventory, setInventory] = useState<InventoryData | null>(null)
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getInventory(characterId)
      setInventory(data)
    } catch {
      setError('Failed to load inventory')
    }
    setLoading(false)
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [characterId])

  const flash = (msg: string) => {
    setFeedback(msg)
    window.setTimeout(() => setFeedback(null), 2500)
  }

  const handleEquip = async (item: InventoryItem) => {
    if (busyId) return
    setBusyId(item.id)
    try {
      const data = await equipItem(characterId, item.id)
      setInventory(data)
      flash(`✓ Equipped ${item.name}`)
    } catch {
      setError('Failed to equip item')
    }
    setBusyId(null)
  }

  const handleUnequip = async (item: InventoryItem) => {
    if (busyId) return
    setBusyId(item.id)
    try {
      const data = await unequipItem(characterId, item.id)
      setInventory(data)
      flash(`✓ Unequipped ${item.name}`)
    } catch {
      setError('Failed to unequip item')
    }
    setBusyId(null)
  }

  const handleUse = async (item: InventoryItem) => {
    if (busyId) return
    setBusyId(item.id)
    try {
      const res = await useInventoryItem(characterId, item.id)
      if (res.success) {
        onHpChange?.(res.current_hp, res.max_hp)
        flash(`✓ ${res.message}`)
      } else {
        flash(`✗ ${res.message}`)
      }
      // Refresh inventory (uses/quantity may have changed)
      const data = await getInventory(characterId)
      setInventory(data)
    } catch {
      setError('Failed to use item')
    }
    setBusyId(null)
  }

  const handleRemove = async (item: InventoryItem) => {
    if (busyId) return
    setBusyId(item.id)
    try {
      const data = await removeInventoryItem(characterId, item.id, item.quantity)
      setInventory(data)
      flash(`✓ Dropped ${item.name}`)
    } catch {
      setError('Failed to remove item')
    }
    setBusyId(null)
  }

  if (loading) {
    return <div className="text-parchment-400 animate-pulse text-center py-12">Inspecting your pack…</div>
  }
  if (error || !inventory) {
    return (
      <div className="text-center py-8">
        <div className="text-blood-400 mb-3">{error || 'No inventory data'}</div>
        <button className="btn-primary" onClick={load}>Retry</button>
      </div>
    )
  }

  // Derived equipment slots.
  const weapon = inventory.equipped_weapon
  const bodyArmor = inventory.equipped_armor
  const shield = inventory.equipped_shield

  return (
    <div>
      {/* --- Equipment slots summary --- */}
      <div className="grid grid-cols-3 gap-2 mb-4">
        <EquipSlot label="Weapon" icon="🗡️" item={weapon} />
        <EquipSlot label="Armor" icon="🛡️" item={bodyArmor} />
        <EquipSlot label="Shield" icon="🛡️" item={shield} />
      </div>

      {/* --- Weight / value summary --- */}
      <div className="flex items-center justify-between mb-3 text-xs text-parchment-500">
        <span>⚖️ {inventory.total_weight.toFixed(1)} lb carried</span>
        <span className="text-gold-400">🪙 {inventory.total_value} gp value</span>
      </div>

      {/* --- Backback / item list --- */}
      <div className="space-y-1.5 max-h-[42vh] overflow-y-auto pr-1 mb-3">
        {inventory.slots.length === 0 && (
          <div className="text-center text-parchment-500 text-sm py-8">
            Your pack is empty.
          </div>
        )}
        {inventory.slots.map((slot: InventorySlotEntry) => (
          <ItemRow
            key={slot.item.id}
            slot={slot}
            busy={busyId === slot.item.id}
            disabled={busyId !== null}
            onEquip={handleEquip}
            onUnequip={handleUnequip}
            onUse={handleUse}
            onRemove={handleRemove}
          />
        ))}
      </div>

      {/* --- Feedback --- */}
      {feedback && (
        <div className="rounded-lg p-2.5 text-sm bg-parchment-900/70 border border-parchment-800/50 animate-scale-in">
          {feedback}
        </div>
      )}
    </div>
  )
}

// --------------------------------------------------------- sub-components ---- #

function EquipSlot({ label, icon, item }: { label: string; icon: string; item: InventoryItem | null }) {
  return (
    <div className={`rounded-lg p-2.5 border text-center ${item ? 'bg-arcane-900/30 border-arcane-700/50' : 'bg-parchment-900/40 border-parchment-800/40'}`}>
      <div className="text-[10px] uppercase tracking-wide text-parchment-500 mb-0.5">{label}</div>
      <div className="text-lg leading-none mb-1">{item ? icon : '—'}</div>
      <div className={`text-xs truncate ${item ? (RARITY_COLOR[item.rarity] ?? 'text-parchment-200') : 'text-parchment-600'}`}>
        {item ? item.name : 'empty'}
      </div>
    </div>
  )
}

interface ItemRowProps {
  slot: InventorySlotEntry
  busy: boolean
  disabled: boolean
  onEquip: (item: InventoryItem) => void
  onUnequip: (item: InventoryItem) => void
  onUse: (item: InventoryItem) => void
  onRemove: (item: InventoryItem) => void
}

function ItemRow({ slot, busy, disabled, onEquip, onUnequip, onUse, onRemove }: ItemRowProps) {
  const { item, equipped } = slot
  const rarityClass = RARITY_COLOR[item.rarity] ?? 'text-parchment-200'
  const [confirmDrop, setConfirmDrop] = useState(false)

  return (
    <div
      className={`rounded-md px-2.5 py-2 bg-parchment-900/60 ${
        equipped ? 'ring-1 ring-gold-500/40' : ''
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className={`text-sm truncate ${rarityClass}`}>
            {TYPE_ICON[item.item_type] ?? '📦'} {item.name}
            {item.quantity > 1 && <span className="text-parchment-600 text-xs"> ×{item.quantity}</span>}
            {equipped && <span className="text-[10px] text-gold-400 ml-1">(equipped)</span>}
          </div>
          {item.description && (
            <div className="text-[11px] text-parchment-500 truncate">{item.description}</div>
          )}
          <div className="text-[11px] text-parchment-500 truncate">{statLine(item) || titleCase(item.item_type)}</div>
        </div>

        {/* Action buttons */}
        <div className="flex gap-1 shrink-0">
          {isEquippable(item) && !equipped && (
            <button
              className="text-xs bg-arcane-700 hover:bg-arcane-600 text-parchment-200 px-2.5 py-1 rounded transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              disabled={disabled}
              onClick={() => onEquip(item)}
              title={`Equip ${item.name}`}
            >
              {busy ? '…' : 'Equip'}
            </button>
          )}
          {isEquippable(item) && equipped && (
            <button
              className="text-xs bg-parchment-700 hover:bg-parchment-600 text-parchment-200 px-2.5 py-1 rounded transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              disabled={disabled}
              onClick={() => onUnequip(item)}
              title={`Unequip ${item.name}`}
            >
              {busy ? '…' : 'Remove'}
            </button>
          )}
          {isConsumable(item) && (
            <button
              className="text-xs bg-leaf-700 hover:bg-leaf-600 text-parchment-200 px-2.5 py-1 rounded transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              disabled={disabled || item.uses <= 0}
              onClick={() => onUse(item)}
              title={`Use ${item.name}`}
            >
              {busy ? '…' : 'Use'}
            </button>
          )}
          {/* Drop / confirm-drop toggle */}
          {!confirmDrop ? (
            <button
              className="text-xs bg-blood-800/70 hover:bg-blood-700 text-parchment-200 px-2 py-1 rounded transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              disabled={disabled}
              onClick={() => setConfirmDrop(true)}
              title={`Drop ${item.name}`}
            >
              🗑
            </button>
          ) : (
            <>
              <button
                className="text-xs bg-blood-700 hover:bg-blood-600 text-parchment-100 px-2 py-1 rounded transition-colors disabled:opacity-40"
                disabled={disabled}
                onClick={() => { onRemove(item); setConfirmDrop(false) }}
                title="Confirm drop"
              >
                ✓
              </button>
              <button
                className="text-xs bg-parchment-700 hover:bg-parchment-600 text-parchment-200 px-2 py-1 rounded transition-colors"
                onClick={() => setConfirmDrop(false)}
                title="Cancel"
              >
                ✕
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
