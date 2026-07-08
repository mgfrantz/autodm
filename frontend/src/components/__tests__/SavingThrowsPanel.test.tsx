import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import SavingThrowsPanel from '../SavingThrowsPanel'
import { getSavingThrowProficiencies, rollSavingThrow } from '../../stores/api'
import type { SavingThrowProficienciesResponse, SavingThrowRollResult } from '../../types'

/* ------------------------------------------------------------------ *
 * Integration test for the SavingThrowsPanel.
 * Verifies that class + feat (Resilient) save proficiencies render, the
 * feat-granted badge appears on the right ability, and rolling a save
 * resolves against a DC.
 * ------------------------------------------------------------------ */

vi.mock('../../stores/api', () => ({
  getSavingThrowProficiencies: vi.fn(),
  rollSavingThrow: vi.fn(),
}))

/**
 * Matcher for the "Proficient in N of 6 saves" summary line.
 *
 * The count is rendered as `Proficient in <span>2</span> of 6 saves`, so the
 * raw textContent is identical on both the inner <span class="text-parchment-500">
 * and its parent <div>. A naive textContent matcher therefore returns multiple
 * elements. This narrows the match to the specific summary span.
 */
const proficientCount = (n: number) => (
  _content: string,
  el: HTMLElement | null,
): boolean =>
  el?.tagName === 'SPAN' &&
  typeof el.className === 'string' &&
  el.className.includes('text-parchment-500') &&
  !!el.textContent?.match(new RegExp(`Proficient in ${n} of 6 saves`, 'i'))

/** Build a proficiencies payload. Fighter = Str/Con class saves by default. */
function profs(
  overrides: Partial<SavingThrowProficienciesResponse> = {},
): SavingThrowProficienciesResponse {
  return {
    character_id: 1,
    proficiencies: ['constitution', 'strength'],
    bonus_by_ability: {
      strength: 6,
      dexterity: 2,
      constitution: 5,
      intelligence: 0,
      wisdom: 1,
      charisma: 0,
    },
    feat_sources: {},
    ...overrides,
  }
}

describe('SavingThrowsPanel', () => {
  beforeEach(() => {
    vi.mocked(getSavingThrowProficiencies).mockResolvedValue(profs())
    vi.mocked(rollSavingThrow).mockResolvedValue({
      ability: 'wisdom',
      roll: 'd20 +1',
      rolls: [14],
      modifier: 1,
      total: 15,
      success: true,
      dc: 13,
      advantage: false,
      disadvantage: false,
      auto_failed: false,
      description: 'Wisdom save DC 13',
    } as SavingThrowRollResult)
  })

  it('renders class save proficiencies with the proficient count', async () => {
    render(<SavingThrowsPanel characterId={1} />)
    // The count is split across a nested <span>, so match on the specific
    // summary span (the naive textContent matcher hits both span and its parent).
    await waitFor(() =>
      expect(screen.getByText(proficientCount(2))).toBeInTheDocument(),
    )
    // Strength is a class-proficient save (no feat badge text "Resilient").
    expect(screen.queryByText(/Resilient/i)).not.toBeInTheDocument()
  })

  it('badges a feat-granted (Resilient) save proficiency', async () => {
    vi.mocked(getSavingThrowProficiencies).mockResolvedValue(
      profs({
        proficiencies: ['constitution', 'strength', 'wisdom'],
        feat_sources: { wisdom: 'Resilient' },
      }),
    )
    render(<SavingThrowsPanel characterId={1} />)
    // The feat name appears as a badge.
    expect(await screen.findByText(/Resilient/i)).toBeInTheDocument()
    // And the proficient count reflects the extra save.
    await waitFor(() =>
      expect(screen.getByText(proficientCount(3))).toBeInTheDocument(),
    )
  })

  it('rolls a save against a DC and reports success', async () => {
    render(<SavingThrowsPanel characterId={1} />)

    // Open the Wisdom save console (the only button whose accessible name
    // contains "Wisdom" before the roll console opens).
    const wisBtn = await screen.findByRole('button', { name: /Wisdom/i })
    fireEvent.click(wisBtn)

    const rollBtn = await screen.findByRole('button', { name: /Roll Wisdom Save/i })
    fireEvent.click(rollBtn)

    await waitFor(() => expect(vi.mocked(rollSavingThrow)).toHaveBeenCalledTimes(1))
    expect(vi.mocked(rollSavingThrow)).toHaveBeenCalledWith(
      1, 'wisdom', 13, false, false, [],
    )
    // Success result is surfaced.
    expect(await screen.findByText(/✓ Success/i)).toBeInTheDocument()
  })

  it('passes active conditions through to the roll', async () => {
    render(<SavingThrowsPanel characterId={1} conditions={['paralyzed']} />)

    const dexBtn = await screen.findByRole('button', { name: /Dexterity/i })
    fireEvent.click(dexBtn)
    fireEvent.click(await screen.findByRole('button', { name: /Roll Dexterity Save/i }))

    await waitFor(() => expect(vi.mocked(rollSavingThrow)).toHaveBeenCalledTimes(1))
    expect(vi.mocked(rollSavingThrow)).toHaveBeenLastCalledWith(
      1, 'dexterity', 13, false, false, ['paralyzed'],
    )
  })
})
