import { describe, it, expect } from 'vitest'
import { StreamEvent } from '../api'

describe('StreamEvent type includes action_suggestions', () => {
  it('accepts action_suggestions in a done event', () => {
    const event: StreamEvent = {
      type: 'done',
      combat_active: false,
      action_suggestions: [
        'Ask the innkeeper about rumors',
        'Search the chest for traps',
      ],
    }

    expect(event.type).toBe('done')
    expect(event.action_suggestions).toHaveLength(2)
    expect(event.action_suggestions?.[0]).toBe('Ask the innkeeper about rumors')
  })

  it('allows optional action_suggestions', () => {
    const event: StreamEvent = {
      type: 'done',
      combat_active: false,
    }

    expect(event.action_suggestions).toBeUndefined()
  })

  it('allows empty array for action_suggestions', () => {
    const event: StreamEvent = {
      type: 'done',
      combat_active: false,
      action_suggestions: [],
    }

    expect(event.action_suggestions).toEqual([])
  })
})