import { Routes, Route } from 'react-router-dom'
import HomeView from './views/HomeView'
import CharacterCreation from './views/CharacterCreation'
import WorldGeneration from './views/WorldGeneration'
import GameView from './views/GameView'

export default function App() {
  return (
    <div className="min-h-screen">
      <Routes>
        <Route path="/" element={<HomeView />} />
        <Route path="/character/new" element={<CharacterCreation />} />
        <Route path="/world/new" element={<WorldGeneration />} />
        <Route path="/game/:gameId" element={<GameView />} />
      </Routes>
    </div>
  )
}
