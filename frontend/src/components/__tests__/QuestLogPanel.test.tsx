import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import QuestLogPanel from '../QuestLogPanel'
import { listQuests, updateQuestStatus } from '../../stores/api'
import type { Quest, StoryEntry } from '../../types'

/* ------------------------------------------------------------------ *
 * Integration tests for the Quest Log panel.
 *
 * The panel is a UI over the already-tested backend quest API
 * (29 tests). These cover the panel's own behaviour: the empty
 * state, quest cards with objective/giver/reward, status filtering,
 * marking a quest complete (with narration), reopening, the filtered-
 * empty state, and error handling.
 * ------------------------------------------------------------------ */

vi.mock('../../stores/api', () => ({
  listQuests: vi.fn(),
  getQuest: vi.fn(),
  updateQuestStatus: vi.fn(),
}))

function makeQuest(overrides: Partial<Quest> = {}): Quest {
  return {
    id: 1,
    title: 'Retrieve the Lost Amulet',
    description: 'The amulet was stolen by goblins hiding in Emberdeep.',
    status: 'active',
    giver: 'Sage Aldric',
    objective: 'Recover the Amulet of Dawn from the goblin camp',
    reward_hint: 'Gold and a healing potion',
    created_at: '2026-07-13T10:00:00',
    updated_at: '2026-07-13T10:00:00',
    ...overrides,
  }
}

describe('QuestLogPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(listQuests).mockResolvedValue({ quests: [] })
  })

  it('shows the empty-state banner when there are no quests', async () => {
    render(<QuestLogPanel gameId={1} />)

    expect(await screen.findByText(/No quests yet/i)).toBeInTheDocument()
  })

  it('renders a quest card with its objective, giver, and reward', async () => {
    vi.mocked(listQuests).mockResolvedValue({ quests: [makeQuest()] })

    render(<QuestLogPanel gameId={1} />)

    // Objective is always visible.
    expect(await screen.findByText(/Recover the Amulet/i)).toBeInTheDocument()
    expect(screen.getByText(/Sage Aldric/i)).toBeInTheDocument()

    // Expand to reveal description + reward.
    fireEvent.click(screen.getByRole('button', { name: /Retrieve the Lost Amulet/i }))

    expect(
      await screen.findByText(/stolen by goblins/i),
    ).toBeInTheDocument()
    expect(screen.getByText(/Gold and a healing potion/i)).toBeInTheDocument()
  })

  it('marks a quest complete via PATCH and narrates to the DM bubble', async () => {
    const onNarration = vi.fn()
    vi.mocked(listQuests).mockResolvedValue({ quests: [makeQuest()] })
    vi.mocked(updateQuestStatus).mockResolvedValue(makeQuest({ status: 'completed' }))

    render(<QuestLogPanel gameId={1} onNarration={onNarration} />)

    // Expand the quest card to reveal the action buttons.
    await screen.findByText(/Recover the Amulet/i)
    fireEvent.click(screen.getByRole('button', { name: /Retrieve the Lost Amulet/i }))

    fireEvent.click(screen.getByRole('button', { name: /Mark Complete/i }))

    await waitFor(() =>
      expect(vi.mocked(updateQuestStatus)).toHaveBeenCalledWith(1, 1, 'completed'),
    )
    await waitFor(() => expect(onNarration).toHaveBeenCalledTimes(1))
    const entry = onNarration.mock.calls[0][0] as StoryEntry
    expect(entry.role).toBe('system')
    expect(entry.content).toMatch(/Quest completed/i)
  })

  it('reopens a completed quest and narrates', async () => {
    const onNarration = vi.fn()
    vi.mocked(listQuests).mockResolvedValue({
      quests: [makeQuest({ status: 'completed' })],
    })
    vi.mocked(updateQuestStatus).mockResolvedValue(makeQuest({ status: 'active' }))

    render(<QuestLogPanel gameId={1} onNarration={onNarration} />)

    await screen.findByText(/Recover the Amulet/i)
    fireEvent.click(screen.getByRole('button', { name: /Retrieve the Lost Amulet/i }))

    fireEvent.click(screen.getByRole('button', { name: /Reopen/i }))

    await waitFor(() =>
      expect(vi.mocked(updateQuestStatus)).toHaveBeenCalledWith(1, 1, 'active'),
    )
    await waitFor(() => expect(onNarration).toHaveBeenCalledTimes(1))
    expect(onNarration.mock.calls[0][0].content).toMatch(/reopened/i)
  })

  it('filters quests by status using the tabs', async () => {
    vi.mocked(listQuests).mockResolvedValue({
      quests: [
        makeQuest({ id: 1, title: 'Active Task', status: 'active' }),
        makeQuest({ id: 2, title: 'Done Deed', status: 'completed' }),
      ],
    })

    render(<QuestLogPanel gameId={1} />)

    // Both visible initially (All tab active).
    expect(await screen.findByText('Active Task')).toBeInTheDocument()
    expect(screen.getByText('Done Deed')).toBeInTheDocument()

    // Switch to the Completed filter (filter tabs show a "(count)" suffix;
    // the quest status badge does not, so this uniquely targets the tab).
    fireEvent.click(screen.getByRole('button', { name: /Completed \(\d+\)/ }))
    expect(screen.queryByText('Active Task')).not.toBeInTheDocument()
    expect(screen.getByText('Done Deed')).toBeInTheDocument()

    // The filtered-empty message does NOT show (there is a completed quest).
    expect(screen.queryByText(/No completed quests/i)).not.toBeInTheDocument()

    // Switch to Failed → filtered-empty message appears.
    fireEvent.click(screen.getByRole('button', { name: /Failed \(\d+\)/ }))
    expect(await screen.findByText(/No failed quests/i)).toBeInTheDocument()
  })

  it('shows a refresh button that re-reads the quest log', async () => {
    vi.mocked(listQuests).mockResolvedValue({ quests: [] })

    render(<QuestLogPanel gameId={1} />)

    await screen.findByText(/No quests yet/i)

    fireEvent.click(screen.getByRole('button', { name: /Refresh/i }))

    await waitFor(() => expect(vi.mocked(listQuests).mock.calls.length).toBeGreaterThanOrEqual(2))
  })

  it('surfaces an error when the status update fails', async () => {
    vi.mocked(listQuests).mockResolvedValue({ quests: [makeQuest()] })
    vi.mocked(updateQuestStatus).mockRejectedValue({
      response: { data: { detail: 'Quest not found' } },
    })

    render(<QuestLogPanel gameId={1} />)

    await screen.findByText(/Recover the Amulet/i)
    fireEvent.click(screen.getByRole('button', { name: /Retrieve the Lost Amulet/i }))
    fireEvent.click(screen.getByRole('button', { name: /Mark Complete/i }))

    expect(await screen.findByText(/Quest not found/i)).toBeInTheDocument()
  })
})
