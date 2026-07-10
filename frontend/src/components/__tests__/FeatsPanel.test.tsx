import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import FeatsPanel from '../FeatsPanel'
import {
  listFeats,
  getCharacterFeats,
  getAvailableFeats,
  learnFeat,
} from '../../stores/api'
import type {
  FeatInfo,
  CharacterFeatsResponse,
  LearnFeatResult,
  LearnedFeatInfo,
} from '../../types'

/* ------------------------------------------------------------------ *
 * The Feats panel is a thin UI over the feats API. We mock the four API
 * functions it imports and drive the full "learn a feat" flow end-to-end:
 * render → see the ASI budget + available feats → open the confirm modal →
 * spend an ASI → see the success result and a refreshed character state.
 *
 * This is an *integration* test of the component, not the backend — the
 * backend's feat engine already has 40 tests of its own. Here we assert the
 * component wires user intent (click) to the right API call (learnFeat with
 * the correct args) and reflects the result in the DOM.
 * ------------------------------------------------------------------ */

vi.mock('../../stores/api', () => ({
  listFeats: vi.fn(),
  getCharacterFeats: vi.fn(),
  getAvailableFeats: vi.fn(),
  learnFeat: vi.fn(),
}))

// --- Fixtures -----------------------------------------------------------

const TOUGH: FeatInfo = {
  name: 'Tough',
  description:
    'Your hit point maximum increases by 2 for every level you have attained.',
  ability_bonus: {},
  ability_bonus_choices: [],
  saving_throw_proficiency: null,
  hp_per_level: 2,
  initiative_bonus: 0,
  speed_bonus: 0,
  ac_bonus: 0,
  skill_proficiencies: [],
  combat_modifiers: {},
  notes: [],
  prerequisite: null,
  source: "Player's Handbook",
}

const ATHLETE: FeatInfo = {
  ...TOUGH,
  name: 'Athlete',
  description: 'Increase your Strength or Dexterity by 1, and move more easily.',
  ability_bonus_choices: ['strength', 'dexterity'],
  hp_per_level: 0,
}

function charFeats(
  feats: LearnedFeatInfo[],
  asiAvailable: number,
  asiUsed: number,
): CharacterFeatsResponse {
  return {
    character_id: 1,
    character_name: 'Test Hero',
    level: 4,
    feats,
    asi_available: asiAvailable,
    asi_used: asiUsed,
    asi_earned: 1,
    next_asi_level: 8,
  }
}

const BEFORE = charFeats([], 1, 0)
const AFTER_TOUGH = charFeats(
  [
    {
      name: 'Tough',
      description: TOUGH.description,
      effects_applied: { hp_per_level: 2 },
      learned_at_level: 4,
    },
  ],
  0,
  1,
)

const TOUGH_RESULT: LearnFeatResult = {
  success: true,
  message: 'Tough learned. Max HP increased by 8.',
  feat_name: 'Tough',
  ability_changes: {},
  max_hp_change: 8,
  current_hp_change: 8,
  max_hp: 39,
  current_hp: 39,
  asi_available: 0,
  asi_used: 1,
  effects_applied: { hp_per_level: 2 },
}

/** The success-view badge renders the feat name with a leading ✓ — this
 *  regex matches it while ignoring the lowercase message paragraph. */
const SUCCESS = (feat: string) => new RegExp(`✓\\s*${feat}\\s*Learned`, 'i')

// --- Tests --------------------------------------------------------------

describe('FeatsPanel — learn flow', () => {
  beforeEach(() => {
    vi.mocked(listFeats).mockResolvedValue([TOUGH, ATHLETE])
    vi.mocked(getCharacterFeats).mockResolvedValue(BEFORE)
    vi.mocked(getAvailableFeats).mockResolvedValue([TOUGH])
    vi.mocked(learnFeat).mockResolvedValue(TOUGH_RESULT)
  })

  it('renders the ASI budget and the available feat list on load', async () => {
    render(<FeatsPanel characterId={1} />)

    // ASI budget + the available Tough feat both render after the API loads.
    expect(await screen.findByText(/available to spend/i)).toBeInTheDocument()
    expect(screen.getByText('Tough')).toBeInTheDocument()

    // The panel fetched data for the right character.
    expect(vi.mocked(getCharacterFeats)).toHaveBeenCalledWith(1)
    expect(vi.mocked(getAvailableFeats)).toHaveBeenCalledWith(1)
  })

  it('spends an ASI to learn a simple feat end-to-end', async () => {
    let toughLearned = false
    vi.mocked(getCharacterFeats).mockImplementation(async () =>
      toughLearned ? AFTER_TOUGH : BEFORE,
    )
    vi.mocked(getAvailableFeats).mockImplementation(async () =>
      toughLearned ? [] : [TOUGH],
    )
    vi.mocked(learnFeat).mockImplementation(async () => {
      toughLearned = true
      return TOUGH_RESULT
    })
    const onChanged = vi.fn()

    render(<FeatsPanel characterId={1} onChanged={onChanged} />)

    await screen.findByText('Tough')

    // Open the confirm modal.
    fireEvent.click(await screen.findByRole('button', { name: /\+\s*Learn/i }))
    expect(await screen.findByText(/Learn:\s*Tough/i)).toBeInTheDocument()

    // Confirm — spends one ASI. Tough has no ability choice, so none is sent.
    fireEvent.click(screen.getByRole('button', { name: /Learn Feat/i }))

    await waitFor(() => {
      expect(vi.mocked(learnFeat)).toHaveBeenCalledTimes(1)
    })
    expect(vi.mocked(learnFeat)).toHaveBeenCalledWith(1, 'Tough', undefined)

    // Success view surfaces and the parent is notified to refresh.
    expect(await screen.findByText(SUCCESS('Tough'))).toBeInTheDocument()
    expect(onChanged).toHaveBeenCalledTimes(1)
  })

  it('forwards the default (first) ability for half-feats', async () => {
    let chosen = false
    vi.mocked(getCharacterFeats).mockImplementation(async () =>
      chosen
        ? charFeats(
            [
              {
                name: 'Athlete',
                description: ATHLETE.description,
                effects_applied: { ability_bonus: { strength: 1 } },
                learned_at_level: 4,
              },
            ],
            0,
            1,
          )
        : BEFORE,
    )
    vi.mocked(getAvailableFeats).mockImplementation(async () =>
      chosen ? [] : [ATHLETE],
    )
    vi.mocked(learnFeat).mockResolvedValue({
      ...TOUGH_RESULT,
      feat_name: 'Athlete',
      message: 'Athlete learned. Strength +1.',
      ability_changes: { strength: 1 },
    })

    render(<FeatsPanel characterId={1} />)

    await screen.findByText('Athlete')
    fireEvent.click(await screen.findByRole('button', { name: /\+\s*Learn/i }))

    // The ability picker is visible; the first choice (Strength) is
    // pre-selected, so confirm is enabled without an extra click.
    expect(
      await screen.findByText(/Choose an ability to increase/i),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Learn Feat/i })).toBeEnabled()

    fireEvent.click(screen.getByRole('button', { name: /Learn Feat/i }))

    await waitFor(() => {
      expect(vi.mocked(learnFeat)).toHaveBeenCalledTimes(1)
    })
    // Default first choice 'strength' is forwarded.
    expect(vi.mocked(learnFeat)).toHaveBeenCalledWith(1, 'Athlete', 'strength')
    expect(await screen.findByText(SUCCESS('Athlete'))).toBeInTheDocument()
  })

  it('lets the player switch the ability choice for a half-feat', async () => {
    let chosen = false
    vi.mocked(getCharacterFeats).mockImplementation(async () =>
      chosen
        ? charFeats(
            [
              {
                name: 'Athlete',
                description: ATHLETE.description,
                effects_applied: { ability_bonus: { dexterity: 1 } },
                learned_at_level: 4,
              },
            ],
            0,
            1,
          )
        : BEFORE,
    )
    vi.mocked(getAvailableFeats).mockImplementation(async () =>
      chosen ? [] : [ATHLETE],
    )
    vi.mocked(learnFeat).mockResolvedValue({
      ...TOUGH_RESULT,
      feat_name: 'Athlete',
      message: 'Athlete learned. Dexterity +1.',
      ability_changes: { dexterity: 1 },
    })

    render(<FeatsPanel characterId={1} />)

    await screen.findByText('Athlete')
    fireEvent.click(await screen.findByRole('button', { name: /\+\s*Learn/i }))
    await screen.findByText(/Choose an ability to increase/i)

    // Override the default (Strength) by picking Dexterity, then confirm.
    fireEvent.click(screen.getByRole('button', { name: 'Dexterity' }))
    fireEvent.click(screen.getByRole('button', { name: /Learn Feat/i }))

    await waitFor(() => {
      expect(vi.mocked(learnFeat)).toHaveBeenCalledTimes(1)
    })
    expect(vi.mocked(learnFeat)).toHaveBeenCalledWith(1, 'Athlete', 'dexterity')
    expect(await screen.findByText(SUCCESS('Athlete'))).toBeInTheDocument()
  })
})

describe('FeatsPanel — race prerequisite display', () => {
  const DWARVEN_FORTITUDE: FeatInfo = {
    ...TOUGH,
    name: 'Dwarven Fortitude',
    description: 'Increase your Constitution by 1. Dodge to spend a Hit Die.',
    ability_bonus_choices: ['constitution'],
    hp_per_level: 0,
    prerequisite: {
      min_level: 1,
      min_abilities: {},
      requires_caster: false,
      requires_class: null,
      requires_armor_proficiency: null,
      requires_race: ['dwarf'],
    },
    source: "Xanathar's Guide to Everything",
  }

  const ELVEN_ACCURACY: FeatInfo = {
    ...TOUGH,
    name: 'Elven Accuracy',
    description: 'Reroll one advantage die on attack rolls.',
    ability_bonus_choices: ['dexterity', 'intelligence', 'wisdom', 'charisma'],
    hp_per_level: 0,
    prerequisite: {
      min_level: 1,
      min_abilities: {},
      requires_caster: false,
      requires_class: null,
      requires_armor_proficiency: null,
      requires_race: ['elf', 'half-elf'],
    },
    source: "Xanathar's Guide to Everything",
  }

  beforeEach(() => {
    vi.mocked(listFeats).mockResolvedValue([DWARVEN_FORTITUDE, ELVEN_ACCURACY])
    vi.mocked(getCharacterFeats).mockResolvedValue(BEFORE)
    vi.mocked(getAvailableFeats).mockResolvedValue([DWARVEN_FORTITUDE, ELVEN_ACCURACY])
    vi.mocked(learnFeat).mockResolvedValue(TOUGH_RESULT)
  })

  it('shows the race requirement in the prerequisite text', async () => {
    render(<FeatsPanel characterId={1} />)

    // Dwarven Fortitude card renders; expand it to see the Requires line.
    const dwarfBtn = await screen.findByRole('button', { name: /Dwarven Fortitude/i })
    expect(dwarfBtn).toBeInTheDocument()
    fireEvent.click(dwarfBtn)

    // The expanded card shows "Requires: … Dwarf".
    expect(await screen.findByText(/Requires:.*Dwarf/i)).toBeInTheDocument()

    // Elven Accuracy lists both Elf and Half-Elf.
    const elfBtn = screen.getByRole('button', { name: /Elven Accuracy/i })
    fireEvent.click(elfBtn)
    expect(await screen.findByText(/Requires:.*Elf\s*\/\s*Half-elf/i)).toBeInTheDocument()
  })
})
