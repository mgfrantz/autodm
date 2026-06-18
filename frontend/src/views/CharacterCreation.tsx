import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createCharacter, listBackgrounds, getBackground, setCharacterBackground } from '../stores/api'
import type { BackgroundSummary, BackgroundDetail } from '../types'

const RACES = ['Human', 'Elf', 'Dwarf', 'Halfling', 'Gnome', 'Half-Elf', 'Half-Orc', 'Tiefling', 'Dragonborn']
const CLASSES = ['Barbarian', 'Bard', 'Cleric', 'Druid', 'Fighter', 'Monk', 'Paladin', 'Ranger', 'Rogue', 'Sorcerer', 'Warlock', 'Wizard']
// Fallback if the backgrounds API is unreachable.
const FALLBACK_BACKGROUNDS = ['Acolyte', 'Criminal', 'Folk Hero', 'Noble', 'Sage', 'Soldier', 'Urchin', 'Outlander', 'Charlatan', 'Entertainer']

const SKILL_LABELS: Record<string, string> = {
  athletics: 'Athletics', acrobatics: 'Acrobatics', sleight_of_hand: 'Sleight of Hand', stealth: 'Stealth',
  arcana: 'Arcana', history: 'History', investigation: 'Investigation', nature: 'Nature', religion: 'Religion',
  animal_handling: 'Animal Handling', insight: 'Insight', medicine: 'Medicine', perception: 'Perception', survival: 'Survival',
  deception: 'Deception', intimidation: 'Intimidation', performance: 'Performance', persuasion: 'Persuasion',
}

export default function CharacterCreation() {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [loading, setLoading] = useState(false)

  const [form, setForm] = useState({
    name: '',
    race: 'Human',
    char_class: 'Fighter',
    background: 'Soldier',
    strength: 15,
    dexterity: 14,
    constitution: 13,
    intelligence: 12,
    wisdom: 10,
    charisma: 8,
    backstory: '',
  })

  // Background registry + live detail preview
  const [backgrounds, setBackgrounds] = useState<string[]>(FALLBACK_BACKGROUNDS)
  const [bgDetail, setBgDetail] = useState<BackgroundDetail | null>(null)
  const [bgLoading, setBgLoading] = useState(false)

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

  const update = (key: string, value: any) => setForm({ ...form, [key]: value })

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

  const steps = ['Identity', 'Abilities', 'Story']
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

      {/* Step indicator */}
      <div className="flex gap-2 mb-8 animate-fade-in" style={{ animationDelay: '0.1s' }}>
        {steps.map((s, i) => (
          <div key={s} className={`flex-1 text-center py-2 px-1 rounded-lg text-xs sm:text-sm font-semibold transition-all duration-300
            ${i === step ? 'bg-blood-600 text-parchment-50 scale-105 shadow-lg shadow-blood-900/40' : i < step ? 'bg-parchment-600 text-parchment-100' : 'bg-parchment-800 text-parchment-500'}`}>
            {i + 1}. {s}
          </div>
        ))}
      </div>

      {/* Step 0: Identity */}
      {step === 0 && (
        <div key="step-0" className="panel space-y-4 animate-slide-up">
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

          <button className="btn-primary w-full" onClick={() => setStep(1)} disabled={!form.name}>
            Next: Abilities →
          </button>
        </div>
      )}

      {/* Step 1: Abilities */}
      {step === 1 && (
        <div key="step-1" className="panel space-y-4 animate-slide-up">
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
          <div className="flex gap-4">
            <button className="btn-secondary flex-1" onClick={() => setStep(0)}>← Back</button>
            <button className="btn-primary flex-1" onClick={() => setStep(2)}>Next: Story →</button>
          </div>
        </div>
      )}

      {/* Step 2: Story */}
      {step === 2 && (
        <div key="step-2" className="panel space-y-4 animate-slide-up">
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
          <div className="flex gap-4">
            <button className="btn-secondary flex-1" onClick={() => setStep(1)}>← Back</button>
            <button
              className="btn-primary"
              onClick={handleSubmit}
              disabled={loading}
            >
              {loading ? 'Creating...' : 'Create Hero ⚔️'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
