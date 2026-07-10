import { useCallback, useEffect, useState } from 'react'
import {
  getImageStatus,
  generateSceneImage,
  generatePortraitImage,
  getGameImages,
  deleteGameImage,
} from '../stores/api'
import type {
  ImageGenerationStatus,
  GeneratedImage,
  ImageGallery,
  StoryEntry,
} from '../types'

/* ------------------------------------------------------------------ *
 * Image Panel — AI-generated scene illustrations & NPC portraits.
 *
 * A UI over the provider-agnostic image-generation API
 * (`/api/game/{id}/images`). When no image provider is configured
 * (IMAGE_API_KEY not set), the panel shows a graceful "not configured"
 * message with setup instructions. When configured, the player can:
 *
 *  • Generate a scene image from the latest DM narration — the backend
 *    auto-builds a visual prompt from the story context + character info.
 *  • Generate an NPC/character portrait by name + description.
 *  • Browse a gallery of all previously generated images (cached in
 *    game_state, survives save/load).
 *  • Delete images from the gallery.
 *
 * Generated images narrate into the DM story bubble so the player sees
 * the result inline.
 * ------------------------------------------------------------------ */

interface ImagePanelProps {
  gameId: number
  onNarration?: (entry: StoryEntry) => void
  onChanged?: () => void | Promise<void>
}

export default function ImagePanel({ gameId, onNarration, onChanged }: ImagePanelProps) {
  const [status, setStatus] = useState<ImageGenerationStatus | null>(null)
  const [gallery, setGallery] = useState<ImageGallery | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Portrait form state
  const [portraitName, setPortraitName] = useState('')
  const [portraitDesc, setPortraitDesc] = useState('')
  const [portraitRace, setPortraitRace] = useState('')
  const [portraitClass, setPortraitClass] = useState('')

  // Selected image for detail view
  const [selected, setSelected] = useState<GeneratedImage | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [s, g] = await Promise.all([
        getImageStatus(gameId),
        getGameImages(gameId),
      ])
      setStatus(s)
      setGallery(g)
    } catch {
      // Non-fatal — panel still renders with defaults
    } finally {
      setLoading(false)
    }
  }, [gameId])

  useEffect(() => {
    refresh()
  }, [refresh])

  const narrate = useCallback(
    (img: GeneratedImage) => {
      if (!onNarration) return
      const kind = img.type === 'scene' ? 'Scene image' : `Portrait of ${img.label}`
      onNarration({
        role: 'system',
        content: `🖼️ ${kind} generated.`,
        timestamp: new Date().toISOString(),
      })
    },
    [onNarration],
  )

  const extractError = (err: unknown, fallback: string): string => {
    if (err && typeof err === 'object' && 'response' in err) {
      const resp = (err as { response?: { data?: { detail?: string } } }).response
      return resp?.data?.detail || fallback
    }
    return fallback
  }

  const handleScene = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await generateSceneImage(gameId)
      narrate(result.image)
      setSelected(result.image)
      await refresh()
      onChanged?.()
    } catch (err: unknown) {
      setError(extractError(err, 'Failed to generate scene image.'))
    } finally {
      setBusy(false)
    }
  }, [gameId, narrate, refresh, onChanged])

  const handlePortrait = useCallback(async () => {
    if (!portraitName.trim()) {
      setError('Enter a name for the portrait subject.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const result = await generatePortraitImage(
        gameId,
        portraitName.trim(),
        portraitDesc.trim(),
        portraitRace.trim(),
        portraitClass.trim(),
      )
      narrate(result.image)
      setSelected(result.image)
      await refresh()
      onChanged?.()
    } catch (err: unknown) {
      setError(extractError(err, 'Failed to generate portrait.'))
    } finally {
      setBusy(false)
    }
  }, [
    gameId,
    portraitName,
    portraitDesc,
    portraitRace,
    portraitClass,
    narrate,
    refresh,
    onChanged,
  ])

  const handleDelete = useCallback(
    async (index: number) => {
      try {
        await deleteGameImage(gameId, index)
        setSelected(null)
        await refresh()
      } catch {
        setError('Failed to delete image.')
      }
    },
    [gameId, refresh],
  )

  if (loading) {
    return (
      <div className="text-center py-8 text-parchment-400">
        Loading image studio…
      </div>
    )
  }

  const configured = status?.configured ?? false

  return (
    <div className="space-y-4">
      {/* Configuration status banner */}
      {!configured && (
        <div className="rounded-lg border border-amber-600/40 bg-amber-900/20 p-4 text-sm text-amber-200">
          <p className="font-semibold mb-1">🖼️ Image generation is not configured.</p>
          <p className="text-amber-300/80">
            Set <code className="bg-amber-900/40 px-1 rounded">IMAGE_API_KEY</code> in
            your <code className="bg-amber-900/40 px-1 rounded">.env</code> to enable
            AI-generated scene illustrations and NPC portraits. The system uses any
            OpenAI-compatible image API (DALL-E 3 by default).
          </p>
        </div>
      )}

      {configured && (
        <div className="flex items-center gap-2 text-xs text-parchment-400">
          <span className="inline-block w-2 h-2 rounded-full bg-green-500" />
          <span>
            Provider: <strong className="text-parchment-200">{status?.provider}</strong>
            {' · '}Model: <strong className="text-parchment-200">{status?.model}</strong>
            {' · '}{status?.size} · {status?.quality}
          </span>
        </div>
      )}

      {/* Error flash */}
      {error && (
        <div className="rounded-lg border border-blood-600/40 bg-blood-900/20 p-3 text-sm text-blood-200">
          {error}
        </div>
      )}

      {/* Scene generation */}
      <div className="rounded-lg border border-arcane-700/40 bg-arcane-900/20 p-4">
        <h3 className="font-fantasy text-lg text-arcane-200 mb-1">🏛️ Scene Illustration</h3>
        <p className="text-sm text-parchment-400 mb-3">
          Generate an illustration of the current scene from the latest DM narration.
          The prompt is built automatically from your character, location, and the most
          recent story entry.
        </p>
        <button
          className="btn-primary text-sm px-4 py-2 disabled:opacity-40 disabled:cursor-not-allowed"
          onClick={handleScene}
          disabled={!configured || busy}
        >
          {busy ? 'Generating…' : '🎨 Generate Scene'}
        </button>
      </div>

      {/* Portrait generation */}
      <div className="rounded-lg border border-gold-700/40 bg-gold-900/10 p-4">
        <h3 className="font-fantasy text-lg text-gold-300 mb-1">🧑 NPC / Character Portrait</h3>
        <p className="text-sm text-parchment-400 mb-3">
          Generate a portrait for an NPC or character by name and description.
        </p>
        <div className="space-y-2">
          <div className="flex gap-2">
            <input
              className="input flex-1"
              placeholder="Name (e.g. Gandalf)"
              value={portraitName}
              onChange={(e) => setPortraitName(e.target.value)}
            />
            <input
              className="input w-28"
              placeholder="Race"
              value={portraitRace}
              onChange={(e) => setPortraitRace(e.target.value)}
            />
            <input
              className="input w-28"
              placeholder="Class"
              value={portraitClass}
              onChange={(e) => setPortraitClass(e.target.value)}
            />
          </div>
          <input
            className="input w-full"
            placeholder="Visual description — appearance, clothing, expression…"
            value={portraitDesc}
            onChange={(e) => setPortraitDesc(e.target.value)}
          />
          <button
            className="btn-primary text-sm px-4 py-2 disabled:opacity-40 disabled:cursor-not-allowed"
            onClick={handlePortrait}
            disabled={!configured || busy || !portraitName.trim()}
          >
            {busy ? 'Generating…' : '🖌️ Generate Portrait'}
          </button>
        </div>
      </div>

      {/* Detail view */}
      {selected && (
        <div className="rounded-lg border border-parchment-700/40 bg-parchment-900/30 p-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-fantasy text-lg text-parchment-200">
              {selected.type === 'scene' ? '🏛️' : '🧑'} {selected.label}
            </h3>
            <button
              className="text-parchment-400 hover:text-parchment-200 text-lg leading-none"
              onClick={() => setSelected(null)}
            >
              ×
            </button>
          </div>
          <img
            src={selected.url}
            alt={selected.label}
            className="w-full rounded-lg border border-parchment-700/30"
          />
          {selected.revised_prompt && (
            <p className="mt-2 text-xs text-parchment-500 italic">
              {selected.revised_prompt}
            </p>
          )}
          <p className="mt-1 text-xs text-parchment-600">
            {selected.model} · {selected.size} · {selected.quality}
          </p>
        </div>
      )}

      {/* Gallery */}
      {gallery && gallery.count > 0 && (
        <div>
          <h3 className="font-fantasy text-lg text-parchment-200 mb-2">
            📸 Gallery ({gallery.count})
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {gallery.images.map((img, i) => (
              <div
                key={i}
                className="group relative rounded-lg border border-parchment-700/30 overflow-hidden cursor-pointer hover:border-arcane-500/50 transition-colors"
                onClick={() => setSelected(img)}
              >
                <img
                  src={img.url}
                  alt={img.label}
                  className="w-full aspect-square object-cover"
                />
                <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-1.5">
                  <p className="text-xs text-parchment-200 truncate">
                    {img.type === 'scene' ? '🏛️' : '🧑'} {img.label}
                  </p>
                </div>
                <button
                  className="absolute top-1 right-1 w-5 h-5 rounded-full bg-black/60 text-parchment-200 text-xs opacity-0 group-hover:opacity-100 transition-opacity hover:bg-blood-700"
                  onClick={(e) => {
                    e.stopPropagation()
                    handleDelete(i)
                  }}
                  title="Delete image"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {configured && gallery && gallery.count === 0 && !selected && (
        <p className="text-center text-sm text-parchment-500 py-4">
          No images yet. Generate a scene or portrait to populate the gallery.
        </p>
      )}
    </div>
  )
}
