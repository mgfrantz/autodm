import { useState, useEffect, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getGameState, streamStartAdventure, streamPlayerAction, getCombatState, makeAttack, nextTurn, getWorldMap, travelToRegion, createSaveSlot, listSaveSlots, loadSaveSlot, deleteSaveSlot, getRestInfo, shortRest, longRest, getEquipmentCombatStats, getCharacterFeats } from '../stores/api'
import { useGameStore } from '../stores/gameStore'
import type { StoryEntry, Attack, WorldMapData, SaveSlotSummary, RestInfo, CombatActionResult, EquipmentCombatStats, CharacterFeatsResponse } from '../types'
import CombatTracker from '../components/CombatTracker'
import WorldMap from '../components/WorldMap'
import SkillsPanel from '../components/SkillsPanel'
import ShopPanel from '../components/ShopPanel'
import InventoryPanel from '../components/InventoryPanel'
import BackgroundPanel from '../components/BackgroundPanel'
import AlignmentPanel from '../components/AlignmentPanel'
import LanguagesPanel from '../components/LanguagesPanel'
import EnvironmentPanel from '../components/EnvironmentPanel'
import CombatActionsPanel from '../components/CombatActionsPanel'
import TrapsPanel from '../components/TrapsPanel'
import SocialPanel from '../components/SocialPanel'
import DowntimePanel from '../components/DowntimePanel'
import SpellsPanel from '../components/SpellsPanel'
import FeatsPanel from '../components/FeatsPanel'
import SubclassPanel from '../components/SubclassPanel'
import ExhaustionPanel from '../components/ExhaustionPanel'
import SurvivalPanel from '../components/SurvivalPanel'
import MountsPanel from '../components/MountsPanel'
import SavingThrowsPanel from '../components/SavingThrowsPanel'
import ImagePanel from '../components/ImagePanel'

// Display labels for the canonical nine alignment ids (for the sidebar).
const ALIGNMENT_LABELS: Record<string, string> = {
  lawful_good: 'Lawful Good',
  neutral_good: 'Neutral Good',
  chaotic_good: 'Chaotic Good',
  lawful_neutral: 'Lawful Neutral',
  neutral: 'True Neutral',
  chaotic_neutral: 'Chaotic Neutral',
  lawful_evil: 'Lawful Evil',
  neutral_evil: 'Neutral Evil',
  chaotic_evil: 'Chaotic Evil',
}

export default function GameView() {
  const { gameId } = useParams<{ gameId: string }>()
  const gid = parseInt(gameId || '0')

  const { gameState, story, combatState, setGameState, setCombatState, addToStory, setStory, loading, setLoading, error, setError } = useGameStore()
  const [actionInput, setActionInput] = useState('')
  const [started, setStarted] = useState(false)
  const [streamingText, setStreamingText] = useState('')
  const [showMap, setShowMap] = useState(false)
  const [worldMap, setWorldMap] = useState<WorldMapData | null>(null)
  const [mapLoading, setMapLoading] = useState(false)
  const [showSaves, setShowSaves] = useState(false)
  const [saveSlots, setSaveSlots] = useState<SaveSlotSummary[]>([])
  const [newSaveName, setNewSaveName] = useState('')
  const [saveBusy, setSaveBusy] = useState(false)
  const [showRest, setShowRest] = useState(false)
  const [restInfo, setRestInfo] = useState<RestInfo | null>(null)
  const [restBusy, setRestBusy] = useState(false)
  const [restResult, setRestResult] = useState<string | null>(null)
  const [showSkills, setShowSkills] = useState(false)
  const [showShop, setShowShop] = useState(false)
  const [showInventory, setShowInventory] = useState(false)
  const [showBackground, setShowBackground] = useState(false)
  const [showAlignment, setShowAlignment] = useState(false)
  const [showLanguages, setShowLanguages] = useState(false)
  const [showEnvironment, setShowEnvironment] = useState(false)
  const [showActions, setShowActions] = useState(false)
  const [showSpells, setShowSpells] = useState(false)
  const [showFeats, setShowFeats] = useState(false)
  const [showSubclass, setShowSubclass] = useState(false)
  const [showExhaustion, setShowExhaustion] = useState(false)
  const [showSurvival, setShowSurvival] = useState(false)
  const [showSavingThrows, setShowSavingThrows] = useState(false)
  const [showTraps, setShowTraps] = useState(false)
  const [showSocial, setShowSocial] = useState(false)
  const [showDowntime, setShowDowntime] = useState(false)
  const [showMounts, setShowMounts] = useState(false)
  const [showImages, setShowImages] = useState(false)
  const [equipmentStats, setEquipmentStats] = useState<EquipmentCombatStats | null>(null)
  const [featStatus, setFeatStatus] = useState<CharacterFeatsResponse | null>(null)
  const storyEndRef = useRef<HTMLDivElement>(null)

  // Load game state and combat state
  useEffect(() => {
    const loadState = async () => {
      try {
        const state = await getGameState(gid)
        setGameState(state)
        
        // Check for combat state
        const combat = await getCombatState(gid)
        setCombatState(combat)
        
        if (state.story_log.length === 0 && !started) {
          handleStart()
        } else {
          state.story_log.forEach((entry: StoryEntry) => addToStory(entry))
        }
      } catch {
        setError('Failed to load game')
      }
    }
    
    loadState()
  }, [gid])

  // Auto-scroll to bottom
  useEffect(() => {
    storyEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [story, streamingText])

  // Fetch equipment-derived combat stats (AC, weapon attacks) once the
  // character is known. These reflect the character's equipped gear.
  useEffect(() => {
    if (!gameState?.character?.id) return
    getEquipmentCombatStats(gameState.character.id)
      .then(setEquipmentStats)
      .catch(() => { /* equipment stats are informational; ignore failures */ })
  }, [gameState?.character?.id])

  // Re-fetch equipment stats after inventory changes (equip/unequip/use) so
  // the sidebar AC + weapon reflect the new loadout.
  const refreshEquipmentStats = async () => {
    if (!gameState?.character?.id) return
    try {
      const stats = await getEquipmentCombatStats(gameState.character.id)
      setEquipmentStats(stats)
    } catch {
      /* informational */
    }
  }

  // Fetch the feat/ASI summary (learned-feat count + ASIs available) so the
  // sidebar can surface it. ASI availability changes with level-ups and when a
  // feat is learned, so this is refreshed after feats panel changes too.
  const refreshFeatStatus = async () => {
    if (!gameState?.character?.id) return
    try {
      const fs = await getCharacterFeats(gameState.character.id)
      setFeatStatus(fs)
    } catch {
      /* informational */
    }
  }

  // Fetch feat/ASI summary once the character is known, and again whenever the
  // character levels up (ASI availability is gated by level milestones).
  useEffect(() => {
    if (!gameState?.character?.id) return
    refreshFeatStatus()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gameState?.character?.id, gameState?.character?.level])

  const handleStart = async () => {
    setLoading(true)
    setStreamingText('')
    try {
      await streamStartAdventure(
        gid,
        (chunk) => setStreamingText((prev) => prev + chunk),
        () => {},
      )
      setStreamingText((final) => {
        addToStory({ role: 'dm', content: final, timestamp: new Date().toISOString() })
        return ''
      })
      setStarted(true)
    } catch (err) {
      setError('Failed to start adventure')
    }
    setLoading(false)
  }

  const handleAction = async () => {
    if (!actionInput.trim() || loading) return
    const action = actionInput.trim()
    setActionInput('')
    addToStory({ role: 'player', content: action, timestamp: new Date().toISOString() })
    setLoading(true)
    setStreamingText('')
    try {
      await streamPlayerAction(
        gid,
        action,
        (chunk) => setStreamingText((prev) => prev + chunk),
        async (combatActive) => {
          // Check combat state after DM responds
          if (combatActive) {
            const combat = await getCombatState(gid)
            setCombatState(combat)
          }
        },
      )
      setStreamingText((final) => {
        addToStory({ role: 'dm', content: final, timestamp: new Date().toISOString() })
        return ''
      })
      // Refresh combat state after action
      const combat = await getCombatState(gid)
      setCombatState(combat)
    } catch (err) {
      setError('The DM falters... (error processing action)')
    }
    setLoading(false)
  }

  const handleAttack = async (attackerId: string, targetId: string, attack: Attack) => {
    try {
      const result = await makeAttack(gid, attackerId, targetId, attack.name)
      
      // Add combat result to story
      addToStory({ 
        role: 'system', 
        content: result.result.description,
        timestamp: new Date().toISOString() 
      })
      
      // Update combat state
      setCombatState({
        in_combat: result.combat_active,
        is_active: result.combat_active,
        winner: result.winner,
        encounter: result.encounter,
      })
      
      // If combat ended, add a message
      if (!result.combat_active && result.winner) {
        addToStory({
          role: 'system',
          content: result.winner === 'player' 
            ? '🎉 Victory! You have defeated all enemies!' 
            : '💀 You have been defeated...',
          timestamp: new Date().toISOString()
        })
      }
    } catch (err) {
      setError('Attack failed')
    }
  }

  const handleNextTurn = async () => {
    try {
      const result = await nextTurn(gid)
      
      // Update combat state
      const combat = await getCombatState(gid)
      setCombatState(combat)
      
      // If combat ended, add a message
      if (result.combat_over && result.winner) {
        addToStory({
          role: 'system',
          content: result.winner === 'player' 
            ? '🎉 Victory! You have defeated all enemies!' 
            : '💀 You have been defeated...',
          timestamp: new Date().toISOString()
        })
      }
    } catch (err) {
      setError('Failed to advance turn')
    }
  }

  const isPlayerTurn = combatState?.encounter?.combatants.find(c => c.id === combatState.current_turn_id)?.side === 'player'
  const inCombat = combatState?.in_combat && combatState?.is_active

  // Handle a combat action result (Grapple, Shove, Dodge, etc.): update the
  // story log and refresh combat state from the returned encounter.
  const handleCombatAction = (result: CombatActionResult) => {
    addToStory({
      role: 'system',
      content: result.result.description,
      timestamp: new Date().toISOString(),
    })
    setCombatState({
      in_combat: result.combat_active,
      is_active: result.combat_active,
      winner: result.winner,
      encounter: result.encounter,
    })
    if (!result.combat_active && result.winner) {
      addToStory({
        role: 'system',
        content: result.winner === 'player'
          ? '🎉 Victory! You have defeated all enemies!'
          : '💀 You have been defeated...',
        timestamp: new Date().toISOString(),
      })
    }
  }

  const hpColor = (pct: number) =>
    pct > 50 ? 'bg-leaf-600' : pct > 25 ? 'bg-amber-600' : 'bg-blood-600'

  const handleOpenMap = async () => {
    setShowMap(true)
    setMapLoading(true)
    try {
      const mapData = await getWorldMap(gid)
      setWorldMap(mapData)
    } catch {
      setError('Failed to load map')
      setShowMap(false)
    }
    setMapLoading(false)
  }

  const handleTravel = async (regionId: string) => {
    if (mapLoading) return
    setMapLoading(true)
    try {
      const result = await travelToRegion(gid, regionId)
      // Refresh the map + game state.
      const [mapData, state] = await Promise.all([getWorldMap(gid), getGameState(gid)])
      setWorldMap(mapData)
      setGameState(state)
      // Surface the travel outcome in the story log.
      if (result.success) {
        addToStory({
          role: 'system',
          content: result.encounter_triggered
            ? `🗺️ ${result.message}${result.encounter_danger ? ` (${result.encounter_danger})` : ''}`
            : `🗺️ ${result.message}`,
          timestamp: new Date().toISOString(),
        })
      } else {
        setError(result.message)
      }
    } catch {
      setError('Travel failed')
    }
    setMapLoading(false)
  }

  const refreshSaves = async () => {
    try {
      const slots = await listSaveSlots(gid)
      setSaveSlots(slots)
    } catch {
      setError('Failed to load saves')
    }
  }

  const handleOpenSaves = async () => {
    setShowSaves(true)
    await refreshSaves()
  }

  const handleCreateSave = async () => {
    const name = newSaveName.trim() || `Save ${new Date().toLocaleString()}`
    setSaveBusy(true)
    try {
      await createSaveSlot(gid, name)
      setNewSaveName('')
      await refreshSaves()
    } catch {
      setError('Failed to create save')
    }
    setSaveBusy(false)
  }

  const handleLoadSave = async (slotId: number) => {
    setSaveBusy(true)
    try {
      await loadSaveSlot(gid, slotId)
      // Reload the full game + combat state after restoring.
      const [state, combat] = await Promise.all([getGameState(gid), getCombatState(gid)])
      setGameState(state)
      setCombatState(combat)
      // Reset the story panel with the restored log.
      setStory([...state.story_log])
      setShowSaves(false)
      addToStory({ role: 'system', content: '💾 Game restored from save.', timestamp: new Date().toISOString() })
    } catch {
      setError('Failed to load save')
    }
    setSaveBusy(false)
  }

  const handleDeleteSave = async (slotId: number) => {
    setSaveBusy(true)
    try {
      await deleteSaveSlot(gid, slotId)
      await refreshSaves()
    } catch {
      setError('Failed to delete save')
    }
    setSaveBusy(false)
  }

  const handleOpenRest = async () => {
    setShowRest(true)
    setRestResult(null)
    try {
      const info = await getRestInfo(gid)
      setRestInfo(info)
    } catch {
      setError('Failed to load rest info')
    }
  }

  const refreshAfterRest = async () => {
    const [state, info] = await Promise.all([getGameState(gid), getRestInfo(gid)])
    setGameState(state)
    setRestInfo(info)
  }

  const handleShortRest = async () => {
    if (restBusy) return
    setRestBusy(true)
    setRestResult(null)
    try {
      const result = await shortRest(gid)
      await refreshAfterRest()
      if (result.success) {
        const rollSummary = result.rolls
          .map((r) => `d${r.faces}: ${r.roll}${r.modifier >= 0 ? '+' : ''}${r.modifier}=${r.total}`)
          .join(', ')
        setRestResult(`✦ ${result.message} (${rollSummary})`)
        addToStory({ role: 'system', content: `campfire 🔥 Short rest — ${result.message}`, timestamp: new Date().toISOString() })
      } else {
        setRestResult(result.message)
      }
    } catch {
      setError('Short rest failed')
    }
    setRestBusy(false)
  }

  const handleLongRest = async () => {
    if (restBusy) return
    setRestBusy(true)
    setRestResult(null)
    try {
      const result = await longRest(gid)
      await refreshAfterRest()
      setRestResult(`✦ ${result.message}`)
      addToStory({ role: 'system', content: `🌙 Long rest — ${result.message}`, timestamp: new Date().toISOString() })
    } catch {
      setError('Long rest failed')
    }
    setRestBusy(false)
  }

  if (!gameState) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-parchment-400 text-xl animate-pulse">Loading adventure...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex flex-col lg:flex-row max-w-7xl mx-auto p-2 sm:p-4 gap-4 view-enter">
      {/* Main Story Panel */}
      <div className={`flex flex-col ${inCombat ? 'lg:flex-[2]' : 'flex-1'}`}>
        {/* Header */}
        <div className="flex items-center justify-between mb-4 gap-2">
          <Link to="/" className="text-parchment-400 hover:text-parchment-200 text-sm shrink-0">
            ← Leave
          </Link>
          <h1 className="font-fantasy text-lg sm:text-xl text-parchment-300 text-center flex-1 min-w-0 truncate">
            {gameState.world.name}
          </h1>
          <div className="flex gap-2 shrink-0">
            <button
              className="btn-primary text-sm px-3 py-1.5"
              onClick={() => setShowSkills(true)}
              title="View skills & roll checks"
            >
              📜 <span className="hidden sm:inline">Skills</span>
            </button>
            <button
              className="btn-primary text-sm px-3 py-1.5"
              onClick={() => setShowSavingThrows(true)}
              title="View saving throw proficiencies & roll saves (feat-granted saves badged)"
            >
              🛡️ <span className="hidden sm:inline">Saves</span>
            </button>
            <button
              className="btn-primary text-sm px-3 py-1.5"
              onClick={() => setShowSpells(true)}
              title="View spellbook, cast spells, prepare & learn magic"
            >
              🔮 <span className="hidden sm:inline">Spells</span>
            </button>
            <button
              className="btn-primary text-sm px-3 py-1.5"
              onClick={() => setShowFeats(true)}
              title="View learned feats, ASI status & learn available feats"
            >
              🏆 <span className="hidden sm:inline">Feats</span>
            </button>
            <button
              className="btn-primary text-sm px-3 py-1.5"
              onClick={() => setShowSubclass(true)}
              title="View your subclass (archetype) & feature timeline, or choose an archetype"
            >
              ⚔️ <span className="hidden sm:inline">Subclass</span>
            </button>
            <button
              className="btn-primary text-sm px-3 py-1.5"
              onClick={() => setShowExhaustion(true)}
              title="View exhaustion level & effects, or adjust (hazards/recovery)"
            >
              🥵 <span className="hidden sm:inline">Exhaustion</span>
            </button>
            <button
              className="btn-primary text-sm px-3 py-1.5"
              onClick={() => setShowSurvival(true)}
              title="Track food & water (starvation/dehydration) and resolve a survival day"
            >
              🍖 <span className="hidden sm:inline">Survival</span>
            </button>
            <button
              className="btn-primary text-sm px-3 py-1.5"
              onClick={() => setShowTraps(true)}
              title="Place, detect, disarm & trigger traps (DMG ch.5)"
            >
              🪤 <span className="hidden sm:inline">Traps</span>
            </button>
            <button
              className="btn-primary text-sm px-3 py-1.5"
              onClick={() => setShowSocial(true)}
              title="Reaction rolls, influence checks & insight (DMG ch.4)"
            >
              💬 <span className="hidden sm:inline">Social</span>
            </button>
            <button
              className="btn-primary text-sm px-3 py-1.5"
              onClick={() => setShowDowntime(true)}
              title="Between-adventures activities: carouse, crime, gamble, craft, train (PHB ch.8 / XGE ch.2)"
            >
              ⏳ <span className="hidden sm:inline">Downtime</span>
            </button>
            <button
              className="btn-primary text-sm px-3 py-1.5"
              onClick={() => setShowMounts(true)}
              title="Acquire, ride & manage mounts and vehicles (mounted travel + combat, PHB ch.5/8/9)"
            >
              🐎 <span className="hidden sm:inline">Mounts</span>
            </button>
            <button
              className="btn-primary text-sm px-3 py-1.5"
              onClick={() => setShowImages(true)}
              title="AI-generated scene illustrations & NPC portraits (provider-agnostic image API)"
            >
              🖼️ <span className="hidden sm:inline">Images</span>
            </button>
            <button
              className="btn-primary text-sm px-3 py-1.5"
              onClick={() => setShowBackground(true)}
              title="View or change background & claim starting gear"
            >
              🎭 <span className="hidden sm:inline">Origin</span>
            </button>
            <button
              className="btn-primary text-sm px-3 py-1.5"
              onClick={() => setShowAlignment(true)}
              title="View or change alignment (3×3 grid with relationship preview)"
            >
              ⚖️ <span className="hidden sm:inline">Alignment</span>
            </button>
            <button
              className="btn-primary text-sm px-3 py-1.5"
              onClick={() => setShowLanguages(true)}
              title="View or change known languages (racial/background grants + extra choices)"
            >
              🗣️ <span className="hidden sm:inline">Tongues</span>
            </button>
            <button
              className="btn-primary text-sm px-3 py-1.5"
              onClick={() => setShowEnvironment(true)}
              title="View or change weather, lighting, terrain & temperature (live combat-modifier preview)"
            >
              🌤️ <span className="hidden sm:inline">Scene</span>
            </button>
            <button
              className="btn-primary text-sm px-3 py-1.5"
              onClick={() => setShowInventory(true)}
              title="Manage inventory & equipment"
            >
              🎒 <span className="hidden sm:inline">Inventory</span>
            </button>
            <button
              className="btn-primary text-sm px-3 py-1.5"
              onClick={() => setShowShop(true)}
              disabled={inCombat}
              title={inCombat ? 'Cannot trade during combat' : 'Visit the market & trade'}
            >
              🛍️ <span className="hidden sm:inline">Shop</span>
            </button>
            <button
              className="btn-primary text-sm px-3 py-1.5"
              onClick={handleOpenSaves}
              title="Save or load game"
            >
              💾 <span className="hidden sm:inline">Save</span>
            </button>
            <button
              className="btn-primary text-sm px-3 py-1.5"
              onClick={handleOpenRest}
              disabled={inCombat}
              title={inCombat ? 'Cannot rest during combat' : 'Short or long rest'}
            >
              💤 <span className="hidden sm:inline">Rest</span>
            </button>
            <button
              className="btn-primary text-sm px-3 py-1.5"
              onClick={handleOpenMap}
              disabled={inCombat}
              title={inCombat ? 'Cannot travel during combat' : 'Open the world map'}
            >
              🗺️ <span className="hidden sm:inline">Map</span>
            </button>
          </div>
        </div>

        {/* Story Log */}
        <div className="panel flex-1 overflow-y-auto mb-4 min-h-[400px] max-h-[60vh]">
          <div className="space-y-4">
            {story.map((entry, i) => (
              <div
                key={i}
                className={`rounded-lg p-4 animate-slide-up ${
                  entry.role === 'dm'
                    ? 'bg-parchment-900/60 border-l-4 border-arcane-500'
                    : entry.role === 'system'
                    ? 'bg-parchment-900/60 border-l-4 border-amber-500'
                    : 'bg-blood-700/30 border-l-4 border-blood-500 ml-8'
                }`}
              >
                <div className="text-xs text-parchment-500 mb-1 font-semibold uppercase">
                  {entry.role === 'dm' ? '🗡️ Dungeon Master' : entry.role === 'system' ? '⚙️ System' : '🧑 Player'}
                </div>
                <div className="text-parchment-200 whitespace-pre-wrap leading-relaxed">
                  {entry.content}
                </div>
              </div>
            ))}
            {/* Live-streaming DM narration */}
            {streamingText && (
              <div className="rounded-lg p-4 bg-parchment-900/60 border-l-4 border-arcane-500">
                <div className="text-xs text-parchment-500 mb-1 font-semibold uppercase">
                  🗡️ Dungeon Master
                  <span className="ml-2 text-arcane-400 animate-pulse">typing...</span>
                </div>
                <div className="text-parchment-200 whitespace-pre-wrap leading-relaxed">
                  {streamingText}
                  <span className="inline-block w-2 h-4 ml-0.5 bg-arcane-400 animate-pulse align-middle" />
                </div>
              </div>
            )}
            {loading && !streamingText && (
              <div className="text-parchment-400 animate-pulse text-center py-4">
                🎲 The DM considers your actions...
              </div>
            )}
            <div ref={storyEndRef} />
          </div>
        </div>

        {/* Action Input - Disabled during combat */}
        {!inCombat && (
          <div className="panel">
            {error && (
              <div className="text-blood-500 text-sm mb-2">{error}</div>
            )}
            <div className="flex gap-2">
              <input
                className="input-field flex-1"
                value={actionInput}
                onChange={(e) => setActionInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAction()}
                placeholder="What do you do? (e.g., 'I examine the door', 'I attack the goblin', 'I talk to the innkeeper')"
                disabled={loading}
              />
              <button
                className="btn-primary px-8"
                onClick={handleAction}
                disabled={loading || !actionInput.trim()}
              >
                Act
              </button>
            </div>
            {/* Quick Actions */}
            <div className="flex gap-2 mt-2 flex-wrap">
              {['Look around', 'Check inventory', 'Check my stats'].map((q) => (
                <button
                  key={q}
                  onClick={() => setActionInput(q)}
                  className="text-xs bg-parchment-700 hover:bg-parchment-600 text-parchment-300 px-3 py-1 rounded-full transition-all duration-200 hover:-translate-y-0.5 active:scale-95"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Combat indicator */}
        {inCombat && (
          <div className="panel bg-blood-900/30 border border-blood-500 animate-scale-in">
            <div className="flex items-center justify-between gap-3">
              <div className="text-center text-parchment-200 font-semibold animate-glow-pulse flex-1">
                ⚔️ COMBAT IN PROGRESS ⚔️
              </div>
              {isPlayerTurn && combatState?.encounter && (
                <button
                  className="btn-primary text-sm px-3 py-1.5 shrink-0"
                  onClick={() => setShowActions(true)}
                  title="Grapple, Shove, Dodge, Dash, Disengage, Help, and more"
                >
                  🎯 <span className="hidden sm:inline">Actions</span>
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Right Sidebar */}
      <div className="lg:w-80 space-y-4">
        {/* Character Info */}
        <div className="panel">
          <h2 className="font-fantasy text-lg text-parchment-200 mb-3">
            {gameState.character.name}
          </h2>
          <div className="text-parchment-400 text-sm mb-4">
            Level {gameState.character.level} {gameState.character.race} {gameState.character.char_class}
            {gameState.character.background && (
              <span className="text-parchment-500"> · {gameState.character.background}</span>
            )}
            {gameState.character.alignment && (
              <span className="text-parchment-500"> · {ALIGNMENT_LABELS[gameState.character.alignment] ?? gameState.character.alignment}</span>
            )}
          </div>

          {/* HP Bar */}
          <div className="mb-3">
            <div className="flex justify-between text-xs text-parchment-400 mb-1">
              <span>Health</span>
              <span>{gameState.character.hp} / {gameState.character.max_hp}</span>
            </div>
            <div className="h-3 bg-parchment-900 rounded-full overflow-hidden">
              <div
                className={`h-full ${hpColor((gameState.character.hp / gameState.character.max_hp) * 100)} transition-all duration-500 ease-out`}
                style={{ width: `${Math.max(0, Math.min(100, (gameState.character.hp / gameState.character.max_hp) * 100))}%` }}
              />
            </div>
          </div>

          {/* Exhaustion indicator — shown only when afflicted (level > 0). */}
          {(gameState.game_state?.exhaustion ?? 0) > 0 && (() => {
            const ex = gameState.game_state?.exhaustion ?? 0
            const tone = ex >= 5 ? 'blood' : ex >= 3 ? 'amber' : 'gold'
            const pipTone = tone === 'blood' ? 'bg-blood-500' : tone === 'amber' ? 'bg-amber-500' : 'bg-gold-500'
            const accent = tone === 'blood' ? 'text-blood-400' : tone === 'amber' ? 'text-amber-300' : 'text-gold-300'
            return (
              <button
                onClick={() => setShowExhaustion(true)}
                className="w-full text-left bg-blood-900/30 border border-blood-700/50 hover:border-blood-600 rounded-md px-2 py-1.5 mb-3 transition-colors"
                title="View exhaustion details & adjust"
              >
                <div className="flex items-center justify-between">
                  <span className={`text-xs font-semibold ${accent}`}>🥵 Exhaustion {ex}/6</span>
                  <div className="flex gap-0.5">
                    {[1, 2, 3, 4, 5, 6].map((n) => (
                      <span
                        key={n}
                        className={`w-1.5 h-3 rounded-sm ${ex >= n ? pipTone : 'bg-parchment-800'}`}
                      />
                    ))}
                  </div>
                </div>
              </button>
            )
          })()}

          {/* Survival indicator — shown only when running a food/water deficit. */}
          {(() => {
            const sv = gameState.game_state?.survival
            const foodDays = sv?.days_without_food ?? 0
            const waterDays = sv?.days_without_water ?? 0
            if (foodDays <= 0 && waterDays <= 0) return null
            const tone = waterDays > 0 ? 'blood' : 'amber'
            const accent = tone === 'blood' ? 'text-blood-400' : 'text-amber-300'
            return (
              <button
                onClick={() => setShowSurvival(true)}
                className={`w-full text-left rounded-md px-2 py-1.5 mb-3 transition-colors border ${
                  tone === 'blood'
                    ? 'bg-blood-900/30 border-blood-700/50 hover:border-blood-600'
                    : 'bg-amber-900/30 border-amber-700/50 hover:border-amber-600'
                }`}
                title="Track food & water, resolve a survival day"
              >
                <div className="flex items-center justify-between text-xs font-semibold">
                  <span className={accent}>🍖 Survival</span>
                  <span className="text-parchment-400">
                    {foodDays > 0 && `🍖${foodDays}d`}
                    {foodDays > 0 && waterDays > 0 && ' · '}
                    {waterDays > 0 && `💧${waterDays}d`}
                  </span>
                </div>
              </button>
            )
          })()}

          {/* Location */}
          <div className="text-sm">
            <span className="text-parchment-500">Location: </span>
            <span className="text-parchment-300">{gameState.game_state?.location || 'Unknown'}</span>
          </div>

          {/* Act & XP */}
          <div className="flex justify-between items-center mt-3 text-sm">
            <span className="bg-arcane-700/50 text-arcane-300 px-2 py-0.5 rounded-md text-xs font-semibold">Act {gameState.current_act}</span>
            <span className="text-gold-400 font-semibold">✦ {gameState.xp} XP</span>
          </div>

          {/* Feats & ASI indicator — mirrors how alignment/background are shown.
              Clicking opens the Feats panel. The gold ASI badge is the headline
              "you have an ability score improvement to spend" prompt. */}
          {featStatus && (
            <button
              onClick={() => setShowFeats(true)}
              className="w-full flex items-center justify-between mt-2 bg-parchment-900/40 hover:bg-parchment-900/70 border border-parchment-800/60 rounded-md px-2 py-1.5 text-xs transition-colors"
              title="View feats, ASI status & learn available feats"
            >
              <span className="text-parchment-300">
                🏆 <span className="text-parchment-400">{featStatus.feats.length}</span> feat{featStatus.feats.length === 1 ? '' : 's'}
              </span>
              {featStatus.asi_available > 0 ? (
                <span className="bg-gold-900/50 text-gold-300 border border-gold-700/50 px-1.5 py-0.5 rounded font-semibold animate-pulse">
                  ✦ {featStatus.asi_available} ASI ready
                </span>
              ) : (
                <span className="text-parchment-600">
                  {featStatus.next_asi_level ? `next ASI at Lv ${featStatus.next_asi_level}` : 'no further ASIs'}
                </span>
              )}
            </button>
          )}
        </div>

        {/* Equipment & Combat Stats */}
        {equipmentStats && (
          <div className="panel">
            <h3 className="font-fantasy text-base text-parchment-200 mb-2">⚔️ Equipment</h3>
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-parchment-500">Armor Class</span>
              <span className="text-xl font-bold text-arcane-300">{equipmentStats.armor_class}</span>
            </div>
            <div className="space-y-1.5 text-sm">
              <div className="flex justify-between">
                <span className="text-parchment-500">Weapon</span>
                <span className="text-parchment-200 text-right">
                  {equipmentStats.weapon ?? '—'}
                  {equipmentStats.weapon_magic_bonus > 0 && (
                    <span className="text-gold-400"> +{equipmentStats.weapon_magic_bonus}</span>
                  )}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-parchment-500">Armor</span>
                <span className="text-parchment-200">{equipmentStats.body_armor ?? 'Unarmored'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-parchment-500">Shield</span>
                <span className="text-parchment-200">{equipmentStats.shield ?? '—'}</span>
              </div>
            </div>
            {equipmentStats.attacks.length > 0 && (
              <div className="mt-3 pt-2 border-t border-parchment-800/60 space-y-1">
                <span className="text-xs text-parchment-500">Attacks</span>
                {equipmentStats.attacks.map((atk, i) => (
                  <div key={i} className="flex justify-between text-xs text-parchment-300">
                    <span>{atk.ranged ? '🏹 ' : '🗡️ '}{atk.name}</span>
                    <span className="font-mono">
                      +{atk.attack_bonus} · {atk.damage_dice_count > 0
                        ? `${atk.damage_dice_count}d${atk.damage_dice_sides}${atk.damage_bonus >= 0 ? '+' : ''}${atk.damage_bonus}`
                        : `${atk.damage_bonus}`}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Combat Tracker - Only show during combat */}
        {inCombat && combatState?.encounter && (
          <CombatTracker
            combatants={combatState.encounter.combatants}
            currentTurnId={combatState.current_turn_id || null}
            roundNumber={combatState.round || 1}
            isPlayerTurn={isPlayerTurn}
            onAttack={handleAttack}
            onNextTurn={handleNextTurn}
          />
        )}
      </div>

      {/* World Map overlay */}
      {showMap && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 animate-overlay-in"
          onClick={() => !mapLoading && setShowMap(false)}
        >
          <div
            className="panel max-w-2xl w-full max-h-[90vh] overflow-y-auto animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-fantasy text-2xl text-parchment-200">🗺️ World Map</h2>
              <button
                className="text-parchment-400 hover:text-parchment-200 text-2xl leading-none"
                onClick={() => setShowMap(false)}
                disabled={mapLoading}
              >
                ×
              </button>
            </div>
            {mapLoading && !worldMap ? (
              <div className="text-parchment-400 animate-pulse text-center py-12">Charting the realm…</div>
            ) : worldMap ? (
              <WorldMap map={worldMap} traveling={mapLoading} onTravel={handleTravel} />
            ) : (
              <div className="text-parchment-500 text-center py-8">No map data available.</div>
            )}
            <p className="text-xs text-parchment-600 mt-3 text-center">
              Click a glowing region to travel. Random encounters may occur en route.
            </p>
          </div>
        </div>
      )}

      {/* Save / Load overlay */}
      {showSaves && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 animate-overlay-in"
          onClick={() => !saveBusy && setShowSaves(false)}
        >
          <div
            className="panel max-w-lg w-full max-h-[90vh] overflow-y-auto animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-fantasy text-2xl text-parchment-200">💾 Save & Load</h2>
              <button
                className="text-parchment-400 hover:text-parchment-200 text-2xl leading-none"
                onClick={() => setShowSaves(false)}
                disabled={saveBusy}
              >
                ×
              </button>
            </div>

            {/* Create new save */}
            <div className="flex gap-2 mb-4">
              <input
                className="input-field flex-1"
                value={newSaveName}
                onChange={(e) => setNewSaveName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleCreateSave()}
                placeholder="Save name (e.g., 'Before the dragon')"
                disabled={saveBusy}
              />
              <button
                className="btn-primary px-4"
                onClick={handleCreateSave}
                disabled={saveBusy}
              >
                Save
              </button>
            </div>

            {/* Existing saves */}
            {saveSlots.length === 0 ? (
              <div className="text-parchment-500 text-center py-8">No saves yet. Create one above.</div>
            ) : (
              <div className="space-y-2">
                {saveSlots.map((slot) => (
                  <div
                    key={slot.id}
                    className="flex items-center justify-between bg-parchment-900/60 rounded-lg p-3"
                  >
                    <div className="min-w-0">
                      <div className="text-parchment-200 font-semibold truncate">{slot.slot_name}</div>
                      <div className="text-xs text-parchment-500">
                        {slot.created_at ? new Date(slot.created_at).toLocaleString() : ''} · Lv {slot.character_level ?? '?'} · {slot.character_hp ?? '?'}/{slot.character_max_hp ?? '?'} HP · Act {slot.current_act}
                      </div>
                    </div>
                    <div className="flex gap-2 shrink-0 ml-2">
                      <button
                        className="text-xs bg-arcane-700 hover:bg-arcane-600 text-parchment-200 px-3 py-1 rounded transition-colors disabled:opacity-50"
                        onClick={() => handleLoadSave(slot.id)}
                        disabled={saveBusy}
                      >
                        Load
                      </button>
                      <button
                        className="text-xs bg-blood-800 hover:bg-blood-700 text-parchment-200 px-2 py-1 rounded transition-colors disabled:opacity-50"
                        onClick={() => handleDeleteSave(slot.id)}
                        disabled={saveBusy}
                      >
                        🗑
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <p className="text-xs text-parchment-600 mt-3 text-center">
              Loading a save rewinds your character, inventory, and story to that moment.
            </p>
          </div>
        </div>
      )}

      {/* Rest overlay */}
      {showRest && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 animate-overlay-in"
          onClick={() => !restBusy && setShowRest(false)}
        >
          <div
            className="panel max-w-md w-full animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-fantasy text-2xl text-parchment-200">💤 Rest</h2>
              <button
                className="text-parchment-400 hover:text-parchment-200 text-2xl leading-none"
                onClick={() => setShowRest(false)}
                disabled={restBusy}
              >
                ×
              </button>
            </div>

            {restInfo ? (
              <>
                <div className="bg-parchment-900/60 rounded-lg p-3 mb-4 space-y-1 text-sm">
                  <div className="flex justify-between">
                    <span className="text-parchment-500">Health</span>
                    <span className="text-parchment-200">{restInfo.current_hp} / {restInfo.max_hp} HP</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-parchment-500">Hit Dice</span>
                    <span className="text-parchment-200">
                      {restInfo.hit_dice_available} / {restInfo.hit_dice_total} × d{restInfo.hit_die_size}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-parchment-500">CON modifier</span>
                    <span className="text-parchment-200">{restInfo.constitution_modifier >= 0 ? '+' : ''}{restInfo.constitution_modifier}</span>
                  </div>
                  {restInfo.is_caster && (
                    <div className="flex justify-between">
                      <span className="text-parchment-500">Spellcaster</span>
                      <span className="text-arcane-300">Slots recover on long rest</span>
                    </div>
                  )}
                </div>

                {restResult && (
                  <div className="bg-arcane-900/40 border border-arcane-700 rounded-lg p-3 mb-4 text-sm text-parchment-200">
                    {restResult}
                  </div>
                )}

                <div className="flex flex-col gap-2">
                  <button
                    className="btn-primary w-full"
                    onClick={handleShortRest}
                    disabled={restBusy || restInfo.hit_dice_available <= 0 || restInfo.current_hp >= restInfo.max_hp}
                    title="Spend Hit Dice to heal (≥1 hour)"
                  >
                    🔥 Short Rest
                  </button>
                  <button
                    className="btn-primary w-full bg-arcane-700 hover:bg-arcane-600"
                    onClick={handleLongRest}
                    disabled={restBusy}
                    title="Full HP, recover Hit Dice + spell slots, clear conditions (≥8 hours)"
                  >
                    🌙 Long Rest
                  </button>
                </div>
                <p className="text-xs text-parchment-600 mt-3 text-center">
                  A short rest spends Hit Dice to heal. A long rest restores full HP and recovers half your Hit Dice.
                </p>
              </>
            ) : (
              <div className="text-parchment-400 animate-pulse text-center py-8">Gathering your strength…</div>
            )}
          </div>
        </div>
      )}

      {/* Skills overlay */}
      {showSkills && gameState?.character?.id && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 animate-overlay-in"
          onClick={() => setShowSkills(false)}
        >
          <div
            className="panel max-w-lg w-full max-h-[90vh] overflow-y-auto animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-fantasy text-2xl text-parchment-200">📜 Skills</h2>
              <button
                className="text-parchment-400 hover:text-parchment-200 text-2xl leading-none"
                onClick={() => setShowSkills(false)}
              >
                ×
              </button>
            </div>
            <SkillsPanel characterId={gameState.character.id} />
          </div>
        </div>
      )}

      {/* Saving Throws overlay */}
      {showSavingThrows && gameState?.character?.id && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 animate-overlay-in"
          onClick={() => setShowSavingThrows(false)}
        >
          <div
            className="panel max-w-lg w-full max-h-[90vh] overflow-y-auto animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-fantasy text-2xl text-parchment-200">🛡️ Saving Throws</h2>
              <button
                className="text-parchment-400 hover:text-parchment-200 text-2xl leading-none"
                onClick={() => setShowSavingThrows(false)}
              >
                ×
              </button>
            </div>
            <SavingThrowsPanel
              characterId={gameState.character.id}
              conditions={gameState.game_state.conditions}
            />
          </div>
        </div>
      )}

      {/* Background / Origin overlay */}
      {showBackground && gameState?.character?.id && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 animate-overlay-in"
          onClick={() => {
            setShowBackground(false)
            refreshEquipmentStats()
          }}
        >
          <div
            className="panel max-w-lg w-full max-h-[90vh] overflow-y-auto animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-fantasy text-2xl text-parchment-200">🎭 Origin</h2>
              <button
                className="text-parchment-400 hover:text-parchment-200 text-2xl leading-none"
                onClick={() => {
                  setShowBackground(false)
                  refreshEquipmentStats()
                }}
              >
                ×
              </button>
            </div>
            <BackgroundPanel
              characterId={gameState.character.id}
              onChanged={async () => {
                // Equipment/gold/HP may have changed; refresh game state.
                const state = await getGameState(gameState.game_id)
                setGameState(state)
              }}
            />
          </div>
        </div>
      )}

      {/* Alignment overlay */}
      {showAlignment && gameState?.character?.id && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 animate-overlay-in"
          onClick={() => setShowAlignment(false)}
        >
          <div
            className="panel max-w-lg w-full max-h-[90vh] overflow-y-auto animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-fantasy text-2xl text-parchment-200">⚖️ Alignment</h2>
              <button
                className="text-parchment-400 hover:text-parchment-200 text-2xl leading-none"
                onClick={() => setShowAlignment(false)}
              >
                ×
              </button>
            </div>
            <AlignmentPanel
              characterId={gameState.character.id}
              onChanged={async () => {
                // The sidebar alignment label + DM context depend on this.
                const state = await getGameState(gameState.game_id)
                setGameState(state)
              }}
            />
          </div>
        </div>
      )}

      {/* Languages overlay */}
      {showLanguages && gameState?.character?.id && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 animate-overlay-in"
          onClick={() => setShowLanguages(false)}
        >
          <div
            className="panel max-w-lg w-full max-h-[90vh] overflow-y-auto animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-fantasy text-2xl text-parchment-200">🗣️ Languages</h2>
              <button
                className="text-parchment-400 hover:text-parchment-200 text-2xl leading-none"
                onClick={() => setShowLanguages(false)}
              >
                ×
              </button>
            </div>
            <LanguagesPanel
              characterId={gameState.character.id}
              onChanged={async () => {
                // Languages shape DM narration & comprehension checks.
                const state = await getGameState(gameState.game_id)
                setGameState(state)
              }}
            />
          </div>
        </div>
      )}

      {/* Environment overlay */}
      {showEnvironment && gameState?.game_id && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 animate-overlay-in"
          onClick={() => setShowEnvironment(false)}
        >
          <div
            className="panel max-w-lg w-full max-h-[90vh] overflow-y-auto animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-fantasy text-2xl text-parchment-200">🌤️ Scene &amp; Weather</h2>
              <button
                className="text-parchment-400 hover:text-parchment-200 text-2xl leading-none"
                onClick={() => setShowEnvironment(false)}
              >
                ×
              </button>
            </div>
            <EnvironmentPanel
              gameId={gameState.game_id}
              onChanged={async () => {
                // The scene drives combat modifiers; refresh game state.
                const state = await getGameState(gameState.game_id)
                setGameState(state)
              }}
            />
          </div>
        </div>
      )}

      {/* Shop overlay */}
      {showShop && gameState?.game_id && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 animate-overlay-in"
          onClick={() => setShowShop(false)}
        >
          <div
            className="panel max-w-lg w-full max-h-[90vh] overflow-y-auto animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-fantasy text-2xl text-parchment-200">🛍️ Market</h2>
              <button
                className="text-parchment-400 hover:text-parchment-200 text-2xl leading-none"
                onClick={() => setShowShop(false)}
              >
                ×
              </button>
            </div>
            <ShopPanel gameId={gameState.game_id} />
          </div>
        </div>
      )}

      {/* Inventory overlay */}
      {showInventory && gameState?.character?.id && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 animate-overlay-in"
          onClick={() => {
            setShowInventory(false)
            refreshEquipmentStats()
          }}
        >
          <div
            className="panel max-w-lg w-full max-h-[90vh] overflow-y-auto animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-fantasy text-2xl text-parchment-200">🎒 Inventory</h2>
              <button
                className="text-parchment-400 hover:text-parchment-200 text-2xl leading-none"
                onClick={() => {
                  setShowInventory(false)
                  refreshEquipmentStats()
                }}
              >
                ×
              </button>
            </div>
            <InventoryPanel
              characterId={gameState.character.id}
              onHpChange={async () => {
                // Potion use changed HP; refresh game state.
                const state = await getGameState(gameState.game_id)
                setGameState(state)
              }}
            />
          </div>
        </div>
      )}

      {showSpells && gameState?.character?.id && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 animate-overlay-in"
          onClick={() => setShowSpells(false)}
        >
          <div
            className="panel max-w-2xl w-full max-h-[90vh] overflow-y-auto animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-fantasy text-2xl text-parchment-200">🔮 Spellbook</h2>
              <button
                className="text-parchment-400 hover:text-parchment-200 text-2xl leading-none"
                onClick={() => setShowSpells(false)}
              >
                ×
              </button>
            </div>
            <SpellsPanel
              characterId={gameState.character.id}
              activeConditions={gameState.game_state.conditions}
              onChanged={async () => {
                // Casting consumes slots / heals / damages — refresh game state.
                const state = await getGameState(gameState.game_id)
                setGameState(state)
              }}
            />
          </div>
        </div>
      )}

      {showFeats && gameState?.character?.id && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 animate-overlay-in"
          onClick={() => setShowFeats(false)}
        >
          <div
            className="panel max-w-2xl w-full max-h-[90vh] overflow-y-auto animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-fantasy text-2xl text-parchment-200">🏆 Feats &amp; Abilities</h2>
              <button
                className="text-parchment-400 hover:text-parchment-200 text-2xl leading-none"
                onClick={() => setShowFeats(false)}
              >
                ×
              </button>
            </div>
            <FeatsPanel
              characterId={gameState.character.id}
              onChanged={async () => {
                // Learning a feat can change ability scores / HP (Tough), which
                // reshapes AC (Dex/Con) and max HP — refresh state, gear & the
                // sidebar feat/ASI indicator.
                const state = await getGameState(gameState.game_id)
                setGameState(state)
                await refreshEquipmentStats()
                await refreshFeatStatus()
              }}
            />
          </div>
        </div>
      )}

      {/* Subclass overlay */}
      {showSubclass && gameState?.character?.id && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 animate-overlay-in"
          onClick={() => setShowSubclass(false)}
        >
          <div
            className="panel max-w-2xl w-full max-h-[90vh] overflow-y-auto animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-fantasy text-2xl text-parchment-200">⚔️ Subclass &amp; Features</h2>
              <button
                className="text-parchment-400 hover:text-parchment-200 text-2xl leading-none"
                onClick={() => setShowSubclass(false)}
              >
                ×
              </button>
            </div>
            <SubclassPanel
              characterId={gameState.character.id}
              onChanged={async () => {
                const state = await getGameState(gameState.game_id)
                setGameState(state)
              }}
            />
          </div>
        </div>
      )}

      {/* Exhaustion overlay */}
      {showExhaustion && gameState?.game_id && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 animate-overlay-in"
          onClick={() => setShowExhaustion(false)}
        >
          <div
            className="panel max-w-lg w-full max-h-[90vh] overflow-y-auto animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-fantasy text-2xl text-parchment-200">🥵 Exhaustion</h2>
              <button
                className="text-parchment-400 hover:text-parchment-200 text-2xl leading-none"
                onClick={() => setShowExhaustion(false)}
              >
                ×
              </button>
            </div>
            <ExhaustionPanel
              gameId={gameState.game_id}
              onNarration={(entry) => addToStory(entry)}
              onChanged={async () => {
                // Changing exhaustion alters the game_state (exhaustion level),
                // and level 6 drops HP to 0 — refresh state so the sidebar
                // indicator + HP bar stay in sync.
                const state = await getGameState(gameState.game_id)
                setGameState(state)
              }}
            />
          </div>
        </div>
      )}

      {/* Survival overlay */}
      {showSurvival && gameState?.game_id && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 animate-overlay-in"
          onClick={() => setShowSurvival(false)}
        >
          <div
            className="panel max-w-lg w-full max-h-[90vh] overflow-y-auto animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-fantasy text-2xl text-parchment-200">🍖 Survival</h2>
              <button
                className="text-parchment-400 hover:text-parchment-200 text-2xl leading-none"
                onClick={() => setShowSurvival(false)}
              >
                ×
              </button>
            </div>
            <SurvivalPanel
              gameId={gameState.game_id}
              onNarration={(entry) => addToStory(entry)}
              onChanged={async () => {
                // A survival day can add exhaustion (and at level 6 drop HP
                // to 0) — refresh state so the sidebar indicator + HP bar
                // stay in sync.
                const state = await getGameState(gameState.game_id)
                setGameState(state)
              }}
            />
          </div>
        </div>
      )}

      {/* Traps overlay */}
      {showTraps && gameState?.game_id && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 animate-overlay-in"
          onClick={() => setShowTraps(false)}
        >
          <div
            className="panel max-w-lg w-full max-h-[90vh] overflow-y-auto animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-fantasy text-2xl text-parchment-200">🪤 Traps & Hazards</h2>
              <button
                className="text-parchment-400 hover:text-parchment-200 text-2xl leading-none"
                onClick={() => setShowTraps(false)}
              >
                ×
              </button>
            </div>
            <TrapsPanel
              gameId={gameState.game_id}
              inCombat={inCombat}
              onNarration={(entry) => addToStory(entry)}
              onChanged={async () => {
                // A trap can deal damage or apply conditions — refresh state
                // so the sidebar / HP bar stay in sync.
                const state = await getGameState(gameState.game_id)
                setGameState(state)
              }}
            />
          </div>
        </div>
      )}

      {/* Social Interaction overlay */}
      {showSocial && gameState?.game_id && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 animate-overlay-in"
          onClick={() => setShowSocial(false)}
        >
          <div
            className="panel max-w-lg w-full max-h-[90vh] overflow-y-auto animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-fantasy text-2xl text-parchment-200">💬 Social Interaction</h2>
              <button
                className="text-parchment-400 hover:text-parchment-200 text-2xl leading-none"
                onClick={() => setShowSocial(false)}
              >
                ×
              </button>
            </div>
            <SocialPanel
              gameId={gameState.game_id}
              onNarration={(entry) => addToStory(entry)}
              onChanged={async () => {
                const state = await getGameState(gameState.game_id)
                setGameState(state)
              }}
            />
          </div>
        </div>
      )}

      {/* Downtime overlay */}
      {showDowntime && gameState?.game_id && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 animate-overlay-in"
          onClick={() => setShowDowntime(false)}
        >
          <div
            className="panel max-w-lg w-full max-h-[90vh] overflow-y-auto animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-fantasy text-2xl text-parchment-200">⏳ Downtime</h2>
              <button
                className="text-parchment-400 hover:text-parchment-200 text-2xl leading-none"
                onClick={() => setShowDowntime(false)}
              >
                ×
              </button>
            </div>
            <DowntimePanel
              gameId={gameState.game_id}
              gold={gameState.character?.gold ?? 0}
              onNarration={(entry) => addToStory(entry)}
              onChanged={async () => {
                const state = await getGameState(gameState.game_id)
                setGameState(state)
              }}
            />
          </div>
        </div>
      )}

      {/* Mounts overlay */}
      {showMounts && gameState?.game_id && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 animate-overlay-in"
          onClick={() => setShowMounts(false)}
        >
          <div
            className="panel max-w-lg w-full max-h-[90vh] overflow-y-auto animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-fantasy text-2xl text-parchment-200">🐎 Mounts &amp; Vehicles</h2>
              <button
                className="text-parchment-400 hover:text-parchment-200 text-2xl leading-none"
                onClick={() => setShowMounts(false)}
              >
                ×
              </button>
            </div>
            <MountsPanel
              gameId={gameState.game_id}
              characterGold={gameState.character?.gold}
              onNarration={(entry) => addToStory(entry)}
              onChanged={async () => {
                // Acquiring a mount with payment deducts gold; damage/dismount
                // can affect HP — refresh the game state to keep things in sync.
                const state = await getGameState(gameState.game_id)
                setGameState(state)
              }}
            />
          </div>
        </div>
      )}

      {/* Images overlay */}
      {showImages && gameState?.game_id && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 animate-overlay-in"
          onClick={() => setShowImages(false)}
        >
          <div
            className="panel max-w-lg w-full max-h-[90vh] overflow-y-auto animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-fantasy text-2xl text-parchment-200">🖼️ Image Studio</h2>
              <button
                className="text-parchment-400 hover:text-parchment-200 text-2xl leading-none"
                onClick={() => setShowImages(false)}
              >
                ×
              </button>
            </div>
            <ImagePanel
              gameId={gameState.game_id}
              onNarration={(entry) => addToStory(entry)}
              onChanged={async () => {
                const state = await getGameState(gameState.game_id)
                setGameState(state)
              }}
            />
          </div>
        </div>
      )}

      {showActions && combatState?.encounter && (() => {
        const player = combatState.encounter.combatants.find((c) => c.id === 'player')
        const enemies = combatState.encounter.combatants.filter((c) => c.side === 'enemy')
        if (!player) return null
        return (
          <CombatActionsPanel
            gameId={gid}
            player={player}
            enemies={enemies}
            onResult={handleCombatAction}
            onClose={() => setShowActions(false)}
          />
        )
      })()}
    </div>
  )
}