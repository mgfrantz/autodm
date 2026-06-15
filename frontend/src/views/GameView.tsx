import { useState, useEffect, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { startAdventure, playerAction, getGameState } from '../stores/api'
import { useGameStore } from '../stores/gameStore'
import type { StoryEntry } from '../types'

export default function GameView() {
  const { gameId } = useParams<{ gameId: string }>()
  const gid = parseInt(gameId || '0')

  const { gameState, story, setGameState, addToStory, loading, setLoading, error, setError } = useGameStore()
  const [actionInput, setActionInput] = useState('')
  const [started, setStarted] = useState(false)
  const storyEndRef = useRef<HTMLDivElement>(null)

  // Load game state
  useEffect(() => {
    getGameState(gid)
      .then((state) => {
        setGameState(state)
        if (state.story_log.length === 0 && !started) {
          handleStart()
        } else {
          state.story_log.forEach((entry: StoryEntry) => addToStory(entry))
        }
      })
      .catch(() => setError('Failed to load game'))
  }, [gid])

  // Auto-scroll to bottom
  useEffect(() => {
    storyEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [story])

  const handleStart = async () => {
    setLoading(true)
    try {
      const res = await startAdventure(gid)
      addToStory({ role: 'dm', content: res.narration, timestamp: new Date().toISOString() })
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
    try {
      const res = await playerAction(gid, action)
      addToStory({ role: 'dm', content: res.narration, timestamp: new Date().toISOString() })
    } catch (err) {
      setError('The DM falters... (error processing action)')
    }
    setLoading(false)
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
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <Link to="/" className="text-parchment-400 hover:text-parchment-200 text-sm">
            ← Leave Game
          </Link>
          <h1 className="font-fantasy text-xl text-parchment-300">
            {gameState.world.name}
          </h1>
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
                    : 'bg-blood-700/30 border-l-4 border-blood-500 ml-8'
                }`}
              >
                <div className="text-xs text-parchment-500 mb-1 font-semibold uppercase">
                  {entry.role === 'dm' ? '🗡️ Dungeon Master' : '🧑 Player'}
                </div>
                <div className="text-parchment-200 whitespace-pre-wrap leading-relaxed">
                  {entry.content}
                </div>
              </div>
            ))}
            {loading && (
              <div className="text-parchment-400 animate-pulse text-center py-4">
                🎲 The DM considers your actions...
              </div>
            )}
            <div ref={storyEndRef} />
          </div>
        </div>

        {/* Action Input */}
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
      </div>

      {/* Character Sidebar */}
      <div className="lg:w-72 space-y-4">
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
      </div>
    </div>
  )
}
