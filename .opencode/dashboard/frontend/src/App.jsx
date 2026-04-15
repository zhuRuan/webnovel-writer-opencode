import { useState, useEffect, useCallback, useMemo } from 'react'
import { fetchJSON, subscribeSSE } from './api.js'
import ForceGraph3D from 'react-force-graph-3d'

// ====================================================================
// 主应用
// ====================================================================

export default function App() {
    const [page, setPage] = useState('dashboard')
    const [projectInfo, setProjectInfo] = useState(null)
    const [refreshKey, setRefreshKey] = useState(0)
    const [connected, setConnected] = useState(false)

    const loadProjectInfo = useCallback(() => {
        fetchJSON('/api/project/info')
            .then(setProjectInfo)
            .catch(() => setProjectInfo(null))
    }, [])

    useEffect(() => { loadProjectInfo() }, [loadProjectInfo, refreshKey])

    // SSE 订阅
    useEffect(() => {
        const unsub = subscribeSSE(
            () => {
                setRefreshKey(k => k + 1)
            },
            {
                onOpen: () => setConnected(true),
                onError: () => setConnected(false),
            },
        )
        return () => { unsub(); setConnected(false) }
    }, [])

    const title = projectInfo?.project_info?.title || '未加载'

    return (
        <div className="app-layout">
            <aside className="sidebar">
                <div className="sidebar-header">
                    <h1>PIXEL WRITER HUB</h1>
                    <div className="subtitle">{title}</div>
                </div>
                <nav className="sidebar-nav">
                    {NAV_ITEMS.map(item => (
                        <button
                            key={item.id}
                            className={`nav-item ${page === item.id ? 'active' : ''}`}
                            onClick={() => setPage(item.id)}
                        >
                            <span className="icon">{item.icon}</span>
                            <span>{item.label}</span>
                        </button>
                    ))}
                </nav>
                <div className="live-indicator">
                    <span className={`live-dot ${connected ? '' : 'disconnected'}`} />
                    {connected ? '实时同步中' : '未连接'}
                </div>
            </aside>

            <main className="main-content">
                {page === 'dashboard' && <DashboardPage data={projectInfo} key={refreshKey} />}
                {page === 'entities' && <EntitiesPage key={refreshKey} />}
                {page === 'graph' && <GraphPage key={refreshKey} />}
                {page === 'chapters' && <ChaptersPage key={refreshKey} />}
                {page === 'files' && <FilesPage />}
                {page === 'reading' && <ReadingPowerPage key={refreshKey} />}
                {page === 'publish' && <PublishPage key={refreshKey} />}
                {page === 'export' && <ExportPage key={refreshKey} />}
            </main>
        </div>
    )
}

const NAV_ITEMS = [
    { id: 'dashboard', icon: '📊', label: '数据总览' },
    { id: 'entities', icon: '👤', label: '设定词典' },
    { id: 'graph', icon: '🕸️', label: '关系图谱' },
    { id: 'chapters', icon: '📝', label: '章节一览' },
    { id: 'files', icon: '📁', label: '文档浏览' },
    { id: 'reading', icon: '🔥', label: '追读力' },
    { id: 'publish', icon: '📖', label: '小说发布' },
    { id: 'export', icon: '📦', label: '导出小说' },
]

const FULL_DATA_GROUPS = [
    { key: 'entities', title: '实体', columns: ['id', 'canonical_name', 'type', 'tier', 'first_appearance', 'last_appearance'], domain: 'core' },
    { key: 'chapters', title: '章节', columns: ['chapter', 'title', 'word_count', 'location', 'characters'], domain: 'core' },
    { key: 'scenes', title: '场景', columns: ['chapter', 'scene_index', 'location', 'time', 'summary'], domain: 'core' },
    { key: 'aliases', title: '别名', columns: ['alias', 'entity_id', 'entity_type'], domain: 'core' },
    { key: 'stateChanges', title: '状态变化', columns: ['entity_id', 'field', 'old_value', 'new_value', 'chapter'], domain: 'core' },
    { key: 'relationships', title: '关系', columns: ['from_entity', 'to_entity', 'type', 'chapter', 'description'], domain: 'network' },
    { key: 'relationshipEvents', title: '关系事件', columns: ['from_entity', 'to_entity', 'type', 'chapter', 'event_type', 'description'], domain: 'network' },
    { key: 'readingPower', title: '追读力', columns: ['chapter', 'hook_type', 'hook_strength', 'is_transition', 'override_count', 'debt_balance'], domain: 'network' },
    { key: 'overrides', title: 'Override 合约', columns: ['chapter', 'constraint_type', 'constraint_id', 'due_chapter', 'status'], domain: 'network' },
    { key: 'debts', title: '追读债务', columns: ['id', 'debt_type', 'current_amount', 'interest_rate', 'due_chapter', 'status'], domain: 'network' },
    { key: 'debtEvents', title: '债务事件', columns: ['debt_id', 'event_type', 'amount', 'chapter', 'note'], domain: 'network' },
    { key: 'reviewMetrics', title: '审查指标', columns: ['start_chapter', 'end_chapter', 'overall_score', 'severity_counts', 'created_at'], domain: 'quality' },
    { key: 'invalidFacts', title: '无效事实', columns: ['source_type', 'source_id', 'reason', 'status', 'chapter_discovered'], domain: 'quality' },
    { key: 'checklistScores', title: '写作清单评分', columns: ['chapter', 'template', 'score', 'completion_rate', 'completed_items', 'total_items'], domain: 'quality' },
    { key: 'ragQueries', title: 'RAG 查询日志', columns: ['query_type', 'query', 'results_count', 'latency_ms', 'chapter', 'created_at'], domain: 'ops' },
    { key: 'toolStats', title: '工具调用统计', columns: ['tool_name', 'success', 'retry_count', 'error_code', 'chapter', 'created_at'], domain: 'ops' },
]

const FULL_DATA_DOMAINS = [
    { id: 'overview', label: '总览' },
    { id: 'core', label: '基础档案' },
    { id: 'network', label: '关系与剧情' },
    { id: 'quality', label: '质量审查' },
    { id: 'ops', label: 'RAG 与工具' },
]


// ====================================================================
// 页面 1：数据总览
// ====================================================================

function DashboardPage({ data }) {
    if (!data) return <div className="loading">加载中…</div>

    const info = data.project_info || {}
    const progress = data.progress || {}
    const protagonist = data.protagonist_state || {}
    const strand = data.strand_tracker || {}
    const foreshadowing = data.plot_threads?.foreshadowing || []

    const totalWords = progress.total_words || 0
    const targetWords = info.target_words || 2000000
    const pct = targetWords > 0 ? Math.min(100, (totalWords / targetWords * 100)).toFixed(1) : 0

    const unresolvedForeshadow = foreshadowing.filter(f => {
        const s = (f.status || '').toLowerCase()
        return s !== '已回收' && s !== '已兑现' && s !== 'resolved'
    })

    // Strand 历史统计
    const history = strand.history || []
    const strandCounts = { quest: 0, fire: 0, constellation: 0 }
    history.forEach(h => { if (strandCounts[h.strand] !== undefined) strandCounts[h.strand]++ })
    const total = history.length || 1

    return (
        <>
            <div className="page-header">
                <h2>📊 数据总览</h2>
                <span className="card-badge badge-blue">{info.genre || '未知题材'}</span>
            </div>

            <div className="dashboard-grid">
                <div className="card stat-card">
                    <span className="stat-label">总字数</span>
                    <span className="stat-value">{formatNumber(totalWords)}</span>
                    <span className="stat-sub">目标 {formatNumber(targetWords)} 字 · {pct}%</span>
                    <div className="progress-track">
                        <div className="progress-fill" style={{ width: `${pct}%` }} />
                    </div>
                </div>

                <div className="card stat-card">
                    <span className="stat-label">当前章节</span>
                    <span className="stat-value">第 {progress.current_chapter || 0} 章</span>
                    <span className="stat-sub">目标 {info.target_chapters || '?'} 章 · 卷 {progress.current_volume || 1}</span>
                </div>

                <div className="card stat-card">
                    <span className="stat-label">主角状态</span>
                    <span className="stat-value plain">{protagonist.name || '未设定'}</span>
                    <span className="stat-sub">
                        {protagonist.power?.realm || '未知境界'}
                        {protagonist.location?.current ? ` · ${protagonist.location.current}` : ''}
                    </span>
                </div>

                <div className="card stat-card">
                    <span className="stat-label">未回收伏笔</span>
                    <span className="stat-value" style={{ color: unresolvedForeshadow.length > 10 ? 'var(--accent-red)' : 'var(--accent-amber)' }}>
                        {unresolvedForeshadow.length}
                    </span>
                    <span className="stat-sub">总计 {foreshadowing.length} 条伏笔</span>
                </div>
            </div>

            {/* Strand Weave 比例 */}
            <div className="card dashboard-section-card">
                <div className="card-header">
                    <span className="card-title">Strand Weave 节奏分布</span>
                    <span className="card-badge badge-purple">{strand.current_dominant || '?'}</span>
                </div>
                <div className="strand-bar">
                    <div className="segment strand-quest" style={{ width: `${(strandCounts.quest / total * 100).toFixed(1)}%` }} />
                    <div className="segment strand-fire" style={{ width: `${(strandCounts.fire / total * 100).toFixed(1)}%` }} />
                    <div className="segment strand-constellation" style={{ width: `${(strandCounts.constellation / total * 100).toFixed(1)}%` }} />
                </div>
                <div className="strand-legend">
                    <span>🔵 Quest {(strandCounts.quest / total * 100).toFixed(0)}%</span>
                    <span>🔴 Fire {(strandCounts.fire / total * 100).toFixed(0)}%</span>
                    <span>🟣 Constellation {(strandCounts.constellation / total * 100).toFixed(0)}%</span>
                </div>
            </div>

            {/* 伏笔列表 */}
            {unresolvedForeshadow.length > 0 ? (
                <div className="card dashboard-section-card">
                    <div className="card-header">
                        <span className="card-title">⚠️ 待回收伏笔 (Top 20)</span>
                    </div>
                    <div className="table-wrap">
                        <table className="data-table">
                            <thead><tr><th>内容</th><th>状态</th><th>埋设章</th></tr></thead>
                            <tbody>
                                {unresolvedForeshadow.slice(0, 20).map((f, i) => (
                                    <tr key={i}>
                                        <td className="truncate" style={{ maxWidth: 400 }}>{f.content || f.description || '—'}</td>
                                        <td><span className="card-badge badge-amber">{f.status || '未知'}</span></td>
                                        <td>{f.chapter || f.planted_chapter || '—'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            ) : null}

            <MergedDataView />
        </>
    )
}


// ====================================================================
// 页面 2：设定词典
// ====================================================================

function EntitiesPage() {
    const [entities, setEntities] = useState([])
    const [typeFilter, setTypeFilter] = useState('')
    const [selected, setSelected] = useState(null)
    const [changes, setChanges] = useState([])

    useEffect(() => {
        fetchJSON('/api/entities').then(setEntities).catch(() => { })
    }, [])

    useEffect(() => {
        if (selected) {
            fetchJSON('/api/state-changes', { entity: selected.id, limit: 30 }).then(setChanges).catch(() => setChanges([]))
        }
    }, [selected])

    const types = [...new Set(entities.map(e => e.type))].sort()
    const filteredEntities = typeFilter ? entities.filter(e => e.type === typeFilter) : entities

    return (
        <>
            <div className="page-header">
                <h2>👤 设定词典</h2>
                <span className="card-badge badge-green">{filteredEntities.length} / {entities.length} 个实体</span>
            </div>

            <div className="filter-group">
                <button className={`filter-btn ${typeFilter === '' ? 'active' : ''}`} onClick={() => setTypeFilter('')}>全部</button>
                {types.map(t => (
                    <button key={t} className={`filter-btn ${typeFilter === t ? 'active' : ''}`} onClick={() => setTypeFilter(t)}>{t}</button>
                ))}
            </div>

            <div className="split-layout">
                <div className="split-main">
                    <div className="card">
                        <div className="table-wrap">
                            <table className="data-table">
                                <thead><tr><th>名称</th><th>类型</th><th>层级</th><th>首现</th><th>末现</th></tr></thead>
                                <tbody>
                                    {filteredEntities.map(e => (
                                        <tr
                                            key={e.id}
                                            role="button"
                                            tabIndex={0}
                                            className={`entity-row ${selected?.id === e.id ? 'selected' : ''}`}
                                            onKeyDown={evt => (evt.key === 'Enter' || evt.key === ' ') && (evt.preventDefault(), setSelected(e))}
                                            onClick={() => setSelected(e)}
                                        >
                                            <td className={e.is_protagonist ? 'entity-name protagonist' : 'entity-name'}>
                                                {e.canonical_name} {e.is_protagonist ? '⭐' : ''}
                                            </td>
                                            <td><span className="card-badge badge-blue">{e.type}</span></td>
                                            <td>{e.tier}</td>
                                            <td>{e.first_appearance || '—'}</td>
                                            <td>{e.last_appearance || '—'}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>

                {selected && (
                    <div className="split-side">
                        <div className="card">
                            <div className="card-header">
                                <span className="card-title">{selected.canonical_name}</span>
                                <span className="card-badge badge-purple">{selected.tier}</span>
                            </div>
                            <div className="entity-detail">
                                <p><strong>类型：</strong>{selected.type}</p>
                                <p><strong>ID：</strong><code>{selected.id}</code></p>
                                {selected.desc && <p className="entity-desc">{selected.desc}</p>}
                                {selected.current_json && (
                                    <div className="entity-current-block">
                                        <strong>当前状态：</strong>
                                        <pre className="entity-json">
                                            {formatJSON(selected.current_json)}
                                        </pre>
                                    </div>
                                )}
                            </div>
                            {changes.length > 0 ? (
                                <div className="entity-history">
                                    <div className="card-title">状态变化历史</div>
                                    <div className="table-wrap">
                                        <table className="data-table">
                                            <thead><tr><th>章</th><th>字段</th><th>变化</th></tr></thead>
                                            <tbody>
                                                {changes.map((c, i) => (
                                                    <tr key={i}>
                                                        <td>{c.chapter}</td>
                                                        <td>{c.field}</td>
                                                        <td>{c.old_value} → {c.new_value}</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            ) : null}
                        </div>
                    </div>
                )}
            </div>
        </>
    )
}


// ====================================================================
// 页面 3：3D 宇宙关系图谱
// ====================================================================

function GraphPage() {
    const [graphData, setGraphData] = useState({ nodes: [], links: [] })
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [searchQuery, setSearchQuery] = useState('')
    const [typeFilter, setTypeFilter] = useState('')
    const [chapterFilter, setChapterFilter] = useState('')
    const [selectedNode, setSelectedNode] = useState(null)

    useEffect(() => {
        setLoading(true)
        fetchJSON('/api/relationships/graph')
            .then(data => {
                setGraphData(data)
                setError(null)
            })
            .catch(e => setError(e.message))
            .finally(() => setLoading(false))
    }, [])

    // 过滤后的数据
    const filteredNodes = useMemo(() => {
        return graphData.nodes.filter(n => {
            if (searchQuery && !n.name.includes(searchQuery) && !n.id.includes(searchQuery)) return false
            if (typeFilter && n.type !== typeFilter) return false
            if (chapterFilter) {
                const ch = parseInt(chapterFilter)
                if (ch && (n.last_appearance < ch || n.first_appearance > ch)) return false
            }
            return true
        })
    }, [graphData.nodes, searchQuery, typeFilter, chapterFilter])

    const filteredNodeIds = new Set(filteredNodes.map(n => n.id))
    const filteredLinks = useMemo(() => {
        return graphData.links.filter(l =>
            filteredNodeIds.has(l.source) && filteredNodeIds.has(l.target)
        )
    }, [graphData.links, filteredNodeIds])

    // 高亮逻辑 — 仅基于 selectedNode，避免 hover 触发重渲染导致场景闪烁
    const connectedNodeIds = useMemo(() => {
        if (!selectedNode) return null
        const ids = new Set([selectedNode.id])
        filteredLinks.forEach(l => {
            if (l.source === selectedNode.id) ids.add(l.target)
            if (l.target === selectedNode.id) ids.add(l.source)
        })
        return ids
    }, [selectedNode, filteredLinks])

    const highlightOpacity = !!selectedNode
    const highlightLinks = highlightOpacity ? new Set(
        filteredLinks
            .filter(l => l.source === selectedNode.id || l.target === selectedNode.id)
            .map(l => `${l.source}→${l.target}`)
    ) : null

    const entityTypes = useMemo(() => {
        const types = new Set(graphData.nodes.map(n => n.type))
        return [...types].sort()
    }, [graphData.nodes])

    const typeColors = {
        '角色': '#4f8ff7', '地点': '#34d399', '星球': '#22d3ee', '神仙': '#f59e0b',
        '势力': '#8b5cf6', '招式': '#ef4444', '法宝': '#ec4899'
    }

    function strengthColor(s) {
        if (s >= 0.8) return '#ef4444'
        if (s >= 0.5) return '#f59e0b'
        return 'rgba(127, 90, 240, 0.35)'
    }

    function resetFilters() {
        setSearchQuery('')
        setTypeFilter('')
        setChapterFilter('')
        setSelectedNode(null)
    }

    if (loading) return (
        <>
            <div className="page-header"><h2>🕸️ 关系图谱</h2></div>
            <div className="card" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 400 }}>
                <div className="loading">加载中…</div>
            </div>
        </>
    )

    if (error) return (
        <>
            <div className="page-header"><h2>🕸️ 关系图谱</h2></div>
            <div className="card" style={{ textAlign: 'center', padding: '3rem', color: '#f87171' }}>
                <p>加载失败: {error}</p>
                <button className="btn btn-primary" onClick={() => window.location.reload()}>重试</button>
            </div>
        </>
    )

    return (
        <>
            <div className="page-header">
                <h2>🕸️ 关系图谱</h2>
                <span className="card-badge badge-blue">{filteredNodes.length} 节点 · {filteredLinks.length} 链接</span>
            </div>

            {/* 工具栏 */}
            <div className="card" style={{ padding: '0.75rem 1rem' }}>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
                    <input className="filter-input" placeholder="搜索实体名称…" value={searchQuery}
                        onChange={e => setSearchQuery(e.target.value)}
                        style={{ padding: '0.4rem 0.6rem', borderRadius: '6px', border: '1px solid var(--border)', background: 'var(--bg-card)', color: 'var(--text)', width: 180 }} />
                    <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)}
                        style={{ padding: '0.4rem 0.6rem', borderRadius: '6px', border: '1px solid var(--border)', background: 'var(--bg-card)', color: 'var(--text)' }}>
                        <option value="">全部类型</option>
                        {entityTypes.map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                    <input type="number" min="1" placeholder="章节号过滤" value={chapterFilter}
                        onChange={e => setChapterFilter(e.target.value)}
                        style={{ padding: '0.4rem 0.6rem', borderRadius: '6px', border: '1px solid var(--border)', background: 'var(--bg-card)', color: 'var(--text)', width: 120 }} />
                    <button className="btn btn-sm" style={{ background: '#64748b', color: '#fff' }} onClick={resetFilters}>重置</button>
                    {selectedNode && (
                        <span style={{ marginLeft: 'auto', color: '#94a3b8', fontSize: '0.85rem' }}>
                            已选中: <strong style={{ color: '#e2e8f0' }}>{selectedNode.name}</strong>
                            <button className="btn btn-sm" style={{ marginLeft: '0.5rem', background: '#334155', color: '#94a3b8' }} onClick={() => setSelectedNode(null)}>取消</button>
                        </span>
                    )}
                </div>
            </div>

            <div className="card graph-shell" style={{ position: 'relative' }}>
                <ForceGraph3D
                    graphData={{ nodes: filteredNodes, links: filteredLinks }}
                    nodeLabel="name"
                    nodeColor="color"
                    nodeRelSize={6}
                    nodeOpacity={highlightOpacity ? n => (connectedNodeIds?.has(n.id) ? 1 : 0.15) : 1}
                    linkColor={d => {
                        const key = `${d.source}→${d.target}`
                        if (highlightLinks?.has(key)) return strengthColor(d.strength)
                        if (highlightOpacity) return 'rgba(127, 90, 240, 0.08)'
                        return strengthColor(d.strength)
                    }}
                    linkWidth={d => (highlightLinks?.has(`${d.source}→${d.target}`) ? d.width * 1.5 : d.width)}
                    linkDirectionalParticles={d => (highlightLinks?.has(`${d.source}→${d.target}`) ? 3 : 1)}
                    linkDirectionalParticleWidth={1.5}
                    linkDirectionalParticleSpeed={d => 0.005 + d.strength * 0.005}
                    linkLabel={d => `${d.name}\n第${d.first_chapter}-${d.last_chapter}章 · 强度${(d.strength * 100).toFixed(0)}%`}
                    backgroundColor="#fffaf0"
                    showNavInfo={false}
                    onNodeHover={node => {
                        document.body.style.cursor = node ? 'pointer' : 'default'
                    }}
                    onNodeClick={node => {
                        setSelectedNode(node === selectedNode ? null : node)
                    }}
                    onBackgroundClick={() => setSelectedNode(null)}
                />

                {/* 图例 */}
                <div style={{ position: 'absolute', bottom: 12, left: 12, background: 'rgba(15,23,42,0.85)', borderRadius: 8, padding: '0.5rem 0.75rem', fontSize: '0.75rem', color: '#cbd5e1', zIndex: 10, pointerEvents: 'none' }}>
                    <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>节点类型</div>
                    {Object.entries(typeColors).map(([type, color]) => (
                        <div key={type} style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', marginBottom: '0.15rem' }}>
                            <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, display: 'inline-block' }} />
                            {type}
                        </div>
                    ))}
                    <div style={{ marginTop: '0.4rem', fontWeight: 600 }}>链接强度</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', marginBottom: '0.15rem' }}>
                        <span style={{ width: 16, height: 3, borderRadius: 2, background: '#ef4444', display: 'inline-block' }} /> 强 (≥80%)
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', marginBottom: '0.15rem' }}>
                        <span style={{ width: 16, height: 3, borderRadius: 2, background: '#f59e0b', display: 'inline-block' }} /> 中 (50-79%)
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                        <span style={{ width: 16, height: 3, borderRadius: 2, background: 'rgba(127,90,240,0.35)', display: 'inline-block' }} /> 弱 (&lt;50%)
                    </div>
                </div>

                {/* 详情面板 */}
                {selectedNode && (() => {
                    const connectedLinks = filteredLinks.filter(l => l.source === selectedNode.id || l.target === selectedNode.id)
                    const connectedEntities = connectedLinks.map(l => {
                        const otherId = l.source === selectedNode.id ? l.target : l.source
                        const other = filteredNodes.find(n => n.id === otherId)
                        return { ...l, other: other || { name: otherId, type: '未知', color: '#5c6078' } }
                    })
                    return (
                        <div style={{
                            position: 'absolute', top: 0, right: 0, width: 320, height: '100%',
                            background: 'rgba(15,23,42,0.95)', borderLeft: '1px solid #334155',
                            padding: '1rem', overflowY: 'auto', zIndex: 20,
                            backdropFilter: 'blur(8px)',
                        }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                                <h3 style={{ margin: 0, color: '#f1f5f9', fontSize: '1rem' }}>{selectedNode.name}</h3>
                                <button onClick={() => setSelectedNode(null)} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: '1.2rem' }}>✕</button>
                            </div>
                            <div style={{ fontSize: '0.8rem', color: '#94a3b8', marginBottom: '1rem' }}>
                                <div>类型: <span style={{ color: selectedNode.color }}>{selectedNode.type}</span></div>
                                <div>等级: {selectedNode.tier}</div>
                                <div>首次出现: 第 {selectedNode.first_appearance} 章</div>
                                <div>最后出现: 第 {selectedNode.last_appearance} 章</div>
                                {selectedNode.is_protagonist && <div style={{ color: '#f59e0b' }}>⭐ 主角</div>}
                                {selectedNode.desc && <div style={{ marginTop: '0.5rem', color: '#cbd5e1' }}>{selectedNode.desc}</div>}
                            </div>
                            <div style={{ fontWeight: 600, fontSize: '0.85rem', color: '#e2e8f0', marginBottom: '0.5rem' }}>
                                关联 ({connectedEntities.length})
                            </div>
                            {connectedEntities.map((ce, i) => (
                                <div key={i} style={{
                                    padding: '0.5rem', marginBottom: '0.4rem', borderRadius: 6,
                                    background: 'rgba(51,65,85,0.5)', border: '1px solid #334155',
                                    cursor: 'pointer',
                                }} onClick={() => setSelectedNode(ce.other)}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                                        <span style={{ width: 8, height: 8, borderRadius: '50%', background: ce.other.color, display: 'inline-block' }} />
                                        <span style={{ color: '#e2e8f0', fontSize: '0.85rem' }}>{ce.other.name}</span>
                                    </div>
                                    <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginTop: '0.2rem' }}>{ce.name}</div>
                                    <div style={{ color: '#64748b', fontSize: '0.7rem' }}>
                                        第 {ce.first_chapter}-{ce.last_chapter} 章 · 强度 {(ce.strength * 100).toFixed(0)}%
                                    </div>
                                </div>
                            ))}
                        </div>
                    )
                })()}
            </div>
        </>
    )
}



// ====================================================================
// 页面 4：章节一览
// ====================================================================

function ChaptersPage() {
    const [chapters, setChapters] = useState([])

    useEffect(() => {
        fetchJSON('/api/chapters').then(setChapters).catch(() => { })
    }, [])

    const totalWords = chapters.reduce((s, c) => s + (c.word_count || 0), 0)

    return (
        <>
            <div className="page-header">
                <h2>📝 章节一览</h2>
                <span className="card-badge badge-green">{chapters.length} 章 · {formatNumber(totalWords)} 字</span>
            </div>
            <div className="card">
                <div className="table-wrap">
                    <table className="data-table">
                        <thead><tr><th>章节</th><th>标题</th><th>字数</th><th>地点</th><th>角色</th></tr></thead>
                        <tbody>
                            {chapters.map(c => (
                                <tr key={c.chapter}>
                                    <td className="chapter-no">第 {c.chapter} 章</td>
                                    <td>{c.title || '—'}</td>
                                    <td>{formatNumber(c.word_count || 0)}</td>
                                    <td>{c.location || '—'}</td>
                                    <td className="truncate chapter-characters">{c.characters || '—'}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
                {chapters.length === 0 ? <div className="empty-state"><div className="empty-icon">📭</div><p>暂无章节数据</p></div> : null}
            </div>
        </>
    )
}


// ====================================================================
// 页面 5：文档浏览
// ====================================================================

function FilesPage() {
    const [tree, setTree] = useState({})
    const [selectedPath, setSelectedPath] = useState(null)
    const [content, setContent] = useState('')

    useEffect(() => {
        fetchJSON('/api/files/tree').then(setTree).catch(() => { })
    }, [])

    useEffect(() => {
        if (selectedPath) {
            fetchJSON('/api/files/read', { path: selectedPath })
                .then(d => setContent(d.content))
                .catch(() => setContent('[读取失败]'))
        }
    }, [selectedPath])

    useEffect(() => {
        if (selectedPath) return
        const first = findFirstFilePath(tree)
        if (first) setSelectedPath(first)
    }, [tree, selectedPath])

    return (
        <>
            <div className="page-header">
                <h2>📁 文档浏览</h2>
            </div>
            <div className="file-layout">
                <div className="file-tree-pane">
                    {Object.entries(tree).map(([folder, items]) => (
                        <div key={folder} className="folder-block">
                            <div className="folder-title">📂 {folder}</div>
                            <ul className="file-tree">
                                <TreeNodes items={items} selected={selectedPath} onSelect={setSelectedPath} />
                            </ul>
                        </div>
                    ))}
                </div>
                <div className="file-content-pane">
                    {selectedPath ? (
                        <div>
                            <div className="selected-path">{selectedPath}</div>
                            <div className="file-preview">{content}</div>
                        </div>
                    ) : (
                        <div className="empty-state"><div className="empty-icon">📄</div><p>选择左侧文件以预览内容</p></div>
                    )}
                </div>
            </div>
        </>
    )
}


// ====================================================================
// 页面 6：追读力
// ====================================================================

function ReadingPowerPage() {
    const [data, setData] = useState([])

    useEffect(() => {
        fetchJSON('/api/reading-power', { limit: 50 }).then(setData).catch(() => { })
    }, [])

    return (
        <>
            <div className="page-header">
                <h2>🔥 追读力分析</h2>
                <span className="card-badge badge-amber">{data.length} 章数据</span>
            </div>
            <div className="card">
                <div className="table-wrap">
                    <table className="data-table">
                        <thead><tr><th>章节</th><th>钩子类型</th><th>钩子强度</th><th>过渡章</th><th>Override</th><th>债务余额</th></tr></thead>
                        <tbody>
                            {data.map(r => (
                                <tr key={r.chapter}>
                                    <td className="chapter-no">第 {r.chapter} 章</td>
                                    <td>{r.hook_type || '—'}</td>
                                    <td>
                                        <span className={`card-badge ${r.hook_strength === 'strong' ? 'badge-green' : r.hook_strength === 'weak' ? 'badge-red' : 'badge-amber'}`}>
                                            {r.hook_strength || '—'}
                                        </span>
                                    </td>
                                    <td>{r.is_transition ? '✅' : '—'}</td>
                                    <td>{r.override_count || 0}</td>
                                    <td className={r.debt_balance > 0 ? 'debt-positive' : 'debt-normal'}>{(r.debt_balance || 0).toFixed(2)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
                {data.length === 0 ? <div className="empty-state"><div className="empty-icon">🔥</div><p>暂无追读力数据</p></div> : null}
            </div>
        </>
    )
}


// ====================================================================
// 页面 7：小说发布
// ====================================================================

const PUB_PAGE_SIZE = 20

function PublishPage() {
    const [status, setStatus] = useState(null)
    const [books, setBooks] = useState([])
    const [selectedBook, setSelectedBook] = useState('')
    const [publishMode, setPublishMode] = useState('draft')
    const [publishing, setPublishing] = useState(false)
    const [task, setTask] = useState(null)
    const [showCreateForm, setShowCreateForm] = useState(false)
    const [newBook, setNewBook] = useState({ title: '', genre: '', synopsis: '', protagonist1: '', protagonist2: '' })
    const [toast, setToast] = useState(null)
    const [localChapters, setLocalChapters] = useState([])
    const [remoteChapters, setRemoteChapters] = useState([])
    const [remoteLoading, setRemoteLoading] = useState(false)
    const [selectedChapters, setSelectedChapters] = useState(new Set())
    const [chPage, setChPage] = useState(1)
    const [chFilter, setChFilter] = useState('all')

    function refreshLocalChapters() {
        fetchJSON('/api/chapters').then(setLocalChapters).catch(() => setLocalChapters([]))
    }

    useEffect(() => {
        fetchJSON('/api/publish/status').then(setStatus).catch(() => setStatus(null))
        fetchJSON('/api/publish/books').then(setBooks).catch(() => setBooks([]))
        fetchJSON('/api/chapters').then(setLocalChapters).catch(() => setLocalChapters([]))
    }, [])

    useEffect(() => {
        if (!selectedBook) {
            setRemoteChapters([])
            setSelectedChapters(new Set())
            return
        }
        setRemoteLoading(true)
        setRemoteChapters([])
        setSelectedChapters(new Set())
        setChPage(1)
        setChFilter('all')
        fetchJSON(`/api/publish/books/${encodeURIComponent(selectedBook)}/remote-chapters`)
            .then(data => {
                if (Array.isArray(data)) setRemoteChapters(data)
                else setRemoteChapters([])
            })
            .catch(() => setRemoteChapters([]))
            .finally(() => setRemoteLoading(false))
    }, [selectedBook])

    useEffect(() => {
        if (!task) return
        if (task.status === 'pending' || task.status === 'running') {
            const timer = setInterval(() => {
                fetchJSON(`/api/publish/task/${task.task_id}`)
                    .then(t => {
                        setTask(t)
                        if (t.status === 'success' || t.status === 'failed') {
                            clearInterval(timer)
                            setPublishing(false)
                        }
                    })
                    .catch(() => clearInterval(timer))
            }, 1500)
            return () => clearInterval(timer)
        }
    }, [task?.task_id, task?.status])

    function showToast(msg, type = 'success') {
        setToast({ msg, type })
        setTimeout(() => setToast(null), 3000)
    }

    const remoteChapterNos = new Set(remoteChapters.map(r => {
        const m = r.title && r.title.match(/第\s*(\d+)\s*章/)
        return m ? parseInt(m[1]) : 0
    }).filter(n => n > 0))

    const filteredChapters = localChapters.filter(c => {
        const isPublished = remoteChapterNos.has(c.chapter)
        if (chFilter === 'unpublished') return !isPublished
        if (chFilter === 'published') return isPublished
        return true
    })

    const unpublishedCount = localChapters.filter(c => !remoteChapterNos.has(c.chapter)).length
    const publishedCount = localChapters.filter(c => remoteChapterNos.has(c.chapter)).length
    const chTotalPages = Math.max(1, Math.ceil(filteredChapters.length / PUB_PAGE_SIZE))
    const safeChPage = Math.min(chPage, chTotalPages)
    const chPageStart = (safeChPage - 1) * PUB_PAGE_SIZE
    const chPageItems = filteredChapters.slice(chPageStart, chPageStart + PUB_PAGE_SIZE)

    function selectAll() { setSelectedChapters(new Set(filteredChapters.map(c => c.chapter))) }
    function selectUnpublished() {
        const unp = filteredChapters.filter(c => !remoteChapterNos.has(c.chapter)).map(c => c.chapter)
        setSelectedChapters(new Set(unp))
    }
    function clearAll() { setSelectedChapters(new Set()) }
    function toggleChapter(ch) {
        setSelectedChapters(prev => {
            const next = new Set(prev)
            if (next.has(ch)) next.delete(ch)
            else next.add(ch)
            return next
        })
    }

    async function handlePublish() {
        if (!selectedBook) { showToast('请先选择书籍', 'error'); return }
        if (selectedChapters.size === 0) { showToast('请至少选择一章', 'error'); return }
        setPublishing(true)
        setTask(null)
        const rangeSpec = [...selectedChapters].sort((a, b) => a - b).join(',')
        try {
            const params = new URLSearchParams({ book_id: selectedBook, range_spec: rangeSpec, publish_mode: publishMode })
            const res = await fetchJSON('/api/publish/chapters?' + params.toString(), { method: 'POST' })
            setTask({ task_id: res.task_id, status: 'pending', progress: 0, total: 0, message: '任务已创建', logs: [] })
            showToast('发布任务已创建')
        } catch (e) {
            showToast('发布失败: ' + e.message, 'error')
            setPublishing(false)
        }
    }

    async function handleCreateBook() {
        if (!newBook.title || !newBook.genre || !newBook.synopsis) { showToast('请填写必填项', 'error'); return }
        try {
            const params = new URLSearchParams({
                title: newBook.title, genre: newBook.genre, synopsis: newBook.synopsis,
                protagonist1: newBook.protagonist1, protagonist2: newBook.protagonist2,
            })
            const res = await fetchJSON('/api/publish/books?' + params.toString(), { method: 'POST' })
            showToast(`书籍创建成功！ID: ${res.book_id}`)
            setNewBook({ title: '', genre: '', synopsis: '', protagonist1: '', protagonist2: '' })
            setShowCreateForm(false)
            setBooks(await fetchJSON('/api/publish/books'))
        } catch (e) {
            showToast('创建失败: ' + e.message, 'error')
        }
    }

    const isReady = status?.ready
    const cliCmd = status?.login?.cli_command || ''

    return (
        <>
            <div className="page-header">
                <h2>📖 小说发布</h2>
                <span className={`card-badge ${isReady ? 'badge-green' : 'badge-red'}`}>{isReady ? '环境就绪' : '需要配置'}</span>
            </div>

            <div className="card">
                <div className="card-header"><span className="card-title">发布环境</span></div>
                {status ? (
                    <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap', alignItems: 'center' }}>
                        <div><span style={{ color: '#94a3b8', fontSize: '0.85rem' }}>Playwright</span><div style={{ color: status.playwright.available ? '#4ade80' : '#f87171' }}>{status.playwright.available ? `✅ 可用 (v${status.playwright.version})` : '❌ 未安装'}</div></div>
                        <div><span style={{ color: '#94a3b8', fontSize: '0.85rem' }}>番茄登录</span><div style={{ color: status.login.logged_in ? '#4ade80' : '#f87171' }}>{status.login.logged_in ? '✅ 已登录' : '❌ 未登录'}</div></div>
                        {!isReady && (<div style={{ background: '#1e293b', padding: '0.75rem 1rem', borderRadius: '8px', border: '1px solid #334155', maxWidth: 500 }}><div style={{ color: '#94a3b8', fontSize: '0.85rem', marginBottom: '0.5rem' }}>首次配置步骤：</div><code style={{ color: '#38bdf8', fontSize: '0.85rem' }}>{cliCmd}</code><div style={{ color: '#64748b', fontSize: '0.8rem', marginTop: '0.5rem' }}>运行此命令后，会弹出浏览器窗口，扫码登录即可。</div></div>)}
                    </div>
                ) : (<div className="loading">检查中…</div>)}
            </div>

            <div className="card">
                <div className="card-header"><span className="card-title">书籍管理</span><button className="btn btn-sm btn-primary" onClick={() => setShowCreateForm(!showCreateForm)}>{showCreateForm ? '取消' : '+ 创建新书'}</button></div>
                {showCreateForm && (
                    <div style={{ marginBottom: '1rem', padding: '1rem', background: '#0f172a', borderRadius: '8px', border: '1px solid #334155' }}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                            <input placeholder="小说标题 *" value={newBook.title} onChange={e => setNewBook(p => ({ ...p, title: e.target.value }))} style={{ padding: '0.5rem', borderRadius: '6px', border: '1px solid #334155', background: '#1e293b', color: '#e2e8f0' }} />
                            <input placeholder="题材（如玄幻、都市）*" value={newBook.genre} onChange={e => setNewBook(p => ({ ...p, genre: e.target.value }))} style={{ padding: '0.5rem', borderRadius: '6px', border: '1px solid #334155', background: '#1e293b', color: '#e2e8f0' }} />
                            <textarea placeholder="小说简介 *（至少50字）" value={newBook.synopsis} onChange={e => setNewBook(p => ({ ...p, synopsis: e.target.value }))} rows={3} style={{ gridColumn: '1 / -1', padding: '0.5rem', borderRadius: '6px', border: '1px solid #334155', background: '#1e293b', color: '#e2e8f0', resize: 'vertical' }} />
                            <input placeholder="主角1（可选）" value={newBook.protagonist1} onChange={e => setNewBook(p => ({ ...p, protagonist1: e.target.value }))} style={{ padding: '0.5rem', borderRadius: '6px', border: '1px solid #334155', background: '#1e293b', color: '#e2e8f0' }} />
                            <input placeholder="主角2（可选）" value={newBook.protagonist2} onChange={e => setNewBook(p => ({ ...p, protagonist2: e.target.value }))} style={{ padding: '0.5rem', borderRadius: '6px', border: '1px solid #334155', background: '#1e293b', color: '#e2e8f0' }} />
                        </div>
                        <button className="btn btn-sm btn-primary" style={{ marginTop: '0.75rem' }} onClick={handleCreateBook}>创建</button>
                    </div>
                )}
                {books.length === 0 ? (<div className="empty-state"><div className="empty-icon">📚</div><p>暂无书籍，请先在番茄作家后台创建</p></div>) : (
                    <div className="table-wrap">
                        <table className="data-table"><thead><tr><th>书名</th><th>ID</th><th>状态</th></tr></thead><tbody>{books.map(b => (<tr key={b.book_id} role="button" tabIndex={0} className={selectedBook === b.book_id ? 'selected' : ''} onClick={() => setSelectedBook(b.book_id)} onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), setSelectedBook(b.book_id))}><td>{b.book_name || '未命名'}</td><td><code style={{ fontSize: '0.8rem' }}>{b.book_id}</code></td><td>{b.status || '—'}</td></tr>))}</tbody></table>
                    </div>
                )}
            </div>

            <div className="card">
                <div className="card-header"><span className="card-title">章节选择</span><div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}><button className="btn btn-sm" style={{ background: '#475569', color: '#fff' }} onClick={refreshLocalChapters}>🔄 刷新</button><button className="btn btn-sm btn-primary" onClick={selectAll}>全选</button><button className="btn btn-sm btn-primary" onClick={selectUnpublished}>仅未发布 ({unpublishedCount})</button><button className="btn btn-sm" style={{ background: '#64748b', color: '#fff' }} onClick={clearAll}>清空</button></div></div>
                {selectedBook ? (<>
                    <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.75rem' }}>
                        {[{ key: 'all', label: `全部 (${localChapters.length})` }, { key: 'unpublished', label: `🆕 可发布 (${unpublishedCount})` }, { key: 'published', label: `✅ 已发布 (${publishedCount})` }].map(f => (<button key={f.key} className={`btn btn-sm ${chFilter === f.key ? 'btn-primary' : ''}`} style={chFilter === f.key ? {} : { background: '#334155', color: '#94a3b8' }} onClick={() => { setChFilter(f.key); setChPage(1) }}>{f.label}</button>))}
                    </div>
                    <div className="table-wrap" style={{ maxHeight: 480, overflowY: 'auto' }}>
                        <table className="data-table"><thead><tr><th style={{ width: 40 }}>☑</th><th>章节</th><th>标题</th><th>字数</th><th>状态</th></tr></thead><tbody>{chPageItems.map(c => { const isPublished = remoteChapterNos.has(c.chapter); const checked = selectedChapters.has(c.chapter); return (<tr key={c.chapter}><td><input type="checkbox" checked={checked} onChange={() => toggleChapter(c.chapter)} style={{ width: 16, height: 16, cursor: 'pointer' }} /></td><td className="chapter-no">第 {c.chapter} 章</td><td>{c.title || '—'}</td><td>{c.word_count ? c.word_count.toLocaleString() + ' 字' : '—'}</td><td>{isPublished ? <span className="card-badge badge-green">✅ 已发布</span> : <span className="card-badge badge-blue">🆕 可发布</span>}</td></tr>) })}</tbody></table>
                    </div>
                    {chTotalPages > 1 && (<div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginTop: '0.75rem', alignItems: 'center' }}><button className="btn btn-sm" disabled={safeChPage <= 1} onClick={() => setChPage(p => Math.max(1, p - 1))} style={safeChPage <= 1 ? { opacity: 0.4 } : {}}>上一页</button><span style={{ color: '#94a3b8', fontSize: '0.85rem' }}>第 {safeChPage} / {chTotalPages} 页</span><button className="btn btn-sm" disabled={safeChPage >= chTotalPages} onClick={() => setChPage(p => Math.min(chTotalPages, p + 1))} style={safeChPage >= chTotalPages ? { opacity: 0.4 } : {}}>下一页</button></div>)}
                    {remoteLoading && <div className="loading">加载平台章节中…</div>}
                </>) : (<div className="empty-state"><div className="empty-icon">📝</div><p>请先选择书籍以加载章节列表</p></div>)}
            </div>

            <div className="card">
                <div className="card-header"><span className="card-title">发布操作</span></div>
                <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
                    <div style={{ flex: 1, minWidth: 150 }}><label style={{ color: '#94a3b8', fontSize: '0.8rem', display: 'block', marginBottom: '0.25rem' }}>发布模式</label><select value={publishMode} onChange={e => setPublishMode(e.target.value)} style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid #334155', background: '#1e293b', color: '#e2e8f0' }}><option value="draft">草稿</option><option value="publish">直接发布</option></select></div>
                    <button className="btn btn-primary" disabled={publishing || !selectedBook || selectedChapters.size === 0} onClick={handlePublish} style={{ padding: '0.5rem 1.5rem' }}>{publishing ? '发布中…' : `发布选中章节 (${selectedChapters.size})`}</button>
                </div>
                {task && (
                    <div style={{ background: '#0f172a', borderRadius: '8px', border: '1px solid #334155', padding: '1rem', marginTop: '1rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}><span style={{ color: '#94a3b8', fontSize: '0.85rem' }}>任务 {task.task_id}</span><span className={`card-badge ${task.status === 'success' ? 'badge-green' : task.status === 'failed' ? 'badge-red' : task.status === 'running' ? 'badge-blue' : 'badge-amber'}`}>{task.status === 'success' ? '✅ 完成' : task.status === 'failed' ? '❌ 失败' : task.status === 'running' ? '⏳ 进行中' : '等待中'}</span></div>
                        {task.total > 0 && (<div style={{ marginBottom: '0.5rem' }}><div style={{ background: '#1e293b', borderRadius: '4px', height: '8px', overflow: 'hidden' }}><div style={{ width: `${(task.progress / task.total * 100).toFixed(0)}%`, height: '100%', background: task.status === 'failed' ? '#ef4444' : '#3b82f6', transition: 'width 0.3s' }} /></div><span style={{ color: '#64748b', fontSize: '0.75rem' }}>{task.progress} / {task.total}</span></div>)}
                        {task.message && <div style={{ color: '#cbd5e1', fontSize: '0.85rem', marginBottom: '0.5rem' }}>{task.message}</div>}
                        {task.logs.length > 0 && (<div style={{ background: '#1e293b', borderRadius: '6px', padding: '0.75rem', maxHeight: 200, overflowY: 'auto', fontFamily: 'monospace', fontSize: '0.8rem', color: '#94a3b8', whiteSpace: 'pre-wrap' }}>{task.logs.map((l, i) => <div key={i}>{l}</div>)}</div>)}
                    </div>
                )}
            </div>

            {toast && (<div style={{ position: 'fixed', bottom: '2rem', right: '2rem', padding: '0.75rem 1.25rem', borderRadius: '8px', fontSize: '0.9rem', zIndex: 200, background: toast.type === 'error' ? '#7f1d1d' : '#166534', color: toast.type === 'error' ? '#f87171' : '#4ade80', border: `1px solid ${toast.type === 'error' ? '#ef4444' : '#22c55e'}` }}>{toast.msg}</div>)}
        </>
    )
}


function findFirstFilePath(tree) {
    const roots = Object.values(tree || {})
    for (const items of roots) {
        const p = walkFirstFile(items)
        if (p) return p
    }
    return null
}

function walkFirstFile(items) {
    if (!Array.isArray(items)) return null
    for (const item of items) {
        if (item?.type === 'file' && item?.path) return item.path
        if (item?.type === 'dir' && Array.isArray(item.children)) {
            const p = walkFirstFile(item.children)
            if (p) return p
        }
    }
    return null
}


// ====================================================================
// 数据总览内嵌：全量数据视图
// ====================================================================

function MergedDataView() {
    const [loading, setLoading] = useState(true)
    const [payload, setPayload] = useState({})
    const [domain, setDomain] = useState('overview')

    useEffect(() => {
        let disposed = false

        async function loadAll() {
            setLoading(true)
            const requests = [
                ['entities', fetchJSON('/api/entities')],
                ['chapters', fetchJSON('/api/chapters')],
                ['scenes', fetchJSON('/api/scenes', { limit: 200 })],
                ['relationships', fetchJSON('/api/relationships', { limit: 300 })],
                ['relationshipEvents', fetchJSON('/api/relationship-events', { limit: 200 })],
                ['readingPower', fetchJSON('/api/reading-power', { limit: 100 })],
                ['reviewMetrics', fetchJSON('/api/review-metrics', { limit: 50 })],
                ['stateChanges', fetchJSON('/api/state-changes', { limit: 120 })],
                ['aliases', fetchJSON('/api/aliases')],
                ['overrides', fetchJSON('/api/overrides', { limit: 120 })],
                ['debts', fetchJSON('/api/debts', { limit: 120 })],
                ['debtEvents', fetchJSON('/api/debt-events', { limit: 150 })],
                ['invalidFacts', fetchJSON('/api/invalid-facts', { limit: 120 })],
                ['ragQueries', fetchJSON('/api/rag-queries', { limit: 150 })],
                ['toolStats', fetchJSON('/api/tool-stats', { limit: 200 })],
                ['checklistScores', fetchJSON('/api/checklist-scores', { limit: 120 })],
            ]

            const entries = await Promise.all(
                requests.map(async ([key, p]) => {
                    try {
                        const val = await p
                        return [key, val]
                    } catch {
                        return [key, []]
                    }
                }),
            )
            if (!disposed) {
                setPayload(Object.fromEntries(entries))
                setLoading(false)
            }
        }

        loadAll()
        return () => { disposed = true }
    }, [])

    if (loading) return <div className="loading">加载全量数据中…</div>

    const groups = domain === 'overview'
        ? FULL_DATA_GROUPS
        : FULL_DATA_GROUPS.filter(g => g.domain === domain)
    const totalRows = FULL_DATA_GROUPS.reduce((sum, g) => sum + (payload[g.key] || []).length, 0)
    const nonEmptyGroups = FULL_DATA_GROUPS.filter(g => (payload[g.key] || []).length > 0).length
    const maxChapter = FULL_DATA_GROUPS.reduce((max, g) => {
        const rows = payload[g.key] || []
        rows.slice(0, 120).forEach(r => {
            const c = extractChapter(r)
            if (c > max) max = c
        })
        return max
    }, 0)
    const domainStats = FULL_DATA_DOMAINS.filter(d => d.id !== 'overview').map(d => {
        const ds = FULL_DATA_GROUPS.filter(g => g.domain === d.id)
        const rowCount = ds.reduce((sum, g) => sum + (payload[g.key] || []).length, 0)
        const filled = ds.filter(g => (payload[g.key] || []).length > 0).length
        return { ...d, rowCount, filled, total: ds.length }
    })

    return (
        <>
            <div className="page-header section-page-header">
                <h2>🧪 全量数据视图</h2>
                <span className="card-badge badge-cyan">{FULL_DATA_GROUPS.length} 类数据源</span>
            </div>

            <div className="demo-summary-grid">
                <div className="card stat-card">
                    <span className="stat-label">总记录数</span>
                    <span className="stat-value">{formatNumber(totalRows)}</span>
                    <span className="stat-sub">当前返回的全部数据行</span>
                </div>
                <div className="card stat-card">
                    <span className="stat-label">已覆盖数据源</span>
                    <span className="stat-value plain">{nonEmptyGroups}/{FULL_DATA_GROUPS.length}</span>
                    <span className="stat-sub">有数据的表 / 总表数</span>
                </div>
                <div className="card stat-card">
                    <span className="stat-label">最新章节触达</span>
                    <span className="stat-value plain">{maxChapter > 0 ? `第 ${maxChapter} 章` : '—'}</span>
                    <span className="stat-sub">按可识别 chapter 字段估算</span>
                </div>
                <div className="card stat-card">
                    <span className="stat-label">当前视图</span>
                    <span className="stat-value plain">{FULL_DATA_DOMAINS.find(d => d.id === domain)?.label}</span>
                    <span className="stat-sub">{groups.length} 个数据分组</span>
                </div>
            </div>

            <div className="demo-domain-tabs">
                {FULL_DATA_DOMAINS.map(item => (
                    <button
                        key={item.id}
                        className={`demo-domain-tab ${domain === item.id ? 'active' : ''}`}
                        onClick={() => setDomain(item.id)}
                    >
                        {item.label}
                    </button>
                ))}
            </div>

            {domain === 'overview' ? (
                <div className="demo-domain-grid">
                    {domainStats.map(ds => (
                        <div className="card" key={ds.id}>
                            <div className="card-header">
                                <span className="card-title">{ds.label}</span>
                                <span className="card-badge badge-purple">{ds.filled}/{ds.total}</span>
                            </div>
                            <div className="domain-stat-number">{formatNumber(ds.rowCount)}</div>
                            <div className="stat-sub">该数据域总记录数</div>
                        </div>
                    ))}
                </div>
            ) : null}

            {groups.map(g => {
                const count = (payload[g.key] || []).length
                return (
                    <div className="card demo-group-card" key={g.key}>
                        <div className="card-header">
                            <span className="card-title">{g.title}</span>
                            <span className={`card-badge ${count > 0 ? 'badge-blue' : 'badge-amber'}`}>{count} 条</span>
                        </div>
                        <MiniTable
                            rows={payload[g.key] || []}
                            columns={g.columns}
                            pageSize={12}
                        />
                    </div>
                )
            })}
        </>
    )
}

function MiniTable({ rows, columns, pageSize = 12 }) {
    const [page, setPage] = useState(1)

    useEffect(() => {
        setPage(1)
    }, [rows, columns, pageSize])

    if (!rows || rows.length === 0) {
        return <div className="empty-state compact"><p>暂无数据</p></div>
    }

    const totalPages = Math.max(1, Math.ceil(rows.length / pageSize))
    const safePage = Math.min(page, totalPages)
    const start = (safePage - 1) * pageSize
    const list = rows.slice(start, start + pageSize)

    return (
        <>
            <div className="table-wrap">
                <table className="data-table">
                    <thead>
                        <tr>{columns.map(c => <th key={c}>{c}</th>)}</tr>
                    </thead>
                    <tbody>
                        {list.map((row, i) => (
                            <tr key={i}>
                                {columns.map(c => (
                                    <td key={c} className="truncate" style={{ maxWidth: 240 }}>
                                        {formatCell(row?.[c])}
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            <div className="table-pagination">
                <button
                    className="page-btn"
                    type="button"
                    onClick={() => setPage(p => Math.max(1, p - 1))}
                    disabled={safePage <= 1}
                >
                    上一页
                </button>
                <span className="page-info">
                    第 {safePage} / {totalPages} 页 · 共 {rows.length} 条
                </span>
                <button
                    className="page-btn"
                    type="button"
                    onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                    disabled={safePage >= totalPages}
                >
                    下一页
                </button>
            </div>
        </>
    )
}

function extractChapter(row) {
    if (!row || typeof row !== 'object') return 0
    const candidates = [
        row.chapter,
        row.start_chapter,
        row.end_chapter,
        row.chapter_discovered,
        row.first_appearance,
        row.last_appearance,
    ]
    for (const c of candidates) {
        const n = Number(c)
        if (Number.isFinite(n) && n > 0) return n
    }
    return 0
}


// ====================================================================
// 子组件：文件树递归
// ====================================================================

function TreeNodes({ items, selected, onSelect, depth = 0 }) {
    const [expanded, setExpanded] = useState({})
    if (!items || items.length === 0) return null

    return items.map((item, i) => {
        const key = item.path || `${depth}-${i}`
        if (item.type === 'dir') {
            const isOpen = expanded[key]
            return (
                <li key={key}>
                    <div
                        className="tree-item"
                        role="button"
                        tabIndex={0}
                        onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), setExpanded(prev => ({ ...prev, [key]: !prev[key] })))}
                        onClick={() => setExpanded(prev => ({ ...prev, [key]: !prev[key] }))}
                    >
                        <span className="tree-icon">{isOpen ? '📂' : '📁'}</span>
                        <span>{item.name}</span>
                    </div>
                    {isOpen && item.children && (
                        <ul className="tree-children">
                            <TreeNodes items={item.children} selected={selected} onSelect={onSelect} depth={depth + 1} />
                        </ul>
                    )}
                </li>
            )
        }
        return (
            <li key={key}>
                <div
                    className={`tree-item ${selected === item.path ? 'active' : ''}`}
                    role="button"
                    tabIndex={0}
                    onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onSelect(item.path))}
                    onClick={() => onSelect(item.path)}
                >
                    <span className="tree-icon">📄</span>
                    <span>{item.name}</span>
                </div>
            </li>
        )
    })
}


// ====================================================================
// 辅助：数字格式化
// ====================================================================

function formatNumber(n) {
    if (n >= 10000) return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 }).format(n / 10000) + ' 万'
    return new Intl.NumberFormat('zh-CN').format(n)
}

function formatJSON(str) {
    try {
        return JSON.stringify(JSON.parse(str), null, 2)
    } catch {
        return str
    }
}

function formatCell(v) {
    if (v === null || v === undefined) return '—'
    if (typeof v === 'boolean') return v ? 'true' : 'false'
    if (typeof v === 'object') {
        try {
            return JSON.stringify(v)
        } catch {
            return String(v)
        }
    }
    const s = String(v)
    return s.length > 180 ? `${s.slice(0, 180)}...` : s
}


// ====================================================================
// 页面 8：导出小说
// ====================================================================

const FORMAT_OPTIONS = [
    { key: 'txt', label: 'TXT', icon: '📝', desc: '纯文本，最通用', color: '#5d8a66' },
    { key: 'markdown', label: 'Markdown', icon: '📋', desc: '保留格式，易编辑', color: '#4a7ab5' },
    { key: 'epub', label: 'EPUB', icon: '📱', desc: '电子书格式', color: '#9b6b9e' },
]

function ExportPage() {
    const [format, setFormat] = useState('markdown')
    const [range, setRange] = useState('all')
    const [author, setAuthor] = useState('')
    const [exporting, setExporting] = useState(false)
    const [info, setInfo] = useState(null)
    const [result, setResult] = useState(null)
    const [history, setHistory] = useState([])
    const [activeTab, setActiveTab] = useState('export')

    useEffect(() => {
        fetchJSON('/api/export/info').then(setInfo).catch(() => setInfo(null))
        fetchJSON('/api/export/files').then(setHistory).catch(() => setHistory([]))
    }, [])

    async function handleExport() {
        setExporting(true)
        setResult(null)
        try {
            const res = await fetchJSON('/api/export/do', {
                method: 'POST',
                body: JSON.stringify({
                    format,
                    range_spec: range || 'all',
                    author: author,
                }),
            })
            setResult(res)
            if (res.success) {
                fetchJSON('/api/export/files').then(setHistory).catch(() => {})
            }
        } catch (e) {
            setResult({ success: false, error: e.message })
        }
        setExporting(false)
    }

    function formatSize(bytes) {
        if (bytes < 1024) return bytes + ' B'
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
        return (bytes / 1024 / 1024).toFixed(2) + ' MB'
    }

    function formatDate(timestamp) {
        return new Date(timestamp * 1000).toLocaleString('zh-CN', {
            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
        })
    }

    return (
        <div className="export-page">
            <div className="page-header">
                <h2>📦 导出小说</h2>
            </div>

            <div className="export-tabs">
                <button
                    className={`export-tab ${activeTab === 'export' ? 'active' : ''}`}
                    onClick={() => setActiveTab('export')}
                >
                    <span className="tab-icon">✨</span>
                    <span>新建导出</span>
                </button>
                <button
                    className={`export-tab ${activeTab === 'history' ? 'active' : ''}`}
                    onClick={() => setActiveTab('history')}
                >
                    <span className="tab-icon">📁</span>
                    <span>导出历史</span>
                    {history.length > 0 && <span className="tab-badge">{history.length}</span>}
                </button>
            </div>

            {activeTab === 'export' ? (
                <div className="export-content">
                    {info && (
                        <div className="export-summary">
                            <div className="summary-item">
                                <span className="summary-icon">📚</span>
                                <span className="summary-value">{info.chapter_count}</span>
                                <span className="summary-label">章节</span>
                            </div>
                            <div className="summary-divider" />
                            <div className="summary-item">
                                <span className="summary-icon">📖</span>
                                <span className="summary-value">{info.chapter_range}</span>
                                <span className="summary-label">章节范围</span>
                            </div>
                            {info.cover_exists || info.cover_png_exists ? (
                                <>
                                    <div className="summary-divider" />
                                    <div className="summary-item">
                                        <span className="summary-icon">🖼️</span>
                                        <span className="summary-value" style={{ color: 'var(--accent-green)' }}>已检测</span>
                                        <span className="summary-label">封面</span>
                                    </div>
                                </>
                            ) : null}
                            {info.style_exists ? (
                                <>
                                    <div className="summary-divider" />
                                    <div className="summary-item">
                                        <span className="summary-icon">🎨</span>
                                        <span className="summary-value" style={{ color: 'var(--accent-green)' }}>已检测</span>
                                        <span className="summary-label">样式</span>
                                    </div>
                                </>
                            ) : null}
                        </div>
                    )}

                    <div className="export-card">
                        <div className="export-card-header">
                            <h3>输出格式</h3>
                        </div>
                        <div className="format-grid">
                            {FORMAT_OPTIONS.map(opt => (
                                <button
                                    key={opt.key}
                                    className={`format-option ${format === opt.key ? 'selected' : ''}`}
                                    onClick={() => setFormat(opt.key)}
                                    style={{ '--format-color': opt.color }}
                                >
                                    <span className="format-icon">{opt.icon}</span>
                                    <span className="format-label">{opt.label}</span>
                                    <span className="format-desc">{opt.desc}</span>
                                    {format === opt.key && <span className="format-check">✓</span>}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div className="export-card">
                        <div className="export-card-header">
                            <h3>导出范围</h3>
                        </div>
                        <div className="range-section">
                            <div className="range-presets">
                                <button
                                    className={`range-preset ${range === 'all' ? 'active' : ''}`}
                                    onClick={() => setRange('all')}
                                >
                                    全部章节
                                </button>
                                <button
                                    className={`range-preset ${range === `${info?.chapter_min || 1}-${info?.chapter_max || 10}` ? 'active' : ''}`}
                                    onClick={() => setRange(`${info?.chapter_min || 1}-${info?.chapter_max || 10}`)}
                                >
                                    当前进度
                                </button>
                            </div>
                            <div className="range-input-group">
                                <label>自定义范围</label>
                                <input
                                    type="text"
                                    value={range}
                                    onChange={e => setRange(e.target.value)}
                                    placeholder="all / 1-10 / 1,3,5"
                                    className="range-input"
                                />
                            </div>
                        </div>
                    </div>

                    {format === 'epub' && (
                        <div className="export-card">
                            <div className="export-card-header">
                                <h3>EPUB 设置</h3>
                            </div>
                            <div className="epub-settings">
                                <div className="setting-row">
                                    <label>作者名</label>
                                    <input
                                        type="text"
                                        value={author}
                                        onChange={e => setAuthor(e.target.value)}
                                        placeholder="输入作者名（EPUB 元数据）"
                                        className="setting-input"
                                    />
                                </div>
                                {info && (info.cover_exists || info.cover_png_exists) && (
                                    <div className="setting-hint">
                                        🖼️ 已自动检测封面文件，导出时将自动应用
                                    </div>
                                )}
                                {info?.style_exists && (
                                    <div className="setting-hint">
                                        🎨 已自动检测样式文件，导出时将自动应用
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    <button
                        className="export-button"
                        onClick={handleExport}
                        disabled={exporting || !info?.chapter_count}
                    >
                        {exporting ? (
                            <>
                                <span className="export-spinner" />
                                <span>导出中...</span>
                            </>
                        ) : (
                            <>
                                <span className="export-icon">🚀</span>
                                <span>开始导出</span>
                            </>
                        )}
                    </button>

                    {result && (
                        <div className={`export-result ${result.success ? 'success' : 'error'}`}>
                            {result.success ? (
                                <>
                                    <div className="result-header">
                                        <span className="result-icon">✅</span>
                                        <span>导出成功</span>
                                    </div>
                                    <div className="result-details">
                                        <div className="result-row">
                                            <span>格式</span>
                                            <span className="result-value">{result.format.toUpperCase()}</span>
                                        </div>
                                        <div className="result-row">
                                            <span>章节</span>
                                            <span className="result-value">{result.chapter_count} 章</span>
                                        </div>
                                        <div className="result-row">
                                            <span>文件</span>
                                            <span className="result-value">{result.filename}</span>
                                        </div>
                                        <div className="result-row">
                                            <span>大小</span>
                                            <span className="result-value">{formatSize(result.file_size)}</span>
                                        </div>
                                    </div>
                                    <a
                                        href={`/api/export/download/${encodeURIComponent(result.filename)}`}
                                        className="download-link"
                                        target="_blank"
                                        rel="noopener noreferrer"
                                    >
                                        <span>📥</span> 下载文件
                                    </a>
                                </>
                            ) : (
                                <>
                                    <div className="result-header">
                                        <span className="result-icon">❌</span>
                                        <span>导出失败</span>
                                    </div>
                                    <div className="result-error">{result.error}</div>
                                </>
                            )}
                        </div>
                    )}
                </div>
            ) : (
                <div className="history-content">
                    {history.length === 0 ? (
                        <div className="empty-state">
                            <div className="empty-icon">📦</div>
                            <p>暂无导出历史</p>
                            <p className="empty-hint">完成导出后，文件将显示在这里</p>
                        </div>
                    ) : (
                        <div className="history-list">
                            {history.map(item => (
                                <div key={item.filename} className="history-item">
                                    <div className="history-icon">
                                        {item.format === 'epub' ? '📱' : item.format === 'markdown' ? '📋' : '📝'}
                                    </div>
                                    <div className="history-info">
                                        <div className="history-name">{item.filename}</div>
                                        <div className="history-meta">
                                            <span className="history-format">{item.format.toUpperCase()}</span>
                                            <span className="history-size">{formatSize(item.size)}</span>
                                            <span className="history-date">{formatDate(item.modified)}</span>
                                        </div>
                                    </div>
                                    <a
                                        href={`/api/export/download/${encodeURIComponent(item.filename)}`}
                                        className="history-download"
                                        target="_blank"
                                        rel="noopener noreferrer"
                                    >
                                        📥
                                    </a>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}

