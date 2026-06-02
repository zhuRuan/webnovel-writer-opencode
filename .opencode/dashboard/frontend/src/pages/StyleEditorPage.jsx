import { useEffect, useState, useCallback } from 'react'
import { useDashboardContext } from '../App.jsx'
import Badge from '../components/Badge.jsx'
import {
    fetchMasterSetting,
    updateMasterSetting,
    fetchAntiPatterns,
    addAntiPattern,
    deleteAntiPattern,
} from '../api.js'

const TABS = [
    { key: 'master', label: '全局文风' },
    { key: 'anti', label: '禁止模式' },
    { key: 'techniques', label: '写作技法' },
    { key: 'chapter', label: '章级合同' },
    { key: 'reviewer', label: '审查维度' },
]

/* ── Tab 1: 全局文风 ── */

function MasterSettingTab() {
    const [data, setData] = useState(null)
    const [editing, setEditing] = useState({})
    const [saving, setSaving] = useState(false)
    const [msg, setMsg] = useState(null)

    useEffect(() => {
        fetchMasterSetting().then(setData).catch(() => setData(null))
    }, [])

    const constraints = data?.master_constraints || {}
    const locked = (data?.override_policy?.locked || []).map(s => s.replace('master_constraints.', ''))

    const handleChange = (key, value) => {
        setEditing(prev => ({ ...prev, [key]: value }))
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

    const allKeys = Object.keys(constraints)
    const hasChanges = Object.keys(editing).length > 0

    return (
        <div>
            <p style={{ marginBottom: 16, color: 'var(--text-secondary)' }}>
                编辑 <code>master_constraints</code> 字段，对所有章节生效。
                locked 字段不可修改。
            </p>
            {allKeys.length === 0 && !data && <p>加载中...</p>}
            {allKeys.length === 0 && data && <p>暂无 master_constraints 配置</p>}
            {allKeys.map(key => (
                <div key={key} style={{ marginBottom: 12 }}>
                    <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
                        {key}
                        {locked.includes(key) && <Badge tone="red" style={{ marginLeft: 8 }}>锁定</Badge>}
                    </label>
                    <input
                        type="text"
                        value={editing[key] !== undefined ? editing[key] : String(constraints[key] || '')}
                        onChange={e => handleChange(key, e.target.value)}
                        disabled={locked.includes(key)}
                        style={{
                            width: '100%', maxWidth: 480, padding: '6px 10px',
                            border: '1px solid var(--border)', borderRadius: 4,
                            background: locked.includes(key) ? 'var(--bg-disabled)' : 'var(--bg-input)',
                            color: 'var(--text-primary)',
                        }}
                    />
                </div>
            ))}
            {hasChanges && (
                <button
                    onClick={handleSave}
                    disabled={saving}
                    style={{
                        marginTop: 12, padding: '8px 20px', borderRadius: 4,
                        border: 'none', background: 'var(--accent)', color: '#fff',
                        cursor: saving ? 'wait' : 'pointer', fontWeight: 500,
                    }}
                >
                    {saving ? '保存中...' : '保存'}
                </button>
            )}
            {msg && (
                <p style={{ marginTop: 8, color: msg.type === 'error' ? 'var(--danger)' : 'var(--success)' }}>
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

    const handleDelete = async (index) => {
        if (!confirm('确认删除该反模式？')) return
        setMsg(null)
        try {
            await deleteAntiPattern(index)
            setMsg({ type: 'success', text: '已删除' })
            reload()
        } catch (e) {
            setMsg({ type: 'error', text: e.message })
        }
    }

    return (
        <div>
            <p style={{ marginBottom: 16, color: 'var(--text-secondary)' }}>
                定义绝对不能出现的写法。审查阶段 reviewer agent 会自动检查。
            </p>
            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                <input
                    type="text"
                    value={newText}
                    onChange={e => setNewText(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleAdd()}
                    placeholder="输入新的反模式..."
                    style={{
                        flex: 1, padding: '6px 10px',
                        border: '1px solid var(--border)', borderRadius: 4,
                        background: 'var(--bg-input)', color: 'var(--text-primary)',
                    }}
                />
                <button
                    onClick={handleAdd}
                    disabled={loading || !newText.trim()}
                    style={{
                        padding: '6px 16px', borderRadius: 4,
                        border: 'none', background: 'var(--accent)', color: '#fff',
                        cursor: loading ? 'wait' : 'pointer',
                    }}
                >
                    添加
                </button>
            </div>
            {msg && (
                <p style={{ marginBottom: 8, color: msg.type === 'error' ? 'var(--danger)' : 'var(--success)' }}>
                    {msg.text}
                </p>
            )}
            {patterns.length === 0 ? (
                <p style={{ color: 'var(--text-secondary)' }}>暂无反模式</p>
            ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr style={{ borderBottom: '1px solid var(--border)' }}>
                            <th style={{ textAlign: 'left', padding: '8px 4px' }}>#</th>
                            <th style={{ textAlign: 'left', padding: '8px 4px' }}>反模式内容</th>
                            <th style={{ textAlign: 'left', padding: '8px 4px' }}>来源</th>
                            <th style={{ textAlign: 'right', padding: '8px 4px' }}>操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        {patterns.map((p, i) => (
                            <tr key={i} style={{ borderBottom: '1px solid var(--border-light)' }}>
                                <td style={{ padding: '8px 4px', color: 'var(--text-secondary)' }}>{i + 1}</td>
                                <td style={{ padding: '8px 4px' }}>{p.text}</td>
                                <td style={{ padding: '8px 4px' }}>
                                    <Badge tone={p.source_table === 'dashboard_manual' ? 'cyan' : 'neutral'}>
                                        {p.source_table || '手动'}
                                    </Badge>
                                </td>
                                <td style={{ padding: '8px 4px', textAlign: 'right' }}>
                                    <button
                                        onClick={() => handleDelete(i)}
                                        style={{
                                            padding: '2px 8px', borderRadius: 3,
                                            border: '1px solid var(--danger)', background: 'transparent',
                                            color: 'var(--danger)', cursor: 'pointer', fontSize: 12,
                                        }}
                                    >
                                        删除
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
            <p style={{ marginTop: 12, color: 'var(--text-secondary)', fontSize: 13 }}>
                共 {patterns.length} 条反模式
            </p>
        </div>
    )
}

/* ── Tab 3-5: 只读展示 ── */

function ReadOnlyTab({ title, description }) {
    return (
        <div>
            <p style={{ marginBottom: 12, color: 'var(--text-secondary)' }}>{description}</p>
            <p style={{ color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                此层级暂不支持在线编辑，请通过 CLI 或直接编辑文件。
            </p>
        </div>
    )
}

/* ── 主页面 ── */

export default function StyleEditorPage() {
    const [activeTab, setActiveTab] = useState('master')

    return (
        <div>
            <h2 style={{ marginBottom: 20 }}>文风约束编辑器</h2>
            <p style={{ marginBottom: 20, color: 'var(--text-secondary)' }}>
                系统有 5 个层级可以插入文风约束，从全局到局部逐级细化。
                此页面支持编辑前两层，其余层级请通过 CLI 操作。
            </p>

            {/* Tab 栏 */}
            <div style={{ display: 'flex', gap: 4, marginBottom: 20, borderBottom: '1px solid var(--border)', paddingBottom: 0 }}>
                {TABS.map(tab => (
                    <button
                        key={tab.key}
                        onClick={() => setActiveTab(tab.key)}
                        style={{
                            padding: '8px 16px', border: 'none', borderRadius: '4px 4px 0 0',
                            background: activeTab === tab.key ? 'var(--accent)' : 'transparent',
                            color: activeTab === tab.key ? '#fff' : 'var(--text-primary)',
                            cursor: 'pointer', fontWeight: activeTab === tab.key ? 600 : 400,
                            borderBottom: activeTab === tab.key ? '2px solid var(--accent)' : '2px solid transparent',
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
            {activeTab === 'techniques' && (
                <ReadOnlyTab
                    title="写作技法"
                    description="题材级技法存储在 写作技法.csv 中，写作时通过 BM25 检索自动匹配。"
                />
            )}
            {activeTab === 'chapter' && (
                <ReadOnlyTab
                    title="章级合同"
                    description="单章覆盖存储在 .story-system/chapters/chapter_NNN.json 的 forbidden_zones 和 override_allowed 字段中。"
                />
            )}
            {activeTab === 'reviewer' && (
                <ReadOnlyTab
                    title="审查维度"
                    description="审查维度定义在 .opencode/agents/reviewer.md 中，包含设定一致性、AI味、节奏等 13 个检查维度。"
                />
            )}
        </div>
    )
}
