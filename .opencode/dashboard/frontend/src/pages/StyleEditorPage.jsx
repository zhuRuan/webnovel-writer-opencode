import { useEffect, useState, useCallback, useMemo } from 'react'
import { useDashboardContext } from '../App.jsx'
import Badge from '../components/Badge.jsx'
import {
    fetchMasterSetting,
    updateMasterSetting,
    fetchAntiPatterns,
    addAntiPattern,
    deleteAntiPattern,
    fetchTechniques,
    fetchChapterContracts,
    fetchChapterContract,
    fetchReviewerChecklist,
} from '../api.js'

const TABS = [
    { key: 'master', label: '全局文风' },
    { key: 'anti', label: '禁止模式' },
    { key: 'techniques', label: '写作技法' },
    { key: 'chapter', label: '章级合同' },
    { key: 'reviewer', label: '审查维度' },
]

const CATEGORY_COLORS = {
    '对话': 'blue', '情感': 'purple', '场景': 'green',
    '节奏': 'amber', '战斗': 'red', '叙事': 'cyan',
}

/* ── Tab 1: 全局文风 ── */

function MasterSettingTab() {
    const [data, setData] = useState(null)
    const [editing, setEditing] = useState({})
    const [saving, setSaving] = useState(false)
    const [msg, setMsg] = useState(null)

    useEffect(() => {
        fetchMasterSetting().then(setData).catch(e => setData({ _error: e.message }))
    }, [])

    const constraints = data?.master_constraints || {}
    const locked = (data?.override_policy?.locked || []).map(s => s.replace('master_constraints.', ''))

    const handleChange = (key, rawValue) => {
        const original = constraints[key]
        let parsed = rawValue
        if (typeof original === 'number' || typeof original === 'boolean') {
            try { parsed = JSON.parse(rawValue) } catch { parsed = rawValue }
        } else if (typeof original === 'object' && original !== null) {
            try { parsed = JSON.parse(rawValue) } catch { parsed = rawValue }
        }
        setEditing(prev => ({ ...prev, [key]: parsed }))
        setMsg(null)
    }

    const handleSave = async () => {
        setSaving(true)
        setMsg(null)
        try {
            const result = await updateMasterSetting(editing)
            setData(prev => ({ ...prev, master_constraints: result.master_constraints }))
            setEditing({})
            setMsg({ type: 'success', text: '保存成功' })
        } catch (e) {
            setMsg({ type: 'error', text: e.message })
        } finally {
            setSaving(false)
        }
    }

    const displayValue = (key) => {
        const val = editing[key] !== undefined ? editing[key] : constraints[key]
        if (typeof val === 'object' && val !== null) return JSON.stringify(val)
        return String(val ?? '')
    }

    const allKeys = Object.keys(constraints)
    const hasChanges = Object.keys(editing).length > 0

    if (!data) return <div className="empty-state">加载中...</div>
    if (data._error) return <div className="empty-state" style={{ color: 'var(--accent-red)' }}>加载失败: {data._error}</div>
    if (allKeys.length === 0) return <div className="empty-state">暂无 master_constraints 配置</div>

    return (
        <div className="card">
            <div className="card-header">
                <span className="card-title">master_constraints</span>
                <span className="mini-label">对所有章节生效</span>
            </div>
            <div className="section-label">字段编辑</div>
            {allKeys.map(key => (
                <div key={key} style={{ marginBottom: 10 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4, fontWeight: 700, fontSize: 13 }}>
                        {key}
                        {locked.includes(key) && <Badge tone="red">锁定</Badge>}
                    </label>
                    <input
                        type="text"
                        value={displayValue(key)}
                        onChange={e => handleChange(key, e.target.value)}
                        disabled={locked.includes(key)}
                        style={{
                            width: '100%', maxWidth: 480, padding: '6px 10px',
                            border: '2px solid var(--border-main)', borderRadius: 0,
                            background: locked.includes(key) ? 'var(--bg-card-2)' : '#fffef8',
                            color: 'var(--text-main)', fontWeight: 500,
                            boxShadow: locked.includes(key) ? 'none' : 'var(--shadow-soft)',
                        }}
                    />
                </div>
            ))}
            {hasChanges && (
                <button onClick={handleSave} disabled={saving} className="page-btn" style={{ marginTop: 12 }}>
                    {saving ? '保存中...' : '保存'}
                </button>
            )}
            {msg && (
                <p style={{ marginTop: 8, color: msg.type === 'error' ? 'var(--accent-red)' : 'var(--accent-green)', fontWeight: 600 }}>
                    {msg.text}
                </p>
            )}
        </div>
    )
}

/* ── Tab 2: 禁止模式 ── */

function AntiPatternsTab() {
    const [patterns, setPatterns] = useState([])
    const [newText, setNewText] = useState('')
    const [msg, setMsg] = useState(null)
    const [loading, setLoading] = useState(false)

    const reload = useCallback(() => {
        fetchAntiPatterns().then(d => setPatterns(d.patterns || [])).catch(() => {})
    }, [])

    useEffect(() => { reload() }, [reload])

    const handleAdd = async () => {
        if (!newText.trim()) return
        setLoading(true)
        setMsg(null)
        try {
            await addAntiPattern(newText.trim())
            setNewText('')
            setMsg({ type: 'success', text: '添加成功' })
            reload()
        } catch (e) {
            setMsg({ type: 'error', text: e.message })
        } finally {
            setLoading(false)
        }
    }

    const handleDelete = async (text) => {
        if (!confirm(`确认删除反模式：${text}？`)) return
        setMsg(null)
        try {
            await deleteAntiPattern(text)
            setMsg({ type: 'success', text: '已删除' })
            reload()
        } catch (e) {
            setMsg({ type: 'error', text: e.message })
        }
    }

    return (
        <div className="card">
            <div className="card-header">
                <span className="card-title">禁止模式</span>
                <span className="mini-label">审查阶段 reviewer 自动检查</span>
            </div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                <input
                    type="text"
                    value={newText}
                    onChange={e => setNewText(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && !loading && handleAdd()}
                    placeholder="输入新的反模式..."
                    style={{
                        flex: 1, padding: '6px 10px',
                        border: '2px solid var(--border-main)', borderRadius: 0,
                        background: '#fffef8', color: 'var(--text-main)', fontWeight: 500,
                        boxShadow: 'var(--shadow-soft)',
                    }}
                />
                <button onClick={handleAdd} disabled={loading || !newText.trim()} className="page-btn">
                    {loading ? '...' : '添加'}
                </button>
            </div>
            {msg && (
                <p style={{ marginBottom: 8, color: msg.type === 'error' ? 'var(--accent-red)' : 'var(--accent-green)', fontWeight: 600 }}>
                    {msg.text}
                </p>
            )}
            {patterns.length === 0 ? (
                <div className="empty-state compact">暂无反模式</div>
            ) : (
                <div className="table-wrap">
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>反模式内容</th>
                                <th>来源</th>
                                <th style={{ textAlign: 'right' }}>操作</th>
                            </tr>
                        </thead>
                        <tbody>
                            {patterns.map((p, i) => (
                                <tr key={p.text}>
                                    <td style={{ color: 'var(--text-mute)', fontSize: 13 }}>{i + 1}</td>
                                    <td>{p.text}</td>
                                    <td>
                                        <Badge tone={p.source_table === 'dashboard_manual' ? 'cyan' : 'neutral'}>
                                            {p.source_table || '手动'}
                                        </Badge>
                                    </td>
                                    <td style={{ textAlign: 'right' }}>
                                        <button onClick={() => handleDelete(p.text)} className="page-btn" style={{ padding: '2px 8px', minHeight: 24, fontSize: 12 }}>
                                            删除
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
            <p style={{ marginTop: 10, color: 'var(--text-mute)', fontSize: 13, fontWeight: 600 }}>
                共 {patterns.length} 条反模式
            </p>
        </div>
    )
}

/* ── Tab 3: 写作技法 ── */

function TechniquesTab() {
    const [techniques, setTechniques] = useState([])
    const [error, setError] = useState(null)
    const [search, setSearch] = useState('')
    const [categoryFilter, setCategoryFilter] = useState('')
    const [expanded, setExpanded] = useState(-1)

    useEffect(() => {
        fetchTechniques()
            .then(d => { setTechniques(d.techniques || []); if (d.error) setError(d.error) })
            .catch(e => setError(e.message))
    }, [])

    const categories = useMemo(() => {
        const cats = new Set(techniques.map(t => t.category).filter(Boolean))
        return Array.from(cats).sort()
    }, [techniques])

    const filtered = useMemo(() => {
        let list = techniques
        if (categoryFilter) list = list.filter(t => t.category === categoryFilter)
        if (search) {
            const q = search.toLowerCase()
            list = list.filter(t =>
                (t.name || '').toLowerCase().includes(q) ||
                (t.summary || '').toLowerCase().includes(q) ||
                (t.keywords || '').toLowerCase().includes(q) ||
                (t.id || '').toLowerCase().includes(q)
            )
        }
        return list
    }, [techniques, search, categoryFilter])

    return (
        <div className="card">
            <div className="card-header">
                <span className="card-title">写作技法库</span>
                <Badge tone="blue">{techniques.length} 条技法</Badge>
            </div>
            <div className="filter-group">
                <input
                    type="text"
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    placeholder="搜索技法名称/关键词/摘要..."
                    style={{
                        flex: 1, minWidth: 200, padding: '6px 10px',
                        border: '2px solid var(--border-main)', borderRadius: 0,
                        background: '#fffef8', color: 'var(--text-main)', fontWeight: 500,
                        boxShadow: 'var(--shadow-soft)',
                    }}
                />
                <select
                    value={categoryFilter}
                    onChange={e => { setCategoryFilter(e.target.value); setExpanded(-1) }}
                    style={{
                        padding: '6px 10px',
                        border: '2px solid var(--border-main)', borderRadius: 0,
                        background: '#fff8e6', color: 'var(--text-main)', fontWeight: 700,
                    }}
                >
                    <option value="">全部分类</option>
                    {categories.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
            </div>
            {error && <p style={{ marginBottom: 8, color: 'var(--accent-red)', fontWeight: 600 }}>加载失败: {error}</p>}
            <p style={{ marginBottom: 8, color: 'var(--text-mute)', fontSize: 13, fontWeight: 600 }}>
                {filtered.length} 条结果
            </p>
            {filtered.length === 0 ? (
                <div className="empty-state compact">无匹配技法</div>
            ) : (
                <div className="table-wrap">
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th style={{ width: 80 }}>编号</th>
                                <th style={{ width: 80 }}>分类</th>
                                <th style={{ width: 120 }}>技法名称</th>
                                <th>核心摘要</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.map((t, idx) => (
                                <tr
                                    key={idx}
                                    onClick={() => setExpanded(expanded === idx ? -1 : idx)}
                                    className={expanded === idx ? 'entity-row selected' : 'entity-row'}
                                >
                                    <td style={{ fontFamily: 'var(--font-display)', fontSize: 8 }}>{t.id}</td>
                                    <td><Badge tone={CATEGORY_COLORS[t.category] || 'neutral'}>{t.category}</Badge></td>
                                    <td style={{ fontWeight: 700 }}>{t.name}</td>
                                    <td style={{ color: 'var(--text-sub)', fontSize: 13 }}>
                                        {t.summary}
                                        {expanded === idx && (
                                            <div style={{ marginTop: 12, padding: 12, background: 'var(--bg-panel)', border: '2px solid var(--border-soft)', boxShadow: 'var(--shadow-soft)' }}>
                                                {t.instruction && (
                                                    <div style={{ marginBottom: 8 }}>
                                                        <div className="mini-label">大模型指令</div>
                                                        <p style={{ margin: '4px 0', color: 'var(--text-main)', fontWeight: 500 }}>{t.instruction}</p>
                                                    </div>
                                                )}
                                                {t.keywords && (
                                                    <div style={{ marginBottom: 8 }}>
                                                        <div className="mini-label">关键词</div>
                                                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
                                                            {t.keywords.split('|').filter(Boolean).map((kw, i) => (
                                                                <Badge key={i} tone="neutral">{kw.trim()}</Badge>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}
                                                {t.pitfalls && (
                                                    <div style={{ marginBottom: 8 }}>
                                                        <div className="mini-label" style={{ color: 'var(--accent-red)' }}>毒点</div>
                                                        <p style={{ margin: '4px 0', color: 'var(--accent-red)', fontWeight: 500 }}>{t.pitfalls}</p>
                                                    </div>
                                                )}
                                                {t.positive_example && (
                                                    <div style={{ marginBottom: 8 }}>
                                                        <div className="mini-label" style={{ color: 'var(--accent-green)' }}>正例</div>
                                                        <p style={{ margin: '4px 0', whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.6 }}>{t.positive_example}</p>
                                                    </div>
                                                )}
                                                {t.negative_example && (
                                                    <div>
                                                        <div className="mini-label" style={{ color: 'var(--accent-red)' }}>反例</div>
                                                        <p style={{ margin: '4px 0', whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.6 }}>{t.negative_example}</p>
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    )
}

/* ── Tab 4: 章级合同 ── */

function ChapterContractTab() {
    const [chapters, setChapters] = useState([])
    const [selected, setSelected] = useState(null)
    const [detail, setDetail] = useState(null)
    const [error, setError] = useState(null)

    useEffect(() => {
        fetchChapterContracts()
            .then(d => {
                const list = d.chapters || []
                setChapters(list)
                if (list.length > 0) setSelected(list[list.length - 1].chapter)
            })
            .catch(e => setError(e.message))
    }, [])

    useEffect(() => {
        if (selected == null) return
        const ctrl = new AbortController()
        fetch(`/api/style/chapters/${selected}`)
            .then(r => r.ok ? r.json() : Promise.reject(new Error(`${r.status}`)))
            .then(d => { if (!ctrl.signal.aborted) setDetail(d) })
            .catch(() => { if (!ctrl.signal.aborted) setDetail(null) })
        return () => ctrl.abort()
    }, [selected])

    const directive = detail?.chapter_directive || {}
    const reasoning = detail?.reasoning || {}
    const dynamicContext = detail?.dynamic_context || []

    return (
        <div className="card">
            <div className="card-header">
                <span className="card-title">章级合同查看器</span>
                <Badge tone="blue">{chapters.length} 章</Badge>
            </div>
            {error && <p style={{ marginBottom: 12, color: 'var(--accent-red)', fontWeight: 600 }}>加载失败: {error}</p>}
            <div style={{ marginBottom: 16 }}>
                <select
                    value={selected ?? ''}
                    onChange={e => setSelected(Number(e.target.value))}
                    style={{
                        padding: '6px 10px',
                        border: '2px solid var(--border-main)', borderRadius: 0,
                        background: '#fff8e6', color: 'var(--text-main)', fontWeight: 700,
                        minWidth: 280,
                    }}
                >
                    {chapters.map(ch => (
                        <option key={ch.chapter} value={ch.chapter}>
                            第{ch.chapter}章 {ch.goal ? `— ${ch.goal.slice(0, 30)}` : ''}
                        </option>
                    ))}
                </select>
            </div>
            {!detail ? (
                <div className="empty-state compact">选择章节查看详情</div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    <section className="summary-card">
                        <div className="mini-label">写作指令</div>
                        <div className="entity-detail">
                            <DetailField label="目标" value={directive.goal} />
                            <DetailField label="时间锚点" value={directive.time_anchor} />
                            <DetailField label="时间跨度" value={directive.chapter_span} />
                            <DetailField label="故事线" value={directive.strand} />
                            <DetailField label="钩子类型" value={directive.hook_type} />
                            <DetailField label="钩子强度" value={directive.hook_strength} />
                            <DetailField label="章末悬念" value={directive.chapter_end_open_question} />
                        </div>
                    </section>

                    {directive.must_cover_nodes?.length > 0 && (
                        <section className="summary-card">
                            <div className="mini-label">必须覆盖节点</div>
                            <ul style={{ margin: 0, paddingLeft: 18 }}>
                                {directive.must_cover_nodes.map((node, i) => (
                                    <li key={i} style={{ marginBottom: 4, fontWeight: 500 }}>
                                        {typeof node === 'object' ? JSON.stringify(node) : String(node)}
                                    </li>
                                ))}
                            </ul>
                        </section>
                    )}

                    {directive.forbidden_zones?.length > 0 && (
                        <section className="summary-card" style={{ borderColor: 'var(--accent-red)' }}>
                            <div className="mini-label" style={{ color: 'var(--accent-red)' }}>禁止区域</div>
                            <ul style={{ margin: 0, paddingLeft: 18 }}>
                                {directive.forbidden_zones.map((z, i) => (
                                    <li key={i} style={{ marginBottom: 4, color: 'var(--accent-red)', fontWeight: 600 }}>
                                        {typeof z === 'object' ? JSON.stringify(z) : String(z)}
                                    </li>
                                ))}
                            </ul>
                        </section>
                    )}

                    {Object.keys(reasoning).length > 0 && (
                        <section className="summary-card">
                            <div className="mini-label">推理策略</div>
                            <div className="entity-detail">
                                <DetailField label="题材" value={reasoning.genre} />
                                <DetailField label="风格优先级" value={reasoning.style_priority} />
                                <DetailField label="节奏策略" value={reasoning.pacing_strategy} />
                            </div>
                        </section>
                    )}

                    {dynamicContext.length > 0 && (
                        <section className="summary-card">
                            <div className="mini-label">注入的写作技法 ({dynamicContext.length})</div>
                            <div className="table-wrap" style={{ marginTop: 8 }}>
                                <table className="data-table">
                                    <thead>
                                        <tr>
                                            <th>编号</th>
                                            <th>分类</th>
                                            <th>核心摘要</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {dynamicContext.map((ctx, i) => (
                                            <tr key={i}>
                                                <td style={{ fontFamily: 'var(--font-display)', fontSize: 8 }}>{ctx.编号 || ctx.id || ''}</td>
                                                <td><Badge tone={CATEGORY_COLORS[ctx.分类] || 'neutral'}>{ctx.分类 || ctx._table || ''}</Badge></td>
                                                <td style={{ fontSize: 13, color: 'var(--text-sub)' }}>{ctx.核心摘要 || ctx.summary || ''}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </section>
                    )}
                </div>
            )}
        </div>
    )
}

function DetailField({ label, value }) {
    if (value == null || value === '') return null
    return (
        <div style={{ display: 'flex', gap: 8, marginBottom: 4 }}>
            <span style={{ fontWeight: 700, fontSize: 13, minWidth: 80, color: 'var(--text-mute)' }}>{label}</span>
            <span style={{ fontWeight: 500, fontSize: 13 }}>{value}</span>
        </div>
    )
}

/* ── Tab 5: 审查维度 ── */

function ReviewerTab() {
    const [data, setData] = useState(null)
    const [error, setError] = useState(null)

    useEffect(() => {
        fetchReviewerChecklist().then(setData).catch(e => setError(e.message))
    }, [])

    const checklist = data?.checklist || []
    const antiPatterns = data?.anti_patterns || []

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div className="card">
                <div className="card-header">
                    <span className="card-title">审查维度清单</span>
                    <Badge tone="blue">{checklist.length} 维度</Badge>
                </div>
                {error && <p style={{ marginBottom: 8, color: 'var(--accent-red)', fontWeight: 600 }}>加载失败: {error}</p>}
                {checklist.length === 0 ? (
                    <div className="empty-state compact">暂无数据</div>
                ) : (
                    <div className="table-wrap">
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>维度</th>
                                    <th>检查内容</th>
                                    <th>输出格式</th>
                                    <th style={{ textAlign: 'center' }}>查询</th>
                                </tr>
                            </thead>
                            <tbody>
                                {checklist.map((item, i) => (
                                    <tr key={i}>
                                        <td style={{ fontWeight: 700, whiteSpace: 'nowrap' }}>{item.dimension}</td>
                                        <td style={{ fontSize: 13 }}>{item.content}</td>
                                        <td style={{ fontFamily: 'var(--font-display)', fontSize: 8 }}>{item.format}</td>
                                        <td style={{ textAlign: 'center' }}>
                                            {item.must_bash && <Badge tone="amber">bash</Badge>}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            <div className="card">
                <div className="card-header">
                    <span className="card-title">反模式列表</span>
                    <Badge tone="red">{antiPatterns.length} 条</Badge>
                </div>
                {antiPatterns.length === 0 ? (
                    <div className="empty-state compact">暂无反模式</div>
                ) : (
                    <div className="table-wrap">
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>#</th>
                                    <th>反模式内容</th>
                                    <th>来源</th>
                                </tr>
                            </thead>
                            <tbody>
                                {antiPatterns.map((p, i) => (
                                    <tr key={i}>
                                        <td style={{ color: 'var(--text-mute)', fontSize: 13 }}>{i + 1}</td>
                                        <td>{p.text}</td>
                                        <td>
                                            <Badge tone="neutral">{p.source_table || '手动'}</Badge>
                                            {p.source_id && <span style={{ marginLeft: 4, fontSize: 12, color: 'var(--text-mute)' }}>({p.source_id})</span>}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    )
}

/* ── 主页面 ── */

export default function StyleEditorPage() {
    const [activeTab, setActiveTab] = useState('master')

    return (
        <div className="dashboard-page">
            <div className="page-header">
                <h2>文风约束编辑器</h2>
            </div>
            <p style={{ color: 'var(--text-sub)', fontSize: 13 }}>
                系统有 5 个层级可以插入文风约束，从全局到局部逐级细化。
            </p>

            {/* Tab 栏 */}
            <div className="tab-strip">
                {TABS.map(tab => (
                    <button
                        key={tab.key}
                        onClick={() => setActiveTab(tab.key)}
                        className={`tab-btn ${activeTab === tab.key ? 'active' : ''}`}
                    >
                        {tab.label}
                    </button>
                ))}
            </div>

            {/* Tab 内容 */}
            {activeTab === 'master' && <MasterSettingTab />}
            {activeTab === 'anti' && <AntiPatternsTab />}
            {activeTab === 'techniques' && <TechniquesTab />}
            {activeTab === 'chapter' && <ChapterContractTab />}
            {activeTab === 'reviewer' && <ReviewerTab />}
        </div>
    )
}
