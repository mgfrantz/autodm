import { useState } from 'react'
import type { Combatant, Attack } from '../types'

interface CombatTrackerProps {
  combatants: Combatant[]
  currentTurnId: string | null
  roundNumber: number
  isPlayerTurn: boolean
  onAttack: (attackerId: string, targetId: string, attack: Attack) => void
  onNextTurn: () => void
}

export default function CombatTracker({
  combatants,
  currentTurnId,
  roundNumber,
  isPlayerTurn,
  onAttack,
  onNextTurn,
}: CombatTrackerProps) {
  const [selectedTargetId, setSelectedTargetId] = useState<string>('')
  const [selectedAttack, setSelectedAttack] = useState<Attack | null>(null)

  const player = combatants.find((c) => c.id === 'player')
  const enemies = combatants.filter((c) => c.side === 'enemy' && c.current_hp > 0)
  const currentCombatant = combatants.find((c) => c.id === currentTurnId)

  const handleAttack = () => {
    if (player && selectedTargetId && selectedAttack) {
      onAttack(player.id, selectedTargetId, selectedAttack)
      setSelectedTargetId('')
      setSelectedAttack(null)
    }
  }

  const getHpPercentage = (combatant: Combatant) =>
    (combatant.current_hp / combatant.max_hp) * 100

  const getHpColor = (combatant: Combatant) => {
    const pct = getHpPercentage(combatant)
    if (pct > 50) return 'bg-leaf-600'
    if (pct > 25) return 'bg-amber-600'
    return 'bg-blood-600'
  }

  // Color-code condition badges by severity so players can read combat state at a glance.
  const INCAPACITATING = new Set([
    'incapacitated', 'paralyzed', 'petrified', 'stunned', 'unconscious',
  ])
  const HARMFUL = new Set([
    'blinded', 'deafened', 'frightened', 'grappled', 'poisoned', 'prone', 'restrained',
  ])
  const BENEFICIAL = new Set(['invisible'])

  const getConditionStyle = (cond: string) => {
    const c = cond.toLowerCase()
    if (INCAPACITATING.has(c)) return 'bg-blood-800 text-blood-100'
    if (HARMFUL.has(c)) return 'bg-amber-800/80 text-amber-100'
    if (BENEFICIAL.has(c)) return 'bg-arcane-800/80 text-arcane-100'
    return 'bg-parchment-700 text-parchment-300'
  }

  if (!player) return null

  return (
    <div className="panel animate-slide-in-right">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-fantasy text-lg text-parchment-200">⚔️ Combat Tracker</h2>
        <div className="text-parchment-400 text-sm">Round {roundNumber}</div>
      </div>

      {/* Current Turn Indicator */}
      {currentCombatant && (
        <div
          className={`p-3 rounded-lg mb-4 ${
            currentCombatant.side === 'player'
              ? 'bg-arcane-900/50 border border-arcane-500'
              : 'bg-blood-900/50 border border-blood-500'
          }`}
        >
          <div className="text-xs text-parchment-500 font-semibold uppercase mb-1">
            {currentCombatant.side === 'player' ? '🧑 Your Turn' : '👹 Enemy Turn'}
          </div>
          <div className="text-parchment-200 font-semibold">{currentCombatant.name}</div>
        </div>
      )}

      {/* Player Stats */}
      <div className="mb-4 p-3 bg-parchment-900/30 rounded-lg">
        <div className="flex items-center justify-between mb-2">
          <div className="font-semibold text-parchment-200">{player.name}</div>
          <div className="text-xs text-parchment-500">
            AC: {player.armor_class} | HP: {player.current_hp}/{player.max_hp}
          </div>
        </div>
        <div className="h-2 bg-parchment-900 rounded-full overflow-hidden">
          <div
            className={`h-full ${getHpColor(player)} transition-all`}
            style={{ width: `${getHpPercentage(player)}%` }}
          />
        </div>
        {player.conditions.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {player.conditions.map((cond) => (
              <span
                key={cond}
                className={`text-xs px-2 py-0.5 rounded ${getConditionStyle(cond)}`}
              >
                {cond}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Enemies */}
      <div className="space-y-2 mb-4">
        <div className="text-xs text-parchment-500 font-semibold uppercase mb-2">Enemies</div>
        {enemies.map((enemy) => (
          <div
            key={enemy.id}
            className={`p-3 rounded-lg ${
              currentTurnId === enemy.id ? 'bg-blood-900/50 border border-blood-500' : 'bg-parchment-900/30'
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <div className="font-semibold text-parchment-200">{enemy.name}</div>
              <div className="text-xs text-parchment-500">
                AC: {enemy.armor_class} | HP: {enemy.current_hp}/{enemy.max_hp}
              </div>
            </div>
            <div className="h-2 bg-parchment-900 rounded-full overflow-hidden">
              <div
                className={`h-full ${getHpColor(enemy)} transition-all`}
                style={{ width: `${getHpPercentage(enemy)}%` }}
              />
            </div>
            {enemy.conditions.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {enemy.conditions.map((cond) => (
                  <span
                    key={cond}
                    className={`text-xs px-2 py-0.5 rounded ${getConditionStyle(cond)}`}
                  >
                    {cond}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Player Actions */}
      {isPlayerTurn && player.current_hp > 0 && (
        <div className="border-t border-parchment-700 pt-4">
          <div className="text-sm text-parchment-400 mb-2">Choose your action:</div>

          {/* Attack Selection */}
          <div className="space-y-3">
            <div>
              <label className="block text-xs text-parchment-500 mb-1">Select Attack</label>
              <select
                className="input-field w-full"
                value={selectedAttack?.name || ''}
                onChange={(e) => {
                  const attack = player.attacks.find((a) => a.name === e.target.value)
                  setSelectedAttack(attack || null)
                }}
                disabled={enemies.length === 0}
              >
                <option value="">-- Choose an attack --</option>
                {player.attacks.map((attack) => (
                  <option key={attack.name} value={attack.name}>
                    {attack.name} (+{attack.attack_bonus} to hit, {attack.damage_dice_count}d{attack.damage_dice_sides}+{attack.damage_bonus} {attack.damage_type})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs text-parchment-500 mb-1">Select Target</label>
              <select
                className="input-field w-full"
                value={selectedTargetId}
                onChange={(e) => setSelectedTargetId(e.target.value)}
                disabled={!selectedAttack || enemies.length === 0}
              >
                <option value="">-- Choose a target --</option>
                {enemies.map((enemy) => (
                  <option key={enemy.id} value={enemy.id}>
                    {enemy.name} (AC {enemy.armor_class}, {enemy.current_hp} HP)
                  </option>
                ))}
              </select>
            </div>

            <button
              className="btn-primary w-full"
              onClick={handleAttack}
              disabled={!selectedAttack || !selectedTargetId || enemies.length === 0}
            >
              ⚔️ Attack
            </button>
          </div>

          {/* Other actions */}
          <div className="mt-3 grid grid-cols-2 gap-2">
            <button
              className="btn-secondary text-sm"
              onClick={() => {
                // For now, just pass turn
                onNextTurn()
              }}
            >
              🛡️ Dodge (+5 AC)
            </button>
            <button
              className="btn-secondary text-sm"
              onClick={onNextTurn}
            >
              ➡️ End Turn
            </button>
          </div>
        </div>
      )}

      {/* Enemy turn indicator */}
      {!isPlayerTurn && enemies.length > 0 && (
        <div className="border-t border-parchment-700 pt-4 text-center">
          <div className="text-parchment-400 animate-pulse">The {currentCombatant?.name} is acting...</div>
        </div>
      )}
    </div>
  )
}