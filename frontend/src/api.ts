import type { ChatResponse } from './types'

export async function askAgent(message: string, threadId?: string | null): Promise<ChatResponse> {
  const response = await fetch('/api/agent/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
    body: JSON.stringify(threadId ? { message, thread_id: threadId } : { message }),
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail || `请求失败（HTTP ${response.status}）`)
  }
  return response.json() as Promise<ChatResponse>
}
