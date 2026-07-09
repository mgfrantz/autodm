import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import TrapsPanel from '../TrapsPanel'
import {
  getTrapRegistry, getGameTraps, placeTrap, detectTrap, disarmTrap, triggerGameTrap,
} from '../../stores/api'
import type { Trap, TrapInstance, StoryEntry } from '../../types'

/* ------------------------------------------------------------------ *
 * Integration tests for the Traps panel.
 *
 * The panel is a thin UI over the already-tested backend trap API
 * (engine/traps.py has 50 tests; api/traps.py has 36). These tests focus
 * on the panel's own behaviour: the registry/place flow, the detect →
 * disarm → trigger workflow, and the story-narration hook that surfaces
 * trap outcomes in the DM bubble.
 * ------------------------------------------------------------------ */

vi.mock('../../stores/api', () => ({
  getTrapRegistry: vi.fn(),
  getTrapDetail: vi.fn(),
  getGameTraps: vi.fn(),
  placeTrap: vi.fn(),
  detectTrap: vi.fn(),
  passiveDetectTrap: vi.fn(),
  disarmTrap: vi.fn(),
  triggerGameTrap: vi.fn(),
  removeTrap: vi.fn(),
  getTrapsDmSummary: vi.fn(),
}))

/** A sample trap template from the registry. */
const SAMPLE_TRAP: Trap = {
  id: 'hidden_pit',
  name: 'Hidden Pit',
  description: 'A covered pit that opens beneath the unwary.',
  trap_type: 'mechanical',
  severity: 'dangerous',
  detection_dc: 15,
  disarm_dc: 12,
  trigger: 'Stepping onto the cover.',
  effects: [{
    type: 'damage',
    damage_dice: '2d6',
    damage_type: 'bludgeoning',
    save_ability: 'dexterity',
    save_dc: 13,
    save_result: 'half',
    condition: '',
    condition_duration: 0,
    description: '',
  }],
  countermeasure: 'Wedge the cover open or find another route.',
  area: '5-ft square',
}

/** Build a placed trap instance with mutable state. */
function instance(overrides: Partial<TrapInstance> = {}): TrapInstance {
  return {
    trap_id: SAMPLE_TRAP.id,
    trap: SAMPLE_TRAP,
    location: '',
    discovered: false,
    disarmed: false,
    triggered: false,
    trigger_count: 0,
    ...overrides,
  }
}

describe('TrapsPanel', () => {
  beforeEach(() => {
    vi.mocked(getTrapRegistry).mockResolvedValue([SAMPLE_TRAP])
    vi.mocked(getGameTraps).mockResolvedValue([])
  })

  it('renders the registry and places a trap, narrating to the DM bubble', async () => {
    vi.mocked(placeTrap).mockResolvedValue(instance({ location: 'corridor' }))
    const onNarration = vi.fn()

    render(<TrapsPanel gameId={1} onNarration={onNarration} />)

    // The registry trap appears as a selectable button.
    const trapBtn = await screen.findByRole('button', { name: /Hidden Pit/i })
    fireEvent.click(trapBtn)

    // Place it.
    fireEvent.click(screen.getByRole('button', { name: /Place.*Hidden Pit/i }))
    await waitFor(() => expect(vi.mocked(placeTrap)).toHaveBeenCalledTimes(1))

    // The placement is narrated as a system story entry.
    await waitFor(() => expect(onNarration).toHaveBeenCalledTimes(1))
    const entry = onNarration.mock.calls[0][0] as StoryEntry
    expect(entry.role).toBe('system')
    expect(entry.content).toContain('Hidden Pit')
    expect(entry.content).toContain('corridor')
    expect(entry.timestamp).toBeTruthy()
  })

  it('narrates a successful detection into the DM bubble', async () => {
    const inst = instance()
    vi.mocked(getGameTraps).mockResolvedValue([inst])
    vi.mocked(detectTrap).mockResolvedValue({
      success: true,
      roll: 18,
      perception_total: 18,
      dc: 15,
      discovered: true,
      narrative: 'You spot a Hidden Pit! (18 vs DC 15) A covered pit that opens beneath the unwary.',
    })
    const onNarration = vi.fn()

    render(<TrapsPanel gameId={1} onNarration={onNarration} />)

    // The placed trap renders with a "Detect" button.
    const detectBtn = await screen.findByRole('button', { name: /🔍 Detect/i })
    fireEvent.click(detectBtn)

    await waitFor(() => expect(vi.mocked(detectTrap)).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(onNarration).toHaveBeenCalledTimes(1))

    const entry = onNarration.mock.calls[0][0] as StoryEntry
    expect(entry.role).toBe('system')
    expect(entry.content).toContain('spot a Hidden Pit')
  })

  it('narrates a disarm attempt (with critical-failure trigger)', async () => {
    const inst = instance({ discovered: true })
    vi.mocked(getGameTraps).mockResolvedValue([inst])
    vi.mocked(disarmTrap).mockResolvedValue({
      success: false,
      roll: 3,
      check_total: 5,
      dc: 12,
      disarmed: false,
      method: 'thieves_tools',
      narrative: 'Your attempt to disarm the Hidden Pit fails. (5 vs DC 12)',
      triggered: {
        triggered: true,
        damage: 7,
        damage_type: 'bludgeoning',
        save_ability: 'dexterity',
        save_dc: 13,
        save_success: false,
        conditions: [],
        effect_descriptions: ['2d6 bludgeoning damage'],
        narrative: 'The Hidden Pit triggers! 2d6 bludgeoning damage (7).',
      },
    })
    const onNarration = vi.fn()

    render(<TrapsPanel gameId={1} onNarration={onNarration} />)

    const disarmBtn = await screen.findByRole('button', { name: /🔧 Disarm/i })
    fireEvent.click(disarmBtn)

    await waitFor(() => expect(vi.mocked(disarmTrap)).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(onNarration).toHaveBeenCalledTimes(1))

    const entry = onNarration.mock.calls[0][0] as StoryEntry
    // Both the failed disarm and the triggered trap appear.
    expect(entry.content).toContain('fails')
    expect(entry.content).toContain('triggers')
  })

  it('narrates a trap trigger with damage', async () => {
    const inst = instance({ discovered: true })
    vi.mocked(getGameTraps).mockResolvedValue([inst])
    vi.mocked(triggerGameTrap).mockResolvedValue({
      triggered: true,
      damage: 12,
      damage_type: 'bludgeoning',
      save_ability: 'dexterity',
      save_dc: 13,
      save_success: false,
      conditions: [],
      effect_descriptions: ['2d6 bludgeoning damage'],
      narrative: 'The Hidden Pit triggers! 2d6 bludgeoning damage (12).',
    })
    const onNarration = vi.fn()

    render(<TrapsPanel gameId={1} onNarration={onNarration} />)

    const triggerBtn = await screen.findByRole('button', { name: /💥 Trigger/i })
    fireEvent.click(triggerBtn)

    await waitFor(() => expect(vi.mocked(triggerGameTrap)).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(onNarration).toHaveBeenCalledTimes(1))

    const entry = onNarration.mock.calls[0][0] as StoryEntry
    expect(entry.content).toContain('triggers')
    expect(entry.content).toContain('12')
  })
})
