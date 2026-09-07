import type { ChatTurn, Conversation } from './types'

export const STORAGE_KEY = 'house-price-agent-conversations-v2'
export const V1_STORAGE_KEY = 'house-price-agent-conversations-v1'
export const ACTIVE_STORAGE_KEY = 'house-price-agent-active-conversation-v2'
export const MAX_CONVERSATIONS = 30
export const MAX_TURNS = 50

type LegacyTurn = ChatTurn & { response?: ChatTurn['response'] }

function validConversations(value: unknown): Conversation[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is Conversation => Boolean(item && typeof item === 'object' && typeof item.id === 'string' && typeof item.title === 'string' && Array.isArray(item.turns))).slice(0, MAX_CONVERSATIONS)
}

export function migrateV1(value: unknown): Conversation[] {
  if (!Array.isArray(value)) return []
  const groups = new Map<string, Conversation>()
  for (const raw of value as LegacyTurn[]) {
    if (!raw || typeof raw.id !== 'string' || typeof raw.question !== 'string') continue
    const threadId = raw.response?.thread_id ?? null
    const key = threadId ? `thread:${threadId}` : `turn:${raw.id}`
    const turn: ChatTurn = { id: raw.id, question: raw.question, createdAt: raw.createdAt, response: raw.response, error: raw.error }
    const existing = groups.get(key)
    if (existing) {
      existing.turns.push(turn)
      existing.turns.sort((a, b) => a.createdAt.localeCompare(b.createdAt))
      existing.updatedAt = existing.turns.at(-1)?.createdAt ?? existing.updatedAt
    } else groups.set(key, { id: raw.id, threadId, title: raw.question.slice(0, 32), createdAt: raw.createdAt, updatedAt: raw.createdAt, turns: [turn] })
  }
  return [...groups.values()].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)).slice(0, MAX_CONVERSATIONS)
}

export function loadConversations(storage: Storage = localStorage): Conversation[] {
  try {
    const current = storage.getItem(STORAGE_KEY)
    if (current) return validConversations(JSON.parse(current))
    const legacy = storage.getItem(V1_STORAGE_KEY)
    const migrated = migrateV1(legacy ? JSON.parse(legacy) : [])
    if (migrated.length) storage.setItem(STORAGE_KEY, JSON.stringify(migrated))
    return migrated
  } catch { return [] }
}

export function trimConversations(items: Conversation[]): Conversation[] {
  return [...items].map((item) => ({ ...item, turns: item.turns.slice(-MAX_TURNS) })).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)).slice(0, MAX_CONVERSATIONS)
}
