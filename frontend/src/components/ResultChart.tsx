import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { ChatResponse } from '../types'

echarts.use([
  BarChart,
  LineChart,
  PieChart,
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
  CanvasRenderer,
])

export function ResultChart({ result }: { result: ChatResponse }) {
  const chartElement = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!chartElement.current || !result.chart) return
    const chart = echarts.init(chartElement.current)
    const categoryIndex = result.columns.indexOf(result.chart.x_field)
    const categories = result.rows.map((row) => row[categoryIndex])
    const palette = ['#e3633d', '#187b77', '#d69a2d', '#496f9c']

    if (result.chart.type === 'pie') {
      const valueIndex = result.columns.indexOf(result.chart.y_fields[0])
      chart.setOption({
        color: palette,
        tooltip: { trigger: 'item' },
        legend: { bottom: 0 },
        series: [{
          type: 'pie',
          radius: ['45%', '72%'],
          center: ['50%', '44%'],
          data: result.rows.map((row) => ({ name: row[categoryIndex], value: row[valueIndex] })),
          label: { color: '#294158' },
        }],
      })
    } else {
      chart.setOption({
        color: palette,
        tooltip: { trigger: 'axis' },
        legend: { bottom: 0 },
        grid: { top: 18, right: 16, bottom: 52, left: 56 },
        xAxis: {
          type: 'category',
          data: categories,
          axisLine: { lineStyle: { color: '#c8d1d8' } },
          axisLabel: { color: '#617383' },
        },
        yAxis: {
          type: 'value',
          splitLine: { lineStyle: { color: '#e8ecef' } },
          axisLabel: { color: '#617383' },
        },
        series: result.chart.y_fields.map((field, index) => ({
          name: field,
          type: result.chart?.type,
          smooth: result.chart?.type === 'line',
          symbolSize: 8,
          barMaxWidth: 42,
          areaStyle: result.chart?.type === 'line' ? { opacity: 0.08 } : undefined,
          data: result.rows.map((row) => row[result.columns.indexOf(field)]),
          itemStyle: { color: palette[index % palette.length] },
        })),
      })
    }

    const resize = () => chart.resize()
    window.addEventListener('resize', resize)
    return () => {
      window.removeEventListener('resize', resize)
      chart.dispose()
    }
  }, [result])

  return <div className="result-chart" ref={chartElement} role="img" aria-label={result.chart?.title} />
}
