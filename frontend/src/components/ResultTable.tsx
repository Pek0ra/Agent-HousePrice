import type { ChatResponse } from '../types'

function formatCell(value: unknown) {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(value)
  return String(value)
}

export function ResultTable({ result }: { result: ChatResponse }) {
  if (!result.columns.length) return null
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>{result.columns.map((column) => <th key={column}>{column}</th>)}</tr>
        </thead>
        <tbody>
          {result.rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, columnIndex) => <td key={`${rowIndex}-${columnIndex}`}>{formatCell(cell)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
