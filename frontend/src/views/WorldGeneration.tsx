import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { generateWorld, createGame, listAdventures, launchStarterAdventure } from '../stores/api'
import type { AdventureSummary } from '../types'

const TONES = ['Heroic Fantasy', 'Dark Fantasy', 'High Magic', 'Sword & Sorcery', 'Gothic Horror', 'Mystery & Intrigue']

type Mode = 'generate' | 'adventure'

export default function WorldGeneration() {
  const navigate = useNavigate()
  const location = useLocation()
  const characterId = (location.state as any)?.characterId

  const [mode, setMode] = useState<Mode>('generate')
  const [tone, setTone] = useState('Heroic Fantasy')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Curated adventures
  const [adventures, setAdventures] = useState<AdventureSummary[]>([])
  const [adventureLoadError, setAdventureLoadError] = useState(false)

  useEffect(() => {
    let cancelled = false
    listAdventures()
      .then((list) => { if (!cancelled) setAdventures(list) })
      .catch(() => { if (!cancelled) setAdventureLoadError(true) })
    return () => { cancelled = true }
  }, [])

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

  const handleStartAdventure = async (adventure: AdventureSummary) => {
    if (!characterId) {
      setError('No character selected. Please create a character first.')
      return
    }

    setLoading(true)
    setError(null)
    try {
      // Create a World row from the curated adventure
      const { world_id } = await launchStarterAdventure(adventure.id)

      // Create game session (same flow as LLM-generated worlds)
      const game = await createGame({
        name: adventure.name,
        character_id: characterId,
        world_id,
      })

      navigate(`/game/${game.game_id}`)
    } catch (err) {
      setError('Failed to start the selected adventure. Is the backend running?')
      setLoading(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto p-4 sm:p-8 view-enter">
      <h1 className="font-fantasy text-3xl sm:text-4xl text-parchment-200 mb-2 animate-slide-up">Forge Your World</h1>
      <p className="text-parchment-400 mb-8 animate-fade-in" style={{ animationDelay: '0.1s' }}>
        Choose a ready-made adventure, or let the DM craft a unique world tailored to your character.
      </p>

      {/* Mode toggle */}
      <div className="flex gap-2 mb-6 animate-slide-up" style={{ animationDelay: '0.12s' }}>
        <button
          onClick={() => { setMode('adventure'); setError(null) }}
          disabled={loading}
          className={`flex-1 py-2.5 rounded-lg text-sm font-semibold transition-all duration-200
            ${mode === 'adventure' ? 'bg-arcane-600 text-parchment-50 shadow-lg shadow-arcane-900/40' : 'bg-parchment-700 text-parchment-300 hover:bg-parchment-600'}`}
        >
          📜 Starter Adventures
        </button>
        <button
          onClick={() => { setMode('generate'); setError(null) }}
          disabled={loading}
          className={`flex-1 py-2.5 rounded-lg text-sm font-semibold transition-all duration-200
            ${mode === 'generate' ? 'bg-arcane-600 text-parchment-50 shadow-lg shadow-arcane-900/40' : 'bg-parchment-700 text-parchment-300 hover:bg-parchment-600'}`}
        >
          ✨ Generate New World
        </button>
      </div>

      <div className="panel space-y-6 animate-slide-up" style={{ animationDelay: '0.15s' }}>
        {/* === Starter adventure picker === */}
        {mode === 'adventure' && (
          <>
            <p className="text-parchment-400 text-sm">
              Ready-to-play, hand-crafted adventures. No LLM configuration required for world
              creation — works out of the box.
            </p>

            {adventureLoadError && (
              <div className="bg-blood-700/40 border border-blood-500 rounded-lg p-3 text-parchment-200 text-sm">
                Couldn't load starter adventures. Is the backend running?
              </div>
            )}

            <div className="space-y-3">
              {adventures.map((adv) => (
                <button
                  key={adv.id}
                  onClick={() => handleStartAdventure(adv)}
                  disabled={loading}
                  className="w-full text-left p-4 rounded-lg bg-parchment-700 hover:bg-parchment-600 border border-parchment-600/50
                    hover:border-arcane-500/60 transition-all duration-200 hover:-translate-y-0.5 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <div className="flex items-start justify-between gap-3 mb-1">
                    <h3 className="font-fantasy text-lg text-parchment-100">{adv.name}</h3>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-parchment-800 text-parchment-400 whitespace-nowrap">
                      Lvl {adv.recommended_level}+
                    </span>
                  </div>
                  <p className="text-parchment-300 text-sm mb-2">{adv.tagline}</p>
                  <p className="text-parchment-500 text-xs leading-relaxed mb-2">{adv.blurb}</p>
                  <div className="flex flex-wrap gap-1.5">
                    <span className="text-xs px-2 py-0.5 rounded bg-arcane-900/40 text-arcane-300">{adv.tone}</span>
                    {adv.tags.map((t) => (
                      <span key={t} className="text-xs px-2 py-0.5 rounded bg-parchment-800 text-parchment-500">{t}</span>
                    ))}
                  </div>
                </button>
              ))}

              {adventures.length === 0 && !adventureLoadError && (
                <div className="text-center text-parchment-500 text-sm py-6">
                  <span className="inline-block animate-spin mr-2">🎲</span> Loading adventures…
                </div>
              )}
            </div>
          </>
        )}

        {/* === LLM world generation === */}
        {mode === 'generate' && (
          <>
            <div>
              <label className="block text-parchment-300 mb-3 font-semibold text-lg">Campaign Tone</label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {TONES.map((t) => (
                  <button
                    key={t}
                    onClick={() => setTone(t)}
                    className={`py-3 rounded-lg text-sm font-semibold transition-all duration-200 text-left px-4
                      ${tone === t ? 'bg-blood-600 text-parchment-50 shadow-lg shadow-blood-900/40' : 'bg-parchment-700 text-parchment-300 hover:bg-parchment-600 hover:-translate-y-0.5'}`}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>

            <button
              className="btn-primary w-full text-lg py-3"
              onClick={handleGenerate}
              disabled={loading}
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="inline-block animate-spin">🎲</span> The DM is weaving your world...
                </span>
              ) : (
                '🎲 Generate World & Begin Adventure'
              )}
            </button>

            {loading && (
              <div className="space-y-2 animate-fade-in">
                <div className="skeleton h-3 rounded w-3/4" />
                <div className="skeleton h-3 rounded w-full" />
                <div className="skeleton h-3 rounded w-5/6" />
              </div>
            )}
          </>
        )}

        {error && (
          <div className="bg-blood-700/40 border border-blood-500 rounded-lg p-3 text-parchment-200 text-sm animate-scale-in">
            {error}
          </div>
        )}

        {!characterId && (
          <p className="text-center text-parchment-500 text-sm">
            <a href="/character/new" className="text-arcane-400 underline">Create a character first</a>
          </p>
        )}
      </div>
    </div>
  )
}
