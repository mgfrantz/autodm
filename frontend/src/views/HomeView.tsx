import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { listCharacters, listWorlds, listGames } from '../stores/api'
import type { Character, World } from '../types'

export default function HomeView() {
  const [characters, setCharacters] = useState<Character[]>([])
  const [worlds, setWorlds] = useState<World[]>([])
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
    <div className="max-w-4xl mx-auto p-8">
      <h1 className="font-fantasy text-5xl text-center text-parchment-200 mb-2">
        ⚔️ LLM Adventure ⚔️
      </h1>
      <p className="text-center text-parchment-400 mb-12">
        A DnD adventure guided by an AI Dungeon Master
      </p>

      {/* Start New Adventure */}
      <div className="panel mb-8">
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
        <div className="panel mb-8">
          <h2 className="title-fantasy mb-4">Your Characters</h2>
          <div className="space-y-2">
            {characters.map((c) => (
              <div key={c.id} className="flex justify-between items-center bg-parchment-900/50 rounded-lg p-3">
                <div>
                  <span className="font-semibold text-parchment-200">{c.name}</span>
                  <span className="text-parchment-400 ml-2">
                    Level {c.level} {c.race} {c.char_class}
                  </span>
                </div>
                <div className="text-parchment-400 text-sm">
                  HP: {c.current_hp}/{c.max_hp} | AC: {c.armor_class}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Existing Games */}
      {games.length > 0 && (
        <div className="panel mb-8">
          <h2 className="title-fantasy mb-4">Continue Adventure</h2>
          <div className="space-y-2">
            {games.map((g: any) => (
              <Link
                key={g.id}
                to={`/game/${g.id}`}
                className="block bg-parchment-900/50 hover:bg-parchment-900 rounded-lg p-3 transition-colors"
              >
                <span className="font-semibold text-parchment-200">{g.name}</span>
                <span className="text-parchment-400 ml-2">
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
