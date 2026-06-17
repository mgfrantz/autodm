import { useEffect, useState } from 'react'
import type { Combatant, CombatActionInfo, CombatActionKey, CombatActionResult } from '../types'
import { listCombatActions, performCombatAction } from '../stores/api'

interface CombatActionsPanelProps {
  gameId: number
  player: Combatant
  enemies: Combatant[]
  onClose: () => void
  onResult: (result: CombatActionResult) => void
}

/**
 * Overlay panel for DnD 5e "Actions in Combat" beyond the basic Attack action
 * (Grapple, Shove, Dash, Disengage, Dodge, Help, Unarmed Strike, Two-Weapon
 * Fighting, Escape Grapple, Opportunity Attack).
 */
export default function CombatActionsPanel({
  gameId,
  player,
  enemies,
  onClose,
  onResult,
}: CombatActionsPanelProps) {
  const [actions, setActions] = useState<CombatActionInfo[]>([])
  const [selected, setSelected] = useState<CombatActionKey | ''>('')
  const [targetId, setTargetId] = useState('')
  const [shoveOption, setShoveOption] = useState<'prone' | 'push'>('prone')
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listCombatActions(gameId)
      .then(setActions)
      .catch(() => setError('Could not load combat actions.'))
  }, [gameId])

  const livingEnemies = enemies.filter((e) => e.current_hp > 0)
  const selectedAction = actions.find((a) => a.key === selected)
  const needsTarget = !!selectedAction?.requires_target

  const handlePerform = async () => {
    if (!selected) return
    setBusy(true)
    setError(null)
    setFeedback(null)
    try {
      const result = await performCombatAction(
        gameId,
        player.id,
        selected as CombatActionKey,
        needsTarget ? targetId : undefined,
        selected === 'shove' ? shoveOption : undefined,
      )
      setFeedback(result.result.description)
      onResult(result)
      if (result.result.success && !needsTarget) {
        // Non-target actions (dash/dodge/disengage) clear the selection.
        setSelected('')
        setTargetId('')
      }
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Action failed.'
      setError(detail)
    } finally {
      setBusy(false)
    }
  }

  const canPerform =
    !!selected && (!needsTarget || !!targetId) && !busy

  return (
    <div
      className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4 animate-overlay-in"
      onClick={onClose}
    >
      <div
        className="panel max-w-2xl w-full max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-fantasy text-2xl text-parchment-200">🎯 Combat Actions</h2>
          <button className="text-parchment-400 hover:text-parchment-200 text-xl" onClick={onClose}>
            ✕
          </button>
        </div>

        <p className="text-sm text-parchment-400 mb-4">
          Special actions from the Player's Handbook. These are resolved by the engine
          with full DnD 5e rules (contests, conditions, advantage).
        </p>

        {/* Action grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-4">
          {actions.map((action) => {
            const active = selected === action.key
            return (
              <button
                key={action.key}
                className={`text-left p-2 rounded-lg border transition-all ${
                  active
                    ? 'bg-arcane-700/60 border-arcane-400 text-parchment-100'
                    : 'bg-parchment-900/30 border-parchment-700 text-parchment-300 hover:border-arcane-500'
                }`}
                onClick={() => {
                  setSelected(action.key)
                  setFeedback(null)
                  setError(null)
                }}
                title={action.description}
              >
                <div className="text-sm font-semibold">{action.name}</div>
                <div className="text-[10px] uppercase tracking-wide text-parchment-500">
                  {action.cost}
                </div>
              </button>
            )
          })}
        </div>

        {selectedAction && (
          <div className="mb-4 p-3 bg-parchment-900/40 rounded-lg">
            <div className="text-parchment-200 font-semibold mb-1">{selectedAction.name}</div>
            <div className="text-xs text-parchment-400">{selectedAction.description}</div>
          </div>
        )}

        {/* Target selector */}
        {needsTarget && (
          <div className="mb-4">
            <label className="block text-xs text-parchment-500 mb-1">Target</label>
            <select
              className="input-field w-full"
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
              disabled={livingEnemies.length === 0}
            >
              <option value="">-- Choose a target --</option>
              {livingEnemies.map((enemy) => (
                <option key={enemy.id} value={enemy.id}>
                  {enemy.name} (AC {enemy.armor_class}, {enemy.current_hp} HP)
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Shove option */}
        {selected === 'shove' && (
          <div className="mb-4 flex gap-2">
            {(['prone', 'push'] as const).map((opt) => (
              <button
                key={opt}
                className={`flex-1 text-sm py-1.5 rounded-lg border transition-all ${
                  shoveOption === opt
                    ? 'bg-arcane-700/60 border-arcane-400 text-parchment-100'
                    : 'bg-parchment-900/30 border-parchment-700 text-parchment-300'
                }`}
                onClick={() => setShoveOption(opt)}
              >
                {opt === 'prone' ? '↩️ Knock Prone' : '⬆️ Push 5 ft'}
              </button>
            ))}
          </div>
        )}

        {/* Active-status hints */}
        <div className="mb-4 flex flex-wrap gap-2 text-xs">
          {player.dodging && (
            <span className="px-2 py-0.5 rounded bg-arcane-800/80 text-arcane-100">Dodging</span>
          )}
          {player.disengaging && (
            <span className="px-2 py-0.5 rounded bg-arcane-800/80 text-arcane-100">Disengaging</span>
          )}
          {player.conditions.includes('grappled') && (
            <span className="px-2 py-0.5 rounded bg-amber-800/80 text-amber-100">Grappled</span>
          )}
          {(player.bonus_movement ?? 0) > 0 && (
            <span className="px-2 py-0.5 rounded bg-leaf-800/80 text-leaf-100">
              +{player.bonus_movement} ft (Dash)
            </span>
          )}
        </div>

        {error && (
          <div className="mb-3 text-sm text-blood-300 bg-blood-900/30 p-2 rounded">{error}</div>
        )}
        {feedback && (
          <div className="mb-3 text-sm text-parchment-200 bg-arcane-900/30 p-2 rounded">
            ✦ {feedback}
          </div>
        )}

        <div className="flex gap-2">
          <button
            className="btn-primary flex-1"
            onClick={handlePerform}
            disabled={!canPerform}
          >
            {busy ? 'Resolving...' : 'Perform Action'}
          </button>
          <button className="btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
