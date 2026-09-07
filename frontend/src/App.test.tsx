import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { ACTIVE_STORAGE_KEY, STORAGE_KEY } from './conversations'
import type { ChatResponse, Conversation } from './types'

vi.mock('./components/ResultChart', () => ({ ResultChart: () => <div>chart</div> }))
vi.mock('./api', () => ({ askAgent: vi.fn() }))
import { askAgent } from './api'
const mockedAsk = vi.mocked(askAgent)

const response = (thread = 'thread-a', answer = '回答') : ChatResponse => ({ answer, sql: 'SELECT 1 LIMIT 100', columns: ['value'], rows: [[1]], chart: null, trace_id: `trace-${answer}`, thread_id: thread, details: { data_source: 'mysql', duration_ms: 1, selected_tables: ['v_agent_house_listing'], retrieved_metrics: [], row_count: 1, retry_count: 0, used_history: false, inherited_fields: [], overridden_fields: [], context_resolution_duration_ms: 0 } })
const send = async (question: string) => { const user = userEvent.setup(); await user.type(screen.getByPlaceholderText(/例如/), question); await user.click(screen.getByLabelText('发送问题')) }
const seed = (items: Conversation[], active: string) => { localStorage.setItem(STORAGE_KEY, JSON.stringify(items)); localStorage.setItem(ACTIVE_STORAGE_KEY, active) }
const conversation = (id: string, threadId: string): Conversation => ({ id, threadId, title: `会话${id}`, createdAt: '2026-01-01T00:00:00Z', updatedAt: '2026-01-01T00:00:00Z', turns: [{ id: `turn-${id}`, question: `问题${id}`, createdAt: '2026-01-01T00:00:00Z', response: response(threadId, `回答${id}`) }] })

describe('App conversations', () => {
  beforeEach(() => { localStorage.clear(); mockedAsk.mockReset() })
  it('creates one conversation and stores the returned thread', async () => {
    mockedAsk.mockResolvedValue(response()); render(<App />); await send('第一问'); await screen.findByText('回答')
    const stored: Conversation[] = JSON.parse(localStorage.getItem(STORAGE_KEY)!); expect(stored).toHaveLength(1); expect(stored[0].threadId).toBe('thread-a')
  })
  it('reuses the same thread on the second question', async () => {
    mockedAsk.mockResolvedValueOnce(response()).mockResolvedValueOnce(response('thread-a', '第二答')); render(<App />); await send('第一问'); await screen.findByText('回答'); await send('第二问'); await screen.findByText('第二答'); expect(mockedAsk).toHaveBeenNthCalledWith(2, '第二问', 'thread-a')
  })
  it('keeps two turns in one sidebar conversation and renders both', async () => {
    mockedAsk.mockResolvedValueOnce(response()).mockResolvedValueOnce(response('thread-a', '第二答')); render(<App />); await send('第一问'); await screen.findByText('回答'); await send('第二问'); await screen.findByText('第二答'); expect(within(screen.getByRole('navigation')).getAllByRole('button')).toHaveLength(2); expect(screen.getAllByText('第一问')).toHaveLength(2); expect(screen.getByText('第二问')).toBeVisible()
  })
  it('new conversation sends no previous thread id', async () => {
    mockedAsk.mockResolvedValueOnce(response()).mockResolvedValueOnce(response('thread-b', '新答')); render(<App />); await send('旧问题'); await screen.findByText('回答'); await userEvent.click(screen.getByText('新建会话')); await send('新问题'); await screen.findByText('新答'); expect(mockedAsk).toHaveBeenNthCalledWith(2, '新问题', null)
  })
  it('switches between conversations without mixing their turns', async () => {
    seed([conversation('a', 'thread-a'), conversation('b', 'thread-b')], 'a'); render(<App />); expect(screen.getByText('问题a')).toBeVisible(); await userEvent.click(screen.getByText('会话b')); expect(screen.getByText('问题b')).toBeVisible(); expect(screen.queryByText('问题a')).not.toBeInTheDocument()
  })
  it('restores the active conversation thread after reload', async () => {
    seed([conversation('a', 'thread-a')], 'a'); mockedAsk.mockResolvedValue(response('thread-a', '继续答')); render(<App />); await send('继续'); await screen.findByText('继续答'); expect(mockedAsk).toHaveBeenCalledWith('继续', 'thread-a')
  })
  it('retries the failed turn without duplicating the question', async () => {
    mockedAsk.mockRejectedValueOnce(new Error('失败')).mockResolvedValueOnce(response()); render(<App />); await send('只出现一次'); await screen.findByText('失败'); await userEvent.click(screen.getByText('重新查询')); await screen.findByText('回答'); expect(screen.getAllByText('只出现一次')).toHaveLength(2); const stored: Conversation[] = JSON.parse(localStorage.getItem(STORAGE_KEY)!); expect(stored[0].turns).toHaveLength(1)
  })
  it('writes an asynchronous response to its originating conversation', async () => {
    let resolve!: (value: ChatResponse) => void; mockedAsk.mockReturnValue(new Promise((done) => { resolve = done })); seed([conversation('a', 'thread-a'), conversation('b', 'thread-b')], 'a'); render(<App />); fireEvent.change(screen.getByPlaceholderText(/例如/), { target: { value: '异步问题' } }); fireEvent.click(screen.getByLabelText('发送问题')); await userEvent.click(screen.getByText('会话b')); await act(async () => resolve(response('thread-a', '异步回答'))); expect(screen.queryByText('异步回答')).not.toBeInTheDocument(); await userEvent.click(screen.getByText('会话a')); expect(await screen.findByText('异步回答')).toBeVisible()
  })
  it('deletes an unwanted history conversation', async () => {
    seed([conversation('a', 'thread-a'), conversation('b', 'thread-b')], 'a'); render(<App />); await userEvent.click(screen.getByLabelText('删除会话：会话a')); expect(screen.queryByText('会话a')).not.toBeInTheDocument(); expect(JSON.parse(localStorage.getItem(STORAGE_KEY)!)).toHaveLength(1)
  })
})
