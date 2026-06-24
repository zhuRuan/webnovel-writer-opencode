import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import Badge from '../components/Badge.jsx'

const AGENT_COLORS = {
    'director-agent': 'purple',
    'actor-agent': 'blue',
    'actor-agent-budget': 'blue',
    'chapter-writer-agent': 'green',
    'reviewer': 'amber',
}

function formatMs(ms) {
    if (ms == null) return '—'
    if (ms < 1000) return `${ms}ms`
    return `${(ms / 1000).toFixed(1)}s`
}

function formatTokens(n) {
    if (n == null) return '—'
    if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
    return String(n)
}

export default function ChapterTracePage() {
    const { chapterId } = useParams()
    const [chapter, setChapter] = useState(chapterId || '')
    const [trace, setTrace] = useState(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)

    async function loadTrace(ch) {
        const num = Number(ch)
        if (!Number.isFinite(num) || num < 1) return
        setLoading(true)
        setError(null)
        try {
            const res = await fetch(`/api/chapters/${num}/trace`)
            if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
            const data = await res.json()
            setTrace(data)
        } catch (e) {
            setTrace(null)
            setError(e.message)
        }
        setLoading(false)
    }

    useEffect(() => {
        if (chapter) loadTrace(chapter)
    }, [chapter])

    const traceSteps = trace?.trace || []
    const debates = trace?.debates || []
    const maxDuration = Math.max(...traceSteps.map(s => s.duration_ms || 0), 0)
    const totalTokens = traceSteps.reduce((sum, s) => sum + (s.token_count || 0), 0)
    const totalTime = traceSteps.reduce((sum, s) => sum + (s.duration_ms || 0), 0)
    const hasError = traceSteps.some(s => s.error_msg)

    return (
        <div className="dashboard-page">
            <div className="page-header">
                <h2>章节心路历程</h2>
            </div>

            <div style={{ display: 'flex', gap: 8, marginBottom: 4 }}>
                <input
                    type="number"
                    min={1}
                    value={chapter}
                    onChange={e => setChapter(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && loadTrace(chapter)}
                    placeholder="输入章节号"
                    style={{ padding: '6px 12px', width: 140 }}
                />
                <button
                    className="page-btn primary"
                    onClick={() => loadTrace(chapter)}
                    disabled={loading || !chapter}
                >
                    {loading ? '查询中...' : '查询'}
                </button>
            </div>

            {error && (
                <div className="empty-state">
                    <div className="section-label">ERROR</div>
                    <p>无法加载章节 {chapter} 的追踪数据：{error}</p>
                </div>
            )}

            {!error && trace && traceSteps.length === 0 && (
                <div className="empty-state">
                    <div className="section-label">NO DATA</div>
                    <p>章节 {chapter} 暂无过程追踪数据。</p>
                </div>
            )}

            {trace && traceSteps.length > 0 && (
                <>
                    {/* ── Stats Summary Bar ── */}
                    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
                        <Badge tone="blue">{traceSteps.length} 步骤</Badge>
                        <Badge tone="purple">{debates.length} 异议</Badge>
                        <Badge tone="amber">总耗时 {formatMs(totalTime)}</Badge>
                        <Badge tone="cyan">{formatTokens(totalTokens)} tokens</Badge>
                        {hasError && <Badge tone="red">含错误</Badge>}
                    </div>

                    {/* ── Timeline ── */}
                    <div className="section-label">执行链路</div>
                    {traceSteps.map((step, i) => {
                        const tone = AGENT_COLORS[step.agent_name] || 'blue'
                        const isSlowest = maxDuration > 0 && (step.duration_ms || 0) === maxDuration

                        return (
                            <div
                                key={i}
                                className="card"
                                style={{
                                    borderLeft: `4px solid var(--accent-${tone})`,
                                    marginBottom: 8,
                                    ...(isSlowest ? { borderColor: 'var(--accent-red)', borderLeftWidth: 4 } : {}),
                                }}
                            >
                                <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6, flexWrap: 'wrap' }}>
                                    <Badge tone={tone}>{step.agent_name}</Badge>
                                    <span className="mini-label" style={{ marginBottom: 0 }}>{step.step}</span>
                                    {step.duration_ms != null && (
                                        isSlowest
                                            ? <Badge tone="red">{formatMs(step.duration_ms)} ⚠</Badge>
                                            : <span style={{ fontSize: 11, color: 'var(--text-mute)' }}>{formatMs(step.duration_ms)}</span>
                                    )}
                                    {step.token_count != null && (
                                        <span style={{ fontSize: 11, color: 'var(--text-mute)' }}>
                                            {formatTokens(step.token_count)} tokens
                                        </span>
                                    )}
                                </div>

                                {step.input_summary && (
                                    <div style={{ fontSize: 12, color: 'var(--text-sub)', marginBottom: 4 }}>
                                        <span style={{ color: 'var(--text-mute)', marginRight: 4 }}>📥</span>
                                        {step.input_summary}
                                    </div>
                                )}
                                {step.output_summary && (
                                    <div style={{ fontSize: 12, color: 'var(--text-main)' }}>
                                        <span style={{ color: 'var(--text-mute)', marginRight: 4 }}>📤</span>
                                        {step.output_summary}
                                    </div>
                                )}
                                {step.error_msg && (
                                    <div style={{ fontSize: 12, color: 'var(--accent-red)', marginTop: 4, fontWeight: 600 }}>
                                        ❌ {step.error_msg}
                                    </div>
                                )}
                            </div>
                        )
                    })}

                    {/* ── Debates ── */}
                    {debates.length > 0 && (
                        <>
                            <div className="section-label" style={{ marginTop: 24 }}>角色异议</div>
                            {debates.map((d, i) => (
                                <div
                                    key={i}
                                    className="card"
                                    style={{
                                        borderLeft: '4px solid var(--accent-amber)',
                                        marginBottom: 8,
                                        background: 'var(--bg-card-2)',
                                    }}
                                >
                                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6, flexWrap: 'wrap' }}>
                                        <strong style={{ fontSize: 13 }}>{d.actor_id}</strong>
                                        <Badge tone="amber">{d.issue_category}</Badge>
                                        <Badge tone={d.director_ruling === '采纳' ? 'green' : 'red'}>
                                            {d.director_ruling}
                                        </Badge>
                                    </div>
                                    <div style={{ fontSize: 12, color: 'var(--text-sub)' }}>{d.actor_argument}</div>
                                    {d.director_response && (
                                        <div style={{ fontSize: 12, color: 'var(--text-mute)', marginTop: 4 }}>
                                            → {d.director_response}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </>
                    )}
                </>
            )}
        </div>
    )
}
