import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { listCharacters, listWorlds, listGames } from '../stores/api'
import type { Character } from '../types'

export default function HomeView() {
  const [characters, setCharacters] = useState<Character[]>([])
  const [_worlds, setWorlds] = useState<any[]>([])
  const [games, setGames] = useState<any[]>([])

  useEffect(() => {
    Promise.all([listCharacters(), listWorlds(), listGames()])
      .then(([chars, worlds, gms]) => {
        setCharacters(chars)
        setWorlds(worlds)
        setGames(gms)
      })
      .catch(() => {}) // Backend may not be running yet
  }, [])

  return (
    <div className="max-w-4xl mx-auto p-4 sm:p-8 view-enter">
      <h1 className="font-fantasy text-4xl sm:text-5xl text-center text-parchment-200 mb-2 animate-slide-up">
        ⚔️ LLM Adventure ⚔️
      </h1>
      <p className="text-center text-parchment-400 mb-8 sm:mb-12 animate-fade-in" style={{ animationDelay: '0.1s' }}>
        A DnD adventure guided by an AI Dungeon Master
      </p>

      {/* Start New Adventure */}
      <div className="panel mb-8 animate-slide-up" style={{ animationDelay: '0.15s' }}>
        <h2 className="title-fantasy mb-4">Begin a New Adventure</h2>
        <div className="flex gap-4 flex-wrap">
          <Link to="/character/new" className="btn-primary">
            1. Create Character
          </Link>
          <Link to="/world/new" className="btn-secondary">
            2. Generate World
          </Link>
        </div>
        <p className="text-parchment-400 text-sm mt-3">
          Create your hero, then generate a world tailored to them.
        </p>
      </div>

      {/* Existing Characters */}
      {characters.length > 0 && (
        <div className="panel mb-8 animate-slide-up" style={{ animationDelay: '0.2s' }}>
          <h2 className="title-fantasy mb-4">Your Characters</h2>
          <div className="grid sm:grid-cols-2 gap-3">
            {characters.map((c) => (
              <div key={c.id} className="flex justify-between items-center bg-parchment-900/50 panel-hover rounded-lg p-3">
                <div className="min-w-0">
                  <span className="font-semibold text-parchment-200 truncate block">{c.name}</span>
                  <span className="text-parchment-400 text-sm">
                    Level {c.level} {c.race} {c.char_class}
                  </span>
                </div>
                <div className="text-parchment-400 text-sm shrink-0 ml-2">
                  HP: {c.current_hp}/{c.max_hp} | AC: {c.armor_class}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Existing Games */}
      {games.length > 0 && (
        <div className="panel mb-8 animate-slide-up" style={{ animationDelay: '0.25s' }}>
          <h2 className="title-fantasy mb-4">Continue Adventure</h2>
          <div className="grid sm:grid-cols-2 gap-3">
            {games.map((g: any) => (
              <Link
                key={g.id}
                to={`/game/${g.id}`}
                className="block bg-parchment-900/50 panel-hover rounded-lg p-3"
              >
                <span className="font-semibold text-parchment-200 truncate block">{g.name}</span>
                <span className="text-parchment-400 text-sm">
                  {g.character_name} in {g.world_name}
                </span>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
