import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import CheckPromptCard from '../CheckPromptCard'
import type { GameEvent } from '../../types'

/* ------------------------------------------------------------------ *
 * Unit tests for CheckPromptCard — the inline game-event card showing
 * a DM-requested check prompt with a roll button.
 * ------------------------------------------------------------------ */

// Mock the resolveCheck API call
vi.mock('../../stores/api', () => ({
  resolveCheck: vi.fn(),
}))

import { resolveCheck } from '../../stores/api'

function checkPromptEvent(overrides: Partial<GameEvent['data']> = {}): GameEvent {
  return {
    type: 'check_prompt',
    label: 'Perception Check',
    data: {
      skill: 'Perception',
      dc: 15,
      reason: '',
      ...overrides,
    },
    timestamp: '',
  }
}

function diceRollResult(): GameEvent {
  return {
    type: 'dice_roll',
    label: 'Perception Check',
    data: {
      rolls: [18],
      modifier: 3,
      total: 21,
      dc: 15,
      success: true,
    },
    timestamp: '',
  }
}

describe('CheckPromptCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the prompt with skill name and DC', () => {
    render(<CheckPromptCard event={checkPromptEvent()} gameId={1} />)
    expect(screen.getByText('📜')).toBeTruthy()
    expect(screen.getByText(/Roll a Perception check/)).toBeTruthy()
    expect(screen.getByText(/DC 15/)).toBeTruthy()
  })

  it('shows the roll button', () => {
    render(<CheckPromptCard event={checkPromptEvent()} gameId={1} />)
    expect(screen.getByText('🎲')).toBeTruthy()
    expect(screen.getByText('Roll')).toBeTruthy()
  })

  it('calls resolveCheck and shows result card on roll click', async () => {
    const mockedResolveCheck = vi.mocked(resolveCheck)
    mockedResolveCheck.mockResolvedValueOnce(diceRollResult())

    render(<CheckPromptCard event={checkPromptEvent()} gameId={1} />)
    fireEvent.click(screen.getByText('Roll'))

    await waitFor(() => {
      // After roll, the DiceRollCard should render with the result
      expect(screen.getByText('18 + 3 = 21')).toBeTruthy()
      expect(screen.getByText(/✅ Success/)).toBeTruthy()
    })

    expect(mockedResolveCheck).toHaveBeenCalledWith(1, 'Perception', 15)
  })

  it('shows error message on roll failure', async () => {
    const mockedResolveCheck = vi.mocked(resolveCheck)
    mockedResolveCheck.mockRejectedValueOnce(new Error('Network error'))

    render(<CheckPromptCard event={checkPromptEvent()} gameId={1} />)
    fireEvent.click(screen.getByText('Roll'))

    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeTruthy()
    })
  })

  it('hides DC when not provided', () => {
    render(
      <CheckPromptCard
        event={checkPromptEvent({ dc: undefined })}
        gameId={1}
      />,
    )
    expect(screen.queryByText(/DC/)).toBeNull()
  })
})
