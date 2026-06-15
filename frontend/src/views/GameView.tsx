import { useState, useEffect, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getGameState, streamStartAdventure, streamPlayerAction, getCombatState, makeAttack, nextTurn, getWorldMap, travelToRegion } from '../stores/api'
import { useGameStore } from '../stores/gameStore'
import type { StoryEntry, Attack, WorldMapData } from '../types'
import CombatTracker from '../components/CombatTracker'
import WorldMap from '../components/WorldMap'

export default function GameView() {
  const { gameId } = useParams<{ gameId: string }>()
  const gid = parseInt(gameId || '0')

  const { gameState, story, combatState, setGameState, setCombatState, addToStory, loading, setLoading, error, setError } = useGameStore()
  const [actionInput, setActionInput] = useState('')
  const [started, setStarted] = useState(false)
  const [streamingText, setStreamingText] = useState('')
  const [showMap, setShowMap] = useState(false)
  const [worldMap, setWorldMap] = useState<WorldMapData | null>(null)
  const [mapLoading, setMapLoading] = useState(false)
  const storyEndRef = useRef<HTMLDivElement>(null)

  // Load game state and combat state
  useEffect(() => {
    const loadState = async () => {
      try {
        const state = await getGameState(gid)
        setGameState(state)
        
        // Check for combat state
        const combat = await getCombatState(gid)
        setCombatState(combat)
        
        if (state.story_log.length === 0 && !started) {
          handleStart()
        } else {
          state.story_log.forEach((entry: StoryEntry) => addToStory(entry))
        }
      } catch {
        setError('Failed to load game')
      }
    }
    
    loadState()
  }, [gid])

  // Auto-scroll to bottom
  useEffect(() => {
    storyEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [story, streamingText])

  const handleStart = async () => {
    setLoading(true)
    setStreamingText('')
    try {
      await streamStartAdventure(
        gid,
        (chunk) => setStreamingText((prev) => prev + chunk),
        () => {},
      )
      setStreamingText((final) => {
        addToStory({ role: 'dm', content: final, timestamp: new Date().toISOString() })
        return ''
      })
      setStarted(true)
    } catch (err) {
      setError('Failed to start adventure')
    }
    setLoading(false)
  }

  const handleAction = async () => {
    if (!actionInput.trim() || loading) return
    const action = actionInput.trim()
    setActionInput('')
    addToStory({ role: 'player', content: action, timestamp: new Date().toISOString() })
    setLoading(true)
    setStreamingText('')
    try {
      await streamPlayerAction(
        gid,
        action,
        (chunk) => setStreamingText((prev) => prev + chunk),
        async (combatActive) => {
          // Check combat state after DM responds
          if (combatActive) {
            const combat = await getCombatState(gid)
            setCombatState(combat)
          }
        },
      )
      setStreamingText((final) => {
        addToStory({ role: 'dm', content: final, timestamp: new Date().toISOString() })
        return ''
      })
      // Refresh combat state after action
      const combat = await getCombatState(gid)
      setCombatState(combat)
    } catch (err) {
      setError('The DM falters... (error processing action)')
    }
    setLoading(false)
  }

  const handleAttack = async (attackerId: string, targetId: string, attack: Attack) => {
    try {
      const result = await makeAttack(gid, attackerId, targetId, attack.name)
      
      // Add combat result to story
      addToStory({ 
        role: 'system', 
        content: result.result.description,
        timestamp: new Date().toISOString() 
      })
      
      // Update combat state
      setCombatState({
        in_combat: result.combat_active,
        is_active: result.combat_active,
        winner: result.winner,
        encounter: result.encounter,
      })
      
      // If combat ended, add a message
      if (!result.combat_active && result.winner) {
        addToStory({
          role: 'system',
          content: result.winner === 'player' 
            ? '🎉 Victory! You have defeated all enemies!' 
            : '💀 You have been defeated...',
          timestamp: new Date().toISOString()
        })
      }
    } catch (err) {
      setError('Attack failed')
    }
  }

  const handleNextTurn = async () => {
    try {
      const result = await nextTurn(gid)
      
      // Update combat state
      const combat = await getCombatState(gid)
      setCombatState(combat)
      
      // If combat ended, add a message
      if (result.combat_over && result.winner) {
        addToStory({
          role: 'system',
          content: result.winner === 'player' 
            ? '🎉 Victory! You have defeated all enemies!' 
            : '💀 You have been defeated...',
          timestamp: new Date().toISOString()
        })
      }
    } catch (err) {
      setError('Failed to advance turn')
    }
  }

  const isPlayerTurn = combatState?.encounter?.combatants.find(c => c.id === combatState.current_turn_id)?.side === 'player'
  const inCombat = combatState?.in_combat && combatState?.is_active

  const handleOpenMap = async () => {
    setShowMap(true)
    setMapLoading(true)
    try {
      const mapData = await getWorldMap(gid)
      setWorldMap(mapData)
    } catch {
      setError('Failed to load map')
      setShowMap(false)
    }
    setMapLoading(false)
  }

  const handleTravel = async (regionId: string) => {
    if (mapLoading) return
    setMapLoading(true)
    try {
      const result = await travelToRegion(gid, regionId)
      // Refresh the map + game state.
      const [mapData, state] = await Promise.all([getWorldMap(gid), getGameState(gid)])
      setWorldMap(mapData)
      setGameState(state)
      // Surface the travel outcome in the story log.
      if (result.success) {
        addToStory({
          role: 'system',
          content: result.encounter_triggered
            ? `🗺️ ${result.message}${result.encounter_danger ? ` (${result.encounter_danger})` : ''}`
            : `🗺️ ${result.message}`,
          timestamp: new Date().toISOString(),
        })
      } else {
        setError(result.message)
      }
    } catch {
      setError('Travel failed')
    }
    setMapLoading(false)
  }

  if (!gameState) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-parchment-400 text-xl animate-pulse">Loading adventure...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex flex-col lg:flex-row max-w-7xl mx-auto p-4 gap-4">
      {/* Main Story Panel */}
      <div className={`flex flex-col ${inCombat ? 'lg:flex-[2]' : 'flex-1'}`}>
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <Link to="/" className="text-parchment-400 hover:text-parchment-200 text-sm">
            ← Leave Game
          </Link>
          <h1 className="font-fantasy text-xl text-parchment-300">
            {gameState.world.name}
          </h1>
          <button
            className="btn-primary text-sm px-3 py-1.5"
            onClick={handleOpenMap}
            disabled={inCombat}
            title={inCombat ? 'Cannot travel during combat' : 'Open the world map'}
          >
            🗺️ Map
          </button>
        </div>

        {/* Story Log */}
        <div className="panel flex-1 overflow-y-auto mb-4 min-h-[400px] max-h-[60vh]">
          <div className="space-y-4">
            {story.map((entry, i) => (
              <div
                key={i}
                className={`rounded-lg p-4 ${
                  entry.role === 'dm'
                    ? 'bg-parchment-900/60 border-l-4 border-arcane-500'
                    : entry.role === 'system'
                    ? 'bg-parchment-900/60 border-l-4 border-amber-500'
                    : 'bg-blood-700/30 border-l-4 border-blood-500 ml-8'
                }`}
              >
                <div className="text-xs text-parchment-500 mb-1 font-semibold uppercase">
                  {entry.role === 'dm' ? '🗡️ Dungeon Master' : entry.role === 'system' ? '⚙️ System' : '🧑 Player'}
                </div>
                <div className="text-parchment-200 whitespace-pre-wrap leading-relaxed">
                  {entry.content}
                </div>
              </div>
            ))}
            {/* Live-streaming DM narration */}
            {streamingText && (
              <div className="rounded-lg p-4 bg-parchment-900/60 border-l-4 border-arcane-500">
                <div className="text-xs text-parchment-500 mb-1 font-semibold uppercase">
                  🗡️ Dungeon Master
                  <span className="ml-2 text-arcane-400 animate-pulse">typing...</span>
                </div>
                <div className="text-parchment-200 whitespace-pre-wrap leading-relaxed">
                  {streamingText}
                  <span className="inline-block w-2 h-4 ml-0.5 bg-arcane-400 animate-pulse align-middle" />
                </div>
              </div>
            )}
            {loading && !streamingText && (
              <div className="text-parchment-400 animate-pulse text-center py-4">
                🎲 The DM considers your actions...
              </div>
            )}
            <div ref={storyEndRef} />
          </div>
        </div>

        {/* Action Input - Disabled during combat */}
        {!inCombat && (
          <div className="panel">
            {error && (
              <div className="text-blood-500 text-sm mb-2">{error}</div>
            )}
            <div className="flex gap-2">
              <input
                className="input-field flex-1"
                value={actionInput}
                onChange={(e) => setActionInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAction()}
                placeholder="What do you do? (e.g., 'I examine the door', 'I attack the goblin', 'I talk to the innkeeper')"
                disabled={loading}
              />
              <button
                className="btn-primary px-8"
                onClick={handleAction}
                disabled={loading || !actionInput.trim()}
              >
                Act
              </button>
            </div>
            {/* Quick Actions */}
            <div className="flex gap-2 mt-2 flex-wrap">
              {['Look around', 'Check inventory', 'Check my stats'].map((q) => (
                <button
                  key={q}
                  onClick={() => setActionInput(q)}
                  className="text-xs bg-parchment-700 hover:bg-parchment-600 text-parchment-300 px-3 py-1 rounded-full transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Combat indicator */}
        {inCombat && (
          <div className="panel bg-blood-900/30 border border-blood-500">
            <div className="text-center text-parchment-200 font-semibold">
              ⚔️ COMBAT IN PROGRESS ⚔️
            </div>
          </div>
        )}
      </div>

      {/* Right Sidebar */}
      <div className="lg:w-80 space-y-4">
        {/* Character Info */}
        <div className="panel">
          <h2 className="font-fantasy text-lg text-parchment-200 mb-3">
            {gameState.character.name}
          </h2>
          <div className="text-parchment-400 text-sm mb-4">
            Level {gameState.character.level} {gameState.character.race} {gameState.character.char_class}
          </div>

          {/* HP Bar */}
          <div className="mb-3">
            <div className="flex justify-between text-xs text-parchment-400 mb-1">
              <span>Health</span>
              <span>{gameState.character.hp} / {gameState.character.max_hp}</span>
            </div>
            <div className="h-3 bg-parchment-900 rounded-full overflow-hidden">
              <div
                className="h-full bg-blood-600 transition-all"
                style={{ width: `${(gameState.character.hp / gameState.character.max_hp) * 100}%` }}
              />
            </div>
          </div>

          {/* Location */}
          <div className="text-sm">
            <span className="text-parchment-500">Location: </span>
            <span className="text-parchment-300">{gameState.game_state?.location || 'Unknown'}</span>
          </div>

          {/* Act & XP */}
          <div className="flex justify-between mt-3 text-sm">
            <span className="text-parchment-500">Act {gameState.current_act}</span>
            <span className="text-parchment-500">{gameState.xp} XP</span>
          </div>
        </div>

        {/* Combat Tracker - Only show during combat */}
        {inCombat && combatState?.encounter && (
          <CombatTracker
            combatants={combatState.encounter.combatants}
            currentTurnId={combatState.current_turn_id || null}
            roundNumber={combatState.round || 1}
            isPlayerTurn={isPlayerTurn}
            onAttack={handleAttack}
            onNextTurn={handleNextTurn}
          />
        )}
      </div>

      {/* World Map overlay */}
      {showMap && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          onClick={() => !mapLoading && setShowMap(false)}
        >
          <div
            className="panel max-w-2xl w-full max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-fantasy text-2xl text-parchment-200">🗺️ World Map</h2>
              <button
                className="text-parchment-400 hover:text-parchment-200 text-2xl leading-none"
                onClick={() => setShowMap(false)}
                disabled={mapLoading}
              >
                ×
              </button>
            </div>
            {mapLoading && !worldMap ? (
              <div className="text-parchment-400 animate-pulse text-center py-12">Charting the realm…</div>
            ) : worldMap ? (
              <WorldMap map={worldMap} traveling={mapLoading} onTravel={handleTravel} />
            ) : (
              <div className="text-parchment-500 text-center py-8">No map data available.</div>
            )}
            <p className="text-xs text-parchment-600 mt-3 text-center">
              Click a glowing region to travel. Random encounters may occur en route.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}