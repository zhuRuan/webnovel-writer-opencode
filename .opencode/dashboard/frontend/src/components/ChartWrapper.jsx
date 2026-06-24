import { useCallback, useEffect, useMemo, useRef } from 'react'
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

    const chartRef = useRef(null)
    const handleChartReady = useCallback(
        (instance) => {
            chartRef.current = instance
            onChartReady?.(instance)
        },
        [onChartReady],
    )
    useEffect(() => {
        return () => {
            if (chartRef.current) {
                chartRef.current.dispose()
                chartRef.current = null
            }
        }
    }, [])

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
            onChartReady={handleChartReady}
        />
    )
}
