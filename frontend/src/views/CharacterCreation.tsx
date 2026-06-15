import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createCharacter } from '../stores/api'

const RACES = ['Human', 'Elf', 'Dwarf', 'Halfling', 'Gnome', 'Half-Elf', 'Half-Orc', 'Tiefling', 'Dragonborn']
const CLASSES = ['Barbarian', 'Bard', 'Cleric', 'Druid', 'Fighter', 'Monk', 'Paladin', 'Ranger', 'Rogue', 'Sorcerer', 'Warlock', 'Wizard']
const BACKGROUNDS = ['Acolyte', 'Criminal', 'Folk Hero', 'Noble', 'Sage', 'Soldier', 'Urchin', 'Outlander', 'Charlatan', 'Entertainer']

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

  const update = (key: string, value: any) => setForm({ ...form, [key]: value })

  const handleSubmit = async () => {
    setLoading(true)
    try {
      const character = await createCharacter(form)
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
    <div className="max-w-2xl mx-auto p-8">
      <h1 className="font-fantasy text-4xl text-parchment-200 mb-2">Create Your Hero</h1>

      {/* Step indicator */}
      <div className="flex gap-2 mb-8">
        {steps.map((s, i) => (
          <div key={s} className={`flex-1 text-center py-2 rounded-lg text-sm font-semibold transition-colors
            ${i === step ? 'bg-blood-600 text-parchment-50' : i < step ? 'bg-parchment-600 text-parchment-100' : 'bg-parchment-800 text-parchment-500'}`}>
            {i + 1}. {s}
          </div>
        ))}
      </div>

      {/* Step 0: Identity */}
      {step === 0 && (
        <div className="panel space-y-4">
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
            <div className="grid grid-cols-3 gap-2">
              {RACES.map((r) => (
                <button
                  key={r}
                  onClick={() => update('race', r)}
                  className={`py-2 rounded-lg text-sm transition-colors
                    ${form.race === r ? 'bg-blood-600 text-parchment-50' : 'bg-parchment-700 text-parchment-300 hover:bg-parchment-600'}`}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-parchment-300 mb-2 font-semibold">Class</label>
            <div className="grid grid-cols-3 gap-2">
              {CLASSES.map((c) => (
                <button
                  key={c}
                  onClick={() => update('char_class', c)}
                  className={`py-2 rounded-lg text-sm transition-colors
                    ${form.char_class === c ? 'bg-blood-600 text-parchment-50' : 'bg-parchment-700 text-parchment-300 hover:bg-parchment-600'}`}
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
              {BACKGROUNDS.map((b) => <option key={b} value={b}>{b}</option>)}
            </select>
          </div>
          <button className="btn-primary w-full" onClick={() => setStep(1)} disabled={!form.name}>
            Next: Abilities →
          </button>
        </div>
      )}

      {/* Step 1: Abilities */}
      {step === 1 && (
        <div className="panel space-y-4">
          <p className="text-parchment-400 text-sm mb-4">
            Assign your ability scores. Standard Array: 15, 14, 13, 12, 10, 8
          </p>
          {abilityLabels.map(([label, key]) => (
            <div key={key} className="flex items-center gap-4">
              <span className="w-32 text-parchment-300 font-semibold">{label}</span>
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
        <div className="panel space-y-4">
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
              className="btn-primary flex-1"
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
