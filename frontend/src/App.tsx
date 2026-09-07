import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react'
import { askAgent } from './api'
import { ACTIVE_STORAGE_KEY, loadConversations, STORAGE_KEY, trimConversations } from './conversations'
import { ExecutionPanel } from './components/ExecutionPanel'
import { ResultChart } from './components/ResultChart'
import { ResultTable } from './components/ResultTable'
import type { ChatTurn, Conversation } from './types'

const suggestions = ['上海浦东三室一厅的平均房价是多少？', '北京各区平均房价最高的五个区是哪几个？', '上海历史房价月度趋势如何？', '哪个区性价比最高？']
const uid = () => crypto.randomUUID()
const now = () => new Date().toISOString()
const compactTime = (iso: string) => new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(iso))

export default function App() {
  const [history, setHistory] = useState<Conversation[]>(loadConversations)
  const [activeId, setActiveId] = useState<string | null>(() => localStorage.getItem(ACTIVE_STORAGE_KEY))
  const [selectedTurnId, setSelectedTurnId] = useState<string | null>(null)
  const [question, setQuestion] = useState('')
  const [loadingTurnId, setLoadingTurnId] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const active = useMemo(() => history.find((item) => item.id === activeId), [activeId, history])
  const selectedResult = useMemo(() => active?.turns.find((turn) => turn.id === selectedTurnId)?.response ?? [...(active?.turns ?? [])].reverse().find((turn) => turn.response)?.response, [active, selectedTurnId])

  useEffect(() => { localStorage.setItem(STORAGE_KEY, JSON.stringify(trimConversations(history))) }, [history])
  useEffect(() => { if (activeId) localStorage.setItem(ACTIVE_STORAGE_KEY, activeId); else localStorage.removeItem(ACTIVE_STORAGE_KEY) }, [activeId])
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [active?.turns, loadingTurnId])
  useEffect(() => { if (activeId && !history.some((item) => item.id === activeId)) setActiveId(history[0]?.id ?? null) }, [activeId, history])

  function updateTurn(conversationId: string, turnId: string, update: (turn: ChatTurn, conversation: Conversation) => Partial<ChatTurn> & { threadId?: string | null }) {
    setHistory((current) => trimConversations(current.map((conversation) => {
      if (conversation.id !== conversationId) return conversation
      let nextThreadId = conversation.threadId
      const turns = conversation.turns.map((turn) => {
        if (turn.id !== turnId) return turn
        const changes = update(turn, conversation)
        if ('threadId' in changes) nextThreadId = changes.threadId ?? null
        const { threadId: _, ...turnChanges } = changes
        return { ...turn, ...turnChanges }
      })
      return { ...conversation, threadId: nextThreadId, turns, updatedAt: now() }
    })))
  }

  async function sendTurn(conversationId: string, turnId: string, message: string, requestThreadId: string | null) {
    setLoadingTurnId(turnId)
    try {
      const response = await askAgent(message, requestThreadId)
      updateTurn(conversationId, turnId, (_turn, conversation) => conversation.threadId && conversation.threadId !== response.thread_id
        ? { error: '服务返回了不匹配的会话标识，已阻止结果写入。' }
        : { response, error: undefined, threadId: response.thread_id })
      setSelectedTurnId(turnId)
    } catch (error) {
      updateTurn(conversationId, turnId, () => ({ error: error instanceof Error ? error.message : '服务暂时不可用，请稍后重试。' }))
    } finally { setLoadingTurnId((current) => current === turnId ? null : current) }
  }

  async function submit(value: string) {
    const message = value.trim()
    if (!message || loadingTurnId) return
    const createdAt = now()
    const turn: ChatTurn = { id: uid(), question: message, createdAt }
    const existing = history.find((item) => item.id === activeId)
    const conversationId = existing?.id ?? uid()
    if (existing) setHistory((current) => trimConversations(current.map((item) => item.id === conversationId ? { ...item, updatedAt: createdAt, turns: [...item.turns, turn] } : item)))
    else {
      setHistory((current) => trimConversations([{ id: conversationId, threadId: null, title: message.slice(0, 32), createdAt, updatedAt: createdAt, turns: [turn] }, ...current]))
      setActiveId(conversationId)
    }
    setSelectedTurnId(turn.id); setQuestion('')
    await sendTurn(conversationId, turn.id, message, existing?.threadId ?? null)
  }

  function retryTurn(conversationId: string, turn: ChatTurn) {
    if (loadingTurnId) return
    const conversation = history.find((item) => item.id === conversationId)
    updateTurn(conversationId, turn.id, () => ({ error: undefined }))
    void sendTurn(conversationId, turn.id, turn.question, conversation?.threadId ?? null)
  }
  function removeConversation(id: string) { setHistory((current) => current.filter((item) => item.id !== id)); if (activeId === id) { setActiveId(null); setSelectedTurnId(null) } }
  function onSubmit(event: FormEvent) { event.preventDefault(); void submit(question) }
  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void submit(question) } }

  return <div className="app-shell">
    <aside className="history-panel"><div className="brand"><span className="brand-mark"><i /><i /><i /></span><div><strong>城析</strong><small>HOUSE INTELLIGENCE</small></div></div>
      <button className="new-chat" onClick={() => { setActiveId(null); setSelectedTurnId(null); setQuestion('') }}><span>＋</span> 新建会话</button>
      <div className="history-heading"><span>最近对话</span><b>{history.length}</b></div>
      <nav className="history-list" aria-label="历史对话">{history.map((item) => <div className={`history-entry ${item.id === activeId ? 'active' : ''}`} key={item.id}>
        <button className="history-select" onClick={() => { setActiveId(item.id); setSelectedTurnId(null) }}><span>{item.title}</span><time>{compactTime(item.updatedAt)}</time></button>
        <button className="history-delete" aria-label={`删除会话：${item.title}`} title="删除会话" onClick={() => removeConversation(item.id)}>×</button>
      </div>)}{!history.length && <p className="history-empty">你的问数记录会保存在当前浏览器。</p>}</nav>
      <div className="privacy-note"><span>只读</span> SQL AST 安全校验已开启</div></aside>
    <main className="chat-panel"><header className="topbar"><div className="service-status"><span><i className="live-dot" /> 数据服务在线</span><small>{active?.threadId ? `会话 ${active.threadId.slice(0, 8)}` : '新会话将在首次提问时创建'}</small></div><a className="analytics-link" href="http://localhost:9900/"><span>房价数据分析中心</span><b>→</b></a></header>
      <div className="conversation">{!active ? <section className="welcome"><span className="eyebrow">NATURAL LANGUAGE → TRUSTED DATA</span><h1>用一句话，读懂<br /><em>城市房价。</em></h1><p>系统会自动理解问题、选择 MySQL 或 Hive、生成并校验只读 SQL，然后返回可核验的数据结论。</p><div className="suggestion-grid">{suggestions.map((item, index) => <button key={item} onClick={() => void submit(item)}><b>0{index + 1}</b><span>{item}</span><i>→</i></button>)}</div></section>
      : <section className="answer-flow">{active.turns.map((turn) => <div className="chat-turn" key={turn.id}><div className="question-bubble"><span>你的问题</span><p>{turn.question}</p></div>
        {loadingTurnId === turn.id ? <div className="thinking"><span /><span /><span /><p>正在理解问题并查询可信数据…</p></div>
        : turn.error ? <div className="error-card"><strong>暂时无法完成查询</strong><p>{turn.error}</p><button onClick={() => retryTurn(active.id, turn)}>重新查询</button></div>
        : turn.response ? <article className={`answer-card ${selectedTurnId === turn.id ? 'selected' : ''}`} onClick={() => setSelectedTurnId(turn.id)}><div className="answer-kicker"><span>AI 数据结论</span><b>{turn.response.details.data_source.toUpperCase()}</b></div><h2>{turn.response.answer}</h2>{turn.response.chart && <section className="result-section"><h3>{turn.response.chart.title}</h3><ResultChart result={turn.response} /></section>}{!!turn.response.columns.length && <section className="result-section"><div className="section-title"><h3>查询结果</h3><span>{turn.response.rows.length} 行</span></div><ResultTable result={turn.response} /></section>}<details className="inline-sql" onClick={(event) => event.stopPropagation()}><summary>展开查看 SQL</summary><pre><code>{turn.response.sql || '本次请求无需执行 SQL'}</code></pre></details><p className="source-note">数据来源：{turn.response.details.data_source === 'hive' ? 'Hive 离线分析层' : turn.response.details.data_source === 'mysql' ? 'MySQL 实时业务库（Agent 只读视图）' : '未访问数据源'}。结论仅代表当前挂牌样本。</p></article> : null}</div>)}<div ref={endRef} /></section>}</div>
      <form className="composer" onSubmit={onSubmit}><div className="composer-box"><textarea value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={onKeyDown} placeholder="例如：对比深圳南山区和福田区的平均租金…" rows={1} maxLength={2000} /><button disabled={!question.trim() || Boolean(loadingTurnId)} aria-label="发送问题">↑</button></div><p>Enter 发送 · Shift + Enter 换行 · Agent 仅执行白名单只读查询</p></form></main>
    <ExecutionPanel result={selectedResult} />
  </div>
}
