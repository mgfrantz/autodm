import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import ConcentrationCard from '../ConcentrationCard'
import type { GameEvent } from '../../types'

function concEvent(
  overrides: Partial<GameEvent['data']> = {},
  label = '🧠 Concentrating on Hold Person',
): GameEvent {
  return {
    type: 'concentration',
    label,
    data: {
      operation: 'started',
      spell_name: 'Hold Person',
      spell_id: 'hold_person',
      reason: 'Concentration spell cast',
      damage_taken: null,
      concentration_dc: null,
      roll_total: null,
      success: true,
      message: '',
      ...overrides,
    },
    timestamp: '',
  }
}

describe('ConcentrationCard', () => {
  it('renders a started concentration with spell name', () => {
    render(<ConcentrationCard event={concEvent()} />)
    expect(screen.getByText(/Hold Person/)).toBeTruthy()
  })

  it('shows the started icon and badge', () => {
    render(<ConcentrationCard event={concEvent()} />)
    expect(screen.getByText('🧠')).toBeTruthy()
    expect(screen.getByText(/Concentration Started/)).toBeTruthy()
  })

  it('shows the reason text for a started concentration', () => {
    render(<ConcentrationCard event={concEvent()} />)
    expect(screen.getByText(/Concentration spell cast/)).toBeTruthy()
  })

  it('renders a broken concentration with the broken badge', () => {
    render(<ConcentrationCard event={concEvent({
      operation: 'broken', reason: 'Incapacitated by stunned',
    }, '💥 Concentration broken on Hold Person')} />)
    expect(screen.getAllByText('💥').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/Concentration Broken/)).toBeTruthy()
    expect(screen.getByText(/Incapacitated/)).toBeTruthy()
  })

  it('renders an ended concentration with the ended badge', () => {
    render(<ConcentrationCard event={concEvent({
      operation: 'ended', reason: 'Player drops the spell',
    }, '🛑 Concentration ended on Hold Person')} />)
    expect(screen.getAllByText('🛑').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/Concentration Ended/)).toBeTruthy()
  })

  it('renders a passed concentration check with the held badge and breakdown', () => {
    render(<ConcentrationCard event={concEvent({
      operation: 'check_passed', reason: 'Concentration save succeeded',
      damage_taken: 10, concentration_dc: 10, roll_total: 15,
    }, '✅ Concentration held on Hold Person')} />)
    expect(screen.getAllByText('✅').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/Concentration Held/)).toBeTruthy()
    expect(screen.getByText(/10 dmg/)).toBeTruthy()
    expect(screen.getByText(/DC 10/)).toBeTruthy()
    expect(screen.getByText(/Con save 15/)).toBeTruthy()
  })

  it('renders a failed concentration check with the lost badge', () => {
    render(<ConcentrationCard event={concEvent({
      operation: 'check_failed', reason: 'Rolled 8 vs DC 11 (failed)',
      damage_taken: 22, concentration_dc: 11, roll_total: 8,
    }, '⚠️ Concentration lost on Hold Person')} />)
    expect(screen.getAllByText('⚠️').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/Concentration Lost/)).toBeTruthy()
    expect(screen.getByText(/22 dmg/)).toBeTruthy()
  })

  it('renders a muted failed card with the message', () => {
    render(<ConcentrationCard event={concEvent({
      success: false, message: 'The player is not concentrating on any spell.',
    }, '🛑 No concentration to end')} />)
    expect(screen.getByText(/concentration event failed/)).toBeTruthy()
    expect(screen.getByText(/not concentrating/)).toBeTruthy()
  })

  it('fires onDismiss when ✕ is clicked', () => {
    const onDismiss = vi.fn()
    render(<ConcentrationCard event={concEvent()} onDismiss={onDismiss} />)
    fireEvent.click(screen.getByLabelText('Dismiss concentration event'))
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('renders without a dismiss button when no callback is given', () => {
    render(<ConcentrationCard event={concEvent()} />)
    expect(screen.queryByLabelText('Dismiss concentration event')).toBeNull()
  })
})
