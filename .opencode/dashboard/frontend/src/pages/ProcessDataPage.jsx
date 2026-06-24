import { useState, useEffect } from 'react'
import Badge from '../components/Badge.jsx'

function StatCard({ label, value, tone }) {
    return (
        <div className="card stat-card" style={{ textAlign: 'center', padding: 16 }}>
            <div className="stat-label">{label}</div>
            <div className="stat-value" style={{ color: `var(--accent-${tone})` }}>
                {value ?? '—'}
            </div>
        </div>
    )
}

export default function ProcessDataPage() {
    const [stats, setStats] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)

    useEffect(() => {
        setLoading(true)
        fetch('/api/process/stats')
            .then(r => {
                if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
                return r.json()
            })
            .then(data => {
                setStats(data)
                setLoading(false)
            })
            .catch(e => {
                setError(e.message)
                setStats(null)
                setLoading(false)
            })
    }, [])

    return (
        <div className="dashboard-page">
            <div className="page-header">
                <h2>过程数据面板</h2>
            </div>

            {loading && (
                <div className="empty-state">
                    <div className="section-label">LOADING</div>
                    <p>正在加载过程数据…</p>
                </div>
            )}

            {error && (
                <div className="empty-state">
                    <div className="section-label">ERROR</div>
                    <p>加载失败：{error}</p>
                </div>
            )}

            {!loading && !error && !stats && (
                <div className="empty-state">
                    <div className="section-label">NO DATA</div>
                    <p>暂无过程统计数据。</p>
                </div>
            )}

            {stats && (
                <>
                    {/* ── Primary Stats ── */}
                    <div className="stat-grid">
                        <StatCard
                            label="有日志的章节"
                            value={stats.total_chapters_with_logs}
                            tone="blue"
                        />
                        <StatCard
                            label="总异议数"
                            value={stats.total_debates}
                            tone="amber"
                        />
                        <StatCard
                            label="平均迭代轮次"
                            value={stats.avg_iterations_per_chapter != null
                                ? Number(stats.avg_iterations_per_chapter).toFixed(1)
                                : '—'}
                            tone="purple"
                        />
                        <StatCard
                            label="最活跃演员"
                            value={stats.most_active_actor || '—'}
                            tone="green"
                        />
                    </div>

                    {/* ── Secondary Stats (if available) ── */}
                    {(stats.total_tokens != null || stats.total_duration_ms != null) && (
                        <>
                            <div className="section-label" style={{ marginTop: 24 }}>累计指标</div>
                            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                                {stats.total_tokens != null && (
                                    <Badge tone="cyan">
                                        累计 tokens: {stats.total_tokens >= 1000
                                            ? `${(stats.total_tokens / 1000).toFixed(1)}K`
                                            : stats.total_tokens}
                                    </Badge>
                                )}
                                {stats.total_duration_ms != null && (
                                    <Badge tone="amber">
                                        累计耗时: {stats.total_duration_ms >= 1000
                                            ? `${(stats.total_duration_ms / 1000).toFixed(1)}s`
                                            : `${stats.total_duration_ms}ms`}
                                    </Badge>
                                )}
                                {stats.total_chapters != null && (
                                    <Badge tone="blue">总章节: {stats.total_chapters}</Badge>
                                )}
                            </div>
                        </>
                    )}
                </>
            )}
        </div>
    )
}
