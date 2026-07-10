import { useCallback, useEffect, useState } from 'react'
import {
  getSocialNPCs, rollSocialReaction, influenceNPC, insightNPC,
} from '../stores/api'
import type { SocialNPC, SocialAttitude, StoryEntry } from '../types'

/* ------------------------------------------------------------------ *
 * Social Interaction panel — DnD 5e DMG ch.4/ch.8.
 *
 * A console over the social-interaction API: the third pillar of DnD 5e
 * (Combat, Exploration, Social). Resolve the three interaction layers:
 *   1. Reaction roll (2d6 + CHA) → an NPC's initial disposition.
 *   2. Influence check (Persuasion/Intimidation/Deception/Performance)
 *      → shift the NPC's attitude one step (improve / hold / worsen).
 *   3. Insight check → detect whether an NPC is lying.
 *
 * All outcomes sync to the world_state NPC relationship (attitude + trust)
 * and log narration to the DM story bubble.
 * ------------------------------------------------------------------ */

const ATTITUDE_STYLES: Record<SocialAttitude, string> = {
  hostile: 'bg-blood-900/50 border-blood-700/50 text-blood-300',
  unfriendly: 'bg-amber-900/40 border-amber-700/50 text-amber-300',
  indifferent: 'bg-parchment-800/50 border-parchment-700 text-parchment-300',
  friendly: 'bg-leaf-900/40 border-leaf-700/50 text-leaf-300',
  helpful: 'bg-arcane-900/40 border-arcane-700/50 text-arcane-200',
}

const ATTITUDE_ICON: Record<SocialAttitude, string> = {
  hostile: '😠',
  unfriendly: '😕',
  indifferent: '😐',
  friendly: '🙂',
  helpful: '🤝',
}

const SKILLS = [
  { id: 'persuasion', label: 'Persuasion', icon: '💬' },
  { id: 'intimidation', label: 'Intimidation', icon: '😤' },
  { id: 'deception', label: 'Deception', icon: '🤥' },
  { id: 'performance', label: 'Performance', icon: '🎭' },
]

interface SocialPanelProps {
  gameId: number
  onChanged?: () => void | Promise<void>
  /** Narrate a social action into the DM story bubble. */
  onNarration?: (entry: StoryEntry) => void
}

export default function SocialPanel({ gameId, onChanged, onNarration }: SocialPanelProps) {
  const [npcs, setNpcs] = useState<SocialNPC[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{ narrative: string; tone: 'good' | 'bad' | 'neutral' } | null>(null)

  // Reaction inputs
  const [reactName, setReactName] = useState('')
  const [reactDice, setReactDice] = useState<[number, number] | ''>('')

  // Influence inputs
  const [infName, setInfName] = useState('')
  const [infSkill, setInfSkill] = useState('persuasion')
  const [infRoll, setInfRoll] = useState<number | ''>('')

  // Insight inputs
  const [insName, setInsName] = useState('')
  const [insRoll, setInsRoll] = useState<number | ''>('')
  const [npcDeception, setNpcDeception] = useState<number | ''>('')

  const refresh = useCallback(async () => {
    try {
      const list = await getSocialNPCs(gameId)
      setNpcs(list)
      setError(null)
    } catch {
      setError('Failed to load NPC relationships.')
    } finally {
      setLoading(false)
    }
  }, [gameId])

  useEffect(() => {
    setLoading(true)
    refresh()
  }, [refresh])

  const showFlash = (narrative: string, tone: 'good' | 'bad' | 'neutral') => {
    setResult({ narrative, tone })
    if (narrative) window.setTimeout(() => setResult(null), 6000)
  }

  const narrate = (content: string) => {
    if (onNarration && content) {
      onNarration({ role: 'system', content, timestamp: new Date().toISOString() })
    }
  }

  // --- Reaction roll -----------------------------------------------------
  const handleReaction = async () => {
    if (!reactName.trim()) {
      setError('Enter an NPC name to roll a reaction.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const r = await rollSocialReaction(
        gameId,
        reactName.trim(),
        undefined,
        Array.isArray(reactDice) ? reactDice : undefined,
      )
      showFlash(r.description, r.attitude === 'hostile' || r.attitude === 'unfriendly' ? 'bad' : 'good')
      narrate(`${ATTITUDE_ICON[r.attitude]} ${reactName.trim()}: ${r.description}`)
      await refresh()
      if (onChanged) await onChanged()
    } catch {
      setError('Could not roll the reaction.')
    } finally {
      setBusy(false)
    }
  }

  // --- Influence check ---------------------------------------------------
  const handleInfluence = async () => {
    if (!infName.trim()) {
      setError('Enter an NPC name to influence.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const r = await influenceNPC(gameId, infName.trim(), infSkill, {
        roll: infRoll === '' ? undefined : infRoll,
      })
      const tone: 'good' | 'bad' | 'neutral' = r.auto_success
        ? 'neutral'
        : r.success ? 'good'
        : r.worsened ? 'bad'
        : 'neutral'
      showFlash(r.description, tone)
      narrate(`${infSkill} vs ${infName.trim()}: ${r.description}`)
      await refresh()
      if (onChanged) await onChanged()
    } catch {
      setError('Could not attempt the influence check.')
    } finally {
      setBusy(false)
    }
  }

  // --- Insight check -----------------------------------------------------
  const handleInsight = async () => {
    if (!insName.trim()) {
      setError('Enter an NPC name to read for deception.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const r = await insightNPC(gameId, insName.trim(), {
        npcDeceptionTotal: npcDeception === '' ? undefined : npcDeception,
        // If no deception given, fall back to a passive 10 default is handled
        // by the server requiring one — pass 10 as a sensible passive default.
        ...(npcDeception === '' ? { npcPassiveDeception: 10 } : {}),
        insightRoll: insRoll === '' ? undefined : insRoll,
      })
      showFlash(r.description, r.detected ? 'good' : 'neutral')
      narrate(`Insight vs ${insName.trim()}: ${r.description}`)
      if (onChanged) await onChanged()
    } catch {
      setError('Provide the NPC’s Deception total to make an Insight check.')
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return <div className="text-parchment-400 animate-pulse text-center py-8">Reading the room…</div>
  }

  return (
    <div className="space-y-4">
      {/* Result flash */}
      {result && result.narrative && (
        <div className={`rounded-lg p-3 border text-sm animate-fade-in ${
          result.tone === 'good'
            ? 'bg-leaf-900/40 border-leaf-700 text-leaf-200'
            : result.tone === 'bad'
            ? 'bg-blood-900/50 border-blood-600 text-blood-200'
            : 'bg-arcane-900/40 border-arcane-700 text-parchment-200'
        }`}>
          {result.narrative}
        </div>
      )}
      {error && <div className="text-blood-500 text-sm">{error}</div>}

      {/* Known NPCs */}
      <div>
        <div className="flex items-baseline justify-between mb-2">
          <h3 className="text-xs text-parchment-500 font-semibold uppercase tracking-wide">
            Known NPCs
          </h3>
          <span className="text-xs text-parchment-600">{npcs.length} tracked</span>
        </div>
        {npcs.length === 0 ? (
          <p className="text-xs text-parchment-600 italic px-1">
            No NPCs tracked yet. Roll a reaction for someone you’ve just met.
          </p>
        ) : (
          <div className="space-y-2">
            {npcs.map((npc) => (
              <div key={npc.npc_name} className="rounded-lg p-3 border bg-parchment-900/60 border-parchment-700/40">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <span className="text-sm font-semibold text-parchment-200 font-fantasy">
                    {npc.npc_name}
                  </span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded border uppercase tracking-wide ${ATTITUDE_STYLES[npc.attitude]}`}>
                    {ATTITUDE_ICON[npc.attitude]} {npc.attitude}
                  </span>
                  <span className="text-[10px] text-parchment-500">
                    trust {npc.trust}
                  </span>
                  {npc.influence_dc > 0 && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded border bg-gold-900/30 border-gold-700/40 text-gold-300">
                      improve DC {npc.influence_dc} → {npc.target_attitude}
                    </span>
                  )}
                </div>
                <p className="text-[11px] text-parchment-500">{npc.summary}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Reaction roll */}
      <div className="bg-parchment-900/60 rounded-lg p-3 border border-parchment-700/30">
        <h3 className="text-xs text-parchment-500 font-semibold uppercase tracking-wide mb-2">
          🎲 Reaction Roll
        </h3>
        <p className="text-[11px] text-parchment-600 mb-2">
          Roll 2d6 + Charisma to establish a newly-met NPC’s disposition.
        </p>
        <div className="grid grid-cols-2 gap-2 mb-2">
          <label className="text-[11px] text-parchment-400">
            NPC name
            <input
              type="text"
              value={reactName}
              onChange={(e) => setReactName(e.target.value)}
              disabled={busy}
              placeholder="e.g. Innkeeper Bren"
              className="w-full mt-0.5 bg-parchment-950/60 border border-parchment-700/50 rounded px-2 py-1 text-parchment-200 text-sm"
            />
          </label>
          <label className="text-[11px] text-parchment-400">
            Dice (optional: d1,d2)
            <input
              type="text"
              value={Array.isArray(reactDice) ? reactDice.join(',') : reactDice}
              onChange={(e) => {
                const parts = e.target.value.split(',').map((s) => parseInt(s.trim(), 10))
                if (parts.length === 2 && parts.every((n) => !isNaN(n))) {
                  setReactDice([parts[0], parts[1]] as [number, number])
                } else if (e.target.value === '') {
                  setReactDice('')
                }
              }}
              disabled={busy}
              placeholder="random"
              className="w-full mt-0.5 bg-parchment-950/60 border border-parchment-700/50 rounded px-2 py-1 text-parchment-200 text-sm"
            />
          </label>
        </div>
        <button
          className="w-full px-3 py-1.5 rounded text-sm font-medium bg-arcane-800/60 hover:bg-arcane-700/60 border border-arcane-600/40 text-arcane-200 disabled:opacity-40"
          onClick={handleReaction}
          disabled={busy || !reactName.trim()}
        >
          Roll Reaction
        </button>
      </div>

      {/* Influence check */}
      <div className="bg-parchment-900/60 rounded-lg p-3 border border-parchment-700/30">
        <h3 className="text-xs text-parchment-500 font-semibold uppercase tracking-wide mb-2">
          💬 Influence Check
        </h3>
        <p className="text-[11px] text-parchment-600 mb-2">
          A Charisma check to shift an NPC’s attitude one step. Success improves;
          failure by 5+ or a nat 1 worsens.
        </p>
        <div className="grid grid-cols-2 gap-2 mb-2">
          <label className="text-[11px] text-parchment-400">
            NPC name
            <input
              type="text"
              value={infName}
              onChange={(e) => setInfName(e.target.value)}
              disabled={busy}
              placeholder="e.g. Captain Aldric"
              className="w-full mt-0.5 bg-parchment-950/60 border border-parchment-700/50 rounded px-2 py-1 text-parchment-200 text-sm"
            />
          </label>
          <label className="text-[11px] text-parchment-400">
            d20 roll (optional)
            <input
              type="number"
              min={1}
              max={20}
              value={infRoll}
              onChange={(e) => setInfRoll(e.target.value === '' ? '' : Number(e.target.value))}
              disabled={busy}
              placeholder="auto"
              className="w-full mt-0.5 bg-parchment-950/60 border border-parchment-700/50 rounded px-2 py-1 text-parchment-200 text-sm"
            />
          </label>
        </div>
        <div className="flex flex-wrap gap-1.5 mb-2">
          {SKILLS.map((s) => (
            <button
              key={s.id}
              onClick={() => setInfSkill(s.id)}
              disabled={busy}
              className={`px-2 py-1 rounded text-[11px] border transition-colors ${
                infSkill === s.id
                  ? 'bg-gold-900/40 border-gold-600/50 text-gold-200'
                  : 'bg-parchment-800/40 border-parchment-700/30 text-parchment-400 hover:bg-parchment-800/70'
              }`}
            >
              {s.icon} {s.label}
            </button>
          ))}
        </div>
        <button
          className="w-full px-3 py-1.5 rounded text-sm font-medium bg-leaf-800/60 hover:bg-leaf-700/60 border border-leaf-600/40 text-leaf-200 disabled:opacity-40"
          onClick={handleInfluence}
          disabled={busy || !infName.trim()}
        >
          Attempt Influence
        </button>
      </div>

      {/* Insight check */}
      <div className="bg-parchment-900/60 rounded-lg p-3 border border-parchment-700/30">
        <h3 className="text-xs text-parchment-500 font-semibold uppercase tracking-wide mb-2">
          👁️ Insight vs Deception
        </h3>
        <p className="text-[11px] text-parchment-600 mb-2">
          Read an NPC to detect a lie. Enter the NPC’s Deception total (rolled or passive).
        </p>
        <div className="grid grid-cols-3 gap-2 mb-2">
          <label className="text-[11px] text-parchment-400">
            NPC name
            <input
              type="text"
              value={insName}
              onChange={(e) => setInsName(e.target.value)}
              disabled={busy}
              placeholder="e.g. Shady Merchant"
              className="w-full mt-0.5 bg-parchment-950/60 border border-parchment-700/50 rounded px-2 py-1 text-parchment-200 text-sm"
            />
          </label>
          <label className="text-[11px] text-parchment-400">
            NPC Deception
            <input
              type="number"
              min={1}
              value={npcDeception}
              onChange={(e) => setNpcDeception(e.target.value === '' ? '' : Number(e.target.value))}
              disabled={busy}
              placeholder="e.g. 14"
              className="w-full mt-0.5 bg-parchment-950/60 border border-parchment-700/50 rounded px-2 py-1 text-parchment-200 text-sm"
            />
          </label>
          <label className="text-[11px] text-parchment-400">
            d20 roll (optional)
            <input
              type="number"
              min={1}
              max={20}
              value={insRoll}
              onChange={(e) => setInsRoll(e.target.value === '' ? '' : Number(e.target.value))}
              disabled={busy}
              placeholder="auto"
              className="w-full mt-0.5 bg-parchment-950/60 border border-parchment-700/50 rounded px-2 py-1 text-parchment-200 text-sm"
            />
          </label>
        </div>
        <button
          className="w-full px-3 py-1.5 rounded text-sm font-medium bg-arcane-800/60 hover:bg-arcane-700/60 border border-arcane-600/40 text-arcane-200 disabled:opacity-40"
          onClick={handleInsight}
          disabled={busy || !insName.trim()}
        >
          Read Intent
        </button>
      </div>
    </div>
  )
}
