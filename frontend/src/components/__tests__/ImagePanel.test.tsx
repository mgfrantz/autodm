import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import ImagePanel from '../ImagePanel'
import {
  getImageStatus,
  generateSceneImage,
  generatePortraitImage,
  getGameImages,
} from '../../stores/api'
import type { ImageGenerationStatus, ImageGallery, StoryEntry } from '../../types'

/* ------------------------------------------------------------------ *
 * Integration tests for the Image panel.
 *
 * The panel is a UI over the already-tested backend images API
 * (36 tests). These tests cover the panel's own behaviour: the
 * not-configured banner, the configured scene-generation flow (with
 * narration), portrait generation, and gallery rendering.
 * ------------------------------------------------------------------ */

vi.mock('../../stores/api', () => ({
  getImageStatus: vi.fn(),
  generateSceneImage: vi.fn(),
  generatePortraitImage: vi.fn(),
  getGameImages: vi.fn(),
  deleteGameImage: vi.fn(),
}))

function configuredStatus(): ImageGenerationStatus {
  return {
    configured: true,
    provider: 'openai',
    model: 'dall-e-3',
    size: '1024x1024',
    quality: 'standard',
  }
}

function notConfiguredStatus(): ImageGenerationStatus {
  return {
    configured: false,
    provider: 'none',
    model: 'dall-e-3',
    size: '1024x1024',
    quality: 'standard',
  }
}

function emptyGallery(): ImageGallery {
  return { images: [], count: 0, configured: true }
}

function galleryWithScene(): ImageGallery {
  return {
    images: [
      {
        type: 'scene',
        label: 'Burning Village',
        prompt: 'A dragon over a village',
        revised_prompt: 'A dramatic dragon scene',
        url: 'https://example.com/scene.png',
        model: 'dall-e-3',
        size: '1024x1024',
        quality: 'standard',
        timestamp: '2025-01-01T00:00:00',
      },
    ],
    count: 1,
    configured: true,
  }
}

describe('ImagePanel', () => {
  beforeEach(() => {
    vi.mocked(getImageStatus).mockResolvedValue(configuredStatus())
    vi.mocked(getGameImages).mockResolvedValue(emptyGallery())
    vi.mocked(generateSceneImage).mockResolvedValue({
      image: galleryWithScene().images[0],
      cached_count: 1,
    })
    vi.mocked(generatePortraitImage).mockResolvedValue({
      image: {
        type: 'portrait',
        label: 'Gandalf',
        prompt: 'Portrait of Gandalf',
        revised_prompt: null,
        url: 'https://example.com/portrait.png',
        model: 'dall-e-3',
        size: '1024x1024',
        quality: 'standard',
        timestamp: '2025-01-01T00:00:00',
      },
      cached_count: 1,
    })
  })

  it('shows the not-configured banner when image generation is disabled', async () => {
    vi.mocked(getImageStatus).mockResolvedValue(notConfiguredStatus())

    render(<ImagePanel gameId={1} />)

    expect(await screen.findByText(/not configured/i)).toBeInTheDocument()
    // The generate button should be disabled.
    const sceneBtn = screen.getByRole('button', { name: /Generate Scene/i })
    expect(sceneBtn).toBeDisabled()
  })

  it('shows provider info and enabled controls when configured', async () => {
    render(<ImagePanel gameId={1} />)

    // Provider info appears.
    expect(await screen.findByText(/openai/i)).toBeInTheDocument()
    // The generate button is enabled.
    const sceneBtn = screen.getByRole('button', { name: /Generate Scene/i })
    expect(sceneBtn).not.toBeDisabled()
  })

  it('generates a scene image and narrates to the DM bubble', async () => {
    const onNarration = vi.fn()

    render(<ImagePanel gameId={1} onNarration={onNarration} />)

    // Wait for status to load.
    await screen.findByText(/openai/i)

    // Click generate scene.
    fireEvent.click(screen.getByRole('button', { name: /Generate Scene/i }))

    // The API was called.
    await waitFor(() => expect(vi.mocked(generateSceneImage)).toHaveBeenCalledWith(1))

    // Narration was fired.
    await waitFor(() => expect(onNarration).toHaveBeenCalledTimes(1))
    const entry = onNarration.mock.calls[0][0] as StoryEntry
    expect(entry.role).toBe('system')
    expect(entry.content).toMatch(/scene image/i)
    expect(entry.timestamp).toBeTruthy()
  })

  it('generates a portrait from the name + description form', async () => {
    render(<ImagePanel gameId={1} />)

    await screen.findByText(/openai/i)

    // Fill in the portrait form.
    fireEvent.change(screen.getByPlaceholderText(/Gandalf/i), {
      target: { value: 'Gandalf' },
    })
    fireEvent.change(screen.getByPlaceholderText(/Visual description/i), {
      target: { value: 'An old wizard with a grey beard' },
    })

    // Click generate portrait.
    fireEvent.click(screen.getByRole('button', { name: /Generate Portrait/i }))

    await waitFor(() =>
      expect(vi.mocked(generatePortraitImage)).toHaveBeenCalledWith(
        1,
        'Gandalf',
        'An old wizard with a grey beard',
        '',
        '',
      ),
    )
  })

  it('renders the gallery with cached images', async () => {
    vi.mocked(getGameImages).mockResolvedValue(galleryWithScene())

    render(<ImagePanel gameId={1} />)

    // The gallery header shows the count.
    expect(await screen.findByText(/Gallery \(1\)/)).toBeInTheDocument()
    // The image label is visible.
    expect(screen.getByText(/Burning Village/)).toBeInTheDocument()
  })

  it('shows an error when scene generation fails with a 503', async () => {
    vi.mocked(generateSceneImage).mockRejectedValue({
      response: { data: { detail: 'Image generation is not configured.' } },
    })

    render(<ImagePanel gameId={1} />)

    await screen.findByText(/openai/i)
    fireEvent.click(screen.getByRole('button', { name: /Generate Scene/i }))

    expect(await screen.findByText(/not configured/i)).toBeInTheDocument()
  })
})
