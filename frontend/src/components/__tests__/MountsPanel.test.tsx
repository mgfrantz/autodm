import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import MountsPanel from '../MountsPanel'
import {
  getMountState,
  getMountRegistry,
  acquireMount,
  damageMount,
} from '../../stores/api'
import type { MountStatusResponse, Mount, StoryEntry } from '../../types'

/* ------------------------------------------------------------------ *
 * Integration tests for the Mounts panel.
 *
 * The panel is a thin UI over the already-tested backend mounts API
 * (84 tests). These tests focus on the panel's own behaviour that is
 * *not* a trivial passthrough: the no-mount / has-mount render paths,
 * the acquire flow (with narration), and the damage-throws-rider flow.
 * ------------------------------------------------------------------ */

vi.mock('../../stores/api', () => ({
  getMountState: vi.fn(),
  getMountRegistry: vi.fn(),
  acquireMount: vi.fn(),
  mountUp: vi.fn(),
  dismount: vi.fn(),
  setMountPace: vi.fn(),
  damageMount: vi.fn(),
  healMount: vi.fn(),
  getMountCombat: vi.fn(),
  previewMountTravel: vi.fn(),
}))

/** A single representative warhorse definition (matches the engine to_dict). */
function warhorse(): Mount {
  return {
    id: 'warhorse',
    name: 'Warhorse',
    type: 'land',
    speed: 60,
    fly_speed: 0,
    swim_speed: 0,
    size: 'large',
    strength: 18,
    hp: 19,
    armor_class: 11,
    cr: 0.5,
    control_type: 'controlled',
    capacity_mult: 1.0,
    cost_gp: 400.0,
    attacks: [
      { name: 'Hooves', attack_bonus: 6, damage_dice_count: 2, damage_dice_sides: 6, damage_bonus: 4, damage_type: 'bludgeoning', ranged: false },
    ],
    notes: 'Trample: DC 14 STR save or knocked prone.',
    description: 'A battle-trained steed that will fight alongside its rider.',
    effective_speed: 60,
    carrying_capacity_lbs: 540,
    speed_multiplier: 2.0,
    can_fly: false,
    can_swim: false,
    is_vehicle: false,
  }
}

/** Build a "no mount" status payload. */
function noMountStatus(): MountStatusResponse {
  return {
    character_id: 1,
    has_mounted_combatant: false,
    state: {
      mount_id: '',
      current_hp: 0,
      max_hp: 0,
      mounted: false,
      conditions: [],
      pace: 'normal',
      galloping: false,
    },
    summary: {
      has_mount: false,
      mounted: false,
      mount: null,
      mount_hp: '0/0',
      mount_conditions: [],
      pace: 'normal',
      pace_note: 'Normal pace: no special modifiers.',
      speed_multiplier: 1.0,
      travel_multiplier: 1.0,
      carrying_capacity_lbs: 0,
      control_type: '',
    },
  }
}

/** Build a status payload where the character owns + rides a warhorse. */
function mountedStatus(): MountStatusResponse {
  const mount = warhorse()
  return {
    character_id: 1,
    has_mounted_combatant: false,
    state: {
      mount_id: 'warhorse',
      current_hp: 19,
      max_hp: 19,
      mounted: true,
      conditions: [],
      pace: 'normal',
      galloping: false,
    },
    summary: {
      has_mount: true,
      mounted: true,
      mount,
      mount_hp: '19/19',
      mount_conditions: [],
      pace: 'normal',
      pace_note: 'Normal pace: no special modifiers.',
      speed_multiplier: 2.0,
      travel_multiplier: 2.0,
      carrying_capacity_lbs: 540,
      control_type: 'controlled',
    },
  }
}

describe('MountsPanel', () => {
  beforeEach(() => {
    vi.mocked(getMountState).mockResolvedValue(noMountStatus())
    vi.mocked(getMountRegistry).mockResolvedValue([warhorse()])
  })

  it('shows the on-foot prompt and registry browser when there is no mount', async () => {
    render(<MountsPanel gameId={1} />)

    // The no-mount state shows the on-foot prompt.
    expect(await screen.findByText(/You are on foot/i)).toBeInTheDocument()
    // The registry browser lists the warhorse.
    expect(screen.getByText('Warhorse')).toBeInTheDocument()
    expect(screen.getByText(/400 gp/)).toBeInTheDocument()
  })

  it('acquires a mount and narrates the acquisition to the DM bubble', async () => {
    vi.mocked(acquireMount).mockResolvedValue({
      character_id: 1,
      state: { mount_id: 'warhorse', current_hp: 19, max_hp: 19, mounted: true, conditions: [], pace: 'normal', galloping: false },
      mount: warhorse(),
      paid_gp: 0,
      character_gold: 100,
      summary: mountedStatus().summary,
    })
    const onNarration = vi.fn()

    render(<MountsPanel gameId={1} onNarration={onNarration} />)

    // Wait for the registry to render, then acquire the warhorse.
    const acquireBtn = await screen.findByRole('button', { name: 'Acquire' })
    fireEvent.click(acquireBtn)

    await waitFor(() => expect(vi.mocked(acquireMount)).toHaveBeenCalledTimes(1))
    expect(vi.mocked(acquireMount)).toHaveBeenCalledWith(1, 'warhorse', true, false)

    // The acquisition should be narrated into the DM story bubble.
    await waitFor(() => expect(onNarration).toHaveBeenCalledTimes(1))
    const entry = onNarration.mock.calls[0][0] as StoryEntry
    expect(entry.role).toBe('system')
    expect(entry.content).toMatch(/acquired a warhorse/i)
    expect(entry.timestamp).toBeTruthy()
  })

  it('renders the mount card with HP and mount-up/dismount controls when mounted', async () => {
    vi.mocked(getMountState).mockResolvedValue(mountedStatus())

    render(<MountsPanel gameId={1} />)

    // The mount card shows the warhorse HP (unique text — the name also appears
    // in the registry browser below).
    expect(await screen.findByText('19/19')).toBeInTheDocument()
    // Mounted status badge.
    expect(screen.getByText('🐴 Mounted')).toBeInTheDocument()
    // The dismount button is available while mounted.
    expect(screen.getByRole('button', { name: /Dismount/i })).toBeInTheDocument()
  })

  it('narrates damage and flags a downed mount that throws the rider', async () => {
    vi.mocked(getMountState).mockResolvedValue(mountedStatus())
    vi.mocked(damageMount).mockResolvedValue({
      character_id: 1,
      state: { mount_id: 'warhorse', current_hp: 0, max_hp: 19, mounted: false, conditions: [], pace: 'normal', galloping: false },
      outcome: {
        forced_dismount: true,
        rider_prone: true,
        dc: null,
        save_ability: null,
        message: 'Your mount collapses beneath you — you are thrown and land prone.',
      },
      overflow: 9,
      summary: { ...mountedStatus().summary, mounted: false, mount_hp: '0/19' },
    })
    const onNarration = vi.fn()

    render(<MountsPanel gameId={1} onNarration={onNarration} />)

    // Wait for the mount card (HP readout is unique), set damage to 19, apply.
    await screen.findByText('19/19')
    // Damage input is the first number input with value '5' (heal also defaults to 5).
    const dmgInput = screen.getAllByDisplayValue('5')[0]
    fireEvent.change(dmgInput, { target: { value: '19' } })
    // Click the damage "Apply" button (the first Apply; heal's is disabled at full HP).
    fireEvent.click(screen.getAllByRole('button', { name: 'Apply' })[0])

    await waitFor(() => expect(vi.mocked(damageMount)).toHaveBeenCalledWith(1, 19))
    // A downed mount (0 HP, forced dismount) is narrated.
    await waitFor(() => expect(onNarration).toHaveBeenCalledTimes(1))
    const entry = onNarration.mock.calls[0][0] as StoryEntry
    expect(entry.content).toMatch(/collapses|thrown/i)
  })
})
