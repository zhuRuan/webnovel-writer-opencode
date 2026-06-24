import { useEffect, useState, useCallback, useMemo, useRef, Fragment } from 'react'
import { useDashboardContext } from '../App.jsx'
import Badge from '../components/Badge.jsx'
import {
    fetchMasterSetting,
    updateMasterSetting,
    fetchAntiPatterns,
    addAntiPattern,
    deleteAntiPattern,
    fetchChapterContracts,
    fetchReviewerChecklist,
    fetchPrompts,
    createPrompt,
    updatePrompt,
    deletePrompt,
    fetchDirectorStyles,
    toggleDirectorStyle,
    upsertDirectorStyle,
    updateCollectedChapter,
    retryAnalyzeChapter,
    deleteCollectedChapter,
    deleteCollectedChaptersBatch,
    deleteStyleSummary,
    retryStyleSummary,
    createTechnique,
    updateTechnique,
    deleteTechnique,
    deleteCollectionReport,
    deleteFailedCollectionReports,
    reanalyzeAuthorChapters,
} from '../api.js'

const TABS = [
    { key: 'prompts', label: '自定义文风 / 文风规则' },
    { key: 'master', label: '全局文风' },
    { key: 'anti', label: '禁止模式' },
    // === 设定构思 ===
    { key: 'char_ref', label: '人设模板' },
    { key: 'gold_ref', label: '金手指库' },
    { key: 'naming_ref', label: '命名规则' },
    { key: 'genre_ref', label: '题材路由' },
    // === 剧情构思 ===
    { key: 'plot_ref', label: '桥段套路' },
    { key: 'pacing_ref', label: '爽点节奏' },
    // === 写作方法 ===
    { key: 'techniques', label: '写作技法' },
    { key: 'scene_ref', label: '场景写法' },
    // === 名家技法 ===
    { key: 'masters', label: '名家技法' },
    // === 质量把控 ===
    { key: 'chapter', label: '章级合同' },
    { key: 'adjudge_ref', label: '裁决规则' },
    { key: 'reviewer', label: '审查维度' },
]

const TAB_SECTIONS = {
    'prompts': '⚙️ 全局配置',
    'master': null,
    'anti': null,
    'char_ref': '📐 设定构思',
    'gold_ref': null,
    'naming_ref': null,
    'genre_ref': null,
    'plot_ref': '📖 剧情构思',
    'pacing_ref': null,
    'techniques': '✍️ 写作方法',
    'scene_ref': null,
    'masters': '🎯 名家参考',
    'chapter': '✅ 质量把控',
    'adjudge_ref': null,
    'reviewer': null,
}

const CATEGORY_COLORS = {
    '对话': 'blue', '情感': 'purple', '场景': 'green',
    '节奏': 'amber', '战斗': 'red', '叙事': 'cyan',
}

/* ── Tab 0: 自定义文风 / 文风规则 ── */

function PromptsTab() {
    // ── 文风规则 (director_style DB) ──
    const [styles, setStyles] = useState([])
    const [stylesError, setStylesError] = useState(null)
    const [stylesLoading, setStylesLoading] = useState(true)
    const [styleMsg, setStyleMsg] = useState(null)
    const [editingStyleId, setEditingStyleId] = useState(null)
    const [editStyleDesc, setEditStyleDesc] = useState('')
    const [togglingIds, setTogglingIds] = useState({})

    const reloadStyles = useCallback(() => {
        setStylesLoading(true)
        fetchDirectorStyles()
            .then(d => setStyles(Array.isArray(d) ? d : d.styles || []))
            .catch(e => setStylesError(e.message))
            .finally(() => setStylesLoading(false))
    }, [])

    useEffect(() => { reloadStyles() }, [reloadStyles])

    const handleToggle = async (style) => {
        const newActive = style.is_active ? 0 : 1
        setTogglingIds(prev => ({ ...prev, [style.id]: true }))
        setStyleMsg(null)
        try {
            await toggleDirectorStyle(style.id, newActive)
            setStyles(prev => prev.map(s => s.id === style.id ? { ...s, is_active: newActive } : s))
        } catch (e) {
            setStyleMsg({ type: 'error', text: e.message })
        } finally {
            setTogglingIds(prev => ({ ...prev, [style.id]: undefined }))
        }
    }

    const handleSaveStyleDesc = async (style) => {
        if (!editStyleDesc.trim() || togglingIds[`save-${style.id}`]) return
        setTogglingIds(prev => ({ ...prev, [`save-${style.id}`]: true }))
        setStyleMsg(null)
        try {
            await upsertDirectorStyle({ ...style, description: editStyleDesc.trim() })
            setStyles(prev => prev.map(s => s.id === style.id ? { ...s, description: editStyleDesc.trim() } : s))
            setEditingStyleId(null)
            setStyleMsg({ type: 'success', text: '已保存' })
        } catch (e) {
            setStyleMsg({ type: 'error', text: e.message })
        } finally {
            setTogglingIds(prev => ({ ...prev, [`save-${style.id}`]: undefined }))
        }
    }

    // ── 自定义文风提示词 (file-based, existing) ──
    const [prompts, setPrompts] = useState([])
    const [promptsError, setPromptsError] = useState(null)
    const [editing, setEditing] = useState(null)
    const [creating, setCreating] = useState(false)
    const [newName, setNewName] = useState('')
    const [newContent, setNewContent] = useState('')
    const [msg, setMsg] = useState(null)
    const [loading, setLoading] = useState(false)
    const [showPrompts, setShowPrompts] = useState(false)

    const reloadPrompts = useCallback(() => {
        fetchPrompts().then(d => setPrompts(d.prompts || [])).catch(e => setPromptsError(e.message))
    }, [])

    useEffect(() => { reloadPrompts() }, [reloadPrompts])

    const handleCreate = async () => {
        if (!newName.trim() || !newContent.trim() || loading) return
        setLoading(true); setMsg(null)
        try {
            await createPrompt(newName.trim(), newContent.trim())
            setNewName(''); setNewContent(''); setCreating(false)
            setMsg({ type: 'success', text: '创建成功' })
            reloadPrompts()
        } catch (e) {
            setMsg({ type: 'error', text: e.message })
        } finally { setLoading(false) }
    }

    const handleSave = async () => {
        if (!editing || loading) return
        setLoading(true); setMsg(null)
        try {
            await updatePrompt(editing.filename, editing.content)
            setEditing(null)
            setMsg({ type: 'success', text: '保存成功' })
            reloadPrompts()
        } catch (e) {
            setMsg({ type: 'error', text: e.message })
        } finally { setLoading(false) }
    }

    const handleDelete = async (filename) => {
        if (loading) return
        if (!confirm(`确认删除提示词文件 ${filename}？`)) return
        setLoading(true); setMsg(null)
        try {
            await deletePrompt(filename)
            if (editing?.filename === filename) setEditing(null)
            setMsg({ type: 'success', text: '已删除' })
            reloadPrompts()
        } catch (e) {
            setMsg({ type: 'error', text: e.message })
        } finally { setLoading(false) }
    }

    const PRIORITY_TONE = { 9: 'red', 8: 'amber', 7: 'green', 6: 'cyan', 5: 'blue' }

    return (
        <div>
            {/* ═══════ 文风规则 (DB) ═══════ */}
            <div className="card">
                <div className="card-header">
                    <span className="card-title">文风规则</span>
                    <Badge tone="cyan">{styles.length} 条规则</Badge>
                </div>
                <p style={{ marginBottom: 12, color: 'var(--text-sub)', fontSize: 13 }}>
                    系统写作时自动注入到导演上下文中。激活/停用按钮可控制是否生效。
                </p>

                {stylesLoading && <div className="empty-state compact">加载中...</div>}
                {stylesError && <p style={{ marginBottom: 8, color: 'var(--accent-red)', fontWeight: 600 }}>加载失败: {stylesError}</p>}
                {styleMsg && (
                    <p style={{ marginBottom: 8, color: styleMsg.type === 'error' ? 'var(--accent-red)' : 'var(--accent-green)', fontWeight: 600 }}>
                        {styleMsg.text}
                    </p>
                )}

                {!stylesLoading && !stylesError && styles.length === 0 && (
                    <div className="empty-state compact">
                        暂无文风规则。请先通过<code style={{ background: 'var(--bg-secondary)', padding: '2px 6px', borderRadius: 4 }}>名家技法采集</code>添加作者文风，或联系管理员初始化默认规则。
                    </div>
                )}

                {styles.map(s => (
                    <div key={s.id} style={{
                        marginBottom: 10, padding: '10px 14px',
                        border: s.is_active ? '2px solid var(--accent)' : '2px solid var(--border-soft)',
                        background: s.is_active ? 'var(--bg-card)' : 'var(--bg-panel)',
                        opacity: s.is_active ? 1 : 0.65,
                        transition: 'border-color .2s, opacity .2s',
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
                            <strong style={{ fontSize: 14 }}>{s.name}</strong>
                            <Badge tone={CATEGORY_COLORS[s.category] || 'neutral'}>{s.category}</Badge>
                            <Badge tone={PRIORITY_TONE[s.priority] || 'blue'}>优先级 {s.priority}</Badge>
                            <span style={{ flex: 1 }} />
                            <button
                                className="page-btn"
                                style={{
                                    padding: '2px 12px', minHeight: 26, fontSize: 12,
                                    background: s.is_active ? 'var(--accent-green)' : 'var(--accent-red)',
                                    color: '#fff', border: 'none', cursor: togglingIds[s.id] ? 'wait' : 'pointer',
                                    opacity: togglingIds[s.id] ? 0.6 : 1,
                                }}
                                onClick={() => handleToggle(s)}
                                disabled={!!togglingIds[s.id]}
                            >
                                {togglingIds[s.id] ? '...' : s.is_active ? '已激活' : '已停用'}
                            </button>
                        </div>

                        {editingStyleId === s.id ? (
                            <div style={{ marginTop: 6 }}>
                                <textarea
                                    value={editStyleDesc}
                                    onChange={e => setEditStyleDesc(e.target.value)}
                                    rows={3}
                                    style={{
                                        width: '100%', padding: 8, fontFamily: 'var(--font-body)', fontSize: 13,
                                        border: '2px solid var(--accent)', borderRadius: 0,
                                        background: '#fffef8', color: 'var(--text-main)', resize: 'vertical',
                                        lineHeight: 1.6,
                                    }}
                                />
                                <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                                    <button className="page-btn" onClick={() => handleSaveStyleDesc(s)}
                                        disabled={!!togglingIds[`save-${s.id}`]}>
                                        {togglingIds[`save-${s.id}`] ? '保存中...' : '保存'}
                                    </button>
                                    <button className="page-btn" style={{ background: '#fff8e6' }}
                                        onClick={() => setEditingStyleId(null)}>
                                        取消
                                    </button>
                                </div>
                            </div>
                        ) : (
                            <div
                                style={{ fontSize: 13, color: 'var(--text-sub)', lineHeight: 1.6, cursor: 'pointer' }}
                                onClick={() => { setEditingStyleId(s.id); setEditStyleDesc(s.description) }}
                                title="点击编辑描述"
                            >
                                {s.description || '（点击编辑描述）'}
                            </div>
                    )}
                    </div>
                ))}
            </div>

            {/* ═══════ 自定义文风提示词 (file-based) ═══════ */}
            <div className="card" style={{ marginTop: 16 }}>
                <div className="card-header" onClick={() => setShowPrompts(!showPrompts)} style={{ cursor: 'pointer' }}>
                    <span className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ transform: showPrompts ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform .2s', fontSize: 10 }}>▶</span>
                        自定义文风提示词（文件）
                    </span>
                    <Badge tone="cyan">{prompts.length} 个文件</Badge>
                </div>
                <p style={{ marginBottom: 12, color: 'var(--text-sub)', fontSize: 13 }}>
                    在 <code>设定集/prompts/</code> 下放置 <code>.md</code> 文件，系统写作时自动加载。
                    详见 <a href="https://github.com/lujih/webnovel-writer-opencode/blob/master/docs/guides/custom-style-prompts.md" target="_blank" style={{ color: 'var(--accent)' }}>自定义文风指南</a>。
                </p>

                {!showPrompts && <div className="empty-state compact" style={{ padding: '8px 0', cursor: 'pointer' }} onClick={() => setShowPrompts(true)}>点击展开</div>}

                {showPrompts && (
                    <>
                        {promptsError && <p style={{ marginBottom: 8, color: 'var(--accent-red)', fontWeight: 600 }}>加载失败: {promptsError}</p>}
                        {msg && (
                            <p style={{ marginBottom: 8, color: msg.type === 'error' ? 'var(--accent-red)' : 'var(--accent-green)', fontWeight: 600 }}>
                                {msg.text}
                            </p>
                        )}

                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
                            {prompts.map(p => (
                                <div key={p.filename} style={{
                                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                    padding: '8px 12px', border: '2px solid var(--border-soft)',
                                    background: editing?.filename === p.filename ? 'var(--bg-card-2)' : 'var(--bg-panel)',
                                    cursor: 'pointer',
                                }} onClick={() => setEditing({ ...p })}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                        <Badge tone="blue">{p.filename}</Badge>
                                        <span style={{ fontSize: 13, color: 'var(--text-sub)' }}>
                                            {p.content.slice(0, 60)}{p.content.length > 60 ? '...' : ''}
                                        </span>
                                    </div>
                                    <div style={{ display: 'flex', gap: 4 }}>
                                        <button className="page-btn" style={{ padding: '2px 8px', minHeight: 24, fontSize: 12 }}
                                            onClick={e => { e.stopPropagation(); handleDelete(p.filename) }}>
                                            删除
                                        </button>
                                    </div>
                    </div>
                ))}
                            {prompts.length === 0 && !creating && (
                                <div className="empty-state compact">暂无自定义提示词。点击下方按钮创建。</div>
                            )}
                        </div>

                        {editing && (
                            <div style={{ marginBottom: 16, padding: 12, border: '2px solid var(--accent)', background: 'var(--bg-card)' }}>
                                <div className="mini-label">编辑: {editing.filename}</div>
                                <textarea
                                    value={editing.content}
                                    onChange={e => setEditing({ ...editing, content: e.target.value })}
                                    rows={10}
                                    style={{
                                        width: '100%', padding: 8, fontFamily: 'var(--font-body)', fontSize: 13,
                                        border: '2px solid var(--border-main)', borderRadius: 0,
                                        background: '#fffef8', color: 'var(--text-main)', resize: 'vertical',
                                        lineHeight: 1.6,
                                    }}
                                />
                                <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                                    <button className="page-btn" onClick={handleSave} disabled={loading}>{loading ? '保存中...' : '保存'}</button>
                                    <button className="page-btn" style={{ background: '#fff8e6' }} onClick={() => setEditing(null)} disabled={loading}>取消</button>
                                </div>
                            </div>
                        )}

                        {creating ? (
                            <div style={{ padding: 12, border: '2px solid var(--accent-green)', background: 'var(--bg-card)' }}>
                                <div className="mini-label">新建提示词文件</div>
                                <input
                                    type="text"
                                    value={newName}
                                    onChange={e => setNewName(e.target.value)}
                                    placeholder="文件名（如：文风、对话风格、禁忌）"
                                    style={{
                                        width: '100%', maxWidth: 300, padding: '6px 10px', marginBottom: 8,
                                        border: '2px solid var(--border-main)', borderRadius: 0,
                                        background: '#fffef8', color: 'var(--text-main)', fontWeight: 500,
                                        boxShadow: 'var(--shadow-soft)',
                                    }}
                                />
                                <textarea
                                    value={newContent}
                                    onChange={e => setNewContent(e.target.value)}
                                    rows={8}
                                    placeholder="写你对文风的具体要求。&#10;&#10;示例：&#10;- 对话要口语化，像真人说话&#10;- 动作描写要短促有力&#10;- 每段不超过 3 句话&#10;- 禁止使用'缓缓''淡淡''微微'"
                                    style={{
                                        width: '100%', padding: 8, fontFamily: 'var(--font-body)', fontSize: 13,
                                        border: '2px solid var(--border-main)', borderRadius: 0,
                                        background: '#fffef8', color: 'var(--text-main)', resize: 'vertical',
                                        lineHeight: 1.6,
                                    }}
                                />
                                <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                                    <button className="page-btn" onClick={handleCreate} disabled={!newName.trim() || !newContent.trim() || loading}>{loading ? '创建中...' : '创建'}</button>
                                    <button className="page-btn" style={{ background: '#fff8e6' }} onClick={() => { setCreating(false); setNewName(''); setNewContent('') }} disabled={loading}>取消</button>
                                </div>
                            </div>
                        ) : (
                            !editing && (
                                <button className="page-btn" onClick={() => setCreating(true)}>+ 新建提示词</button>
                            )
                        )}
                    </>
                )}
            </div>
        </div>
    )
}

/* ── Tab 1: 全局文风 ── */

function MasterSettingTab() {
    const [data, setData] = useState(null)
    const [editing, setEditing] = useState({})
    const [saving, setSaving] = useState(false)
    const [msg, setMsg] = useState(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        setLoading(true)
        fetchMasterSetting()
            .then(setData)
            .catch(e => setData({ _error: e.message }))
            .finally(() => setLoading(false))
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

    if (loading) return <div className="empty-state">加载中...</div>
    if (data._error) return <div className="empty-state" style={{ color: 'var(--accent-red)' }}>加载失败: {data._error}</div>
    if (allKeys.length === 0) return (
        <div style={{ padding: 32, textAlign: 'center' }}>
            <div style={{ fontSize: 24, marginBottom: 8 }}>📋</div>
            <div style={{ color: 'var(--text-sub)' }}>全局文风需要通过 <code style={{ background: 'var(--bg-secondary)', padding: '2px 6px', borderRadius: 4 }}>/webnovel-init</code> 初始化项目后设置。</div>
        </div>
    )

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
                <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
                    {patterns.map((p, i) => (
                        <div key={p.text + i} style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)' }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                <strong style={{ fontSize: 13 }}>{p.text}</strong>
                                <button onClick={() => handleDelete(p.text)} className="page-btn"
                                    style={{ padding: '2px 8px', minHeight: 24, fontSize: 11, flexShrink: 0 }}>
                                    删除
                                </button>
                            </div>
                            <div style={{ fontSize: 11, color: 'var(--text-sub)', marginTop: 4 }}>
                                📖 来源: {p.source || p.source_table || '手动'}
                            </div>
                            {(p.category || p.genre) && (
                                <div style={{ fontSize: 11, color: 'var(--text-sub)' }}>
                                    🏷️ 分类: {[p.category, p.genre].filter(Boolean).join(' · ')}
                                </div>
                            )}
                        </div>
                    ))}
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
    const [groups, setGroups] = useState([])
    const [error, setError] = useState(null)
    const [search, setSearch] = useState('')
    const [expandedCat, setExpandedCat] = useState('对话')
    const [sourceFilter, setSourceFilter] = useState('')
    // ── CRUD state ──
    const [editingId, setEditingId] = useState(null)
    const [editName, setEditName] = useState('')
    const [editDesc, setEditDesc] = useState('')
    const [editSubCat, setEditSubCat] = useState('')
    const [editPrimaryCat, setEditPrimaryCat] = useState('')
    const [editWhenToUse, setEditWhenToUse] = useState('')
    const [editKeywords, setEditKeywords] = useState('')
    const [editDetailDesc, setEditDetailDesc] = useState('')
    const [editExample, setEditExample] = useState('')
    const [editNegativeExample, setEditNegativeExample] = useState('')
    const [editAntiPattern, setEditAntiPattern] = useState('')
    const [editModelInstruction, setEditModelInstruction] = useState('')
    const [editApplicableGenres, setEditApplicableGenres] = useState('')
    const [editLevelName, setEditLevelName] = useState('')
    const [editDifficulty, setEditDifficulty] = useState('5')
    const [creating, setCreating] = useState(false)
    const [newName, setNewName] = useState('')
    const [newDesc, setNewDesc] = useState('')
    const [newSubCat, setNewSubCat] = useState('')
    const [newPrimaryCat, setNewPrimaryCat] = useState('')
    const [newSourceCsv, setNewSourceCsv] = useState('')
    const [actionLoading, setActionLoading] = useState({})
    const [actionMsg, setActionMsg] = useState(null)

    const reload = useCallback(() => {
        fetch('/api/techniques/grouped')
            .then(r => r.json())
            .then(d => {
                if (Array.isArray(d)) {
                    setGroups(d)
                } else if (d && Array.isArray(d.groups)) {
                    setGroups(d.groups)
                } else {
                    console.warn('Unexpected techniques/grouped response:', typeof d, d)
                    setGroups([])
                }
            })
            .catch(e => setError(e.message))
    }, [])

    useEffect(() => { reload() }, [reload])

    const filtered = useMemo(() => {
        let result = groups
        if (search) {
            const q = search.toLowerCase()
            result = result.map(g => ({
                ...g,
                techniques: g.techniques.filter(t =>
                    (t.name || '').toLowerCase().includes(q) ||
                    (t.description || '').toLowerCase().includes(q) ||
                    (t.sub_category || '').toLowerCase().includes(q) ||
                    (t.keywords || '').toLowerCase().includes(q) ||
                    (t.when_to_use || '').toLowerCase().includes(q)
                )
            })).filter(g => g.techniques.length > 0)
        }
        if (sourceFilter) {
            result = result.map(g => ({
                ...g,
                techniques: g.techniques.filter(t => t.source_csv === sourceFilter)
            })).filter(g => g.techniques.length > 0)
        }
        return result
    }, [groups, search, sourceFilter])

    const sourceOptions = useMemo(() => {
        const sources = new Set()
        groups.forEach(g => g.techniques.forEach(t => {
            if (t.source_csv) sources.add(t.source_csv)
        }))
        return Array.from(sources).sort()
    }, [groups])

    const totalCount = groups.reduce((s, g) => s + g.count, 0)

    const setLoading = (id, v) => setActionLoading(prev => v ? { ...prev, [id]: true } : { ...prev, [id]: undefined })

    // ── Edit ──
    const startEdit = (t) => {
        setEditingId(t.id)
        setEditName(t.name || '')
        setEditDesc(t.description || '')
        setEditSubCat(t.sub_category || '')
        setEditPrimaryCat(t.primary_category || t.category || '')
        setEditWhenToUse(t.when_to_use || '')
        setEditKeywords(t.keywords || '')
        setEditDetailDesc(t.detailed_description || '')
        setEditExample(t.positive_example || t.example || '')
        setEditNegativeExample(t.negative_example || '')
        setEditAntiPattern(t.anti_pattern || '')
        setEditModelInstruction(t.model_instruction || '')
        setEditApplicableGenres(t.applicable_genres || '')
        setEditLevelName(t.level_name || '')
        setEditDifficulty(t.difficulty != null ? String(t.difficulty) : '5')
        setActionMsg(null)
    }

    const saveEdit = async (t) => {
        if (!editName.trim()) return
        setLoading(`save-${t.id}`, true)
        setActionMsg(null)
        try {
            await updateTechnique(t.id, {
                name: editName.trim(),
                description: editDesc.trim(),
                category: editPrimaryCat.trim(),
                primary_category: editPrimaryCat.trim(),
                sub_category: editSubCat.trim(),
                when_to_use: editWhenToUse.trim(),
                keywords: editKeywords.trim(),
                detailed_description: editDetailDesc.trim(),
                positive_example: editExample.trim(),
                negative_example: editNegativeExample.trim(),
                anti_pattern: editAntiPattern.trim(),
                example: (editExample.trim() && editNegativeExample.trim())
                    ? `✅ ${editExample.trim()}\n❌ ${editNegativeExample.trim()}`
                    : (editExample.trim() || editNegativeExample.trim() || ''),
                model_instruction: editModelInstruction.trim(),
                applicable_genres: editApplicableGenres.trim(),
                level_name: editLevelName.trim(),
                difficulty: parseInt(editDifficulty) || 5,
            })
            setEditingId(null)
            setActionMsg({ type: 'success', text: '技法已更新' })
            reload()
        } catch (e) {
            setActionMsg({ type: 'error', text: e.message })
        } finally {
            setLoading(`save-${t.id}`, false)
        }
    }

    // ── Delete ──
    const handleDelete = async (t) => {
        if (!confirm(`确认删除技法「${t.name}」？`)) return
        setLoading(`del-${t.id}`, true)
        setActionMsg(null)
        try {
            await deleteTechnique(t.id)
            setActionMsg({ type: 'success', text: `已删除「${t.name}」` })
            reload()
        } catch (e) {
            setActionMsg({ type: 'error', text: e.message })
        } finally {
            setLoading(`del-${t.id}`, false)
        }
    }

    // ── Create ──
    const handleCreate = async () => {
        if (!newName.trim() || !newDesc.trim()) return
        setLoading('create', true)
        setActionMsg(null)
        try {
            await createTechnique({
                name: newName.trim(),
                description: newDesc.trim(),
                sub_category: newSubCat.trim(),
                primary_category: newPrimaryCat.trim(),
                source_csv: newSourceCsv.trim(),
            })
            setNewName(''); setNewDesc(''); setNewSubCat(''); setNewPrimaryCat(''); setNewSourceCsv('')
            setCreating(false)
            setActionMsg({ type: 'success', text: '技法已创建' })
            reload()
        } catch (e) {
            setActionMsg({ type: 'error', text: e.message })
        } finally {
            setLoading('create', false)
        }
    }

    return (
        <div className="card">
            <div className="card-header">
                <span className="card-title">写作技法库</span>
                <Badge tone="blue">{totalCount} 条技法 · {groups.length} 大类</Badge>
            </div>
            
            {/* Search + New button */}
            <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 8 }}>
                <input type="text" value={search} onChange={e => setSearch(e.target.value)}
                    placeholder="搜索技法名称/关键词..."
                    style={{ flex: 1, padding: '8px 12px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 13 }} />
                <button className="page-btn" onClick={() => { setCreating(!creating); setActionMsg(null) }}
                    style={{ fontSize: 13, whiteSpace: 'nowrap' }}>
                    ➕ 新建技法
                </button>
            </div>

            {/* Source filter */}
            {sourceOptions.length > 0 && (
                <div style={{ display: 'flex', gap: 4, padding: '8px 16px', flexWrap: 'wrap', borderBottom: '1px solid var(--border)' }}>
                    <button className={`page-btn ${!sourceFilter ? 'active' : ''}`}
                        onClick={() => setSourceFilter('')}
                        style={{ fontSize: 12 }}>
                        全部
                    </button>
                    {sourceOptions.map(s => (
                        <button key={s}
                            className={`page-btn ${sourceFilter === s ? 'active' : ''}`}
                            onClick={() => setSourceFilter(sourceFilter === s ? '' : s)}
                            style={{ fontSize: 12 }}>
                            {s}
                        </button>
                    ))}
                </div>
            )}

            {/* Status message */}
            {actionMsg && (
                <div style={{ padding: '6px 16px', fontSize: 12, fontWeight: 600,
                    color: actionMsg.type === 'error' ? 'var(--accent-red)' : 'var(--accent-green)',
                    borderBottom: '1px solid var(--border)' }}>
                    {actionMsg.text}
                </div>
            )}

            {/* Create form */}
            {creating && (
                <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', background: 'var(--bg-card)' }}>
                    <div style={{ fontWeight: 700, marginBottom: 8, fontSize: 13 }}>新建写作技法</div>
                    <div style={{ display: 'flex', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
                        <input type="text" value={newName} onChange={e => setNewName(e.target.value)}
                            placeholder="技法名称 *"
                            style={{ flex: 1, minWidth: 150, padding: '6px 10px', border: '2px solid var(--border-main)', borderRadius: 0, fontSize: 12, background: '#fff8e6' }} />
                        <input type="text" value={newPrimaryCat} onChange={e => setNewPrimaryCat(e.target.value)}
                            placeholder="主分类"
                            style={{ flex: 1, minWidth: 100, padding: '6px 10px', border: '2px solid var(--border-main)', borderRadius: 0, fontSize: 12, background: '#fff8e6' }} />
                        <input type="text" value={newSubCat} onChange={e => setNewSubCat(e.target.value)}
                            placeholder="子分类"
                            style={{ flex: 1, minWidth: 100, padding: '6px 10px', border: '2px solid var(--border-main)', borderRadius: 0, fontSize: 12, background: '#fff8e6' }} />
                        <input type="text" value={newSourceCsv} onChange={e => setNewSourceCsv(e.target.value)}
                            placeholder="来源"
                            style={{ flex: 1, minWidth: 100, padding: '6px 10px', border: '2px solid var(--border-main)', borderRadius: 0, fontSize: 12, background: '#fff8e6' }} />
                    </div>
                    <textarea value={newDesc} onChange={e => setNewDesc(e.target.value)}
                        placeholder="核心摘要/描述 *" rows={3}
                        style={{ width: '100%', padding: 8, fontFamily: 'var(--font-body)', fontSize: 12, border: '2px solid var(--border-main)', borderRadius: 0, background: '#fff8e6', color: 'var(--text-main)', resize: 'vertical', lineHeight: 1.6, marginBottom: 8 }} />
                    <div style={{ display: 'flex', gap: 8 }}>
                        <button className="page-btn" onClick={handleCreate} disabled={!newName.trim() || !newDesc.trim() || actionLoading['create']}>
                            {actionLoading['create'] ? '创建中...' : '创建'}
                        </button>
                        <button className="page-btn" style={{ background: '#fff8e6' }}
                            onClick={() => { setCreating(false); setNewName(''); setNewDesc(''); setNewSubCat(''); setNewPrimaryCat(''); setNewSourceCsv('') }}>
                            取消
                        </button>
                    </div>
                </div>
            )}

            {/* Category tabs */}
            <div style={{ display: 'flex', gap: 4, padding: '8px 16px', flexWrap: 'wrap', borderBottom: '1px solid var(--border)', background: 'var(--bg-secondary)' }}>
                {groups.map(g => (
                    <button key={g.primary_category}
                        className={`page-btn ${expandedCat === g.primary_category ? 'active' : ''}`}
                        onClick={() => setExpandedCat(expandedCat === g.primary_category ? '' : g.primary_category)}
                        style={{ fontSize: 12 }}>
                        {g.primary_category} ({g.count})
                    </button>
                ))}
            </div>

            {/* Grouped techniques */}
            <div style={{ maxHeight: 600, overflow: 'auto' }}>
                {error && (
                    <div style={{ padding: '40px 16px', textAlign: 'center', color: 'var(--accent-red)', fontSize: 13 }}>
                        ⚠️ 加载失败: {error}
                    </div>
                )}
                {!error && groups.length === 0 && (
                    <div style={{ padding: '40px 16px', textAlign: 'center', color: 'var(--text-sub)', fontSize: 13 }}>
                        暂无技法数据，请先导入 CSV 或手动创建技法。
                    </div>
                )}
                {!error && groups.length > 0 && filtered.length === 0 && (
                    <div style={{ padding: '40px 16px', textAlign: 'center', color: 'var(--text-sub)', fontSize: 13 }}>
                        没有找到匹配的技法，请尝试其他搜索关键词。
                    </div>
                )}
                {filtered.map(g => (
                    <div key={g.primary_category}>
                        <div onClick={() => setExpandedCat(expandedCat === g.primary_category ? '' : g.primary_category)}
                            style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 16px', cursor: 'pointer', background: 'var(--bg-secondary)', borderBottom: '1px solid var(--border)', fontWeight: 600 }}>
                            <span>{g.primary_category} <span style={{ color: 'var(--text-sub)', fontWeight: 400 }}>· {g.count} 条技法</span></span>
                            <span style={{ fontSize: 12, color: 'var(--text-sub)' }}>{expandedCat === g.primary_category ? '收起' : '展开'}</span>
                        </div>
                        {expandedCat === g.primary_category && g.techniques.map((t, i) => (
                            editingId === t.id ? (
                                /* ── Inline edit card ── */
                                <div key={`edit-${t.id}`} style={{ padding: '10px 16px', borderBottom: '1px solid var(--accent)', background: 'var(--bg-card)' }}>
                                    <div style={{ display: 'flex', gap: 6, marginBottom: 4, flexWrap: 'wrap', alignItems: 'center' }}>
                                        <span style={{ fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap' }}>技法名:</span>
                                        <input type="text" value={editName} onChange={e => setEditName(e.target.value)}
                                            style={{ flex: 1, minWidth: 120, padding: '4px 8px', border: '1px solid var(--border)', borderRadius: 4, fontSize: 12, background: '#fffef8' }} />
                                        <span style={{ fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap' }}>分类:</span>
                                        <input type="text" value={editPrimaryCat} onChange={e => setEditPrimaryCat(e.target.value)}
                                            style={{ width: 80, padding: '4px 8px', border: '1px solid var(--border)', borderRadius: 4, fontSize: 12, background: '#fffef8' }} />
                                        <span style={{ fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap' }}>子分类:</span>
                                        <input type="text" value={editSubCat} onChange={e => setEditSubCat(e.target.value)}
                                            style={{ width: 80, padding: '4px 8px', border: '1px solid var(--border)', borderRadius: 4, fontSize: 12, background: '#fffef8' }} />
                                    </div>
                                    <div style={{ display: 'flex', gap: 6, marginBottom: 4, alignItems: 'center' }}>
                                        <span style={{ fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap' }}>描述:</span>
                                        <input type="text" value={editDesc} onChange={e => setEditDesc(e.target.value)}
                                            style={{ flex: 1, padding: '4px 8px', border: '1px solid var(--border)', borderRadius: 4, fontSize: 12, background: '#fffef8' }} />
                                    </div>
                                    <div style={{ display: 'flex', gap: 6, marginBottom: 4, alignItems: 'center' }}>
                                        <span style={{ fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap' }}>适用场景:</span>
                                        <input type="text" value={editWhenToUse} onChange={e => setEditWhenToUse(e.target.value)}
                                            style={{ flex: 1, padding: '4px 8px', border: '1px solid var(--border)', borderRadius: 4, fontSize: 12, background: '#fffef8' }} />
                                    </div>
                                    <div style={{ display: 'flex', gap: 6, marginBottom: 4, alignItems: 'center' }}>
                                        <span style={{ fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap' }}>关键词:</span>
                                        <input type="text" value={editKeywords} onChange={e => setEditKeywords(e.target.value)}
                                            style={{ flex: 1, padding: '4px 8px', border: '1px solid var(--border)', borderRadius: 4, fontSize: 12, background: '#fffef8' }} />
                                    </div>

                                    {/* 题材 */}
                                    <div style={{ display: 'flex', gap: 6, marginBottom: 4, alignItems: 'center' }}>
                                        <span style={{ fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap' }}>题材:</span>
                                        <input type="text" value={editApplicableGenres} onChange={e => setEditApplicableGenres(e.target.value)}
                                            style={{ flex: 1, padding: '4px 8px', border: '1px solid var(--border)', borderRadius: 4, fontSize: 12, background: '#fffef8' }} />
                                    </div>

                                    {/* 详细展开 */}
                                    <div style={{ marginBottom: 4 }}>
                                        <span style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 2 }}>详细展开:</span>
                                        <textarea value={editDetailDesc} onChange={e => setEditDetailDesc(e.target.value)}
                                            rows={3} style={{ width: '100%', padding: '4px 8px', border: '1px solid var(--border)', borderRadius: 4, fontSize: 12, background: '#fffef8', resize: 'vertical', fontFamily: 'var(--font-body)' }} />
                                    </div>

                                    {/* 正例 */}
                                    <div style={{ marginBottom: 4 }}>
                                        <span style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 2 }}>正例:</span>
                                        <textarea value={editExample} onChange={e => setEditExample(e.target.value)}
                                            rows={2} style={{ width: '100%', padding: '4px 8px', border: '1px solid var(--border)', borderRadius: 4, fontSize: 12, background: '#fffef8', resize: 'vertical', fontFamily: 'var(--font-body)' }} />
                                    </div>
                                    {/* 反例 */}
                                    <div style={{ marginBottom: 4 }}>
                                        <span style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 2 }}>反例:</span>
                                        <textarea value={editNegativeExample} onChange={e => setEditNegativeExample(e.target.value)}
                                            rows={2} style={{ width: '100%', padding: '4px 8px', border: '1px solid var(--border)', borderRadius: 4, fontSize: 12, background: '#fffef8', resize: 'vertical', fontFamily: 'var(--font-body)' }} />
                                    </div>
                                    {/* 毒点 */}
                                    <div style={{ marginBottom: 4 }}>
                                        <span style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 2 }}>毒点:</span>
                                        <textarea value={editAntiPattern} onChange={e => setEditAntiPattern(e.target.value)}
                                            rows={2} style={{ width: '100%', padding: '4px 8px', border: '1px solid var(--border)', borderRadius: 4, fontSize: 12, background: '#fffef8', resize: 'vertical', fontFamily: 'var(--font-body)' }} />
                                    </div>

                                    {/* 大模型指令 */}
                                    <div style={{ marginBottom: 4 }}>
                                        <span style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 2 }}>大模型指令:</span>
                                        <textarea value={editModelInstruction} onChange={e => setEditModelInstruction(e.target.value)}
                                            rows={2} style={{ width: '100%', padding: '4px 8px', border: '1px solid var(--border)', borderRadius: 4, fontSize: 12, background: '#fffef8', resize: 'vertical', fontFamily: 'var(--font-body)' }} />
                                    </div>

                                    {/* 层级 + 难度 一行 */}
                                    <div style={{ display: 'flex', gap: 12, marginBottom: 4, alignItems: 'center' }}>
                                        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                                            <span style={{ fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap' }}>层级:</span>
                                            <select value={editLevelName} onChange={e => setEditLevelName(e.target.value)}
                                                style={{ padding: '4px 8px', border: '1px solid var(--border)', borderRadius: 4, fontSize: 12, background: '#fffef8' }}>
                                                <option value="">-</option>
                                                <option value="核心技法">核心技法</option>
                                                <option value="知识补充">知识补充</option>
                                                <option value="进阶技巧">进阶技巧</option>
                                            </select>
                                        </div>
                                        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                                            <span style={{ fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap' }}>难度:</span>
                                            <input type="number" min="1" max="5" value={editDifficulty}
                                                onChange={e => setEditDifficulty(e.target.value)}
                                                style={{ width: 60, padding: '4px 8px', border: '1px solid var(--border)', borderRadius: 4, fontSize: 12, background: '#fffef8' }} />
                                        </div>
                                    </div>

                                    <div style={{ display: 'flex', gap: 8, marginTop: 2 }}>
                                        <button className="page-btn" onClick={() => saveEdit(t)} disabled={actionLoading[`save-${t.id}`]}>
                                            {actionLoading[`save-${t.id}`] ? '保存中...' : '保存'}
                                        </button>
                                        <button className="page-btn" style={{ background: '#fff8e6' }} onClick={() => {
                                            setEditingId(null); setEditDetailDesc(''); setEditExample(''); setEditNegativeExample(''); setEditAntiPattern('');
                                            setEditModelInstruction(''); setEditApplicableGenres(''); setEditLevelName(''); setEditDifficulty('5');
                                        }}>取消</button>
                                    </div>
                                </div>
                            ) : (
                                /* ── Technique card ── */
                                <div key={`card-${t.id}`} style={{ padding: '10px 16px', borderBottom: '1px solid var(--border)' }}>
                                    {/* Title row: [主分类badge] 技法名 [编号] [来源badge]  — 13px */}
                                    <div style={{ display: 'flex', gap: 6, marginBottom: 2, flexWrap: 'wrap', alignItems: 'center', fontSize: 13 }}>
                                        {t.primary_category && <Badge tone={CATEGORY_COLORS[t.primary_category] || 'blue'}>{t.primary_category}</Badge>}
                                        <strong>{t.name}</strong>
                                        {t.code && <span style={{ color: 'var(--text-mute)', fontSize: 10 }}>{t.code}</span>}
                                        {t.source_csv && <Badge tone="green">{t.source_csv}</Badge>}
                                        <span style={{ flex: 1 }} />
                                        <button className="page-btn" style={{ fontSize: 11, padding: '2px 6px', minHeight: 22 }}
                                            onClick={() => startEdit(t)} title="编辑技法">✏️</button>
                                        <button className="page-btn" style={{ fontSize: 11, padding: '2px 6px', minHeight: 22, color: 'var(--accent-red)' }}
                                            onClick={() => handleDelete(t)} disabled={actionLoading[`del-${t.id}`]}
                                            title="删除技法">
                                            {actionLoading[`del-${t.id}`] ? '...' : '🗑️'}
                                        </button>
                                    </div>

                                    {/* Description — 12px */}
                                    {t.description && (
                                        <div style={{ color: 'var(--text-sub)', fontSize: 12, lineHeight: 1.6, marginBottom: 2 }}>
                                            {t.description}
                                        </div>
                                    )}

                                    {/* Meta row: 适用 + 题材 + 关键词 — 11px plain text */}
                                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', fontSize: 11, color: 'var(--text-mute)', marginTop: 2 }}>
                                        {t.when_to_use && (
                                            <span style={{ color: 'var(--accent-blue)' }}>💡 适用: {t.when_to_use}</span>
                                        )}
                                        {t.applicable_genres && t.source_csv !== '名家技法' && (
                                            <span style={{ color: 'var(--accent-green)' }}>📚 题材: {t.applicable_genres}</span>
                                        )}
                                        {t.keywords && (
                                            <span>🔑 关键词: {t.keywords.split('|').filter(Boolean).join(' / ')}</span>
                                        )}
                                        {t.intent_synonyms && (
                                            <span style={{ color: 'var(--text-mute)' }}>🎯 意图: {t.intent_synonyms}</span>
                                        )}
                                        {t.skill_tags && (
                                            <span style={{ color: 'var(--text-mute)' }}>🏷️ 技能: {t.skill_tags}</span>
                                        )}
                                    </div>

                                    {/* 层级 — 11px gray text, not a badge */}
                                    {t.level_name && (
                                        <div style={{ fontSize: 11, color: 'var(--text-mute)', marginTop: 1 }}>
                                            层级: {t.level_name}
                                        </div>
                                    )}

                                    {/* 出处 — 名家技法专用 */}
                                    {t.source_csv === '名家技法' && t.applicable_genres && (
                                        <div style={{ fontSize: 11, marginTop: 2, color: 'var(--accent-gold, #c9a44b)' }}>
                                            📖 出处: {t.applicable_genres}
                                        </div>
                                    )}

                                    {/* ── Expandable sections (below non-expandable content) ── */}
                                    {t.detailed_description && (
                                        <details style={{ marginTop: 3, fontSize: 12 }}>
                                            <summary style={{ cursor: 'pointer', color: 'var(--accent-blue)' }}>▸ 详细展开</summary>
                                            <div style={{ padding: '4px 0 0 8px', color: 'var(--text-sub)', lineHeight: 1.6, borderLeft: '2px solid var(--border)' }}>
                                                {t.detailed_description}
                                            </div>
                                        </details>
                                    )}

                                    {t.example && (
                                        <details style={{ marginTop: 2, fontSize: 12 }}>
                                            <summary style={{ cursor: 'pointer', color: 'var(--accent-green)' }}>▸ 正例 / 反例</summary>
                                            <div style={{ padding: '6px 0 0 8px', whiteSpace: 'pre-wrap', lineHeight: 1.6, borderLeft: '2px solid var(--border)', fontSize: 11, color: 'var(--text-sub)' }}>
                                                {t.example}
                                            </div>
                                        </details>
                                    )}
                                    {t.anti_pattern && (
                                        <details style={{ marginTop: 2, fontSize: 12 }}>
                                            <summary style={{ cursor: 'pointer', color: '#d97706' }}>▸ 毒点/常见误区</summary>
                                            <div style={{ padding: '4px 0 0 8px', lineHeight: 1.6, borderLeft: '2px solid var(--accent-orange, #d97706)', fontSize: 11, color: 'var(--text-sub)' }}>
                                                {t.anti_pattern}
                                            </div>
                                        </details>
                                    )}

                                    {t.model_instruction && (
                                        <details style={{ marginTop: 2, fontSize: 12 }}>
                                            <summary style={{ cursor: 'pointer', color: 'var(--accent-purple)' }}>▸ 大模型指令</summary>
                                            <div style={{ padding: '4px 0 0 8px', lineHeight: 1.5, borderLeft: '2px solid var(--border)', fontSize: 11, color: 'var(--text-sub)' }}>
                                                {t.model_instruction}
                                            </div>
                                        </details>
                                    )}
                                </div>
                            )
                        ))}
                    </div>
                ))}
                {filtered.length === 0 && (
                    <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-sub)' }}>暂无技法数据</div>
                )}
            </div>
        </div>
    )
}


/* ── Reference tab (reusable for 人设模板/金手指库/桥段套路/爽点节奏/场景写法) ── */

function ReferenceTab({ sourceCsv, title }) {
    const [items, setItems] = useState([])
    const [search, setSearch] = useState('')
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)

    const load = useCallback(() => {
        setLoading(true)
        const params = new URLSearchParams({ source: sourceCsv, limit: 100 })
        if (search) params.set('q', search)
        fetch(`/api/reference/search?${params}`)
            .then(r => r.json())
            .then(d => setItems(Array.isArray(d) ? d : []))
            .catch(e => setError(e.message))
            .finally(() => setLoading(false))
    }, [sourceCsv, search])

    useEffect(() => { load() }, [load])

    const totalCount = items.length

    return (
        <div className="card">
            <div className="card-header">
                <span className="card-title">{title}</span>
                <Badge tone="blue">{totalCount} 条</Badge>
            </div>
            <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 8 }}>
                <input type="text" value={search} onChange={e => setSearch(e.target.value)}
                    placeholder={`搜索${title}...`}
                    style={{ flex: 1, padding: '8px 12px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 13 }} />
            </div>

            {loading && <div className="empty-state compact">加载中...</div>}
            {error && <div className="empty-state compact" style={{ color: 'var(--accent-red)' }}>加载失败: {error}</div>}
            {!loading && items.length === 0 && <div className="empty-state compact">{search ? '无匹配条目' : '暂无数据'}</div>}

            <div style={{ maxHeight: 600, overflow: 'auto' }}>
                {items.map((item, i) => (
                    <div key={item.id || i} style={{ padding: '10px 16px', borderBottom: '1px solid var(--border)' }}>
                        <div style={{ display: 'flex', gap: 6, marginBottom: 2, alignItems: 'center', fontSize: 13 }}>
                            <strong>{item.name}</strong>
                            {item.code && <span style={{ color: 'var(--text-mute)', fontSize: 10 }}>{item.code}</span>}
                            {item.category && <Badge tone="blue">{item.category}</Badge>}
                        </div>
                        {item.description && (
                            <div style={{ color: 'var(--text-sub)', fontSize: 12, lineHeight: 1.6, marginBottom: 2 }}>
                                {item.description}
                            </div>
                        )}
                        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', fontSize: 11, color: 'var(--text-mute)', marginTop: 2 }}>
                            {item.keywords && <span>🔑 {item.keywords}</span>}
                            {item.intent_synonyms && <span>🎯 {item.intent_synonyms}</span>}
                            {item.applicable_genres && <span>📚 {item.applicable_genres}</span>}
                            {item.skill_tags && <span>🏷️ {item.skill_tags}</span>}
                            {item.level_name && <span>📊 层级: {item.level_name}</span>}
                        </div>
                        {(item.positive_example || item.negative_example) && (
                            <details style={{ marginTop: 2, fontSize: 12 }}>
                                <summary style={{ cursor: 'pointer', color: 'var(--accent-green)' }}>▸ 正例 / 反例</summary>
                                <div style={{ padding: '4px 0 0 8px', whiteSpace: 'pre-wrap', lineHeight: 1.5, borderLeft: '2px solid var(--border)', fontSize: 11, color: 'var(--text-sub)' }}>
                                    {item.example || (item.positive_example ? `✅ ${item.positive_example}` : '')}
                                    {item.negative_example ? `\n❌ ${item.negative_example}` : ''}
                                </div>
                            </details>
                        )}
                        {item.anti_pattern && (
                            <details style={{ marginTop: 2, fontSize: 12 }}>
                                <summary style={{ cursor: 'pointer', color: '#d97706' }}>▸ 毒点/常见误区</summary>
                                <div style={{ padding: '4px 0 0 8px', lineHeight: 1.5, borderLeft: '2px solid #d97706', fontSize: 11, color: 'var(--text-sub)' }}>
                                    {item.anti_pattern}
                                </div>
                            </details>
                        )}
                        {item.model_instruction && (
                            <details style={{ marginTop: 2, fontSize: 12 }}>
                                <summary style={{ cursor: 'pointer', color: 'var(--accent-purple)' }}>▸ 大模型指令</summary>
                                <div style={{ padding: '4px 0 0 8px', lineHeight: 1.5, borderLeft: '2px solid var(--border)', fontSize: 11, color: 'var(--text-sub)' }}>
                                    {item.model_instruction}
                                </div>
                            </details>
                        )}
                        {item.detailed_description && (() => {
                            const parts = item.detailed_description.split(/(【[^】]+】[^\n【]*)/g).filter(Boolean)
                            const labeledFields = []
                            let remaining = []
                            for (const p of parts) {
                                const match = p.match(/^【(.+?)】(.*)/)
                                if (match) {
                                    labeledFields.push({ label: match[1], value: match[2].trim() })
                                } else {
                                    remaining.push(p.trim())
                                }
                            }
                            const plainText = remaining.join('\n').trim()

                            return (
                                <>
                                    {labeledFields.map(({label, value}, i) => (
                                        <div key={i} style={{ margin: '4px 0', fontSize: 11 }}>
                                            <span style={{ fontWeight: 600, color: 'var(--accent-blue)' }}>
                                                {label}：
                                            </span>
                                            <span style={{ color: 'var(--text-sub)' }}>{value}</span>
                                        </div>
                                    ))}
                                    {plainText && (
                                        <details style={{ marginTop: 2, fontSize: 12 }}>
                                            <summary style={{ cursor: 'pointer', color: 'var(--accent-blue)' }}>▸ 详细展开</summary>
                                            <div style={{ padding: '4px 0 0 8px', lineHeight: 1.5, borderLeft: '2px solid var(--border)', fontSize: 11, color: 'var(--text-sub)' }}>
                                                {plainText}
                                            </div>
                                        </details>
                                    )}
                                </>
                            )
                        })()}
                    </div>
                ))}
            </div>
        </div>
    )
}

/* ── Tab 4: 名家技法 ── */

function MastersTab() {
    const [author, setAuthor] = useState('')
    const [authors, setAuthors] = useState([])
    const [summaries, setSummaries] = useState([])
    const [chapters, setChapters] = useState([])
    const [reports, setReports] = useState([])
    const [activeTask, setActiveTask] = useState(null)
    const [loading, setLoading] = useState(false)
    const [selectedAuthor, setSelectedAuthor] = useState(null)
    const [uploadFile, setUploadFile] = useState(null)
    const [uploadAuthor, setUploadAuthor] = useState('')
    const [uploadWork, setUploadWork] = useState('')
    const [uploading, setUploading] = useState(false)
    const [uploadMsg, setUploadMsg] = useState(null)
    const [uploadTaskId, setUploadTaskId] = useState(null)
    const [editingChapterId, setEditingChapterId] = useState(null)
    const [editChapterTitle, setEditChapterTitle] = useState('')
    const [actionLoading, setActionLoading] = useState({})
    const [actionMsg, setActionMsg] = useState(null)
    const [chaptersShowAll, setChaptersShowAll] = useState(false)
    const [aiProgress, setAiProgress] = useState(null)
    const aiProgressRef = useRef(null)
    const [aiRunning, setAiRunning] = useState(false)
    const [authorStyles, setAuthorStyles] = useState(null)
    const selectedAuthorRef = useRef(null)
    const taskStartRef = useRef(null)
    aiProgressRef.current = aiProgress
    selectedAuthorRef.current = selectedAuthor
    
    useEffect(() => {
        fetch('/api/collect/authors').then(r=>r.json()).then(d=>setAuthors(d.authors||[]))
        fetch('/api/collect/active').then(r=>r.json()).then(d=>{
            if (d.tasks?.length) setActiveTask(d.tasks[0])
        })
    }, [])
    
    // ── SSE reconnect + auto-reload on server restart ──
    const sseRetryRef = useRef(0)
    const sseHeartbeatRef = useRef(null)
    const [sseConnLost, setSseConnLost] = useState(false)

    useEffect(() => {
        let eventSource = null
        let mounted = true

        function connectSSE() {
            eventSource = new EventSource("/api/events")

            eventSource.addEventListener("collection-progress", (e) => {
                const d = JSON.parse(e.data)
                if (d.type !== "collection-progress") return
                const { task_id, author, status, progress } = d.data
                setActiveTask(prev => prev?.task_id === task_id ? {
                    ...prev, status, progress: JSON.stringify(progress),
                    steps_json: JSON.stringify([...JSON.parse(prev.steps_json||'[]'), {step:status, message:progress.message}])
                } : prev)
                // Handle AI summarize progress steps
                if (status === "loading-context" || status === "ai-summarizing" || status === "publishing" || status === "analyzing") {
                    setAiProgress({ step: status, message: progress?.message || '' })
                }
                if (status === "done") {
                    taskStartRef.current = null
                    setUploadMsg({ type: "success", text: `「${author}」文风分析完成！` })
                    fetch('/api/collect/authors').then(r=>r.json()).then(d=>setAuthors(d.authors||[]))
                    if (aiProgressRef.current) {
                        setAiProgress({ step: 'done', message: '' })
                        setAiRunning(false)
                        loadAuthorData(author)
                    }
                } else if (status === "failed") {
                    taskStartRef.current = null
                    setUploadMsg({ type: "error", text: progress.message || "分析失败" })
                    if (aiProgressRef.current) {
                        setAiProgress({ step: 'failed', message: progress?.message || '分析失败' })
                        setAiRunning(false)
                    }
                }
            })

            // Auto-reload when backend signals server restart
            eventSource.addEventListener("server-restart", () => {
                window.location.reload()
            })

            // Heartbeat: any SSE message resets the disconnect timer
            eventSource.addEventListener("message", () => {
                sseHeartbeatRef.current = Date.now()
                if (sseRetryRef.current > 0) setSseConnLost(false)
            })

            eventSource.onerror = () => {
                if (eventSource) {
                    eventSource.close()
                    eventSource = null
                }
                if (!mounted) return
                sseRetryRef.current++
                const delay = Math.min(1000 * Math.pow(2, sseRetryRef.current), 30000)
                setTimeout(connectSSE, delay)
            }

            eventSource.onopen = () => {
                sseRetryRef.current = 0
                sseHeartbeatRef.current = Date.now()
            }
        }

        connectSSE()

        // Heartbeat watchdog: show banner if no event for 30s
        const hbTimer = setInterval(() => {
            if (sseHeartbeatRef.current && Date.now() - sseHeartbeatRef.current > 30000) {
                setSseConnLost(true)
            }
        }, 5000)

        return () => {
            mounted = false
            clearInterval(hbTimer)
            if (eventSource) eventSource.close()
        }
    }, [])
    
    async function startCollection() {
        if (!author.trim()) return
        setLoading(true)
        const res = await fetch('/api/collect/start', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({author: author.trim()})
        })
        const data = await res.json()
        setActiveTask(data)
        taskStartRef.current = Date.now()
        setLoading(false)
    }

    async function handleUpload() {
        if (!uploadFile) return
        setUploading(true)
        setUploadMsg(null)
        try {
            const formData = new FormData()
            formData.append('file', uploadFile)
            formData.append('author', uploadAuthor.trim())
            formData.append('work_title', uploadWork.trim())
            const res = await fetch('/api/collect/upload', {
                method: 'POST',
                body: formData,
            })
            const data = await res.json()
            if (!res.ok) throw new Error(data.detail || '上传失败')
            setUploadTaskId(data.task_id)
            // 立即设置 activeTask，让 SSE 监听器可以匹配 task_id 更新进度
            setActiveTask(data)
            taskStartRef.current = Date.now()
            setUploadMsg({ type: 'success', text: `已识别 ${data.chapters_detected} 章，保存 ${data.chapters_saved} 章，正在后台分析...` })
            setUploadFile(null)
        } catch (e) {
            setUploadMsg({ type: 'error', text: e.message })
        } finally {
            setUploading(false)
        }
    }
    
    async function loadAuthorData(name) {
        setSelectedAuthor(name)
        const [s, c, r] = await Promise.all([
            fetch(`/api/collect/summaries?author=${encodeURIComponent(name)}`).then(r=>r.json()),
            fetch(`/api/collect/chapters?author=${encodeURIComponent(name)}`).then(r=>r.json()),
            fetch(`/api/collect/reports?author=${encodeURIComponent(name)}`).then(r=>r.json()),
        ])
        setSummaries(s.summaries||[])
        setChapters(c.chapters||[])
        setReports(r.reports||[])
    }

    const setActLoading = (id, v) => setActionLoading(prev => v ? { ...prev, [id]: true } : { ...prev, [id]: undefined })

    async function handleEditChapter(ch) {
        setEditingChapterId(ch.id)
        setEditChapterTitle(ch.chapter_title || '')
        setActionMsg(null)
    }

    async function handleSaveChapter(ch) {
        if (!editChapterTitle.trim()) return
        setActLoading(`edit-${ch.id}`, true)
        setActionMsg(null)
        try {
            await updateCollectedChapter(ch.id, { chapter_title: editChapterTitle.trim() })
            setEditingChapterId(null)
            setActionMsg({ type: 'success', text: '章节标题已更新' })
            loadAuthorData(selectedAuthor)
        } catch (e) {
            setActionMsg({ type: 'error', text: e.message })
        } finally {
            setActLoading(`edit-${ch.id}`, false)
        }
    }

    async function handleRetryChapter(ch) {
        setActLoading(`retry-ch-${ch.id}`, true)
        setActionMsg(null)
        try {
            await retryAnalyzeChapter(ch.id)
            setActionMsg({ type: 'success', text: `第${ch.chapter_num}章重分析已启动` })
            loadAuthorData(selectedAuthor)
        } catch (e) {
            setActionMsg({ type: 'error', text: e.message })
        } finally {
            setActLoading(`retry-ch-${ch.id}`, false)
        }
    }

    async function handleDeleteChapter(ch) {
        if (!confirm(`确认删除「${ch.work_title}」第${ch.chapter_num}章？关联的文风摘要也会被清理。`)) return
        setActLoading(`del-ch-${ch.id}`, true)
        setActionMsg(null)
        try {
            await deleteCollectedChapter(ch.id)
            setActionMsg({ type: 'success', text: `已删除第${ch.chapter_num}章` })
            loadAuthorData(selectedAuthor)
        } catch (e) {
            setActionMsg({ type: 'error', text: e.message })
        } finally {
            setActLoading(`del-ch-${ch.id}`, false)
        }
    }

    async function handleDeleteSummary(s) {
        if (!confirm(`确认删除「${s.category}」维度的文风摘要？`)) return
        setActLoading(`del-sum-${s.id}`, true)
        setActionMsg(null)
        try {
            await deleteStyleSummary(s.id)
            setActionMsg({ type: 'success', text: '摘要已删除' })
            loadAuthorData(selectedAuthor)
        } catch (e) {
            setActionMsg({ type: 'error', text: e.message })
        } finally {
            setActLoading(`del-sum-${s.id}`, false)
        }
    }

    async function handleRetrySummary(s) {
        setActLoading(`retry-sum-${s.id}`, true)
        setActionMsg(null)
        try {
            await retryStyleSummary(s.id)
            setActionMsg({ type: 'success', text: `「${s.category}」摘要重新生成中...` })
            loadAuthorData(selectedAuthor)
        } catch (e) {
            setActionMsg({ type: 'error', text: e.message })
        } finally {
            setActLoading(`retry-sum-${s.id}`, false)
        }
    }

    async function handleDeleteReport(r) {
        if (!confirm(`确认删除该采集报告？关联的章节数据不会被删除。`)) return
        setActLoading(`del-report-${r.id}`, true)
        setActionMsg(null)
        try {
            await deleteCollectionReport(r.id)
            setActionMsg({ type: 'success', text: '采集报告已删除' })
            loadAuthorData(selectedAuthor)
        } catch (e) {
            setActionMsg({ type: 'error', text: e.message })
        } finally {
            setActLoading(`del-report-${r.id}`, false)
        }
    }

    async function handleClearFailedReports() {
        if (!confirm(`确认删除所有失败的采集报告？此操作不可撤销。`)) return
        setLoading(true)
        setActionMsg(null)
        try {
            const res = await deleteFailedCollectionReports()
            setActionMsg({ type: 'success', text: res.message || `已删除 ${res.deleted} 条失败报告` })
            loadAuthorData(selectedAuthor)
        } catch (e) {
            setActionMsg({ type: 'error', text: e.message })
        } finally {
            setLoading(false)
        }
    }

    async function handleDeleteAuthor(authorName) {
        if (!confirm(`确认删除作家「${authorName}」及其所有章节、总结、报告？此操作不可撤销。`)) return
        setActLoading(`del-author-${authorName}`, true)
        setActionMsg(null)
        try {
            const res = await fetch(`/api/collect/authors/${encodeURIComponent(authorName)}`, { method: 'DELETE' })
            if (!res.ok) {
                const err = await res.json().catch(() => ({}))
                throw new Error(err.detail || `删除失败 (${res.status})`)
            }
            const data = await res.json()
            setActionMsg({ type: 'success', text: `已删除「${authorName}」: ${data.chapters_deleted}章, ${data.summaries_deleted}总结` })
            setAuthors(prev => prev.filter(a => a.author !== authorName))
            if (selectedAuthor === authorName) {
                setSelectedAuthor(null)
                setSummaries([])
                setChapters([])
                setReports([])
            }
        } catch (e) {
            setActionMsg({ type: 'error', text: e.message })
        } finally {
            setActLoading(`del-author-${authorName}`, false)
        }
    }

    async function handleViewStyles(authorName) {
        try {
            const res = await fetch(`/api/collect/authors/${encodeURIComponent(authorName)}/styles`)
            const data = await res.json()
            setAuthorStyles(data)
        } catch (e) {
            setActionMsg({ type: 'error', text: `加载文风失败: ${e.message}` })
        }
    }

    async function handleAiSummary() {
        if (!selectedAuthor || aiRunning) return
        setAiRunning(true)
        setAiProgress({ step: 'analyzing', message: '正在启动 AI 总结...' })
        try {
            const res = await fetch(`/api/collect/authors/${encodeURIComponent(selectedAuthor)}/reanalyze`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
            })
            if (!res.ok) {
                const err = await res.json().catch(() => ({}))
                throw new Error(err.detail || `请求失败 (${res.status})`)
            }
            const data = await res.json()
            // Set active task for tracking; SSE will update progress
            setActiveTask(data)
            taskStartRef.current = Date.now()
        } catch (e) {
            setAiProgress({ step: 'failed', message: e.message })
            setAiRunning(false)
        }
    }
    
    const steps = activeTask ? JSON.parse(activeTask.steps_json || '[]') : []
    const progress = activeTask ? JSON.parse(activeTask.progress || '{}') : {}
    const [elapsed, setElapsed] = useState('')
    const [eta, setEta] = useState('')

    useEffect(() => {
        if (!activeTask || activeTask.status === 'done' || activeTask.status === 'failed' || activeTask.status === 'cancelled') {
            setElapsed('')
            setEta('')
            return
        }
        const iv = setInterval(() => {
            if (!taskStartRef.current) return
            const ms = Date.now() - taskStartRef.current
            const minutes = Math.floor(ms / 60000)
            const seconds = Math.floor((ms % 60000) / 1000)
            setElapsed(`${minutes}:${String(seconds).padStart(2, '0')}`)

            const p = activeTask ? JSON.parse(activeTask.progress || '{}') : {}
            const m = p.message?.match(/\((\d+)\/(\d+)\)/)
            if (m && taskStartRef.current) {
                const [cur, total] = [parseInt(m[1]), parseInt(m[2])]
                if (cur > 0 && total > 0) {
                    const rate = ms / cur
                    const remainingMs = rate * (total - cur)
                    const rm = Math.floor(remainingMs / 60000)
                    const rs = Math.floor((remainingMs % 60000) / 1000)
                    setEta(`${rm}:${String(rs).padStart(2, '0')}`)
                }
            }
        }, 1000)
        return () => clearInterval(iv)
    }, [activeTask?.task_id, activeTask?.status])

    function groupSummariesByWorkBatch(summaries) {
        const byWork = {}
        for (const s of summaries) {
            const work = s.work_title || '未分类'
            if (!byWork[work]) byWork[work] = []
            byWork[work].push(s)
        }
        const result = []
        for (const [workTitle, items] of Object.entries(byWork)) {
            const byRange = {}
            for (const s of items) {
                const range = s.chapter_range || '全部'
                if (!byRange[range]) byRange[range] = []
                byRange[range].push(s)
            }
            const batches = Object.entries(byRange).map(([range, summaries]) => ({
                chapter_range: range,
                date: summaries[0]?.created_at?.slice(0, 10) || '',
                count: summaries.length,
                summaries,
            }))
            result.push({ work_title: workTitle, batches })
        }
        return result
    }
    
    return (
        <div className="card">
            <div className="card-header">
                <span className="card-title">名家技法采集</span>
                <Badge tone="purple">{authors.length} 位作家</Badge>
            </div>
            
            <div style={{display:'flex',gap:8,padding:'12px 16px',borderBottom:'1px solid var(--border)'}}>
                <input type="text" value={author} onChange={e=>setAuthor(e.target.value)}
                    placeholder="输入作家名字, 如: 金庸" 
                    style={{flex:1,padding:'8px 12px',border:'1px solid var(--border)',borderRadius:6,fontSize:13}} />
                <button className="page-btn primary" onClick={startCollection} disabled={loading}>
                    {loading ? '启动中...' : '开始采集'}
                </button>
            </div>
            
            {/* 文件上传 */}
            <div style={{padding:'12px 16px',borderBottom:'1px solid var(--border)',background:'var(--bg-card)'}}>
                <div style={{fontWeight:700,marginBottom:8,fontSize:13}}>📁 上传整本小说（.txt / .md）</div>
                <div style={{display:'flex',gap:8,marginBottom:8,flexWrap:'wrap'}}>
                    <input type="text" value={uploadAuthor} onChange={e=>setUploadAuthor(e.target.value)}
                        placeholder="作者名（可选）" 
                        style={{flex:1,minWidth:120,padding:'6px 10px',border:'2px solid var(--border-main)',borderRadius:0,fontSize:12,background:'#fffef8'}} />
                    <input type="text" value={uploadWork} onChange={e=>setUploadWork(e.target.value)}
                        placeholder="作品名（可选）" 
                        style={{flex:1,minWidth:120,padding:'6px 10px',border:'2px solid var(--border-main)',borderRadius:0,fontSize:12,background:'#fffef8'}} />
                </div>
                <div style={{display:'flex',gap:8,alignItems:'center'}}>
                    <input type="file" accept=".txt,.md" onChange={e=>{setUploadFile(e.target.files?.[0]||null);setUploadMsg(null)}}
                        style={{flex:1,fontSize:12}} />
                    <button className="page-btn" onClick={handleUpload} disabled={uploading || !uploadFile}>
                        {uploading ? '上传中...' : '上传'}
                    </button>
                </div>
                {uploadMsg && (
                    <p style={{marginTop:8,fontSize:12,fontWeight:600,
                        color: uploadMsg.type==='error'?'var(--accent-red)':'var(--accent-green)'}}>
                        {uploadMsg.text}
                    </p>
                )}
            </div>
            
            
            {activeTask && activeTask.status !== 'done' && activeTask.status !== 'failed' && (
                <div style={{padding:'12px 16px',borderBottom:'1px solid var(--border)',background:'var(--bg-secondary)'}}>
                    <div style={{fontWeight:600,marginBottom:8,display:'flex',justifyContent:'space-between',alignItems:'center'}}>
                        <span>🔍 正在采集: {activeTask.author}</span>
                        {elapsed && (
                            <span style={{fontSize:11,color:'var(--text-mute)',margin: '0 12px'}}>
                                ⏱ {elapsed}
                                {eta && ` · 剩余 ${eta}`}
                            </span>
                        )}
                        <button className="page-btn" style={{fontSize:11,padding:'2px 8px',color:'var(--accent-red)'}}
                            onClick={async () => {
                                await fetch(`/api/collect/tasks/${activeTask.task_id}/cancel`, {method:'POST'})
                                setActiveTask(null)
                                fetch('/api/collect/authors').then(r=>r.json()).then(d=>setAuthors(d.authors||[]))
                            }}>✕ 取消</button>
                    </div>
                    <div style={{display:'flex',flexDirection:'column',gap:4}}>
                        {(() => {
                            const stepKeys = steps.some(st => st.step === 'searching' || st.step === 'downloading')
                                ? ['searching','downloading','analyzing','summarizing','done']
                                : ['uploading','splitting','saving','analyzing','summarizing','done']
                            const STATUS_TO_KEY = { processing: 'uploading' }
                            const curKey = STATUS_TO_KEY[activeTask.status] || activeTask.status
                            const curIdx = stepKeys.indexOf(curKey)
                            const labels = {searching:'搜索作品',downloading:'下载章节',uploading:'上传文件',splitting:'解析章节',saving:'保存数据',analyzing:'分析文风',summarizing:'生成总结',done:'完成'}

                            return stepKeys.map((s, i) => {
                                const isDone = curIdx > i
                                const isActive = curIdx === i && activeTask.status !== 'done' && activeTask.status !== 'failed'
                                const isFailed = activeTask.status === 'failed' && curIdx === -1 && progress.current && progress.current === i + 1
                                return (
                                    <div key={s} style={{display:'flex',alignItems:'center',gap:8,fontSize:12,
                                        color: isDone ? 'var(--accent-green)' : isFailed ? 'var(--accent-red)' : isActive ? 'var(--accent-blue)' : 'var(--text-sub)'}}>
                                        <span>{isDone ? '✅' : isFailed ? '❌' : isActive ? '⏳' : '⬜'}</span>
                                        <span>{labels[s]}</span>
                                        {(isActive || isFailed) && progress.message && <span style={{color: isFailed ? 'var(--accent-red)' : 'var(--text-sub)'}}>— {progress.message}</span>}
                                    </div>
                                )
                            })
                        })()}
                    </div>
                    {steps.length > 0 && (
                        <div style={{fontSize:11,color:'var(--text-sub)',marginTop:8}}>
                            {steps.map((st,i) => (
                                <div key={i}>[{st.step}] {st.message}</div>
                            ))}
                        </div>
                    )}
                </div>
            )}
            
            <div style={{padding:'8px 16px',borderBottom:'1px solid var(--border)'}}>
                {authors.map(a => (
                    <div key={a.author} style={{
                        marginBottom: 10, padding: '12px 14px',
                        border: '1px solid var(--border)',
                        borderRadius: 8,
                        background: 'var(--bg-card)',
                        boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
                    }}>
                        {/* Header row: author name + badge + delete */}
                        <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:6,flexWrap:'wrap'}}>
                            <strong style={{fontSize:14}}>{a.author}</strong>
                            {a.total_chapters > 0 && <Badge tone="blue">{a.total_chapters}章</Badge>}
                            {a.summaries > 0 && <Badge tone="purple">{a.summaries}总结</Badge>}
                            <span style={{flex:1}} />
                            <button className="page-btn" style={{fontSize:11,padding:'2px 8px',color:'var(--accent-red)'}}
                                onClick={() => handleDeleteAuthor(a.author)}
                                disabled={actionLoading[`del-author-${a.author}`]}>
                                {actionLoading[`del-author-${a.author}`] ? '...' : '🗑️ 删除'}
                            </button>
                        </div>

                        {/* Works list */}
                        {a.works?.length > 0 && (
                            <div style={{fontSize:12,color:'var(--text-sub)',marginBottom:4}}>
                                {a.works.map(w => (
                                    <span key={w.title} style={{marginRight:8}}>
                                        《{w.title}》({w.chapters}章)
                                    </span>
                                ))}
                            </div>
                        )}

                        {/* Last updated */}
                        {a.works?.[0]?.last_updated && (
                            <div style={{fontSize:11,color:'var(--text-mute)',marginBottom:6}}>
                                最近更新: {a.works[0].last_updated?.slice(0,10) || '-'}
                            </div>
                        )}

                        {/* Action buttons */}
                        <div style={{display:'flex',gap:6,flexWrap:'wrap',marginTop:2}}>
                            {a.total_chapters > 0 && (
                                <>
                                    <button className="page-btn" style={{fontSize:11,padding:'2px 8px'}}
                                        onClick={() => {
                                            setSelectedAuthor(a.author)
                                            handleViewStyles(a.author)
                                        }}>
                                        📖 查看风格
                                    </button>
                                    <button className="page-btn" style={{fontSize:11,padding:'2px 8px',background:'var(--accent-green)',color:'white'}}
                                        onClick={async ()=>{
                                            const res = await reanalyzeAuthorChapters(a.author, {})
                                            setActiveTask(res)
                                        }}
                                        disabled={aiRunning}>
                                        🔄 重新分析
                                    </button>
                                    <button className="page-btn" style={{fontSize:11,padding:'2px 8px',background:'var(--accent-blue)',color:'white'}}
                                        onClick={() => {
                                            setSelectedAuthor(a.author)
                                            handleAiSummary()
                                        }}
                                        disabled={aiRunning}>
                                        🤖 AI 总结
                                    </button>
                                    {/* Per-work reanalyze buttons */}
                                    {a.works?.map(w => (
                                        <button key={w.title} className="page-btn"
                                            style={{fontSize:10,padding:'2px 6px'}}
                                            onClick={async () => {
                                                const res = await reanalyzeAuthorChapters(a.author, { work_title: w.title })
                                                setActiveTask(res)
                                            }}>
                                            《{w.title}》↻
                                        </button>
                                    ))}
                                </>
                            )}
                        </div>

                        {/* AI progress inline */}
                        {selectedAuthor === a.author && aiProgress && (
                            <div style={{padding:'8px 16px',background:'var(--bg-secondary)',borderRadius:8,marginTop:8,marginBottom:4}}>
                                {['analyzing','loading-context','ai-summarizing','publishing','done'].map((step, i) => {
                                    const s = [
                                        {key:'analyzing',label:'分析文风'},
                                        {key:'loading-context',label:'加载参考'},
                                        {key:'ai-summarizing',label:'AI 总结'},
                                        {key:'publishing',label:'发布入库'},
                                        {key:'done',label:'完成'},
                                    ].find(s => s.key === step)
                                    const isDone = step === 'done' || (['analyzing','loading-context','ai-summarizing','publishing'].indexOf(step) < ['analyzing','loading-context','ai-summarizing','publishing'].indexOf(aiProgress.step))
                                    const isActive = step === aiProgress.step
                                    return (
                                        <div key={step} style={{display:'flex',alignItems:'center',gap:8,padding:'4px 0',fontSize:12,
                                            color: isDone ? 'var(--accent-green)' : isActive ? 'var(--accent-blue)' : 'var(--text-sub)'}}>
                                            <span>{isDone ? '✅' : isActive ? '⏳' : '⬜'}</span>
                                            <span>{s.label}</span>
                                            {isActive && aiProgress.message && <span style={{color:'var(--text-sub)',fontSize:11}}>— {aiProgress.message}</span>}
                                        </div>
                                    )
                                })}
                            </div>
                        )}
                    </div>
                ))}
                {authors.length === 0 && (
                    <div style={{padding:'20px 0',textAlign:'center',color:'var(--text-sub)',fontSize:13}}>
                        暂无采集数据，请输入作家名开始采集或上传小说文件。
                    </div>
                )}
            </div>
            
            {/* ── Author style details (new card-based view) ── */}
            {authorStyles && (
                <div style={{padding:'0 16px 16px',maxHeight:500,overflow:'auto'}}>
                    {actionMsg && (
                        <p style={{marginTop:8,marginBottom:0,fontSize:12,fontWeight:600,
                            color: actionMsg.type==='error'?'var(--accent-red)':'var(--accent-green)'}}>
                            {actionMsg.text}
                        </p>
                    )}

                    <h4 style={{marginTop:12,marginBottom:8}}>
                        📖 {authorStyles.author} 文风风格
                        <span style={{fontWeight:400,fontSize:12,color:'var(--text-sub)',marginLeft:8}}>
                            ({authorStyles.total_chapters}章 · {authorStyles.total_summaries}条总结)
                        </span>
                    </h4>

                    {/* Last updated */}
                    {authorStyles.last_updated && (
                        <div style={{fontSize:11,color:'var(--text-mute)',marginBottom:8}}>
                            最近更新: {authorStyles.last_updated?.slice(0,10)}
                        </div>
                    )}

                    {/* Style rules from director_style */}
                    {authorStyles.style_rules?.length > 0 && (
                        <div style={{marginBottom:12}}>
                            <div style={{fontWeight:600,fontSize:13,marginBottom:6}}>🎨 文风规则</div>
                            {authorStyles.style_rules.map((rule,i) => (
                                <div key={rule.id || i} style={{
                                    padding:'8px 12px',marginBottom:6,
                                    border:'1px solid var(--border)',borderRadius:6,
                                    background:'var(--bg-secondary)',fontSize:12
                                }}>
                                    <div style={{fontWeight:600,marginBottom:4}}>{rule.category}</div>
                                    {rule.description && (
                                        <div style={{color:'var(--text-sub)',lineHeight:1.5,fontSize:11}}>{rule.description}</div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Summaries from style_summaries — grouped by work → batch */}
                    {authorStyles.summaries?.length > 0 && (() => {
                        const grouped = groupSummariesByWorkBatch(authorStyles.summaries)
                        return (
                            <div>
                                <div style={{fontWeight:600,fontSize:13,marginBottom:8}}>
                                    📊 文风总结 ({authorStyles.total_summaries}条)
                                    <span style={{fontWeight:400,fontSize:11,color:'var(--text-sub)',marginLeft:8}}>
                                        🤖 AI 总结
                                    </span>
                                    <button className="page-btn" style={{fontSize:11,padding:'2px 8px',marginLeft:8,
                                        background:'var(--accent-green)',color:'white'}}
                                        onClick={handleAiSummary} disabled={aiRunning}>
                                        {aiRunning ? '⏳' : '🤖 AI 总结'}
                                    </button>
                                </div>
                                {grouped.map(work => (
                                    <div key={work.work_title} style={{marginBottom:12}}>
                                        <h5 style={{fontSize:13,margin:'0 0 6px 0',color:'var(--text-main)'}}>
                                            📖 {work.work_title}
                                        </h5>
                                        {work.batches.map(batch => (
                                            <details key={batch.chapter_range} style={{marginBottom:6}}>
                                                <summary style={{
                                                    cursor:'pointer',fontSize:12,fontWeight:600,
                                                    color:'var(--accent-blue)',padding:'4px 0'
                                                }}>
                                                    第{batch.chapter_range}章 ({batch.date}) — {batch.count}条总结
                                                </summary>
                                                <div style={{marginLeft:12,marginTop:4}}>
                                                    {batch.summaries.map((s,i) => (
                                                        <div key={s.id || i} style={{
                                                            padding:'6px 10px',marginBottom:4,
                                                            border:'1px solid var(--border)',borderRadius:6,
                                                            background:'var(--bg-secondary)',fontSize:12
                                                        }}>
                                                            <div style={{display:'flex',gap:6,alignItems:'center',marginBottom:2}}>
                                                                <Badge tone="purple" style={{fontSize:10}}>{s.category}</Badge>
                                                                <span style={{fontWeight:600,fontSize:12}}>{s.summary_title}</span>
                                                            </div>
                                                            {s.content && (
                                                                <div style={{color:'var(--text-sub)',lineHeight:1.5,fontSize:11,
                                                                    maxHeight:80,overflow:'hidden',textOverflow:'ellipsis'}}>
                                                                    {s.content.length > 200 ? s.content.slice(0,200) + '...' : s.content}
                                                                </div>
                                                            )}
                                                            <div style={{display:'flex',gap:4,marginTop:4}}>
                                                                <button className="page-btn" style={{fontSize:10,padding:'1px 6px'}}
                                                                    onClick={() => handleRetrySummary(s)}
                                                                    disabled={actionLoading[`retry-sum-${s.id}`]}>
                                                                    {actionLoading[`retry-sum-${s.id}`] ? '⏳' : '重试'}
                                                                </button>
                                                                <button className="page-btn" style={{fontSize:10,padding:'1px 6px',color:'var(--accent-red)'}}
                                                                    onClick={() => handleDeleteSummary(s)}
                                                                    disabled={actionLoading[`del-sum-${s.id}`]}>
                                                                    {actionLoading[`del-sum-${s.id}`] ? '...' : '删除'}
                                                                </button>
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                            </details>
                                        ))}
                                    </div>
                                ))}
                            </div>
                        )
                    })()}

                    {/* Close button */}
                    <button className="page-btn" onClick={() => setAuthorStyles(null)}
                        style={{marginTop:8,fontSize:12}}>
                        收起详情
                    </button>
                </div>
            )}

            {/* ── Fallback: old summaries/chapters/reports (shown when selectedAuthor set via loadAuthorData) ── */}
            {!authorStyles && selectedAuthor && summaries.length > 0 && (
                <div style={{padding:'0 16px 16px',maxHeight:500,overflow:'auto'}}>
                    {actionMsg && (
                        <p style={{marginTop:8,marginBottom:0,fontSize:12,fontWeight:600,
                            color: actionMsg.type==='error'?'var(--accent-red)':'var(--accent-green)'}}>
                            {actionMsg.text}
                        </p>
                    )}
                    <h4 style={{marginTop:12}}>文风总结 ({summaries.length})</h4>
                    {summaries.map((s,i) => (
                        <div key={i} style={{padding:'10px 14px',marginBottom:8,border:'1px solid var(--border)',borderRadius:8,background:'var(--bg-secondary)'}}>
                            <div style={{display:'flex',gap:6,marginBottom:6,alignItems:'center'}}>
                                <Badge tone="purple" style={{fontSize:10}}>{s.category}</Badge>
                                <strong style={{fontSize:13,flex:1}}>{s.summary_title}</strong>
                                <button className="page-btn" style={{fontSize:10,padding:'2px 6px',minHeight:22}}
                                    onClick={() => handleDeleteSummary(s)}
                                    disabled={actionLoading[`del-sum-${s.id}`]}>
                                    {actionLoading[`del-sum-${s.id}`] ? '...' : '删除'}
                                </button>
                                <button className="page-btn" style={{fontSize:10,padding:'2px 6px',minHeight:22}}
                                    onClick={() => handleRetrySummary(s)}
                                    disabled={actionLoading[`retry-sum-${s.id}`]}>
                                    {actionLoading[`retry-sum-${s.id}`] ? '⏳' : '重试'}
                                </button>
                            </div>
                            <div style={{fontSize:12,color:'var(--text-sub)',lineHeight:1.6}}>{s.content}</div>
                            {s.keywords && (
                                <div style={{display:'flex',gap:4,flexWrap:'wrap',marginTop:6}}>
                                    {(typeof s.keywords==='string'?JSON.parse(s.keywords):s.keywords).map((k,j)=>(
                                        <Badge key={j} tone="amber" style={{fontSize:10}}>{k}</Badge>
                                    ))}
                                </div>
                            )}
                        </div>
                    ))}
                    
                    <h4 style={{marginTop:16}}>已采集章节 ({chapters.length})</h4>
                    {(chaptersShowAll ? chapters : chapters.slice(0, 10)).map((c, i) => (
                        <div key={c.id || i} style={{fontSize:12,padding:'4px 0',borderBottom:'1px solid var(--border)',display:'flex',alignItems:'center',gap:8,flexWrap:'wrap'}}>
                            {editingChapterId === c.id ? (
                                <>
                                    <span style={{flex:1,minWidth:200}}>
                                        <input
                                            type="text"
                                            value={editChapterTitle}
                                            onChange={e => setEditChapterTitle(e.target.value)}
                                            onKeyDown={e => { if (e.key === 'Enter') handleSaveChapter(c); if (e.key === 'Escape') setEditingChapterId(null) }}
                                            autoFocus
                                            style={{width:'100%',padding:'2px 6px',border:'2px solid var(--accent)',borderRadius:0,fontSize:12,background:'#fffef8',color:'var(--text-main)'}}
                                        />
                                    </span>
                                    <button className="page-btn" style={{fontSize:10,padding:'2px 6px',minHeight:22}}
                                        onClick={() => handleSaveChapter(c)}
                                        disabled={actionLoading[`edit-${c.id}`]}>
                                        {actionLoading[`edit-${c.id}`] ? '...' : '保存'}
                                    </button>
                                    <button className="page-btn" style={{fontSize:10,padding:'2px 6px',minHeight:22,background:'#fff8e6'}}
                                        onClick={() => setEditingChapterId(null)}>取消</button>
                                </>
                            ) : (
                                <>
                                    <span style={{flex:1,minWidth:200}}>
                                        {c.work_title} 第{c.chapter_num}章 — {c.word_count}字
                                        {c.chapter_title && <span style={{color:'var(--text-sub)'}}> ({c.chapter_title})</span>}
                                    </span>
                                    <button className="page-btn" style={{fontSize:10,padding:'2px 6px',minHeight:22}}
                                        onClick={() => handleEditChapter(c)}
                                        disabled={!!actionLoading[`del-ch-${c.id}`] || !!actionLoading[`retry-ch-${c.id}`]}>
                                        编辑
                                    </button>
                                    <button className="page-btn" style={{fontSize:10,padding:'2px 6px',minHeight:22}}
                                        onClick={() => handleRetryChapter(c)}
                                        disabled={actionLoading[`retry-ch-${c.id}`]}>
                                        {actionLoading[`retry-ch-${c.id}`] ? '⏳' : '重试'}
                                    </button>
                                    <button className="page-btn" style={{fontSize:10,padding:'2px 6px',minHeight:22,color:'var(--accent-red)'}}
                                        onClick={() => handleDeleteChapter(c)}
                                        disabled={actionLoading[`del-ch-${c.id}`]}>
                                        {actionLoading[`del-ch-${c.id}`] ? '...' : '删除'}
                                    </button>
                                </>
                            )}
                        </div>
                    ))}
                    {chapters.length > 10 && !chaptersShowAll && (
                        <button className="page-btn" style={{fontSize:11,marginTop:4,padding:'2px 10px'}}
                            onClick={() => setChaptersShowAll(true)}>
                            显示全部 {chapters.length} 章
                        </button>
                    )}
                    
                    <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginTop:16}}>
                        <h4 style={{margin:0}}>采集报告 ({reports.length})</h4>
                        {reports.some(r => r.status === 'failed') && (
                            <button className="page-btn" style={{fontSize:11,padding:'2px 8px',color:'var(--accent-red)'}}
                                onClick={handleClearFailedReports} disabled={loading}>
                                🗑️ 清空失败记录
                            </button>
                        )}
                    </div>
                    {reports.map((r,i)=>(
                        <div key={i} style={{fontSize:12,padding:'6px 0',borderBottom:'1px solid var(--border)',display:'flex',justifyContent:'space-between',alignItems:'center'}}>
                            <div>
                                <Badge tone={r.status==='done'?'green':'red'} style={{fontSize:10}}>{r.status}</Badge>
                                <span style={{marginLeft:8}}>{r.chapters_collected}章 · {r.summaries_generated}条总结</span>
                                {r.error_message && <span style={{color:'var(--accent-red)',marginLeft:8}}>{r.error_message}</span>}
                            </div>
                            <button className="page-btn" style={{fontSize:10,padding:'2px 6px',minHeight:22,color:'var(--accent-red)'}}
                                onClick={() => handleDeleteReport(r)}
                                disabled={actionLoading[`del-report-${r.id}`]}>
                                {actionLoading[`del-report-${r.id}`] ? '...' : '🗑️ 删除'}
                            </button>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}

/* ── Tab 5: 章级合同 ── */

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
        fetch(`/api/style/chapters/${selected}`, { signal: ctrl.signal })
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
            {chapters.length === 0 ? (
                <div style={{ padding: 32, textAlign: 'center' }}>
                    <div style={{ fontSize: 24, marginBottom: 8 }}>📝</div>
                    <div style={{ color: 'var(--text-sub)' }}>章级合同需要通过 <code style={{ background: 'var(--bg-secondary)', padding: '2px 6px', borderRadius: 4 }}>/webnovel-plan</code> 规划章节后生成。</div>
                </div>
            ) : (
                <>
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
            </>
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

/* ── Tab 6: 审查维度 ── */

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
                <h2>文风编辑器</h2>
            </div>
            <p style={{ color: 'var(--text-sub)', fontSize: 13 }}>
                系统有 5 个层级可以插入文风，从全局到局部逐级细化。
            </p>

            {/* Tab 栏 */}
            <div className="tab-strip">
                {TABS.map((tab, i) => {
                    const section = TAB_SECTIONS[tab.key]
                    const showSection = section && (i === 0 || TAB_SECTIONS[TABS[i - 1]?.key] !== section)
                    return (
                        <Fragment key={tab.key}>
                            {showSection && (
                                <div style={{
                                    fontSize: 11, fontWeight: 700, color: 'var(--text-mute)',
                                    padding: '8px 4px 2px', letterSpacing: 1,
                                    borderBottom: '1px solid var(--border-sub)', margin: '0 4px 2px',
                                }}>
                                    {section}
                                </div>
                            )}
                            <button
                                onClick={() => setActiveTab(tab.key)}
                                className={`tab-btn ${activeTab === tab.key ? 'active' : ''}`}
                            >
                                {tab.label}
                            </button>
                        </Fragment>
                    )
                })}
            </div>

            {/* Tab 内容 */}
            {activeTab === 'prompts' && <PromptsTab />}
            {activeTab === 'master' && <MasterSettingTab />}
            {activeTab === 'anti' && <AntiPatternsTab />}
            {activeTab === 'char_ref' && <ReferenceTab sourceCsv="人设与关系" title="人设模板" />}
            {activeTab === 'gold_ref' && <ReferenceTab sourceCsv="金手指与设定" title="金手指库" />}
            {activeTab === 'naming_ref' && <ReferenceTab sourceCsv="命名规则" title="命名规则" />}
            {activeTab === 'genre_ref' && <ReferenceTab sourceCsv="题材与调性推理" title="题材路由" />}
            {activeTab === 'plot_ref' && <ReferenceTab sourceCsv="桥段套路" title="桥段套路" />}
            {activeTab === 'pacing_ref' && <ReferenceTab sourceCsv="爽点与节奏" title="爽点节奏" />}
            {activeTab === 'techniques' && <TechniquesTab />}
            {activeTab === 'scene_ref' && <ReferenceTab sourceCsv="场景写法" title="场景写法" />}
            {activeTab === 'masters' && <MastersTab />}
            {activeTab === 'chapter' && <ChapterContractTab />}
            {activeTab === 'reviewer' && <ReviewerTab />}
            {activeTab === 'adjudge_ref' && <ReferenceTab sourceCsv="裁决规则" title="裁决规则" />}
        </div>
    )
}
