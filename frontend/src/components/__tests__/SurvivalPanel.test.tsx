import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import SurvivalPanel from '../SurvivalPanel'
import { getSurvival, advanceSurvival } from '../../stores/api'
import type { SurvivalStatus, SurvivalAdvanceResult, StoryEntry } from '../../types'

/* ------------------------------------------------------------------ *
 * Integration tests for the Survival panel.
 *
 * The panel is a thin UI over the already-tested backend survival API.
 * These tests focus on the panel's own behaviour that is *not* a trivial
 * passthrough: the story-narration hook (onNarration) that surfaces a
 * survival day's toll in the DM bubble, the deficit readout, and the
 * advance-day flow.
 * ------------------------------------------------------------------ */

vi.mock('../../stores/api', () => ({
  getSurvival: vi.fn(),
  advanceSurvival: vi.fn(),
  resetSurvival: vi.fn(),
}))

/** Build a complete survival-status payload, overriding just the fields under test. */
function status(overrides: Partial<SurvivalStatus> = {}): SurvivalStatus {
  return {
    character_id: 1,
    exhaustion: 0,
    state: { days_without_food: 0, days_without_water: 0 },
    deficit: {
      days_without_food: 0,
      days_without_water: 0,
      food_grace_days: 3,
      food_days_until_exhaustion: 3,
      starving: false,
      dehydrated: false,
      daily_food_lbs: 1,
      daily_water_gal: 1,
      hot: false,
    },
    daily_needs: { food: 1, water: 1 },
    ...overrides,
  }
}

/** Build a complete advance-result payload, overriding just the fields under test. */
function result(overrides: Partial<SurvivalAdvanceResult> = {}): SurvivalAdvanceResult {
  return {
    state: { days_without_food: 0, days_without_water: 0 },
    food_intake_ok: true,
    water_intake_ok: true,
    water_half_or_more: true,
    water_needed: 1,
    exhaustion_from_food: 0,
    exhaustion_from_water: 0,
    exhaustion_added: 0,
    new_exhaustion: 0,
    character_id: 1,
    exhaustion_before: 0,
    exhaustion_after: 0,
    changed: false,
    hot: false,
    deficit: {
      days_without_food: 0,
      days_without_water: 0,
      food_grace_days: 3,
      food_days_until_exhaustion: 3,
      starving: false,
      dehydrated: false,
      daily_food_lbs: 1,
      daily_water_gal: 1,
      hot: false,
    },
    thirst_save_dc: null,
    thirst_save_roll: null,
    thirst_save_bonus: 0,
    thirst_save_success: null,
    died: false,
    messages: [],
    character: { current_hp: 30, max_hp: 30 },
    level: 0,
    description: 'No exhaustion.',
    disadvantage_ability_checks: false,
    disadvantage_attack_rolls: false,
    disadvantage_saving_throws: false,
    speed_divisor: 1,
    max_hp_halved: false,
    dead: false,
    active_effects: [],
    ...overrides,
  }
}

describe('SurvivalPanel', () => {
  beforeEach(() => {
    vi.mocked(getSurvival).mockResolvedValue(status())
    vi.mocked(advanceSurvival).mockResolvedValue(result())
  })

  it('renders the deficit readout and an uneventful day stays silent', async () => {
    const onNarration = vi.fn()
    render(<SurvivalPanel gameId={1} onNarration={onNarration} />)

    // A healthy day shows both cards as well-fed/watered (single-element labels,
    // so they survive testing-library's text-matching).
    expect(await screen.findByText(/Well-fed today/i)).toBeInTheDocument()
    expect(screen.getByText(/Well-watered today/i)).toBeInTheDocument()

    // A default healthy day (no prior exhaustion, full intake) is uneventful —
    // the panel must NOT push a story entry for it.
    fireEvent.click(screen.getByRole('button', { name: /Resolve day/i }))
    await waitFor(() => expect(vi.mocked(advanceSurvival)).toHaveBeenCalledTimes(1))
    expect(onNarration).not.toHaveBeenCalled()
  })

  it('narrates dehydration exhaustion into the DM bubble', async () => {
    vi.mocked(getSurvival).mockResolvedValue(status({
      exhaustion: 0,
      state: { days_without_food: 0, days_without_water: 1 },
      deficit: { ...status().deficit, days_without_water: 1, dehydrated: true },
    }))
    vi.mocked(advanceSurvival).mockResolvedValue(result({
      food_intake_ok: true,
      water_intake_ok: false,
      water_half_or_more: false,
      exhaustion_from_water: 1,
      exhaustion_added: 1,
      new_exhaustion: 1,
      exhaustion_before: 0,
      exhaustion_after: 1,
      changed: true,
      messages: ['Less than half the needed water — dehydration inflicts a level of exhaustion automatically.'],
    }))
    const onNarration = vi.fn()

    render(<SurvivalPanel gameId={1} onNarration={onNarration} />)

    fireEvent.click(await screen.findByRole('button', { name: /Resolve day/i }))

    await waitFor(() => expect(onNarration).toHaveBeenCalledTimes(1))
    const entry = onNarration.mock.calls[0][0] as StoryEntry
    expect(entry.role).toBe('system')
    expect(entry.content).toMatch(/dehydration/i)
    expect(entry.content).toContain('0 → 1')
    expect(entry.timestamp).toBeTruthy()
  })

  it('narrates death distinctly when deprivation is fatal', async () => {
    vi.mocked(advanceSurvival).mockResolvedValue(result({
      exhaustion_added: 1,
      new_exhaustion: 6,
      exhaustion_before: 5,
      exhaustion_after: 6,
      died: true,
      dead: true,
      character: { current_hp: 0, max_hp: 30 },
      messages: ['Exhaustion reaches level 6 — death from deprivation.'],
    }))
    const onNarration = vi.fn()

    render(<SurvivalPanel gameId={1} onNarration={onNarration} />)
    fireEvent.click(await screen.findByRole('button', { name: /Resolve day/i }))

    await waitFor(() => expect(onNarration).toHaveBeenCalledTimes(1))
    const entry = onNarration.mock.calls[0][0] as StoryEntry
    expect(entry.content).toMatch(/fatal/i)
    expect(entry.content).toMatch(/starvation/i)
  })

  it('shows the exhaustion-sustenance link and grace summary', async () => {
    vi.mocked(getSurvival).mockResolvedValue(status({
      exhaustion: 2,
      state: { days_without_food: 1, days_without_water: 0 },
      deficit: { ...status().deficit, days_without_food: 1, food_days_until_exhaustion: 2 },
    }))

    render(<SurvivalPanel gameId={1} />)

    // The food card is in warning state (1 day short) — it shows the grace
    // countdown (continuous text within a single span, so it matches cleanly).
    expect(await screen.findByText(/day\(s\) of grace left/i)).toBeInTheDocument()
    // The exhaustion link shows the driven exhaustion level.
    expect(screen.getByText(/2\/6/)).toBeInTheDocument()
  })
})
