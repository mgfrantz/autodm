import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import LegendaryPanel from '../LegendaryPanel'
import {
  getEncounterLegendary,
  useLegendaryAction,
  getLairState,
  fireLairAction,
  listLegendaryCreatures,
} from '../../stores/api'
import type {
  LegendaryCombatantView,
  LairStateResponse,
  LegendaryCreaturePreset,
  UseLegendaryActionResult,
  FireLairActionResult,
  StoryEntry,
} from '../../types'

/* ------------------------------------------------------------------ *
 * Integration tests for the Legendary Actions & Lair Actions panel.
 *
 * The panel is a UI over the already-tested backend legendary API
 * (76 tests). These cover the panel's own behaviour: the no-boss
 * banner, the boss card with action budget, spending a legendary action
 * (with narration), firing a lair action, and the registry browser.
 * ------------------------------------------------------------------ */

vi.mock('../../stores/api', () => ({
  getEncounterLegendary: vi.fn(),
  useLegendaryAction: vi.fn(),
  getLairState: vi.fn(),
  fireLairAction: vi.fn(),
  listLegendaryCreatures: vi.fn(),
  getLegendaryCreature: vi.fn(),
}))

function bossView(): LegendaryCombatantView {
  return {
    combatant_id: 'enemy_1',
    name: 'Adult Red Dragon',
    is_legendary: true,
    budget_max: 3,
    budget_used: 0,
    budget_remaining: 3,
    legendary_actions: [
      {
        id: 'detect',
        name: 'Detect',
        description: 'The dragon makes a Perception check.',
        cost: 1,
        kind: 'detect',
      },
      {
        id: 'tail_attack',
        name: 'Tail Attack',
        description: 'The dragon makes one tail attack.',
        cost: 1,
        kind: 'attack',
        attack: { name: 'Tail', attack_bonus: 14 },
      },
    ],
    available_actions: [
      {
        id: 'detect',
        name: 'Detect',
        description: '',
        cost: 1,
        kind: 'detect',
      },
      {
        id: 'tail_attack',
        name: 'Tail Attack',
        description: '',
        cost: 1,
        kind: 'attack',
        attack: { name: 'Tail' },
      },
    ],
  }
}

function noBossEncounter() {
  return { in_combat: true, legendary_creatures: [], has_lair: false }
}

function noLair(): LairStateResponse {
  return {
    has_lair: false,
    initiative_count: 20,
    lair_last_fired_round: null,
    round_number: 1,
    lair_actions: [],
  }
}

function registry(): LegendaryCreaturePreset[] {
  return [
    {
      id: 'adult_red_dragon',
      name: 'Adult Red Dragon',
      cr: 17,
      max_hp: 256,
      armor_class: 19,
      speed: 40,
      size: 'huge',
      strength: 27,
      dexterity: 10,
      initiative_bonus: 0,
      attacks: [],
      damage_modifiers: [],
      legendary_budget_max: 3,
      legendary_actions: [],
      lair_actions: [],
      notes: 'Iconic CR 17 dragon.',
    },
    {
      id: 'lich',
      name: 'Lich',
      cr: 21,
      max_hp: 135,
      armor_class: 17,
      speed: 30,
      size: 'medium',
      strength: 11,
      dexterity: 16,
      initiative_bonus: 3,
      attacks: [],
      damage_modifiers: [],
      legendary_budget_max: 3,
      legendary_actions: [],
      lair_actions: [],
      notes: 'CR 21 undead archmage.',
    },
  ]
}

describe('LegendaryPanel', () => {
  beforeEach(() => {
    vi.mocked(getEncounterLegendary).mockResolvedValue(noBossEncounter())
    vi.mocked(getLairState).mockResolvedValue(noLair())
    vi.mocked(listLegendaryCreatures).mockResolvedValue(registry())
    vi.mocked(useLegendaryAction).mockResolvedValue({
      used: true,
      action: bossView().legendary_actions[0],
      remaining_budget: 2,
      description: 'Adult Red Dragon uses the legendary action Detect.',
    } as UseLegendaryActionResult)
    vi.mocked(fireLairAction).mockResolvedValue({
      triggered: true,
      action: null,
      description: 'Lair action fired.',
      lair_last_fired_round: 1,
    } as FireLairActionResult)
  })

  it('shows the no-boss banner when no legendary creature is present', async () => {
    render(<LegendaryPanel gameId={1} />)

    expect(await screen.findByText(/No legendary creature in this fight/i)).toBeInTheDocument()
    // Registry still renders.
    expect(await screen.findByText(/Legendary Bestiary/i)).toBeInTheDocument()
    expect(screen.getByText('Adult Red Dragon')).toBeInTheDocument()
    expect(screen.getByText('Lich')).toBeInTheDocument()
  })

  it('renders the boss card with its action budget and use buttons', async () => {
    vi.mocked(getEncounterLegendary).mockResolvedValue({
      in_combat: true,
      legendary_creatures: [bossView()],
      has_lair: false,
    })

    render(<LegendaryPanel gameId={1} />)

    // The boss card's "actions left" label is unique to boss cards (the
    // registry lists the creature name too, so the name alone is ambiguous).
    expect(await screen.findByText(/actions left/i)).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument() // budget remaining
    // Both action use buttons present.
    expect(screen.getByRole('button', { name: /Use Detect/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Use Tail Attack/i })).toBeInTheDocument()
  })

  it('spends a legendary action and narrates to the DM bubble', async () => {
    vi.mocked(getEncounterLegendary).mockResolvedValue({
      in_combat: true,
      legendary_creatures: [bossView()],
      has_lair: false,
    })
    const onNarration = vi.fn()

    render(<LegendaryPanel gameId={1} onNarration={onNarration} />)

    // Wait for the boss card's use button to appear.
    await screen.findByRole('button', { name: /Use Detect/i })

    fireEvent.click(screen.getByRole('button', { name: /Use Detect/i }))

    await waitFor(() => expect(vi.mocked(useLegendaryAction)).toHaveBeenCalledWith(1, 'enemy_1', 'detect', undefined))
    await waitFor(() => expect(onNarration).toHaveBeenCalledTimes(1))
    const entry = onNarration.mock.calls[0][0] as StoryEntry
    expect(entry.role).toBe('system')
    expect(entry.content).toMatch(/legendary action Detect/i)
  })

  it('shows a lair-action console and fires it with narration', async () => {
    vi.mocked(getEncounterLegendary).mockResolvedValue({
      in_combat: true,
      legendary_creatures: [bossView()],
      has_lair: true,
    })
    vi.mocked(getLairState).mockResolvedValue({
      has_lair: true,
      initiative_count: 20,
      lair_last_fired_round: null,
      round_number: 1,
      lair_actions: [
        {
          id: 'magma_fissure',
          name: 'Magma Fissure',
          description: 'Magma erupts.',
          initiative_count: 20,
          kind: 'save',
          damage: 21,
          damage_type: 'fire',
          save_dc: 15,
          save_ability: 'dex',
        },
      ],
    })
    const onNarration = vi.fn()

    render(<LegendaryPanel gameId={1} onNarration={onNarration} />)

    expect(await screen.findByText(/Lair Actions/i)).toBeInTheDocument()
    expect(screen.getByText('Magma Fissure')).toBeInTheDocument()
    expect(screen.getByText(/DC 15 DEX/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Fire lair action/i }))

    await waitFor(() => expect(vi.mocked(fireLairAction)).toHaveBeenCalledWith(1))
    await waitFor(() => expect(onNarration).toHaveBeenCalledTimes(1))
  })

  it('expands a registry creature to reveal its details', async () => {
    render(<LegendaryPanel gameId={1} />)

    // Click the Lich registry card to expand it.
    const lichCard = (await screen.findByText('Lich')).closest('button')
    expect(lichCard).toBeTruthy()
    fireEvent.click(lichCard!)

    expect(await screen.findByText('CR 21 undead archmage.')).toBeInTheDocument()
  })
})
