import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import VoicePanel from '../VoicePanel'
import {
  getTTSStatus,
  narrateLatest,
  synthesizeSpeech,
  listCachedAudio,
} from '../../stores/api'
import type { TTSStatus, TTSListResponse, CachedAudio, StoryEntry } from '../../types'

/* ------------------------------------------------------------------ *
 * Integration tests for the Voice (TTS) panel.
 *
 * The panel is a UI over the already-tested backend TTS API
 * (40 tests). These tests cover the panel's own behaviour: the
 * not-configured banner, the configured narrate-latest flow (with
 * narration), custom-text synthesis, and cached-narration list
 * rendering.
 * ------------------------------------------------------------------ */

vi.mock('../../stores/api', () => ({
  getTTSStatus: vi.fn(),
  narrateLatest: vi.fn(),
  synthesizeSpeech: vi.fn(),
  cachedAudioUrl: (gameId: number, audioId: string) =>
    `/api/game/${gameId}/tts/audio/${audioId}`,
  listCachedAudio: vi.fn(),
  deleteCachedAudio: vi.fn(),
}))

function configuredStatus(): TTSStatus {
  return {
    configured: true,
    provider: 'openai',
    model: 'tts-1',
    voice: 'alloy',
    format: 'mp3',
    speed: 1,
  }
}

function notConfiguredStatus(): TTSStatus {
  return {
    configured: false,
    provider: 'none',
    model: 'tts-1',
    voice: 'alloy',
    format: 'mp3',
    speed: 1,
  }
}

function emptyList(): TTSListResponse {
  return { audio: [], count: 0, configured: true }
}

function cachedAudio(): CachedAudio {
  return {
    id: 'abc123',
    label: 'Latest Narration',
    text: 'The dragon roars and swoops down upon the village.',
    voice: 'alloy',
    model: 'tts-1',
    format: 'mp3',
    speed: 1,
    size_bytes: 51200,
    timestamp: '2025-01-01T00:00:00',
  }
}

function listWithAudio(): TTSListResponse {
  return { audio: [cachedAudio()], count: 1, configured: true }
}

describe('VoicePanel', () => {
  beforeEach(() => {
    vi.mocked(getTTSStatus).mockResolvedValue(configuredStatus())
    vi.mocked(listCachedAudio).mockResolvedValue(emptyList())
    vi.mocked(narrateLatest).mockResolvedValue({
      audio: cachedAudio(),
      cached_count: 1,
    })
    vi.mocked(synthesizeSpeech).mockResolvedValue('blob:mock-url')
  })

  it('shows the not-configured banner when TTS is disabled', async () => {
    vi.mocked(getTTSStatus).mockResolvedValue(notConfiguredStatus())

    render(<VoicePanel gameId={1} />)

    expect(await screen.findByText(/not configured/i)).toBeInTheDocument()
    // The narrate button should be disabled.
    const narrateBtn = screen.getByRole('button', { name: /Narrate Latest/i })
    expect(narrateBtn).toBeDisabled()
  })

  it('shows provider info and enabled controls when configured', async () => {
    render(<VoicePanel gameId={1} />)

    // Provider info appears.
    expect(await screen.findByText(/openai/i)).toBeInTheDocument()
    // The narrate button is enabled.
    const narrateBtn = screen.getByRole('button', { name: /Narrate Latest/i })
    expect(narrateBtn).not.toBeDisabled()
  })

  it('narrates the latest entry and fires narration to the DM bubble', async () => {
    vi.mocked(listCachedAudio)
      .mockResolvedValueOnce(emptyList())
      .mockResolvedValueOnce(listWithAudio())
    const onNarration = vi.fn()

    render(<VoicePanel gameId={1} onNarration={onNarration} />)

    // Wait for status to load.
    await screen.findByText(/openai/i)

    // Click narrate latest.
    fireEvent.click(screen.getByRole('button', { name: /Narrate Latest/i }))

    // The API was called.
    await waitFor(() => expect(vi.mocked(narrateLatest)).toHaveBeenCalledWith(1))

    // Narration was fired.
    await waitFor(() => expect(onNarration).toHaveBeenCalledTimes(1))
    const entry = onNarration.mock.calls[0][0] as StoryEntry
    expect(entry.role).toBe('system')
    expect(entry.content).toMatch(/narration/i)
    expect(entry.timestamp).toBeTruthy()
  })

  it('synthesizes custom text via the one-shot Speak Text button', async () => {
    render(<VoicePanel gameId={1} />)

    await screen.findByText(/openai/i)

    // Type custom text.
    fireEvent.change(screen.getByPlaceholderText(/Type text to speak/i), {
      target: { value: 'A dramatic entrance.' },
    })

    // Click speak text.
    fireEvent.click(screen.getByRole('button', { name: /Speak Text/i }))

    await waitFor(() =>
      expect(vi.mocked(synthesizeSpeech)).toHaveBeenCalledWith(1, 'A dramatic entrance.'),
    )
  })

  it('renders the cached narrations list', async () => {
    vi.mocked(listCachedAudio).mockResolvedValue(listWithAudio())

    render(<VoicePanel gameId={1} />)

    // The list header shows the count.
    expect(await screen.findByText(/Cached Narrations \(1\)/)).toBeInTheDocument()
    // The narration label is visible.
    expect(screen.getByText(/Latest Narration/)).toBeInTheDocument()
    // The play button is present.
    expect(screen.getByRole('button', { name: /Play/i })).toBeInTheDocument()
  })

  it('shows an error when narration fails with a 503', async () => {
    vi.mocked(narrateLatest).mockRejectedValue({
      response: { data: { detail: 'Voice narration (TTS) is not configured.' } },
    })

    render(<VoicePanel gameId={1} />)

    await screen.findByText(/openai/i)
    fireEvent.click(screen.getByRole('button', { name: /Narrate Latest/i }))

    expect(await screen.findByText(/not configured/i)).toBeInTheDocument()
  })
})
