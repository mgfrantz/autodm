import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import * as api from '../../stores/api'
import GameView from '../GameView'

// Mock the game store
vi.mock('../../stores/gameStore', () => ({
  useGameStore: vi.fn(() => ({
    gameState: {
      game_id: 1,
      name: 'Test Game',
      character: {
        id: 1,
        name: 'Test Hero',
        race: 'Human',
        char_class: 'Fighter',
        level: 1,
        hp: 10,
        max_hp: 10,
        gold: 50,
        alignment: 'lawful_good',
        background: 'Soldier',
      },
      world: {
        id: 1,
        name: 'Test World',
      },
      game_state: {
        location: 'Tavern',
        visited_locations: ['Tavern'],
        active_quests: [],
        conditions: [],
        in_combat: false,
      },
      story_log: [],
      current_act: 1,
      xp: 0,
    },
    story: [],
    combatState: null,
    setGameState: vi.fn(),
    setCombatState: vi.fn(),
    addToStory: vi.fn(),
    setStory: vi.fn(),
    loading: false,
    setLoading: vi.fn(),
    error: null,
    setError: vi.fn(),
    autoNarrate: false,
  })),
}))

// Mock API functions
vi.mock('../../stores/api', () => ({
  getGameState: vi.fn(() => Promise.resolve({
    game_id: 1,
    name: 'Test Game',
    character: {
      id: 1,
      name: 'Test Hero',
      race: 'Human',
      char_class: 'Fighter',
      level: 1,
      hp: 10,
      max_hp: 10,
    },
    world: { id: 1, name: 'Test World' },
    game_state: {
      location: 'Tavern',
      visited_locations: ['Tavern'],
      active_quests: [],
      conditions: [],
      in_combat: false,
    },
    story_log: [],
    current_act: 1,
    xp: 0,
  })),
  streamStartAdventure: vi.fn(),
  streamPlayerAction: vi.fn(),
  getCombatState: vi.fn(() => Promise.resolve(null)),
  getTTSStatus: vi.fn(() => Promise.resolve({ configured: false })),
  narrateLatest: vi.fn(() => Promise.resolve({})),
  cachedAudioUrl: vi.fn(() => ''),
}))

describe('GameView Action Suggestions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders fallback suggestions when no AI suggestions are available', () => {
    render(
      <BrowserRouter>
        <GameView />
      </BrowserRouter>
    )

    // Static fallback suggestions should be visible
    expect(screen.getByText('Look around')).toBeInTheDocument()
    expect(screen.getByText('Check inventory')).toBeInTheDocument()
    expect(screen.getByText('Check my stats')).toBeInTheDocument()
  })

  it('displays AI-generated action suggestions after DM narration', async () => {
    const mockSuggestions = [
      'Ask the innkeeper about rumors',
      'Search the chest for traps',
      'Talk to the mysterious stranger',
      'Inspect the mural on the wall',
    ]

    // Mock the streaming function to call onDone with suggestions
    vi.mocked(api.streamStartAdventure).mockImplementation(
      (_gameId, onChunk, onDone) => {
        // Simulate streaming chunks
        onChunk('The adventure begins...')
        onChunk(' You enter a bustling tavern.')
        // Simulate done event with suggestions
        onDone(mockSuggestions)
        return Promise.resolve()
      }
    )

    render(
      <BrowserRouter>
        <GameView />
      </BrowserRouter>
    )

    // Click "Start Adventure"
    const startButton = await screen.findByText('Start Adventure')
    fireEvent.click(startButton)

    // Wait for AI suggestions to appear
    await waitFor(() => {
      expect(screen.getByText('✨ Ask the innkeeper about rumors')).toBeInTheDocument()
      expect(screen.getByText('✨ Search the chest for traps')).toBeInTheDocument()
      expect(screen.getByText('✨ Talk to the mysterious stranger')).toBeInTheDocument()
      expect(screen.getByText('✨ Inspect the mural on the wall')).toBeInTheDocument()
    })

    // Static fallback suggestions should NOT be visible when AI suggestions exist
    expect(screen.queryByText('Look around')).not.toBeInTheDocument()
    expect(screen.queryByText('Check inventory')).not.toBeInTheDocument()
  })

  it('clears AI suggestions when player takes an action', async () => {
    const mockSuggestions = ['Ask the innkeeper about rumors']

    vi.mocked(api.streamStartAdventure).mockImplementation(
      (_gameId, onChunk, onDone) => {
        onChunk('Narration...')
        onDone(mockSuggestions)
        return Promise.resolve()
      }
    )

    vi.mocked(api.streamPlayerAction).mockImplementation(
      (_gameId, _action, onChunk, onDone) => {
        onChunk('DM response...')
        onDone(false, []) // No suggestions after player action (empty)
        return Promise.resolve()
      }
    )

    render(
      <BrowserRouter>
        <GameView />
      </BrowserRouter>
    )

    // Start adventure
    const startButton = await screen.findByText('Start Adventure')
    fireEvent.click(startButton)

    // Wait for AI suggestions
    await waitFor(() => {
      expect(screen.getByText('✨ Ask the innkeeper about rumors')).toBeInTheDocument()
    })

    // Type an action and submit
    const input = screen.getByPlaceholderText(/What do you do/)
    fireEvent.change(input, { target: { value: 'I sit at the bar' } })
    const actButton = screen.getByText('Act')
    fireEvent.click(actButton)

    // After action, static fallback should return (no AI suggestions)
    await waitFor(() => {
      expect(screen.queryByText('✨ Ask the innkeeper about rumors')).not.toBeInTheDocument()
    })
  })

  it('limits AI suggestions to 6 chips', async () => {
    const mockSuggestions = [
      'Suggestion 1',
      'Suggestion 2',
      'Suggestion 3',
      'Suggestion 4',
      'Suggestion 5',
      'Suggestion 6',
      'Suggestion 7',
      'Suggestion 8',
    ]

    vi.mocked(api.streamStartAdventure).mockImplementation(
      (_gameId, onChunk, onDone) => {
        onChunk('Narration...')
        onDone(mockSuggestions)
        return Promise.resolve()
      }
    )

    render(
      <BrowserRouter>
        <GameView />
      </BrowserRouter>
    )

    const startButton = await screen.findByText('Start Adventure')
    fireEvent.click(startButton)

    // Only first 6 suggestions should be rendered
    await waitFor(() => {
      expect(screen.getByText('✨ Suggestion 1')).toBeInTheDocument()
      expect(screen.getByText('✨ Suggestion 6')).toBeInTheDocument()
      expect(screen.queryByText('✨ Suggestion 7')).not.toBeInTheDocument()
      expect(screen.queryByText('✨ Suggestion 8')).not.toBeInTheDocument()
    })
  })
})