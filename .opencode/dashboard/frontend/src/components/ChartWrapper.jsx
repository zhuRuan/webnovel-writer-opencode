import { useEffect, useMemo } from 'react'
import ReactEChartsCore from 'echarts-for-react/lib/core'
import { echarts, ensurePixelTheme, getChartTheme } from '../lib/charts.js'

export default function ChartWrapper({
    option,
    className = '',
    height = 320,
    loading = false,
    onChartReady,
}) {
    useEffect(() => {
        ensurePixelTheme()
    }, [])
    const theme = useMemo(() => getChartTheme(), [])

    return (
        <ReactEChartsCore
            className={`chart-box ${className}`.trim()}
            echarts={echarts}
            theme={theme}
            option={option}
            style={{ height }}
            showLoading={loading}
            notMerge
            lazyUpdate
            opts={{ renderer: 'canvas' }}
            onChartReady={onChartReady}
        />
    )
}
