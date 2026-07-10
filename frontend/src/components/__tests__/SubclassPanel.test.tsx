import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import SubclassPanel from '../SubclassPanel'
import {
  getCharacterSubclass,
  getAvailableSubclasses,
  chooseSubclass,
} from '../../stores/api'
import type {
  SubclassInfo,
  CharacterSubclassResponse,
  AvailableSubclassesResponse,
  ChooseSubclassResult,
} from '../../types'

/* ------------------------------------------------------------------ *
 * The Subclass panel is a thin UI over the subclass API. We mock the
 * three API functions it imports and drive the "choose an archetype"
 * flow end-to-end, plus assert the chosen-state + timeline rendering.
 * ------------------------------------------------------------------ */

vi.mock('../../stores/api', () => ({
  getCharacterSubclass: vi.fn(),
  getAvailableSubclasses: vi.fn(),
  chooseSubclass: vi.fn(),
}))

// --- Fixtures -----------------------------------------------------------

const CHAMPION: SubclassInfo = {
  id: 'champion',
  name: 'Champion',
  char_class: 'fighter',
  category: 'Martial Archetype',
  description: 'A fighter who relentlessly hones physical talent.',
  choice_level: 3,
  features: [
    { level: 3, feature: 'Improved Critical — critical hits on a 19 or 20' },
    { level: 7, feature: 'Remarkable Athlete — half proficiency to checks' },
    { level: 15, feature: 'Superior Critical — crits on 18-20' },
  ],
}

const BATTLE_MASTER: SubclassInfo = {
  ...CHAMPION,
  id: 'battle-master',
  name: 'Battle Master',
  features: [
    { level: 3, feature: 'Combat Superiority — 3 maneuvers' },
  ],
}

const AVAIL: AvailableSubclassesResponse = {
  character_id: 1,
  level: 3,
  available: [CHAMPION, BATTLE_MASTER],
}

function statePending(): CharacterSubclassResponse {
  return {
    character_id: 1,
    character_name: 'Roland',
    level: 3,
    choices: [],
    pending: [
      {
        class_name: 'fighter',
        choice_level: 3,
        category: 'Martial Archetype',
        options: ['champion', 'battle-master'],
      },
    ],
    timeline: [
      { level: 1, source: 'class', feature: 'Fighting Style, Second Wind' },
      { level: 2, source: 'class', feature: 'Action Surge' },
      { level: 3, source: 'class', feature: 'Martial Archetype' },
    ],
    dm_summary: 'none (should choose a Martial Archetype)',
  }
}

function stateChosen(): CharacterSubclassResponse {
  return {
    character_id: 1,
    character_name: 'Roland',
    level: 7,
    choices: [
      {
        class_name: 'fighter',
        subclass_id: 'champion',
        name: 'Champion',
        category: 'Martial Archetype',
        features: [
          { level: 3, feature: 'Improved Critical — critical hits on a 19 or 20' },
          { level: 7, feature: 'Remarkable Athlete — half proficiency to checks' },
        ],
      },
    ],
    pending: [],
    timeline: [
      { level: 1, source: 'class', feature: 'Fighting Style, Second Wind' },
      { level: 3, source: 'Champion', feature: 'Improved Critical' },
      { level: 7, source: 'Champion', feature: 'Remarkable Athlete' },
    ],
    dm_summary: 'Champion: Improved Critical; Remarkable Athlete',
  }
}

const CHOOSE_RESULT: ChooseSubclassResult = {
  success: true,
  message: 'Roland became a Champion.',
  class_name: 'fighter',
  subclass_id: 'champion',
  subclass_name: 'Champion',
  dm_summary: 'Champion: Improved Critical',
}

// --- Tests --------------------------------------------------------------

describe('SubclassPanel', () => {
  beforeEach(() => {
    vi.mocked(getCharacterSubclass).mockResolvedValue(statePending())
    vi.mocked(getAvailableSubclasses).mockResolvedValue(AVAIL)
    vi.mocked(chooseSubclass).mockResolvedValue(CHOOSE_RESULT)
  })

  it('renders the available subclasses when a choice is pending', async () => {
    render(<SubclassPanel characterId={1} />)

    // Both available archetypes render.
    expect(await screen.findByText('Champion')).toBeInTheDocument()
    expect(screen.getByText('Battle Master')).toBeInTheDocument()

    // The panel fetched data for the right character.
    expect(vi.mocked(getCharacterSubclass)).toHaveBeenCalledWith(1)
    expect(vi.mocked(getAvailableSubclasses)).toHaveBeenCalledWith(1)
  })

  it('chooses a subclass end-to-end and shows the success flash', async () => {
    let chosen = false
    vi.mocked(getCharacterSubclass).mockImplementation(async () =>
      chosen ? stateChosen() : statePending(),
    )
    vi.mocked(getAvailableSubclasses).mockImplementation(async () =>
      chosen ? { ...AVAIL, available: [] } : AVAIL,
    )
    vi.mocked(chooseSubclass).mockImplementation(async () => {
      chosen = true
      return CHOOSE_RESULT
    })
    const onChanged = vi.fn()

    render(<SubclassPanel characterId={1} onChanged={onChanged} />)

    await screen.findByText('Champion')

    // Click "Choose Champion".
    fireEvent.click(
      screen.getByRole('button', { name: /Choose Champion/i }),
    )

    // chooseSubclass was called with the right args; parent notified.
    await waitFor(() => {
      expect(vi.mocked(chooseSubclass)).toHaveBeenCalledTimes(1)
    })
    expect(vi.mocked(chooseSubclass)).toHaveBeenCalledWith(1, 'champion', 'fighter')
    expect(onChanged).toHaveBeenCalledTimes(1)

    // Success flash surfaces.
    expect(await screen.findByText(/Roland became a Champion/i)).toBeInTheDocument()
  })

  it('shows the current subclass and its active features when chosen', async () => {
    vi.mocked(getCharacterSubclass).mockResolvedValue(stateChosen())
    vi.mocked(getAvailableSubclasses).mockResolvedValue({ ...AVAIL, available: [] })

    render(<SubclassPanel characterId={1} />)

    // Current archetype heading renders.
    expect(await screen.findByText(/Current Archetype/i)).toBeInTheDocument()

    // Active features (levels 3 and 7) render with their levels.
    // The level markers are unique within the chosen-features list.
    expect(screen.getAllByText('Lv 3').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Lv 7').length).toBeGreaterThan(0)
    // Level 15 is not active at level 7.
    expect(screen.queryByText('Lv 15')).not.toBeInTheDocument()
    // Category + class line renders.
    expect(screen.getByText(/Martial Archetype · fighter/i)).toBeInTheDocument()
  })

  it('renders the merged class + subclass feature timeline', async () => {
    vi.mocked(getCharacterSubclass).mockResolvedValue(stateChosen())
    vi.mocked(getAvailableSubclasses).mockResolvedValue({ ...AVAIL, available: [] })

    render(<SubclassPanel characterId={1} />)

    expect(await screen.findByText(/Feature Timeline/i)).toBeInTheDocument()
    // A class feature appears in the timeline (only place it renders in
    // chosen state).
    expect(screen.getByText(/Fighting Style, Second Wind/i)).toBeInTheDocument()
    // The subclass source label prefixes timeline entries (appears in both
    // the DM summary line and the timeline, so assert at least one).
    expect(screen.getAllByText('Champion:').length).toBeGreaterThan(0)
  })
})
