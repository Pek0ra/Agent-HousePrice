import { FormEvent, KeyboardEvent, useEffect, useMemo, useState } from 'react'
import { askAgent } from './api'
import { ExecutionPanel } from './components/ExecutionPanel'
import { ResultChart } from './components/ResultChart'
import { ResultTable } from './components/ResultTable'
import type { Conversation } from './types'

const STORAGE_KEY = 'house-price-agent-conversations-v1'
const suggestions = [
  '上海浦东三室一厅的平均租金是多少？',
  '北京各区平均房价最高的五个区是哪几个？',
  '上海历史房价月度趋势如何？',
  '哪个区性价比最高？',
]

function loadHistory(): Conversation[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]') as Conversation[]
  } catch {
    return []
  }
}

function compactTime(iso: string) {
  return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(iso))
}

export default function App() {
  const [history, setHistory] = useState<Conversation[]>(loadHistory)
  const [activeId, setActiveId] = useState<string | null>(history[0]?.id ?? null)
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const active = useMemo(() => history.find((item) => item.id === activeId), [activeId, history])

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(history.slice(0, 30)))
  }, [history])

  async function submit(value: string) {
    const message = value.trim()
    if (!message || loading) return
    const item: Conversation = { id: crypto.randomUUID(), question: message, createdAt: new Date().toISOString() }
    setHistory((current) => [item, ...current].slice(0, 30))
    setActiveId(item.id)
    setQuestion('')
    setLoading(true)
    try {
      const response = await askAgent(message)
      setHistory((current) => current.map((entry) => entry.id === item.id ? { ...entry, response } : entry))
    } catch (error) {
      const messageText = error instanceof Error ? error.message : '服务暂时不可用，请稍后重试。'
      setHistory((current) => current.map((entry) => entry.id === item.id ? { ...entry, error: messageText } : entry))
    } finally {
      setLoading(false)
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    void submit(question)
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void submit(question)
    }
  }

  return (
    <div className="app-shell">
      <aside className="history-panel">
        <div className="brand">
          <span className="brand-mark"><i /><i /><i /></span>
          <div><strong>城析</strong><small>HOUSE INTELLIGENCE</small></div>
        </div>
        <button className="new-chat" onClick={() => { setActiveId(null); setQuestion('') }}>
          <span>＋</span> 新建问数
        </button>
        <div className="history-heading"><span>最近对话</span><b>{history.length}</b></div>
        <nav className="history-list" aria-label="历史对话">
          {history.map((item) => (
            <button className={item.id === activeId ? 'active' : ''} key={item.id} onClick={() => setActiveId(item.id)}>
              <span>{item.question}</span><time>{compactTime(item.createdAt)}</time>
            </button>
          ))}
          {!history.length && <p className="history-empty">你的问数记录会保存在当前浏览器。</p>}
        </nav>
        <div className="privacy-note"><span>只读</span> SQL AST 安全校验已开启</div>
      </aside>

      <main className="chat-panel">
        <header className="topbar">
          <div><span className="live-dot" /> 数据服务在线</div>
          <a href="/api/java/system/capabilities" target="_blank" rel="noreferrer">系统能力 ↗</a>
        </header>

        <div className="conversation">
          {!active ? (
            <section className="welcome">
              <span className="eyebrow">NATURAL LANGUAGE → TRUSTED DATA</span>
              <h1>用一句话，读懂<br /><em>城市房价。</em></h1>
              <p>系统会自动理解问题、选择 MySQL 或 Hive、生成并校验只读 SQL，然后返回可核验的数据结论。</p>
              <div className="suggestion-grid">
                {suggestions.map((item, index) => (
                  <button key={item} onClick={() => void submit(item)}><b>0{index + 1}</b><span>{item}</span><i>→</i></button>
                ))}
              </div>
            </section>
          ) : (
            <section className="answer-flow">
              <div className="question-bubble"><span>你的问题</span><p>{active.question}</p></div>
              {loading && active.id === activeId ? (
                <div className="thinking"><span /><span /><span /><p>正在理解问题并查询可信数据…</p></div>
              ) : active.error ? (
                <div className="error-card"><strong>暂时无法完成查询</strong><p>{active.error}</p><button onClick={() => void submit(active.question)}>重新查询</button></div>
              ) : active.response ? (
                <article className="answer-card">
                  <div className="answer-kicker"><span>AI 数据结论</span><b>{active.response.details.data_source.toUpperCase()}</b></div>
                  <h2>{active.response.answer}</h2>
                  {active.response.chart && <section className="result-section"><h3>{active.response.chart.title}</h3><ResultChart result={active.response} /></section>}
                  {!!active.response.columns.length && <section className="result-section"><div className="section-title"><h3>查询结果</h3><span>{active.response.rows.length} 行</span></div><ResultTable result={active.response} /></section>}
                  <details className="inline-sql"><summary>展开查看 SQL</summary><pre><code>{active.response.sql || '本次请求无需执行 SQL'}</code></pre></details>
                  <p className="source-note">数据来源：{active.response.details.data_source === 'hive' ? 'Hive 离线分析层' : active.response.details.data_source === 'mysql' ? 'MySQL 实时业务库（Agent 只读视图）' : '未访问数据源'}。结论仅代表当前挂牌样本。</p>
                </article>
              ) : null}
            </section>
          )}
        </div>

        <form className="composer" onSubmit={onSubmit}>
          <div className="composer-box">
            <textarea value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={onKeyDown} placeholder="例如：对比深圳南山区和福田区的平均租金…" rows={1} maxLength={2000} />
            <button disabled={!question.trim() || loading} aria-label="发送问题">↑</button>
          </div>
          <p>Enter 发送 · Shift + Enter 换行 · Agent 仅执行白名单只读查询</p>
        </form>
      </main>

      <ExecutionPanel result={active?.response} />
    </div>
  )
}
