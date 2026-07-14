import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import SkillCheckResolutionCard from '../SkillCheckResolutionCard'
import type { SkillCheckResolution } from '../../types'

/* ------------------------------------------------------------------ *
 * Unit tests for the SkillCheckResolutionCard — the inline game-event
 * card that surfaces the structured mechanical outcome of a freeform
 * player action (degree, notes, XP, stat changes, items).
 * ------------------------------------------------------------------ */

function resolution(
  overrides: Partial<SkillCheckResolution> = {},
): SkillCheckResolution {
  return {
    success: true,
    degree: 'success',
    stat_changes: {},
    items_gained: [],
    experience_gained: 0,
    narrative_notes: '',
    ...overrides,
  }
}

describe('SkillCheckResolutionCard', () => {
  it('renders nothing for an empty / null resolution', () => {
    const { container } = render(<SkillCheckResolutionCard resolution={null} />)
    expect(container).toBeEmptyDOMElement()

    const { container: c2 } = render(
      <SkillCheckResolutionCard resolution={undefined} />,
    )
    expect(c2).toBeEmptyDOMElement()

    const { container: c3 } = render(
      <SkillCheckResolutionCard resolution={resolution({ degree: 'failure' })} />,
    )
    // A bare failure with no other content is considered a non-resolution.
    expect(c3).toBeEmptyDOMElement()
  })

  it('shows the degree label and icon for a success', () => {
    render(<SkillCheckResolutionCard resolution={resolution({ degree: 'success' })} />)
    expect(screen.getByText('Success')).toBeTruthy()
    expect(screen.getByText('✅', { exact: false }) || screen.getByText('Success')).toBeTruthy()
  })

  it('shows a great-success badge distinctly', () => {
    render(
      <SkillCheckResolutionCard resolution={resolution({ degree: 'great_success' })} />,
    )
    expect(screen.getByText('Great Success')).toBeTruthy()
  })

  it('displays narrative notes when present', () => {
    render(
      <SkillCheckResolutionCard
        resolution={resolution({ narrative_notes: 'You nimbly cross the chasm.' })}
      />,
    )
    expect(screen.getByText('You nimbly cross the chasm.')).toBeTruthy()
  })

  it('displays XP gained as a chip', () => {
    render(
      <SkillCheckResolutionCard
        resolution={resolution({ experience_gained: 75 })}
      />,
    )
    expect(screen.getByText(/75 XP/)).toBeTruthy()
  })

  it('displays items gained', () => {
    render(
      <SkillCheckResolutionCard
        resolution={resolution({ items_gained: ['Rusty Key', 'Healing Potion'] })}
      />,
    )
    expect(screen.getByText('Items Gained')).toBeTruthy()
    expect(screen.getByText(/Rusty Key/)).toBeTruthy()
    expect(screen.getByText(/Healing Potion/)).toBeTruthy()
  })

  it('displays stat changes with positive/negative colouring', () => {
    render(
      <SkillCheckResolutionCard
        resolution={resolution({ stat_changes: { hp: -5, gold: 20 } })}
      />,
    )
    expect(screen.getByText('HP −5')).toBeTruthy()
    expect(screen.getByText('Gold +20')).toBeTruthy()
  })

  it('fires onDismiss when the ✕ button is clicked', () => {
    const onDismiss = vi.fn()
    render(
      <SkillCheckResolutionCard
        resolution={resolution({ degree: 'success', experience_gained: 10 })}
        onDismiss={onDismiss}
      />,
    )
    const btn = screen.getByLabelText('Dismiss resolution')
    fireEvent.click(btn)
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('works without an onDismiss callback', () => {
    render(
      <SkillCheckResolutionCard resolution={resolution({ degree: 'partial_success' })} />,
    )
    expect(screen.getByText('Partial Success')).toBeTruthy()
    // No dismiss button rendered.
    expect(screen.queryByLabelText('Dismiss resolution')).toBeNull()
  })

  it('renders a critical failure distinctly', () => {
    render(
      <SkillCheckResolutionCard
        resolution={resolution({
          degree: 'critical_failure',
          success: false,
          narrative_notes: 'You trip and drop your sword into the abyss.',
        })}
      />,
    )
    expect(screen.getByText('Critical Failure')).toBeTruthy()
  })
})
