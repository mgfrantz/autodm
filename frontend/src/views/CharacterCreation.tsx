import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createCharacter, generateCharacterFlavor, listBackgrounds, getBackground, setCharacterBackground, listAlignments } from '../stores/api'
import type { BackgroundSummary, BackgroundDetail, AlignmentSummary } from '../types'

const RACES = ['Human', 'Elf', 'Dwarf', 'Halfling', 'Gnome', 'Half-Elf', 'Half-Orc', 'Tiefling', 'Dragonborn']
const CLASSES = ['Barbarian', 'Bard', 'Cleric', 'Druid', 'Fighter', 'Monk', 'Paladin', 'Ranger', 'Rogue', 'Sorcerer', 'Warlock', 'Wizard']
// Fallback if the backgrounds API is unreachable.
const FALLBACK_BACKGROUNDS = ['Acolyte', 'Criminal', 'Folk Hero', 'Noble', 'Sage', 'Soldier', 'Urchin', 'Outlander', 'Charlatan', 'Entertainer']
// Fallback nine alignments if the alignment API is unreachable.
const FALLBACK_ALIGNMENTS: AlignmentSummary[] = [
  { id: 'lawful_good', name: 'Lawful Good', abbreviation: 'LG', ethics: 'lawful', morals: 'good', description: 'Honors the spirit and letter of the law.' },
  { id: 'neutral_good', name: 'Neutral Good', abbreviation: 'NG', ethics: 'neutral', morals: 'good', description: 'Driven by conscience above law or chaos.' },
  { id: 'chaotic_good', name: 'Chaotic Good', abbreviation: 'CG', ethics: 'chaotic', morals: 'good', description: 'Follows their conscience with little regard for law.' },
  { id: 'lawful_neutral', name: 'Lawful Neutral', abbreviation: 'LN', ethics: 'lawful', morals: 'neutral', description: 'Acts by law, tradition, or personal code.' },
  { id: 'neutral', name: 'True Neutral', abbreviation: 'N', ethics: 'neutral', morals: 'neutral', description: 'Acts naturally, without prejudice or compulsion.' },
  { id: 'chaotic_neutral', name: 'Chaotic Neutral', abbreviation: 'CN', ethics: 'chaotic', morals: 'neutral', description: 'Follows their whims; freedom above all else.' },
  { id: 'lawful_evil', name: 'Lawful Evil', abbreviation: 'LE', ethics: 'lawful', morals: 'evil', description: 'Takes what they want within a code of order.' },
  { id: 'neutral_evil', name: 'Neutral Evil', abbreviation: 'NE', ethics: 'neutral', morals: 'evil', description: 'Pure, uncompromising selfishness.' },
  { id: 'chaotic_evil', name: 'Chaotic Evil', abbreviation: 'CE', ethics: 'chaotic', morals: 'evil', description: 'Acts with arbitrary violence and bloodlust.' },
]

// Tailwind text-color class per morals axis for the alignment grid.
const MORALS_COLOR: Record<string, string> = {
  good: 'text-leaf-400',
  neutral: 'text-parchment-300',
  evil: 'text-blood-400',
}

const SKILL_LABELS: Record<string, string> = {
  athletics: 'Athletics', acrobatics: 'Acrobatics', sleight_of_hand: 'Sleight of Hand', stealth: 'Stealth',
  arcana: 'Arcana', history: 'History', investigation: 'Investigation', nature: 'Nature', religion: 'Religion',
  animal_handling: 'Animal Handling', insight: 'Insight', medicine: 'Medicine', perception: 'Perception', survival: 'Survival',
  deception: 'Deception', intimidation: 'Intimidation', performance: 'Performance', persuasion: 'Persuasion',
}

export default function CharacterCreation() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)

  const [form, setForm] = useState({
    name: '',
    race: 'Human',
    char_class: 'Fighter',
    background: 'Soldier',
    alignment: 'lawful_good',
    strength: 15,
    dexterity: 14,
    constitution: 13,
    intelligence: 12,
    wisdom: 10,
    charisma: 8,
    backstory: '',
    personality_traits: [] as string[],
    ideal: '',
    bond: '',
    flaw: '',
  })

  // Background registry + live detail preview
  const [backgrounds, setBackgrounds] = useState<string[]>(FALLBACK_BACKGROUNDS)
  const [bgDetail, setBgDetail] = useState<BackgroundDetail | null>(null)
  const [bgLoading, setBgLoading] = useState(false)

  // Alignment registry (nine alignments for the classic 3x3 grid)
  const [alignments, setAlignments] = useState<AlignmentSummary[]>(FALLBACK_ALIGNMENTS)

  const [generating, setGenerating] = useState(false)
  const [genError, setGenError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listBackgrounds()
      .then((list: BackgroundSummary[]) => {
        if (cancelled) return
        // Show canonical (non-variant) backgrounds first for a clean picker,
        // then variants — keeps the list complete but tidy.
        const primary = list.filter((b) => !b.variant_of).map((b) => b.name)
        const variants = list.filter((b) => b.variant_of).map((b) => b.name)
        const ordered = [...primary, ...variants]
        if (ordered.length) setBackgrounds(ordered)
      })
      .catch(() => { /* keep fallback */ })
    return () => { cancelled = true }
  }, [])

  // Fetch the nine-alignment registry once for the picker grid
  useEffect(() => {
    let cancelled = false
    listAlignments()
      .then((list: AlignmentSummary[]) => { if (!cancelled && list.length) setAlignments(list) })
      .catch(() => { /* keep fallback */ })
    return () => { cancelled = true }
  }, [])

  // Fetch detail for the selected background to show a live preview
  useEffect(() => {
    let cancelled = false
    setBgLoading(true)
    getBackground(form.background)
      .then((d: BackgroundDetail) => { if (!cancelled) setBgDetail(d) })
      .catch(() => { if (!cancelled) setBgDetail(null) })
      .finally(() => { if (!cancelled) setBgLoading(false) })
    return () => { cancelled = true }
  }, [form.background])

  const update = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  const handleSubmit = async () => {
    setLoading(true)
    try {
      // Create the character without a background, then apply the background
      // via its dedicated endpoint so the starting equipment + gold pouch are
      // granted (the create endpoint only stores the background string).
      const { background: _bg, ...createPayload } = form
      void _bg
      const character = await createCharacter(createPayload)
      try {
        await setCharacterBackground(character.id, form.background, true)
      } catch {
        // Equipment grant is best-effort; the character is still valid.
      }
      navigate('/world/new', { state: { characterId: character.id } })
    } catch (err) {
      alert('Failed to create character. Is the backend running?')
      setLoading(false)
    }
  }

  const handleGenerateFlavor = async () => {
    setGenerating(true)
    setGenError(null)
    try {
      const flavor = await generateCharacterFlavor({
        race: form.race, char_class: form.char_class,
        background: form.background, alignment: form.alignment,
        strength: form.strength, dexterity: form.dexterity,
        constitution: form.constitution, intelligence: form.intelligence,
        wisdom: form.wisdom, charisma: form.charisma,
      })
      update('name', flavor.name)
      update('backstory', flavor.backstory)
      update('personality_traits', flavor.personality_traits)
      update('ideal', flavor.ideal)
      update('bond', flavor.bond)
      update('flaw', flavor.flaw)
    } catch {
      setGenError('Could not generate character details. You can write your own backstory below.')
    } finally {
      setGenerating(false)
    }
  }

  const abilityLabels: [string, keyof typeof form][] = [
    ['Strength', 'strength'],
    ['Dexterity', 'dexterity'],
    ['Constitution', 'constitution'],
    ['Intelligence', 'intelligence'],
    ['Wisdom', 'wisdom'],
    ['Charisma', 'charisma'],
  ]

  return (
    <div className="max-w-2xl mx-auto p-4 sm:p-8 view-enter">
      <h1 className="font-fantasy text-3xl sm:text-4xl text-parchment-200 mb-2 animate-slide-up">Create Your Hero</h1>

      <div className="panel space-y-6 mt-6 animate-slide-up">
        <div>
          <label className="block text-parchment-300 mb-2 font-semibold">Character Name</label>
          <input
            className="input-field w-full"
            value={form.name}
            onChange={(e) => update('name', e.target.value)}
            placeholder="Enter your hero's name..."
          />
        </div>
        <div>
          <label className="block text-parchment-300 mb-2 font-semibold">Race</label>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {RACES.map((r) => (
              <button
                key={r}
                onClick={() => update('race', r)}
                className={`py-2 rounded-lg text-sm transition-all duration-200
                  ${form.race === r ? 'bg-blood-600 text-parchment-50 shadow-md shadow-blood-900/40' : 'bg-parchment-700 text-parchment-300 hover:bg-parchment-600 hover:-translate-y-0.5'}`}
              >
                {r}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="block text-parchment-300 mb-2 font-semibold">Class</label>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {CLASSES.map((c) => (
              <button
                key={c}
                onClick={() => update('char_class', c)}
                className={`py-2 rounded-lg text-sm transition-all duration-200
                  ${form.char_class === c ? 'bg-blood-600 text-parchment-50 shadow-md shadow-blood-900/40' : 'bg-parchment-700 text-parchment-300 hover:bg-parchment-600 hover:-translate-y-0.5'}`}
              >
                {c}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="block text-parchment-300 mb-2 font-semibold">Background</label>
          <select
            className="input-field w-full"
            value={form.background}
            onChange={(e) => update('background', e.target.value)}
          >
            {backgrounds.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
        </div>

        {/* Live background preview */}
        {bgLoading ? (
          <div className="text-parchment-500 text-xs italic">Loading background…</div>
        ) : bgDetail ? (
          <div className="rounded-lg border border-arcane-700/40 bg-arcane-900/20 p-3 space-y-2 animate-fade-in">
            {bgDetail.feature && (
              <div>
                <div className="text-arcane-300 font-semibold text-sm flex items-center gap-1">
                  <span>✦</span> Feature: {bgDetail.feature.name}
                </div>
                <p className="text-parchment-400 text-xs mt-1 leading-relaxed">{bgDetail.feature.description}</p>
              </div>
            )}
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs pt-1">
              <span className="text-parchment-300">
                <span className="text-parchment-500">Skills:</span>{' '}
                {bgDetail.skill_proficiencies.map((s) => SKILL_LABELS[s] ?? s).join(', ') || '—'}
              </span>
              {bgDetail.extra_languages > 0 && (
                <span className="text-parchment-300">
                  <span className="text-parchment-500">Languages:</span> +{bgDetail.extra_languages} of choice
                </span>
              )}
              <span className="text-gold-400">
                <span className="text-parchment-500">Gold:</span> {bgDetail.equipment_gold} gp
              </span>
            </div>
            {bgDetail.equipment.length > 0 && (
              <div className="text-xs text-parchment-400">
                <span className="text-parchment-500">Equipment:</span>{' '}
                {bgDetail.equipment.map((e) => (e.quantity > 1 ? `${e.name} ×${e.quantity}` : e.name)).join(', ')}
              </div>
            )}
          </div>
        ) : null}

        <div>
          <label className="block text-parchment-300 mb-2 font-semibold">Alignment</label>
          <p className="text-parchment-500 text-xs mb-2">
            The classic nine alignments. This shapes how the DM portrays your hero and how the world reacts.
          </p>
          <div className="grid grid-cols-3 gap-1.5 sm:gap-2">
            {alignments.map((a) => {
              const selected = form.alignment === a.id
              return (
                <button
                  key={a.id}
                  onClick={() => update('alignment', a.id)}
                  title={a.description}
                  className={`flex flex-col items-center justify-center py-2 px-1 rounded-lg text-center transition-all duration-200 border
                    ${selected
                      ? 'bg-blood-600 text-parchment-50 border-blood-400 shadow-md shadow-blood-900/40 scale-105'
                      : 'bg-parchment-800/60 text-parchment-400 border-parchment-700/40 hover:bg-parchment-700 hover:-translate-y-0.5'}`}
                >
                  <span className={`font-fantasy text-sm sm:text-base ${selected ? 'text-parchment-50' : MORALS_COLOR[a.morals] ?? 'text-parchment-300'}`}>
                    {a.abbreviation}
                  </span>
                  <span className="text-[10px] sm:text-xs leading-tight mt-0.5">
                    {a.name === 'True Neutral' ? 'Neutral' : a.name.split(' ').length === 2 ? a.name.split(' ')[0] : 'Neutral'}
                  </span>
                </button>
              )
            })}
          </div>
          {(() => {
            const sel = alignments.find((a) => a.id === form.alignment)
            return sel ? (
              <p className="text-parchment-400 text-xs mt-2 italic leading-relaxed">
                <span className={`font-semibold not-italic ${MORALS_COLOR[sel.morals] ?? 'text-parchment-300'}`}>{sel.name}.</span>{' '}
                {sel.description}
              </p>
            ) : null
          })()}
        </div>

        {/* Abilities */}
        <div>
          <p className="text-parchment-400 text-sm mb-4">
            Assign your ability scores. Standard Array: 15, 14, 13, 12, 10, 8
          </p>
          {abilityLabels.map(([label, key]) => (
            <div key={key} className="flex items-center gap-2 sm:gap-4">
              <span className="w-24 sm:w-32 text-parchment-300 font-semibold text-sm sm:text-base">{label}</span>
              <input
                type="range"
                min={3}
                max={20}
                value={form[key] as number}
                onChange={(e) => update(key, parseInt(e.target.value))}
                className="flex-1"
              />
              <span className="w-10 text-center text-xl font-fantasy text-parchment-200">
                {form[key] as number}
              </span>
              <span className="w-12 text-center text-sm text-parchment-400">
                {Math.floor(((form[key] as number) - 10) / 2) >= 0 ? '+' : ''}
                {Math.floor(((form[key] as number) - 10) / 2)}
              </span>
            </div>
          ))}
        </div>

        {/* Generate character flavor via DSPy */}
        <div>
          <button
            className="btn-primary w-full"
            onClick={handleGenerateFlavor}
            disabled={generating}
          >
            {generating ? 'Generating...' : '✨ Generate Character'}
          </button>
          {genError && (
            <p className="text-red-400 text-sm mt-2">{genError}</p>
          )}
        </div>

        {/* Generated / editable flavor */}
        <div>
          <label className="block text-parchment-300 mb-2 font-semibold">Backstory (Optional)</label>
          <textarea
            className="input-field w-full h-40 resize-none"
            value={form.backstory}
            onChange={(e) => update('backstory', e.target.value)}
            placeholder="Where did your hero come from? What drives them? This will influence the campaign..."
          />
          <p className="text-parchment-500 text-xs mt-2">
            The more detail you provide, the more personalized your adventure will be.
          </p>
        </div>
        <div>
          <label className="block text-parchment-300 mb-2 font-semibold">Personality Traits</label>
          {form.personality_traits.length > 0 ? (
            form.personality_traits.map((trait, i) => (
              <input
                key={i}
                className="input-field w-full mb-2"
                value={trait}
                onChange={(e) => update('personality_traits', form.personality_traits.map((t, idx) => idx === i ? e.target.value : t))}
                placeholder={`Personality trait ${i + 1}`}
              />
            ))
          ) : (
            <p className="text-parchment-500 text-xs">
              Click "Generate Character" to populate, or write your own below.
            </p>
          )}
        </div>
        <div>
          <label className="block text-parchment-300 mb-2 font-semibold">Ideal</label>
          <input
            className="input-field w-full"
            value={form.ideal}
            onChange={(e) => update('ideal', e.target.value)}
            placeholder="A core ideal your character holds dear"
          />
        </div>
        <div>
          <label className="block text-parchment-300 mb-2 font-semibold">Bond</label>
          <input
            className="input-field w-full"
            value={form.bond}
            onChange={(e) => update('bond', e.target.value)}
            placeholder="A bond linking your character to the world"
          />
        </div>
        <div>
          <label className="block text-parchment-300 mb-2 font-semibold">Flaw</label>
          <input
            className="input-field w-full"
            value={form.flaw}
            onChange={(e) => update('flaw', e.target.value)}
            placeholder="A flaw or weakness"
          />
        </div>

        <button
          className="btn-primary w-full"
          onClick={handleSubmit}
          disabled={loading || !form.name}
        >
          {loading ? 'Creating...' : 'Create Hero ⚔️'}
        </button>
      </div>
    </div>
  )
}
