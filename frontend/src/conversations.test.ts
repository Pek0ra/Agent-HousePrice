import { describe, expect, it } from 'vitest'
import { MAX_CONVERSATIONS, MAX_TURNS, migrateV1, trimConversations } from './conversations'
import type { Conversation } from './types'

const legacy = (id: string, question: string, thread?: string) => ({ id, question, createdAt: `2026-01-0${id}T00:00:00Z`, response: thread ? { thread_id: thread } : undefined })

describe('conversation storage', () => {
  it('migrates v1 turns sharing a thread into one conversation', () => {
    const result = migrateV1([legacy('1', '第一问', 'thread-a'), legacy('2', '第二问', 'thread-a')])
    expect(result).toHaveLength(1); expect(result[0].turns.map((turn) => turn.question)).toEqual(['第一问', '第二问'])
  })
  it('keeps legacy turns without thread ids separate', () => expect(migrateV1([legacy('1', '一'), legacy('2', '二')])).toHaveLength(2))
  it('caps conversations and turns independently', () => {
    const items = Array.from({ length: MAX_CONVERSATIONS + 2 }, (_, index): Conversation => ({ id: `${index}`, title: `${index}`, threadId: null, createdAt: `${index}`, updatedAt: String(index).padStart(3, '0'), turns: Array.from({ length: MAX_TURNS + 2 }, (_, turn) => ({ id: `${turn}`, question: 'q', createdAt: `${turn}` })) }))
    const result = trimConversations(items); expect(result).toHaveLength(MAX_CONVERSATIONS); expect(result[0].turns).toHaveLength(MAX_TURNS)
  })
})
