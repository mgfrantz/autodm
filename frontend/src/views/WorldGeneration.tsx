import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { generateWorld, createGame } from '../stores/api'

const TONES = ['Heroic Fantasy', 'Dark Fantasy', 'High Magic', 'Sword & Sorcery', 'Gothic Horror', 'Mystery & Intrigue']

export default function WorldGeneration() {
  const navigate = useNavigate()
  const location = useLocation()
  const characterId = (location.state as any)?.characterId

  const [tone, setTone] = useState('Heroic Fantasy')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleGenerate = async () => {
    if (!characterId) {
      setError('No character selected. Please create a character first.')
      return
    }

    setLoading(true)
    setError(null)
    try {
      // Generate world tailored to character
      const world = await generateWorld({ tone, character_id: characterId })

      // Create game session
      const game = await createGame({
        name: 'New Adventure',
        character_id: characterId,
        world_id: world.id,
      })

      navigate(`/game/${game.game_id}`)
    } catch (err) {
      setError('Failed to generate world. Is the backend running and LLM configured?')
      setLoading(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto p-8">
      <h1 className="font-fantasy text-4xl text-parchment-200 mb-2">Forge Your World</h1>
      <p className="text-parchment-400 mb-8">
        The DM will craft a unique world and campaign tailored to your character.
      </p>

      <div className="panel space-y-6">
        <div>
          <label className="block text-parchment-300 mb-3 font-semibold text-lg">Campaign Tone</label>
          <div className="grid grid-cols-2 gap-3">
            {TONES.map((t) => (
              <button
                key={t}
                onClick={() => setTone(t)}
                className={`py-3 rounded-lg text-sm font-semibold transition-colors text-left px-4
                  ${tone === t ? 'bg-blood-600 text-parchment-50' : 'bg-parchment-700 text-parchment-300 hover:bg-parchment-600'}`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="bg-blood-700/40 border border-blood-500 rounded-lg p-3 text-parchment-200 text-sm">
            {error}
          </div>
        )}

        <button
          className="btn-primary w-full text-lg py-3"
          onClick={handleGenerate}
          disabled={loading}
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <span className="animate-spin">🎲</span> The DM is weaving your world...
            </span>
          ) : (
            '🎲 Generate World & Begin Adventure'
          )}
        </button>

        {!characterId && (
          <p className="text-center text-parchment-500 text-sm">
            <a href="/character/new" className="text-arcane-500 underline">Create a character first</a>
          </p>
        )}
      </div>
    </div>
  )
}
