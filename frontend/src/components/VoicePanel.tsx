import { useCallback, useEffect, useRef, useState } from 'react'
import {
  getTTSStatus,
  narrateLatest,
  synthesizeSpeech,
  cachedAudioUrl,
  listCachedAudio,
  deleteCachedAudio,
} from '../stores/api'
import { useGameStore } from '../stores/gameStore'
import type {
  TTSStatus,
  TTSListResponse,
  CachedAudio,
  StoryEntry,
} from '../types'

/* ------------------------------------------------------------------ *
 * Voice Panel — AI-generated voice narration (TTS DM).
 *
 * A UI over the provider-agnostic TTS API (`/api/game/{id}/tts`). When no
 * TTS provider is configured (TTS_API_KEY not set), the panel shows a
 * graceful "not configured" message with setup instructions. When
 * configured, the player can:
 *
 *  • Narrate the latest DM narration aloud — the backend synthesizes the
 *    most recent DM story entry, caches it, and returns metadata.
 *  • Speak arbitrary custom text (one-shot, not cached).
 *  • Replay any previously synthesized narration (cached in game_state,
 *    survives save/load) via an HTML5 <audio> player.
 *  • Delete narrations from the cache.
 *
 * Generated narrations narrate into the DM story bubble so the player sees
 * the result inline.
 * ------------------------------------------------------------------ */

interface VoicePanelProps {
  gameId: number
  onNarration?: (entry: StoryEntry) => void
  onChanged?: () => void | Promise<void>
}

export default function VoicePanel({ gameId, onNarration, onChanged }: VoicePanelProps) {
  const [status, setStatus] = useState<TTSStatus | null>(null)
  const [list, setList] = useState<TTSListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Custom-text one-shot synthesis state
  const [customText, setCustomText] = useState('')
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)

  // Currently-playing cached narration
  const [playingId, setPlayingId] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  // Persisted auto-narrate preference (shared with GameView so it can fire
  // even when this overlay is closed).
  const autoNarrate = useGameStore((s) => s.autoNarrate)
  const setAutoNarrate = useGameStore((s) => s.setAutoNarrate)

  const refresh = useCallback(async () => {
    try {
      const [s, l] = await Promise.all([
        getTTSStatus(gameId),
        listCachedAudio(gameId),
      ])
      setStatus(s)
      setList(l)
    } catch {
      // Non-fatal — panel still renders with defaults
    } finally {
      setLoading(false)
    }
  }, [gameId])

  useEffect(() => {
    refresh()
  }, [refresh])

  // Revoke any one-shot preview object URL on unmount / change.
  // Guard: some environments (e.g. jsdom) don't implement revokeObjectURL.
  useEffect(() => {
    return () => {
      if (previewUrl && typeof URL !== 'undefined' && typeof URL.revokeObjectURL === 'function') {
        URL.revokeObjectURL(previewUrl)
      }
    }
  }, [previewUrl])

  const narrate = useCallback(
    (audio: CachedAudio) => {
      if (!onNarration) return
      onNarration({
        role: 'system',
        content: `🔊 Narration generated (${audio.voice}, ${Math.round(audio.size_bytes / 1024)} KB).`,
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

  const handleNarrate = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await narrateLatest(gameId)
      narrate(result.audio)
      await refresh()
      onChanged?.()
    } catch (err: unknown) {
      setError(extractError(err, 'Failed to narrate the latest narration.'))
    } finally {
      setBusy(false)
    }
  }, [gameId, narrate, refresh, onChanged])

  const handleSpeak = useCallback(async () => {
    if (!customText.trim()) {
      setError('Enter some text to speak.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      // Revoke a previous preview URL before creating a new one.
      if (previewUrl && typeof URL !== 'undefined' && typeof URL.revokeObjectURL === 'function') {
        URL.revokeObjectURL(previewUrl)
      }
      const url = await synthesizeSpeech(gameId, customText.trim())
      setPreviewUrl(url)
    } catch (err: unknown) {
      setError(extractError(err, 'Failed to synthesize speech.'))
    } finally {
      setBusy(false)
    }
  }, [gameId, customText, previewUrl])

  const playCached = useCallback(
    (audio: CachedAudio) => {
      // Stop the previous audio if switching tracks.
      if (audioRef.current) {
        audioRef.current.pause()
      }
      setPlayingId(audio.id)
      // Defer play until the <audio> src updates.
      setTimeout(() => {
        audioRef.current?.play().catch(() => {
          /* autoplay can be blocked — user can press play manually */
        })
      }, 0)
    },
    [],
  )

  const stopPlayback = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
    }
    setPlayingId(null)
  }, [])

  const handleDelete = useCallback(
    async (audioId: string) => {
      if (playingId === audioId) {
        stopPlayback()
      }
      try {
        await deleteCachedAudio(gameId, audioId)
        await refresh()
      } catch {
        setError('Failed to delete narration.')
      }
    },
    [gameId, playingId, stopPlayback, refresh],
  )

  if (loading) {
    return (
      <div className="text-center py-8 text-parchment-400">
        Loading voice narration…
      </div>
    )
  }

  const configured = status?.configured ?? false

  return (
    <div className="space-y-4">
      {/* Hidden audio element drives cached playback */}
      {playingId && (
        <audio
          ref={audioRef}
          src={cachedAudioUrl(gameId, playingId)}
          onEnded={stopPlayback}
          className="hidden"
        />
      )}

      {/* Configuration status banner */}
      {!configured && (
        <div className="rounded-lg border border-amber-600/40 bg-amber-900/20 p-4 text-sm text-amber-200">
          <p className="font-semibold mb-1">🔊 Voice narration is not configured.</p>
          <p className="text-amber-300/80">
            Set <code className="bg-amber-900/40 px-1 rounded">TTS_API_KEY</code> in
            your <code className="bg-amber-900/40 px-1 rounded">.env</code> to enable
            AI-generated DM voice narration. The system uses any OpenAI-compatible
            TTS API (tts-1 by default; works with local/self-hosted endpoints via{' '}
            <code className="bg-amber-900/40 px-1 rounded">TTS_BASE_URL</code>).
          </p>
        </div>
      )}

      {configured && (
        <div className="flex items-center gap-2 text-xs text-parchment-400">
          <span className="inline-block w-2 h-2 rounded-full bg-green-500" />
          <span>
            Provider: <strong className="text-parchment-200">{status?.provider}</strong>
            {' · '}Model: <strong className="text-parchment-200">{status?.model}</strong>
            {' · '}Voice: <strong className="text-parchment-200">{status?.voice}</strong>
            {' · '}{status?.format} · {status?.speed}× speed
          </span>
        </div>
      )}

      {/* Auto-narrate toggle — speaks each new DM narration automatically. */}
      {configured && (
        <label className="flex items-center gap-3 rounded-lg border border-arcane-700/40 bg-arcane-900/20 p-3 cursor-pointer select-none">
          <input
            type="checkbox"
            className="h-4 w-4 rounded accent-arcane-400"
            checked={autoNarrate}
            onChange={(e) => setAutoNarrate(e.target.checked)}
          />
          <span className="flex-1">
            <span className="block text-sm font-semibold text-arcane-200">
              🔈 Auto-narrate new DM messages
            </span>
            <span className="block text-xs text-parchment-500">
              {autoNarrate
                ? 'On — every new DM narration is spoken aloud automatically as it arrives.'
                : 'Off — speak narrations manually with the “Narrate Latest” button.'}
            </span>
          </span>
        </label>
      )}

      {/* Error flash */}
      {error && (
        <div className="rounded-lg border border-blood-600/40 bg-blood-900/20 p-3 text-sm text-blood-200">
          {error}
        </div>
      )}

      {/* Narrate latest DM entry */}
      <div className="rounded-lg border border-arcane-700/40 bg-arcane-900/20 p-4">
        <h3 className="font-fantasy text-lg text-arcane-200 mb-1">🗣️ Narrate Latest</h3>
        <p className="text-sm text-parchment-400 mb-3">
          Speak the most recent DM narration aloud. The audio is synthesized, cached,
          and added to the list below for replay.
        </p>
        <button
          className="btn-primary text-sm px-4 py-2 disabled:opacity-40 disabled:cursor-not-allowed"
          onClick={handleNarrate}
          disabled={!configured || busy}
        >
          {busy ? 'Synthesizing…' : '🔊 Narrate Latest'}
        </button>
      </div>

      {/* Speak custom text (one-shot) */}
      <div className="rounded-lg border border-gold-700/40 bg-gold-900/10 p-4">
        <h3 className="font-fantasy text-lg text-gold-300 mb-1">💬 Speak Custom Text</h3>
        <p className="text-sm text-parchment-400 mb-3">
          Type any text and hear it spoken aloud (one-shot, not cached).
        </p>
        <textarea
          className="input w-full mb-2"
          rows={3}
          placeholder="Type text to speak aloud…"
          value={customText}
          onChange={(e) => setCustomText(e.target.value)}
        />
        <div className="flex flex-wrap items-center gap-2">
          <button
            className="btn-primary text-sm px-4 py-2 disabled:opacity-40 disabled:cursor-not-allowed"
            onClick={handleSpeak}
            disabled={!configured || busy || !customText.trim()}
          >
            {busy ? 'Synthesizing…' : '🎙️ Speak Text'}
          </button>
          {previewUrl && (
            <audio controls src={previewUrl} className="h-9 flex-1 min-w-[200px]" />
          )}
        </div>
      </div>

      {/* Cached narrations */}
      {configured && (
        <div>
          <h3 className="font-fantasy text-lg text-parchment-200 mb-2">
            🎵 Cached Narrations ({list?.count ?? 0})
          </h3>
          {list && list.count > 0 ? (
            <ul className="space-y-2">
              {list.audio.map((audio) => (
                <li
                  key={audio.id}
                  className="rounded-lg border border-parchment-700/30 bg-parchment-900/20 p-3"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-parchment-200 truncate">
                        {audio.label}
                      </p>
                      <p className="text-xs text-parchment-500 line-clamp-2 mt-0.5">
                        {audio.text}
                      </p>
                      <p className="text-xs text-parchment-600 mt-1">
                        {audio.voice} · {audio.model} · {Math.round(audio.size_bytes / 1024)} KB
                      </p>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      {playingId === audio.id ? (
                        <button
                          className="text-xs px-2 py-1 rounded bg-blood-800/60 text-parchment-200 hover:bg-blood-700"
                          onClick={stopPlayback}
                          title="Stop playback"
                        >
                          ⏹ Stop
                        </button>
                      ) : (
                        <button
                          className="text-xs px-2 py-1 rounded bg-arcane-800/60 text-parchment-200 hover:bg-arcane-700"
                          onClick={() => playCached(audio)}
                          title="Play narration"
                        >
                          ▶ Play
                        </button>
                      )}
                      <button
                        className="w-6 h-6 rounded-full bg-black/40 text-parchment-300 text-xs hover:bg-blood-700 hover:text-parchment-100"
                        onClick={() => handleDelete(audio.id)}
                        title="Delete narration"
                      >
                        ×
                      </button>
                    </div>
                  </div>
                  {/* Inline player for the currently-selected narration */}
                  {playingId === audio.id && (
                    <audio
                      controls
                      autoPlay
                      src={cachedAudioUrl(gameId, audio.id)}
                      onEnded={stopPlayback}
                      className="w-full mt-2 h-9"
                    />
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-center text-sm text-parchment-500 py-4">
              No narrations yet. Use “Narrate Latest” to generate and cache one.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
