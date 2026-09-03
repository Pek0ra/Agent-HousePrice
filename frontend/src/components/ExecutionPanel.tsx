import type { ChatResponse } from '../types'

const sourceCopy: Record<string, { name: string; note: string }> = {
  mysql: { name: 'MySQL', note: '实时房源与业务数据' },
  hive: { name: 'Hive', note: '离线明细与历史分析' },
  none: { name: '未查询', note: '等待有效的问数请求' },
}

export function ExecutionPanel({ result }: { result?: ChatResponse }) {
  if (!result) {
    return (
      <aside className="details-panel empty-details">
        <span className="eyebrow">EXECUTION TRACE</span>
        <h2>执行详情</h2>
        <p>提交问题后，这里会展示数据源、SQL、安全限制和检索到的指标口径。</p>
      </aside>
    )
  }
  const details = result.details
  const source = sourceCopy[details.data_source] ?? { name: details.data_source, note: '数据查询服务' }
  return (
    <aside className="details-panel">
      <div className="details-title">
        <div><span className="eyebrow">EXECUTION TRACE</span><h2>执行详情</h2></div>
        <span className="status-dot">已完成</span>
      </div>

      <section className="detail-section">
        <span className="detail-label">数据来源</span>
        <div className={`source-card source-${details.data_source}`}>
          <strong>{source.name}</strong><span>{source.note}</span>
        </div>
      </section>

      <div className="stats-row">
        <div><strong>{details.duration_ms}</strong><span>毫秒</span></div>
        <div><strong>{details.row_count}</strong><span>结果行</span></div>
        <div><strong>{details.retry_count}</strong><span>重试</span></div>
      </div>

      <section className="detail-section">
        <span className="detail-label">访问对象</span>
        <div className="tag-list">
          {details.selected_tables.length
            ? details.selected_tables.map((table) => <code className="table-tag" key={table}>{table}</code>)
            : <span className="muted">未访问数据库</span>}
        </div>
      </section>

      <section className="detail-section">
        <span className="detail-label">安全 SQL</span>
        <pre className="sql-block"><code>{result.sql || '本次请求无需执行 SQL'}</code></pre>
      </section>

      <section className="detail-section metrics-section">
        <span className="detail-label">命中指标口径</span>
        {details.retrieved_metrics.length ? details.retrieved_metrics.map((metric) => (
          <details className="metric-card" key={metric.id}>
            <summary>{metric.title}<span>{metric.id}</span></summary>
            <p>{metric.description}</p>
          </details>
        )) : <p className="muted">未命中额外指标定义</p>}
      </section>

      <footer className="trace-id">TRACE · {result.trace_id}</footer>
    </aside>
  )
}
