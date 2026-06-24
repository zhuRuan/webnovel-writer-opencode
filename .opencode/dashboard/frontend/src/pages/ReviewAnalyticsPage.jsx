import { useEffect, useMemo, useState } from 'react'
import { useDashboardContext } from '../App.jsx'
import Badge from '../components/Badge.jsx'
import ChartWrapper from '../components/ChartWrapper.jsx'
import { fetchReviewAnalytics, fetchReviewReports, fetchReviewReport } from '../api.js'

const DIMENSION_LABELS = {
    continuity: '叙事连贯',
    setting: '设定一致性',
    character: '角色一致性',
    timeline: '时间线',
    ai_flavor: 'AI味',
    logic: '逻辑',
    pacing: '节奏',
    other: '其他',
}

const SEVERITY_LABELS = {
    critical: '致命',
    high: '严重',
    medium: '中等',
    low: '轻微',
}

const SEVERITY_COLORS = {
    critical: '#d7263d',
    high: '#f5a524',
    medium: '#26a8ff',
    low: '#8f7f5c',
}

function parseReviewReport(markdown) {
    const issues = []
    let currentSection = ''
    let currentIssue = null

    const lines = markdown.split('\n')
    for (const line of lines) {
        if (line.startsWith('## 阻断问题')) { currentSection = 'blocking'; continue }
        if (line.startsWith('## 其他问题')) { currentSection = 'other'; continue }
        if (line.startsWith('## 总览') || line.startsWith('# ')) continue

        const issueMatch = line.match(/^\d+\.\s+\*\*(.+)\*\*$/)
        if (issueMatch) {
            if (currentIssue) issues.push(currentIssue)
            currentIssue = { title: issueMatch[1], section: currentSection, severity: '', category: '', location: '', blocking: false, evidence: '', fix: '' }
            continue
        }

        if (currentIssue) {
            if (line.includes('严重级别：')) currentIssue.severity = line.split('严重级别：')[1].trim()
            else if (line.includes('分类：')) currentIssue.category = line.split('分类：')[1].trim()
            else if (line.includes('位置：')) currentIssue.location = line.split('位置：')[1].trim()
            else if (line.includes('阻断：')) currentIssue.blocking = line.includes('是')
            else if (line.includes('证据：')) currentIssue.evidence = line.split('证据：')[1].trim()
            else if (line.includes('修复方向：')) currentIssue.fix = line.split('修复方向：')[1].trim()
        }
    }
    if (currentIssue) issues.push(currentIssue)
    return issues
}

function parseReportOverview(markdown) {
    const overview = { total: 0, blocking: 0, critical: 0, high: 0, medium: 0, low: 0 }
    const lines = markdown.split('\n')
    let inOverview = false
    for (const line of lines) {
        if (line.startsWith('## 总览')) { inOverview = true; continue }
        if (inOverview && line.startsWith('## ') && !line.startsWith('## 总览')) break
        if (!inOverview) continue
        if (line.includes('总问题数：')) overview.total = parseInt(line.split('总问题数：')[1]) || 0
        else if (line.includes('阻断问题：')) overview.blocking = parseInt(line.split('阻断问题：')[1]) || 0
        else if (line.includes('致命：')) overview.critical = parseInt(line.split('致命：')[1]) || 0
        else if (line.includes('严重：')) overview.high = parseInt(line.split('严重：')[1]) || 0
        else if (line.includes('中等：')) overview.medium = parseInt(line.split('中等：')[1]) || 0
        else if (line.includes('轻微：')) overview.low = parseInt(line.split('轻微：')[1]) || 0
    }
    return overview
}

function renderIssueCard(issue, index, config) {
    const sev = config[issue.severity] || config.medium
    return (
        <div key={index} style={{
            marginBottom: 10, padding: '10px 14px', borderRadius: 6,
            borderLeft: `3px solid ${sev.border}`,
            background: sev.bg, fontSize: 13,
        }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <span style={{
                    display: 'inline-block', padding: '1px 8px', borderRadius: 4,
                    background: sev.border, color: '#fff', fontSize: 11, fontWeight: 600
                }}>
                    {sev.label}
                </span>
                <strong>{issue.title}</strong>
                {issue.blocking && <span style={{ color: 'var(--accent-red)', fontSize: 11 }}>阻断</span>}
            </div>
            <div style={{ color: 'var(--text-sub)', fontSize: 12, lineHeight: 1.6 }}>
                <div>📍 位置: {issue.location || '-'}</div>
                {issue.evidence && <div style={{ marginTop: 2 }}>📝 {issue.evidence}</div>}
                {issue.fix && <div style={{ marginTop: 4, color: 'var(--accent-green)' }}>💡 修复: {issue.fix}</div>}
            </div>
        </div>
    )
}

function buildRadarOption(averages) {
    if (!averages) return null
    const dims = Object.keys(averages)
    if (!dims.length) return null

    return {
        tooltip: {},
        radar: {
            indicator: dims.map(d => ({
                name: DIMENSION_LABELS[d] || d,
                max: 100,
            })),
            shape: 'polygon',
            splitArea: { show: true },
            axisName: { color: '#5d5035', fontSize: 11, fontWeight: 600 },
        },
        series: [{
            type: 'radar',
            data: [{
                value: dims.map(d => Math.round(averages[d] * 10) / 10),
                name: '平均分',
                areaStyle: { color: 'rgba(38, 168, 255, 0.2)' },
                lineStyle: { color: '#26a8ff', width: 2 },
                itemStyle: { color: '#26a8ff', borderColor: '#2a220f', borderWidth: 2 },
            }],
        }],
    }
}

function buildTrendOption(trends) {
    if (!trends) return null
    const dims = Object.keys(trends)
    if (!dims.length) return null

    // 收集所有章节并排序
    const allChapters = new Set()
    for (const points of Object.values(trends)) {
        for (const p of points) allChapters.add(p.chapter)
    }
    const chapters = [...allChapters].sort((a, b) => a - b)

    const colors = ['#26a8ff', '#7f5af0', '#2ec27e', '#f5a524', '#d7263d', '#00b8d4', '#ff6b6b', '#ffd93d']

    return {
        tooltip: { trigger: 'axis' },
        legend: { bottom: 0, type: 'scroll' },
        grid: { left: 52, right: 24, top: 36, bottom: 46 },
        xAxis: {
            type: 'category',
            data: chapters,
            axisLabel: { interval: Math.max(1, Math.floor(chapters.length / 10)), formatter: v => `${v}` },
        },
        yAxis: {
            type: 'value',
            min: 0,
            max: 100,
        },
        series: dims.map((dim, i) => {
            const pointMap = new Map(trends[dim].map(p => [p.chapter, p.score]))
            return {
                name: DIMENSION_LABELS[dim] || dim,
                type: 'line',
                data: chapters.map(ch => pointMap.get(ch) ?? null),
                lineStyle: { width: 2, color: colors[i % colors.length] },
                itemStyle: { color: colors[i % colors.length], borderColor: '#2a220f', borderWidth: 1 },
                symbol: 'circle',
                symbolSize: 4,
                connectNulls: true,
            }
        }),
    }
}

function buildSeverityOption(severityTotals) {
    const entries = Object.entries(severityTotals || {}).filter(([, v]) => v > 0)
    if (!entries.length) return null

    return {
        tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
        series: [{
            type: 'pie',
            radius: ['35%', '65%'],
            avoidLabelOverlap: false,
            itemStyle: { borderColor: '#2a220f', borderWidth: 2 },
            label: {
                show: true,
                formatter: '{b}\n{c}',
                color: '#5d5035',
                fontSize: 12,
                fontWeight: 600,
            },
            data: entries.map(([name, value]) => ({
                name: SEVERITY_LABELS[name] || name,
                value,
                itemStyle: { color: SEVERITY_COLORS[name] || '#8f7f5c' },
            })),
        }],
    }
}

function scoreTone(score) {
    if (score >= 80) return 'green'
    if (score >= 60) return 'amber'
    return 'red'
}

export default function ReviewAnalyticsPage() {
    const { refreshToken } = useDashboardContext()
    const [data, setData] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [reviewReports, setReviewReports] = useState([])
    const [selectedReport, setSelectedReport] = useState(null)
    const [reportContent, setReportContent] = useState('')
    const [loadingReport, setLoadingReport] = useState(false)

    useEffect(() => {
        setLoading(true)
        setError(null)
        fetchReviewAnalytics(50)
            .then(setData)
            .catch(e => setError(e.message))
            .finally(() => setLoading(false))
    }, [refreshToken])

    useEffect(() => {
        fetchReviewReports().then(d => setReviewReports(d.reports || []))
    }, [refreshToken])

    const radarOption = useMemo(() => buildRadarOption(data?.dimension_averages), [data])
    const trendOption = useMemo(() => buildTrendOption(data?.dimension_trends), [data])
    const severityOption = useMemo(() => buildSeverityOption(data?.severity_totals), [data])

    return (
        <section className="dashboard-page">
            <header className="page-header">
                <h2>审查分析</h2>
                {data && <Badge tone="blue">{data.total_reviews} 次审查</Badge>}
            </header>

            {loading && <div className="empty-state">加载中...</div>}
            {error && <div className="empty-state" style={{ color: 'var(--accent-red)' }}>加载失败: {error}</div>}

            {!loading && !error && data && (
                <>
                    {/* 最薄弱维度 */}
                    {data.weakest_dimensions?.length > 0 && (
                        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
                            <span style={{ fontWeight: 700, lineHeight: '28px' }}>最薄弱维度：</span>
                            {data.weakest_dimensions.map(w => (
                                <Badge key={w.dimension} tone={scoreTone(w.avg_score)}>
                                    {DIMENSION_LABELS[w.dimension] || w.dimension}: {Math.round(w.avg_score * 10) / 10}
                                </Badge>
                            ))}
                        </div>
                    )}

                    {/* 雷达图 + 严重程度分布 */}
                    <div className="content-grid two-columns">
                        <article className="card">
                            <div className="card-header">
                                <span className="card-title">维度雷达图</span>
                                <Badge tone="purple">8 维度</Badge>
                            </div>
                            {radarOption ? (
                                <ChartWrapper option={radarOption} height={320} />
                            ) : (
                                <div className="empty-state" style={{ minHeight: 320, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                    <p>暂无维度数据可供展示</p>
                                </div>
                            )}
                        </article>

                        <article className="card">
                            <div className="card-header">
                                <span className="card-title">严重程度分布</span>
                                <Badge tone="amber">累计</Badge>
                            </div>
                            {severityOption ? (
                                <ChartWrapper option={severityOption} height={320} />
                            ) : (
                                <div className="empty-state" style={{ minHeight: 320, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                    <p>暂无严重程度数据</p>
                                </div>
                            )}
                            <div style={{
                                marginTop: 16,
                                padding: '12px 16px',
                                background: 'var(--bg-card)',
                                border: '2px solid var(--border-main)',
                                fontSize: 13,
                                lineHeight: 1.7,
                                color: 'var(--text-mute)',
                            }}>
                                <div style={{ fontWeight: 700, color: 'var(--text-main)', marginBottom: 6 }}>
                                    严重度说明
                                </div>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 18px' }}>
                                    <span><span style={{ color: SEVERITY_COLORS.critical, fontWeight: 700 }}>● 致命</span> 阻断发布，必须修复</span>
                                    <span><span style={{ color: SEVERITY_COLORS.high, fontWeight: 700 }}>● 严重</span> 严重影响质量，应修复</span>
                                    <span><span style={{ color: SEVERITY_COLORS.medium, fontWeight: 700 }}>● 中等</span> 建议修复</span>
                                    <span><span style={{ color: SEVERITY_COLORS.low, fontWeight: 700 }}>● 轻微</span> 可选优化</span>
                                </div>
                            </div>
                        </article>
                    </div>

                    {/* 维度趋势 */}
                    {trendOption && (
                        <article className="card">
                            <div className="card-header">
                                <span className="card-title">维度得分趋势</span>
                                <Badge tone="green">最近 50 次审查</Badge>
                            </div>
                            <ChartWrapper option={trendOption} loading={loading} />
                        </article>
                    )}

                    {/* 严重程度详情（按级别分组） */}
                    {data.severity_totals && Object.keys(data.severity_totals).length > 0 && (() => {
                        const totalIssues = Object.values(data.severity_totals).reduce((a, b) => a + b, 0)
                        if (totalIssues === 0) return null
                        return (
                            <article className="card" style={{ borderColor: 'var(--border-main)' }}>
                                <div className="card-header">
                                    <span className="card-title">问题详情（按严重程度）</span>
                                    <Badge tone="amber">共 {totalIssues} 条</Badge>
                                </div>
                                <div style={{ padding: '8px 0' }}>
                                    {['critical', 'high', 'medium', 'low'].map(sev => {
                                        const count = data.severity_totals[sev] || 0
                                        if (count === 0) return null
                                        const isCritical = sev === 'critical'
                                        const issues = isCritical && data.critical_issues ? data.critical_issues : []
                                        return (
                                            <div key={sev} style={{
                                                marginBottom: 14,
                                                paddingLeft: 12,
                                                borderLeft: `3px solid ${SEVERITY_COLORS[sev]}`,
                                            }}>
                                                <div style={{
                                                    fontWeight: 700,
                                                    color: SEVERITY_COLORS[sev],
                                                    marginBottom: 6,
                                                    fontSize: 14,
                                                }}>
                                                    {SEVERITY_LABELS[sev]}问题 ({count})
                                                </div>
                                                {issues.length > 0 ? (
                                                    <ul style={{ margin: 0, paddingLeft: 20 }}>
                                                        {issues.slice(0, 10).map((issue, i) => (
                                                            <li key={i} style={{
                                                                marginBottom: 4,
                                                                color: 'var(--text-sub)',
                                                                fontSize: 13,
                                                                lineHeight: 1.6,
                                                            }}>
                                                                {issue}
                                                            </li>
                                                        ))}
                                                        {issues.length > 10 && (
                                                            <li style={{
                                                                color: 'var(--text-mute)',
                                                                fontSize: 12,
                                                                fontStyle: 'italic',
                                                            }}>
                                                                … 还有 {issues.length - 10} 条问题
                                                            </li>
                                                        )}
                                                    </ul>
                                                ) : (
                                                    <div style={{
                                                        fontSize: 13,
                                                        color: 'var(--text-mute)',
                                                    }}>
                                                        共 {count} 条{SEVERITY_LABELS[sev]}问题，详情请查看各章审查报告
                                                    </div>
                                                )}
                                            </div>
                                        )
                                    })}
                                </div>
                            </article>
                        )
                    })()}
                </>
            )}

            {!loading && !error && !data && (
                <div className="empty-state">
                    <p>暂无审查数据。需要先执行至少一次审查。</p>
                </div>
            )}

            {/* 审查报告浏览器 */}
            <article className="card">
                <div className="card-header">
                    <span className="card-title">📋 审查报告</span>
                    <Badge tone="blue">{reviewReports.length} 份</Badge>
                </div>

                <div style={{ display: 'flex', gap: 8, padding: '12px 16px', flexWrap: 'wrap', borderBottom: '1px solid var(--border)' }}>
                    {reviewReports.length === 0 && (
                        <span style={{ color: 'var(--text-sub)', fontSize: 13 }}>暂无审查报告</span>
                    )}
                    {reviewReports.map(r => (
                        <button key={r.chapter} className={`page-btn ${selectedReport === r.chapter ? 'active' : ''}`}
                            onClick={async () => {
                                setSelectedReport(r.chapter)
                                setLoadingReport(true)
                                try {
                                    const res = await fetchReviewReport(r.chapter)
                                    setReportContent(res.content || '')
                                } catch { setReportContent('加载失败') }
                                setLoadingReport(false)
                            }}>
                            第{r.chapter}章
                        </button>
                    ))}
                </div>

                {loadingReport && <div style={{ padding: 24, color: 'var(--text-sub)', fontSize: 13 }}>加载中...</div>}
                {!loadingReport && reportContent && (() => {
                    const overview = parseReportOverview(reportContent)
                    const issues = parseReviewReport(reportContent)

                    const severityConfig = {
                        critical: { color: '#991b1b', bg: 'rgba(153,27,27,0.06)', label: '致命', border: '#dc2626' },
                        high:     { color: '#ef4444', bg: 'rgba(239,68,68,0.05)', label: '严重', border: '#ef4444' },
                        medium:   { color: '#f97316', bg: 'rgba(249,115,22,0.04)', label: '中等', border: '#f97316' },
                        low:      { color: '#eab308', bg: 'rgba(234,179,8,0.03)', label: '轻微', border: '#eab308' },
                    }

                    const blocking = issues.filter(i => i.section === 'blocking')
                    const other = issues.filter(i => i.section === 'other')

                    return (
                        <div style={{ padding: '0 16px 16px' }}>
                            {/* Overview summary */}
                            {overview.total > 0 && (
                                <div style={{
                                    display: 'flex', gap: 16, flexWrap: 'wrap', padding: '12px 0',
                                    borderBottom: '1px solid var(--border)', marginBottom: 12
                                }}>
                                    <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-main)' }}>
                                        📊 共 {overview.total} 个问题
                                    </span>
                                    {overview.blocking > 0 && (
                                        <span style={{ fontSize: 13, color: 'var(--accent-red)', fontWeight: 600 }}>
                                            🚫 {overview.blocking} 个阻断
                                        </span>
                                    )}
                                    {overview.critical > 0 && (
                                        <span style={{ fontSize: 13, color: severityConfig.critical.border }}>致命 {overview.critical}</span>
                                    )}
                                    {overview.high > 0 && (
                                        <span style={{ fontSize: 13, color: severityConfig.high.border }}>严重 {overview.high}</span>
                                    )}
                                    {overview.medium > 0 && (
                                        <span style={{ fontSize: 13, color: severityConfig.medium.border }}>中等 {overview.medium}</span>
                                    )}
                                    {overview.low > 0 && (
                                        <span style={{ fontSize: 13, color: severityConfig.low.border }}>轻微 {overview.low}</span>
                                    )}
                                </div>
                            )}

                            {issues.length === 0 && (
                                <div style={{ padding: 24, color: 'var(--text-sub)', fontSize: 13 }}>无法解析报告内容</div>
                            )}

                            {/* Blocking issues first */}
                            {blocking.length > 0 && (
                                <div style={{ marginBottom: 16 }}>
                                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--accent-red)', marginBottom: 8 }}>
                                        🚫 阻断问题 ({blocking.length})
                                    </div>
                                    {blocking.map((issue, i) => renderIssueCard(issue, i, severityConfig))}
                                </div>
                            )}

                            {/* Other issues */}
                            {other.length > 0 && (
                                <div>
                                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-sub)', marginBottom: 8 }}>
                                        ⚠ 其他问题 ({other.length})
                                    </div>
                                    {other.map((issue, i) => renderIssueCard(issue, i, severityConfig))}
                                </div>
                            )}
                        </div>
                    )
                })()}
                {!loadingReport && selectedReport && !reportContent && (
                    <div style={{ padding: 24, color: 'var(--text-sub)', fontSize: 13 }}>暂无内容</div>
                )}
            </article>
        </section>
    )
}
