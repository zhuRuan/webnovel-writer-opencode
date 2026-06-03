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

    return (
        <div>
            <p style={{ marginBottom: 16, color: 'var(--text-sub)' }}>
                编辑 <code>master_constraints</code> 字段，对所有章节生效。
                locked 字段不可修改。
            </p>
            {allKeys.length === 0 && !data && <p>加载中...</p>}
            {allKeys.length === 0 && data?._error && <p style={{ color: 'var(--accent-red)' }}>加载失败: {data._error}</p>}
            {allKeys.length === 0 && data && !data._error && <p>暂无 master_constraints 配置</p>}
            {allKeys.map(key => (
                <div key={key} style={{ marginBottom: 12 }}>
                    <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
                        {key}
                        {locked.includes(key) && <Badge tone="red" style={{ marginLeft: 8 }}>锁定</Badge>}
                    </label>
                    <input
                        type="text"
                        value={displayValue(key)}
                        onChange={e => handleChange(key, e.target.value)}
                        disabled={locked.includes(key)}
                        style={{
                            width: '100%', maxWidth: 480, padding: '6px 10px',
                            border: '1px solid var(--border-main)', borderRadius: 4,
                            background: locked.includes(key) ? 'var(--bg-card-2)' : 'var(--bg-card)',
                            color: 'var(--text-main)',
                        }}
                    />
                </div>
            ))}
            {hasChanges && (
                <button onClick={handleSave} disabled={saving} style={{
                    marginTop: 12, padding: '8px 20px', borderRadius: 4,
                    border: 'none', background: 'var(--accent-blue)', color: '#fff',
                    cursor: saving ? 'wait' : 'pointer', fontWeight: 500,
                }}>
                    {saving ? '保存中...' : '保存'}
                </button>
            )}
            {msg && (
                <p style={{ marginTop: 8, color: msg.type === 'error' ? 'var(--accent-red)' : 'var(--accent-green)' }}>
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
        <div>
            <p style={{ marginBottom: 16, color: 'var(--text-sub)' }}>
                定义绝对不能出现的写法。审查阶段 reviewer agent 会自动检查。
            </p>
            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                <input
                    type="text"
                    value={newText}
                    onChange={e => setNewText(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && !loading && handleAdd()}
                    placeholder="输入新的反模式..."
                    style={{
                        flex: 1, padding: '6px 10px',
                        border: '1px solid var(--border-main)', borderRadius: 4,
                        background: 'var(--bg-card)', color: 'var(--text-main)',
                    }}
                />
                <button onClick={handleAdd} disabled={loading || !newText.trim()} style={{
                    padding: '6px 16px', borderRadius: 4,
                    border: 'none', background: 'var(--accent-blue)', color: '#fff',
                    cursor: loading ? 'wait' : 'pointer',
                }}>
                    添加
                </button>
            </div>
            {msg && (
                <p style={{ marginBottom: 8, color: msg.type === 'error' ? 'var(--accent-red)' : 'var(--accent-green)' }}>
                    {msg.text}
                </p>
            )}
            {patterns.length === 0 ? (
                <p style={{ color: 'var(--text-sub)' }}>暂无反模式</p>
            ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr style={{ borderBottom: '1px solid var(--border-main)' }}>
                            <th style={{ textAlign: 'left', padding: '8px 4px' }}>#</th>
                            <th style={{ textAlign: 'left', padding: '8px 4px' }}>反模式内容</th>
                            <th style={{ textAlign: 'left', padding: '8px 4px' }}>来源</th>
                            <th style={{ textAlign: 'right', padding: '8px 4px' }}>操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        {patterns.map((p, i) => (
                            <tr key={p.text} style={{ borderBottom: '1px solid var(--border-soft)' }}>
                                <td style={{ padding: '8px 4px', color: 'var(--text-sub)' }}>{i + 1}</td>
                                <td style={{ padding: '8px 4px' }}>{p.text}</td>
                                <td style={{ padding: '8px 4px' }}>
                                    <Badge tone={p.source_table === 'dashboard_manual' ? 'cyan' : 'neutral'}>
                                        {p.source_table || '手动'}
                                    </Badge>
                                </td>
                                <td style={{ padding: '8px 4px', textAlign: 'right' }}>
                                    <button onClick={() => handleDelete(p.text)} style={{
                                        padding: '2px 8px', borderRadius: 3,
                                        border: '1px solid var(--accent-red)', background: 'transparent',
                                        color: 'var(--accent-red)', cursor: 'pointer', fontSize: 12,
                                    }}>
                                        删除
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
            <p style={{ marginTop: 12, color: 'var(--text-sub)', fontSize: 13 }}>
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
        <div>
            <p style={{ marginBottom: 16, color: 'var(--text-sub)' }}>
                题材级技法库，写作时通过 BM25 检索自动匹配。共 {techniques.length} 条技法。
            </p>
            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                <input
                    type="text"
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    placeholder="搜索技法名称/关键词/摘要..."
                    style={{
                        flex: 1, padding: '6px 10px',
                        border: '1px solid var(--border-main)', borderRadius: 4,
                        background: 'var(--bg-card)', color: 'var(--text-main)',
                    }}
                />
                <select
                    value={categoryFilter}
                    onChange={e => setCategoryFilter(e.target.value)}
                    style={{
                        padding: '6px 10px', borderRadius: 4,
                        border: '1px solid var(--border-main)',
                        background: 'var(--bg-card)', color: 'var(--text-main)',
                    }}
                >
                    <option value="">全部分类</option>
                    {categories.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
            </div>
            {error && <p style={{ marginBottom: 8, color: 'var(--accent-red)' }}>加载失败: {error}</p>}
            <p style={{ marginBottom: 8, color: 'var(--text-sub)', fontSize: 13 }}>
                {filtered.length} 条结果
            </p>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-main)' }}>
                        <th style={{ textAlign: 'left', padding: '8px 4px', width: 80 }}>编号</th>
                        <th style={{ textAlign: 'left', padding: '8px 4px', width: 80 }}>分类</th>
                        <th style={{ textAlign: 'left', padding: '8px 4px', width: 120 }}>技法名称</th>
                        <th style={{ textAlign: 'left', padding: '8px 4px' }}>核心摘要</th>
                    </tr>
                </thead>
                <tbody>
                    {filtered.map((t, idx) => (
                        <tr
                            key={idx}
                            onClick={() => setExpanded(expanded === idx ? -1 : idx)}
                            style={{
                                cursor: 'pointer',
                                borderBottom: '1px solid var(--border-soft)',
                                background: expanded === idx ? 'var(--bg-card-2)' : 'transparent',
                            }}
                        >
                            <td style={{ padding: '8px 4px', fontFamily: 'var(--font-body)', fontSize: 13 }}>{t.id}</td>
                            <td style={{ padding: '8px 4px' }}>
                                <Badge tone={CATEGORY_COLORS[t.category] || 'neutral'}>{t.category}</Badge>
                            </td>
                            <td style={{ padding: '8px 4px', fontWeight: 500 }}>{t.name}</td>
                            <td style={{ padding: '8px 4px', color: 'var(--text-sub)', fontSize: 13 }}>
                                {t.summary}
                                {expanded === idx && (
                                    <div style={{ marginTop: 12, padding: 12, background: 'var(--bg-card)', borderRadius: 4, border: '1px solid var(--border-soft)' }}>
                                        {t.instruction && (
                                            <div style={{ marginBottom: 8 }}>
                                                <strong>大模型指令：</strong>
                                                <p style={{ margin: '4px 0', color: 'var(--text-main)' }}>{t.instruction}</p>
                                            </div>
                                        )}
                                        {t.keywords && (
                                            <div style={{ marginBottom: 8 }}>
                                                <strong>关键词：</strong>
                                                {t.keywords.split('|').map((kw, i) => (
                                                    <Badge key={i} tone="neutral" style={{ marginLeft: 4 }}>{kw.trim()}</Badge>
                                                ))}
                                            </div>
                                        )}
                                        {t.pitfalls && (
                                            <div style={{ marginBottom: 8 }}>
                                                <strong style={{ color: 'var(--accent-red)' }}>毒点：</strong>
                                                <p style={{ margin: '4px 0', color: 'var(--accent-red)' }}>{t.pitfalls}</p>
                                            </div>
                                        )}
                                        {t.positive_example && (
                                            <div style={{ marginBottom: 8 }}>
                                                <strong style={{ color: 'var(--accent-green)' }}>正例：</strong>
                                                <p style={{ margin: '4px 0', whiteSpace: 'pre-wrap', fontSize: 13 }}>{t.positive_example}</p>
                                            </div>
                                        )}
                                        {t.negative_example && (
                                            <div>
                                                <strong style={{ color: 'var(--accent-red)' }}>反例：</strong>
                                                <p style={{ margin: '4px 0', whiteSpace: 'pre-wrap', fontSize: 13 }}>{t.negative_example}</p>
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
        <div>
            <p style={{ marginBottom: 16, color: 'var(--text-sub)' }}>
                查看章级合同详情，包括写作指令、禁止区域、注入的写作技法。共 {chapters.length} 章。
            </p>
            {error && <p style={{ marginBottom: 16, color: 'var(--accent-red)' }}>加载失败: {error}</p>}
            <div style={{ marginBottom: 16 }}>
                <select
                    value={selected ?? ''}
                    onChange={e => setSelected(Number(e.target.value))}
                    style={{
                        padding: '6px 10px', borderRadius: 4,
                        border: '1px solid var(--border-main)',
                        background: 'var(--bg-card)', color: 'var(--text-main)',
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
                <p style={{ color: 'var(--text-sub)' }}>选择章节查看详情</p>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                    {/* 基本信息 */}
                    <section style={sectionStyle}>
                        <h4 style={sectionTitleStyle}>写作指令</h4>
                        <Field label="目标" value={directive.goal} />
                        <Field label="时间锚点" value={directive.time_anchor} />
                        <Field label="时间跨度" value={directive.chapter_span} />
                        <Field label="故事线" value={directive.strand} />
                        <Field label="钩子类型" value={directive.hook_type} />
                        <Field label="钩子强度" value={directive.hook_strength} />
                        <Field label="章末悬念" value={directive.chapter_end_open_question} />
                    </section>

                    {/* 必须覆盖节点 */}
                    {directive.must_cover_nodes?.length > 0 && (
                        <section style={sectionStyle}>
                            <h4 style={sectionTitleStyle}>必须覆盖节点</h4>
                            <ul style={{ margin: 0, paddingLeft: 20 }}>
                                {directive.must_cover_nodes.map((node, i) => (
                                    <li key={i} style={{ marginBottom: 4 }}>
                                        {typeof node === 'object' ? JSON.stringify(node) : String(node)}
                                    </li>
                                ))}
                            </ul>
                        </section>
                    )}

                    {/* 禁止区域 */}
                    {directive.forbidden_zones?.length > 0 && (
                        <section style={sectionStyle}>
                            <h4 style={{ ...sectionTitleStyle, color: 'var(--accent-red)' }}>禁止区域</h4>
                            <ul style={{ margin: 0, paddingLeft: 20 }}>
                                {directive.forbidden_zones.map((z, i) => (
                                    <li key={i} style={{ marginBottom: 4, color: 'var(--accent-red)' }}>
                                        {typeof z === 'object' ? JSON.stringify(z) : String(z)}
                                    </li>
                                ))}
                            </ul>
                        </section>
                    )}

                    {/* 推理 */}
                    {Object.keys(reasoning).length > 0 && (
                        <section style={sectionStyle}>
                            <h4 style={sectionTitleStyle}>推理策略</h4>
                            <Field label="题材" value={reasoning.genre} />
                            <Field label="风格优先级" value={reasoning.style_priority} />
                            <Field label="节奏策略" value={reasoning.pacing_strategy} />
                        </section>
                    )}

                    {/* 注入的写作技法 */}
                    {dynamicContext.length > 0 && (
                        <section style={sectionStyle}>
                            <h4 style={sectionTitleStyle}>注入的写作技法 ({dynamicContext.length})</h4>
                            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <thead>
                                    <tr style={{ borderBottom: '1px solid var(--border-main)' }}>
                                        <th style={{ textAlign: 'left', padding: '6px 4px' }}>编号</th>
                                        <th style={{ textAlign: 'left', padding: '6px 4px' }}>分类</th>
                                        <th style={{ textAlign: 'left', padding: '6px 4px' }}>核心摘要</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {dynamicContext.map((ctx, i) => (
                                        <tr key={i} style={{ borderBottom: '1px solid var(--border-soft)' }}>
                                            <td style={{ padding: '6px 4px', fontSize: 13 }}>{ctx.编号 || ctx.id || ''}</td>
                                            <td style={{ padding: '6px 4px' }}>
                                                <Badge tone={CATEGORY_COLORS[ctx.分类] || 'neutral'}>{ctx.分类 || ctx._table || ''}</Badge>
                                            </td>
                                            <td style={{ padding: '6px 4px', fontSize: 13, color: 'var(--text-sub)' }}>
                                                {ctx.核心摘要 || ctx.summary || ''}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </section>
                    )}
                </div>
            )}
        </div>
    )
}

function Field({ label, value }) {
    if (value == null || value === '') return null
    return (
        <div style={{ marginBottom: 6 }}>
            <span style={{ fontWeight: 500, marginRight: 8 }}>{label}：</span>
            <span style={{ color: 'var(--text-sub)' }}>{value}</span>
        </div>
    )
}

const sectionStyle = {
    padding: 16, borderRadius: 6,
    border: '1px solid var(--border-soft)', background: 'var(--bg-card)',
}

const sectionTitleStyle = {
    margin: '0 0 12px', fontSize: 14, fontWeight: 600,
}

/* ── Tab 5: 审查维度 ── */

function ReviewerTab() {
    const [data, setData] = useState(null)

    useEffect(() => {
        fetchReviewerChecklist().then(setData).catch(() => {})
    }, [])

    const checklist = data?.checklist || []
    const antiPatterns = data?.anti_patterns || []

    return (
        <div>
            <p style={{ marginBottom: 16, color: 'var(--text-sub)' }}>
                审查阶段 reviewer agent 的 13 维度检查清单。每个维度必须逐项输出结论。
            </p>
            <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 24 }}>
                <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-main)' }}>
                        <th style={{ textAlign: 'left', padding: '8px 4px' }}>维度</th>
                        <th style={{ textAlign: 'left', padding: '8px 4px' }}>检查内容</th>
                        <th style={{ textAlign: 'left', padding: '8px 4px' }}>输出格式</th>
                        <th style={{ textAlign: 'center', padding: '8px 4px' }}>必须查询</th>
                    </tr>
                </thead>
                <tbody>
                    {checklist.map((item, i) => (
                        <tr key={i} style={{ borderBottom: '1px solid var(--border-soft)' }}>
                            <td style={{ padding: '8px 4px', fontWeight: 500, whiteSpace: 'nowrap' }}>{item.dimension}</td>
                            <td style={{ padding: '8px 4px', fontSize: 13 }}>{item.content}</td>
                            <td style={{ padding: '8px 4px', fontSize: 13, fontFamily: 'var(--font-body)' }}>
                                <code style={{ fontSize: 12 }}>{item.format}</code>
                            </td>
                            <td style={{ padding: '8px 4px', textAlign: 'center' }}>
                                {item.must_bash && <Badge tone="amber">bash</Badge>}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>

            <h4 style={{ marginBottom: 12 }}>反模式列表 ({antiPatterns.length})</h4>
            {antiPatterns.length === 0 ? (
                <p style={{ color: 'var(--text-sub)' }}>暂无反模式</p>
            ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr style={{ borderBottom: '1px solid var(--border-main)' }}>
                            <th style={{ textAlign: 'left', padding: '8px 4px' }}>#</th>
                            <th style={{ textAlign: 'left', padding: '8px 4px' }}>反模式内容</th>
                            <th style={{ textAlign: 'left', padding: '8px 4px' }}>来源</th>
                        </tr>
                    </thead>
                    <tbody>
                        {antiPatterns.map((p, i) => (
                            <tr key={i} style={{ borderBottom: '1px solid var(--border-soft)' }}>
                                <td style={{ padding: '8px 4px', color: 'var(--text-sub)' }}>{i + 1}</td>
                                <td style={{ padding: '8px 4px' }}>{p.text}</td>
                                <td style={{ padding: '8px 4px' }}>
                                    <Badge tone="neutral">{p.source_table || '手动'}</Badge>
                                    {p.source_id && <span style={{ marginLeft: 4, fontSize: 12, color: 'var(--text-sub)' }}>({p.source_id})</span>}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </div>
    )
}

/* ── 主页面 ── */

export default function StyleEditorPage() {
    const [activeTab, setActiveTab] = useState('master')

    return (
        <div>
            <h2 style={{ marginBottom: 20 }}>文风约束编辑器</h2>
            <p style={{ marginBottom: 20, color: 'var(--text-sub)' }}>
                系统有 5 个层级可以插入文风约束，从全局到局部逐级细化。
            </p>

            {/* Tab 栏 */}
            <div style={{ display: 'flex', gap: 4, marginBottom: 20, borderBottom: '1px solid var(--border-main)', paddingBottom: 0 }}>
                {TABS.map(tab => (
                    <button
                        key={tab.key}
                        onClick={() => setActiveTab(tab.key)}
                        style={{
                            padding: '8px 16px', border: 'none', borderRadius: '4px 4px 0 0',
                            background: activeTab === tab.key ? 'var(--accent-blue)' : 'transparent',
                            color: activeTab === tab.key ? '#fff' : 'var(--text-main)',
                            cursor: 'pointer', fontWeight: activeTab === tab.key ? 600 : 400,
                            borderBottom: activeTab === tab.key ? '2px solid var(--accent-blue)' : '2px solid transparent',
                            marginBottom: -1,
                        }}
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
