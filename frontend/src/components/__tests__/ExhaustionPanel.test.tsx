import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import ExhaustionPanel from '../ExhaustionPanel'
import { getExhaustion, modifyExhaustion } from '../../stores/api'
import type { ExhaustionModifyResult, StoryEntry } from '../../types'

/* ------------------------------------------------------------------ *
 * Integration test for the exhaustion panel's new story-narration hook.
 * When the player raises/lowers exhaustion, the panel should push a system
 * story entry (the "DM bubble" line) via ``onNarration`` — but only when the
 * level actually changed. No-ops and death are handled distinctly.
 * ------------------------------------------------------------------ */

vi.mock('../../stores/api', () => ({
  getExhaustion: vi.fn(),
  modifyExhaustion: vi.fn(),
}))

/** Build a complete exhaustion payload, overriding just the fields under test. */
function status(overrides: Partial<ExhaustionModifyResult> = {}): ExhaustionModifyResult {
  return {
    character_id: 1,
    in_combat: false,
    exhaustion: 0,
    level: 0,
    description: 'No exhaustion.',
    disadvantage_ability_checks: false,
    disadvantage_attack_rolls: false,
    disadvantage_saving_throws: false,
    speed_divisor: 1,
    max_hp_halved: false,
    dead: false,
    active_effects: [],
    before: 0,
    after: 0,
    changed: false,
    died: false,
    character: { current_hp: 30, max_hp: 30 },
    ...overrides,
  }
}

describe('ExhaustionPanel — story narration', () => {
  beforeEach(() => {
    vi.mocked(getExhaustion).mockResolvedValue(status())
    vi.mocked(modifyExhaustion).mockResolvedValue(status())
  })

  it('narrates a gained level into the DM bubble', async () => {
    vi.mocked(getExhaustion).mockResolvedValue(status({ exhaustion: 0, level: 0 }))
    vi.mocked(modifyExhaustion).mockResolvedValue(
      status({
        exhaustion: 1,
        level: 1,
        before: 0,
        after: 1,
        changed: true,
        description: 'Disadvantage on ability checks',
        disadvantage_ability_checks: true,
      }),
    )
    const onNarration = vi.fn()

    render(<ExhaustionPanel gameId={1} onNarration={onNarration} />)

    // Wait for the panel to load, then trigger a hazard.
    const gainBtn = await screen.findByRole('button', { name: /Gain a level/i })
    fireEvent.click(gainBtn)

    await waitFor(() => expect(onNarration).toHaveBeenCalledTimes(1))
    const entry = onNarration.mock.calls[0][0] as StoryEntry
    expect(entry.role).toBe('system')
    expect(entry.content).toMatch(/worsens/i)
    expect(entry.content).toContain('0 → 1')
    expect(entry.timestamp).toBeTruthy()
  })

  it('narrates a recovered level', async () => {
    vi.mocked(getExhaustion).mockResolvedValue(status({ exhaustion: 2, level: 2 }))
    vi.mocked(modifyExhaustion).mockResolvedValue(
      status({ exhaustion: 1, level: 1, before: 2, after: 1, changed: true }),
    )
    const onNarration = vi.fn()

    render(<ExhaustionPanel gameId={1} onNarration={onNarration} />)

    fireEvent.click(await screen.findByRole('button', { name: /Recover a level/i }))

    await waitFor(() => expect(onNarration).toHaveBeenCalledTimes(1))
    const entry = onNarration.mock.calls[0][0] as StoryEntry
    expect(entry.role).toBe('system')
    expect(entry.content).toMatch(/eases/i)
    expect(entry.content).toContain('2 → 1')
  })

  it('does not narrate a no-op change', async () => {
    vi.mocked(getExhaustion).mockResolvedValue(status({ exhaustion: 1, level: 1 }))
    // A "set to current level" returns changed=false.
    vi.mocked(modifyExhaustion).mockResolvedValue(
      status({ exhaustion: 1, level: 1, before: 1, after: 1, changed: false }),
    )
    const onNarration = vi.fn()

    render(<ExhaustionPanel gameId={1} onNarration={onNarration} />)

    fireEvent.click(await screen.findByRole('button', { name: /Gain a level/i }))

    // Give the async handler a chance to fire, then assert silence.
    await waitFor(() => expect(vi.mocked(modifyExhaustion)).toHaveBeenCalledTimes(1))
    expect(onNarration).not.toHaveBeenCalled()
  })

  it('narrates death distinctly when exhaustion reaches level 6', async () => {
    vi.mocked(getExhaustion).mockResolvedValue(status({ exhaustion: 5, level: 5 }))
    vi.mocked(modifyExhaustion).mockResolvedValue(
      status({
        exhaustion: 6,
        level: 6,
        before: 5,
        after: 6,
        changed: true,
        died: true,
        dead: true,
        character: { current_hp: 0, max_hp: 30 },
      }),
    )
    const onNarration = vi.fn()

    render(<ExhaustionPanel gameId={1} onNarration={onNarration} />)

    fireEvent.click(await screen.findByRole('button', { name: /Gain a level/i }))

    await waitFor(() => expect(onNarration).toHaveBeenCalledTimes(1))
    const entry = onNarration.mock.calls[0][0] as StoryEntry
    expect(entry.content).toMatch(/level 6/i)
    expect(entry.content).toMatch(/death/i)
  })
})
