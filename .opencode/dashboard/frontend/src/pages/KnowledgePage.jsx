import { startTransition, useEffect, useMemo, useState } from 'react'
import { useDashboardContext } from '../App.jsx'
import { fetchActorKnowledge, fetchActorSkills } from '../api.js'
import Badge from '../components/Badge.jsx'
import KnowledgeBasePage from './KnowledgeBasePage.jsx'

const TIER_LABELS = { main: '主角', supporting: '配角', extra: '龙套' }
const TIER_TONES = { main: 'amber', supporting: 'blue', extra: 'neutral' }

const DOMAIN_CATEGORY_NODES = [
    { key: '战斗', label: '战斗', tone: 'red' },
    { key: '工程', label: '工程', tone: 'gold' },
    { key: '生存', label: '生存', tone: 'green' },
    { key: '科学', label: '科学', tone: 'blue' },
    { key: '社交', label: '社交', tone: 'purple' },
]

// ── 熟练度: 效率值 → 中文标签 ──
function domainProficiencyLabel(efficiency) {
    const v = Number(efficiency) || 0
    if (v >= 1.0) return { label: '至圣', tone: 'crimson' }
    if (v >= 0.95) return { label: '宗师', tone: 'red' }
    if (v >= 0.9)  return { label: '大师', tone: 'gold' }
    if (v >= 0.7)  return { label: '精通', tone: 'purple' }
    if (v >= 0.5)  return { label: '熟练', tone: 'blue' }
    if (v >= 0.3)  return { label: '基础', tone: 'green' }
    return { label: '入门', tone: 'gray' }
}

// ── 技能熟练度颜色 ──
function skillLevelTone(label) {
    const map = { '至圣': 'crimson', '宗师': 'red', '大师': 'gold', '精通': 'purple', '熟练': 'blue', '基础': 'green', '入门': 'gray' }
    return map[label] || 'gray'
}

// ══════════════════════════════════════════════════════════════
// Domain Tree (unchanged)
// ══════════════════════════════════════════════════════════════

function DomainTree({ tree, expanded, onToggle }) {
    return (
        <div className="domain-tree">
            {DOMAIN_CATEGORY_NODES.map(cat => {
                const subdomains = tree?.[cat.key]
                const isOpen = expanded.has(cat.key)
                const hasChildren = subdomains && typeof subdomains === 'object' && Object.keys(subdomains).length > 0

                return (
                    <div key={cat.key} className="domain-category">
                        <button
                            type="button"
                            className="domain-category-header"
                            onClick={() => onToggle(cat.key)}
                            aria-expanded={isOpen}
                        >
                            <span className={`domain-chevron ${isOpen ? 'open' : ''}`.trim()}>▸</span>
                            <Badge tone={cat.tone}>{cat.label}</Badge>
                            {hasChildren && (
                                <span className="domain-count">{Object.keys(subdomains).length}</span>
                            )}
                        </button>
                        {isOpen && hasChildren && (
                            <div className="domain-subdomains">
                                {Object.entries(subdomains).map(([key, value]) => {
                                    const items = Array.isArray(value) ? value : []
                                    const label = typeof value === 'object' && value.label ? value.label : key
                                    return (
                                        <div key={key} className="domain-leaf">
                                            <span className="domain-leaf-bullet">•</span>
                                            <span className="domain-leaf-label">{label}</span>
                                            {items.length > 0 && (
                                                <span className="domain-leaf-items">
                                                    ({items.length})
                                                </span>
                                            )}
                                        </div>
                                    )
                                })}
                            </div>
                        )}
                        {isOpen && !hasChildren && (
                            <div className="domain-subdomains domain-empty">暂无子域</div>
                        )}
                    </div>
                )
            })}
        </div>
    )
}

// ══════════════════════════════════════════════════════════════
// Efficiency Bar + Proficiency Label
// ══════════════════════════════════════════════════════════════

function EfficiencyBar({ efficiency }) {
    const pct = Math.round(efficiency * 100)
    const { label, tone } = domainProficiencyLabel(efficiency)

    return (
        <div className="efficiency-bar-wrap" title={`掌握度 ${pct}% — ${label}`}>
            <div className={`efficiency-bar efficiency-${tone}`} style={{ width: `${Math.max(pct, 2)}%` }} />
            <span className="efficiency-label">{pct}%</span>
            <span className={`proficiency-tag proficiency-tag-${tone}`}>{label}</span>
        </div>
    )
}

// ══════════════════════════════════════════════════════════════
// Public Knowledge: Domain Efficiency Table
// ══════════════════════════════════════════════════════════════

function DomainEfficiencyTable({ domains }) {
    if (!domains || !Object.keys(domains).length) {
        return <div className="empty-state compact"><p>暂无已知领域数据</p></div>
    }

    const rows = Object.entries(domains)
        .map(([domain, efficiency]) => ({
            domain,
            efficiency: typeof efficiency === 'object' ? (efficiency.efficiency ?? 0) : (Number(efficiency) || 0),
        }))
        .sort((a, b) => b.efficiency - a.efficiency)

    return (
        <div className="table-wrap">
            <table className="data-table">
                <thead>
                    <tr>
                        <th>领域</th>
                        <th>掌握度</th>
                        <th>熟练度</th>
                    </tr>
                </thead>
                <tbody>
                    {rows.map(row => {
                        const { label } = domainProficiencyLabel(row.efficiency)
                        return (
                            <tr key={row.domain}>
                                <td>{row.domain}</td>
                                <td><EfficiencyBar efficiency={row.efficiency} /></td>
                                <td>{label}</td>
                            </tr>
                        )
                    })}
                </tbody>
            </table>
        </div>
    )
}

// ══════════════════════════════════════════════════════════════
// Skills Table
// ══════════════════════════════════════════════════════════════

function SkillsTable({ skills, loading, error }) {
    if (loading) {
        return <div className="empty-state compact"><p>加载技能数据…</p></div>
    }
    if (error) {
        return <div className="empty-state compact"><p>技能数据加载失败: {error}</p></div>
    }
    if (!skills || !skills.length) {
        return <div className="empty-state compact"><p>该角色暂无技能数据</p></div>
    }

    return (
        <div className="table-wrap">
            <table className="data-table">
                <thead>
                    <tr>
                        <th>技能名</th>
                        <th>等级</th>
                        <th>说明</th>
                    </tr>
                </thead>
                <tbody>
                    {skills.map(skill => (
                        <tr key={skill.name}>
                            <td className="skill-name-cell">{skill.name}</td>
                            <td>
                                <span className={`proficiency-tag proficiency-tag-${skillLevelTone(skill.label)}`}>
                                    {skill.label}
                                </span>
                                {skill.level > 0 && (
                                    <span className="skill-level-num">Lv.{skill.level}</span>
                                )}
                            </td>
                            <td className="skill-note-cell">{skill.note || '—'}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    )
}

// ══════════════════════════════════════════════════════════════
// Private Knowledge Section
// ══════════════════════════════════════════════════════════════

function PrivateKnowledge({ entity }) {
    if (!entity) {
        return <div className="empty-state compact"><p>暂无私有经验数据</p></div>
    }

    const traits = entity.traits || []
    const hasTraits = Array.isArray(traits) && traits.length > 0

    return (
        <div className="private-knowledge">
            {hasTraits && (
                <div className="private-row">
                    <span className="private-label">特质</span>
                    <div className="private-tags">
                        {traits.map((t, i) => (
                            <span key={i} className="trait-tag">{typeof t === 'string' ? t : JSON.stringify(t)}</span>
                        ))}
                    </div>
                </div>
            )}
            {entity.type && (
                <div className="private-row">
                    <span className="private-label">实体类型</span>
                    <span className="private-value">{entity.type}</span>
                </div>
            )}
            {entity.first_appearance > 0 && (
                <div className="private-row">
                    <span className="private-label">首次出场</span>
                    <span className="private-value">第{entity.first_appearance}章</span>
                </div>
            )}
            {entity.last_appearance > 0 && (
                <div className="private-row">
                    <span className="private-label">最近出场</span>
                    <span className="private-value">第{entity.last_appearance}章</span>
                </div>
            )}
            {entity.desc && (
                <div className="private-row">
                    <span className="private-label">描述</span>
                    <span className="private-value private-desc">{entity.desc}</span>
                </div>
            )}
        </div>
    )
}

// ══════════════════════════════════════════════════════════════
// Actor Card — expanded view with skills / public / private
// ══════════════════════════════════════════════════════════════

function ActorCard({ actor, isExpanded, onToggle, onFilter }) {
    const tierLabel = TIER_LABELS[actor.tier] || actor.tier || '未知'
    const tierTone = TIER_TONES[actor.tier] || 'neutral'
    const domainCount = Object.keys(actor.known_domains || {}).length

    // ── skills state: fetched on expand ──
    const [skillsData, setSkillsData] = useState(null)
    const [skillsLoading, setSkillsLoading] = useState(false)
    const [skillsError, setSkillsError] = useState(null)

    useEffect(() => {
        if (!isExpanded || skillsData !== null) return
        let cancelled = false
        setSkillsLoading(true)
        setSkillsError(null)
        fetchActorSkills(actor.actor_id)
            .then(result => {
                if (!cancelled) {
                    setSkillsData(result.skills || [])
                    setSkillsLoading(false)
                }
            })
            .catch(err => {
                if (!cancelled) {
                    setSkillsError(err.message || '加载技能失败')
                    setSkillsLoading(false)
                }
            })
        return () => { cancelled = true }
    }, [isExpanded, actor.actor_id, skillsData])

    return (
        <div className={`card actor-knowledge-card ${isExpanded ? 'expanded' : ''}`.trim()}>
            <div
                className="actor-knowledge-header"
                onClick={() => onToggle(actor.actor_id)}
                role="button"
                tabIndex={0}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onToggle(actor.actor_id) } }}
            >
                <span className="actor-name-btn">
                    <span className={`actor-collapse-indicator ${isExpanded ? 'open' : ''}`.trim()}>▸</span>
                    <span className="actor-name">{actor.name}</span>
                </span>
                <div className="actor-meta">
                    <Badge tone={tierTone}>{tierLabel}</Badge>
                    <span className="actor-domain-count" title="已知领域总数">
                        {domainCount} 领域
                    </span>
                    {actor.retrieval_base != null && (
                        <span className="actor-retrieval" title="检索基准值">
                            基准: {Math.round(actor.retrieval_base * 100)}%
                        </span>
                    )}
                    <button
                        type="button"
                        className="filter-btn"
                        onClick={e => { e.stopPropagation(); onFilter(actor.actor_id) }}
                        title="仅查看此角色"
                    >
                        筛选
                    </button>
                </div>
            </div>
            {isExpanded && (
                <div className="actor-knowledge-body">
                    {/* ── 技能 ── */}
                    <div className="knowledge-section">
                        <h4 className="knowledge-section-title">📋 技能</h4>
                        <SkillsTable
                            skills={skillsData}
                            loading={skillsLoading}
                            error={skillsError}
                        />
                    </div>

                    {/* ── 公共常识 ── */}
                    <div className="knowledge-section">
                        <h4 className="knowledge-section-title">📚 公共常识</h4>
                        <DomainEfficiencyTable domains={actor.known_domains} />
                    </div>

                    {/* ── 私有经验 ── */}
                    <div className="knowledge-section">
                        <h4 className="knowledge-section-title">🔒 私有经验</h4>
                        <PrivateKnowledge entity={actor.entity} />
                    </div>
                </div>
            )}
        </div>
    )
}

// ══════════════════════════════════════════════════════════════
// Actor Filter
// ══════════════════════════════════════════════════════════════

function ActorFilter({ actors, value, onChange }) {
    const options = useMemo(() => {
        const seen = new Set()
        return actors.filter(actor => {
            if (seen.has(actor.actor_id)) return false
            seen.add(actor.actor_id)
            return true
        })
    }, [actors])

    return (
        <div className="filter-group">
            <button
                type="button"
                className={`filter-btn ${value === '' ? 'active' : ''}`.trim()}
                onClick={() => onChange('')}
            >
                全部角色
            </button>
            {options.map(actor => (
                <button
                    key={actor.actor_id}
                    type="button"
                    className={`filter-btn ${value === actor.actor_id ? 'active' : ''}`.trim()}
                    onClick={() => onChange(actor.actor_id)}
                >
                    {actor.name}
                </button>
            ))}
        </div>
    )
}

// ══════════════════════════════════════════════════════════════
// Page
// ══════════════════════════════════════════════════════════════

export default function KnowledgePage() {
    const { refreshToken } = useDashboardContext()
    const [data, setData] = useState(null)
    const [error, setError] = useState(null)
    const [expandedDomains, setExpandedDomains] = useState(new Set(['科学', '战斗']))
    const [expandedActors, setExpandedActors] = useState(new Set())
    const [actorFilter, setActorFilter] = useState('')
    const [subTab, setSubTab] = useState('actors')

    useEffect(() => {
        let cancelled = false

        fetchActorKnowledge()
            .then(result => {
                if (!cancelled) {
                    setData(result)
                    setError(null)
                }
            })
            .catch(err => {
                if (!cancelled) {
                    setError(err.message || '加载角色知识数据失败')
                    setData(null)
                }
            })

        return () => { cancelled = true }
    }, [refreshToken])

    const handleDomainToggle = key => {
        setExpandedDomains(prev => {
            const next = new Set(prev)
            if (next.has(key)) {
                next.delete(key)
            } else {
                next.add(key)
            }
            return next
        })
    }

    const handleActorToggle = actorId => {
        setExpandedActors(prev => {
            const next = new Set(prev)
            if (next.has(actorId)) {
                next.delete(actorId)
            } else {
                next.add(actorId)
            }
            return next
        })
    }

    const handleFilter = actorId => {
        setActorFilter(actorId)
        if (actorId) {
            setExpandedActors(new Set([actorId]))
        }
    }

    const filteredActors = useMemo(() => {
        if (!data?.actors) return []
        if (!actorFilter) return data.actors
        return data.actors.filter(a => a.actor_id === actorFilter)
    }, [data, actorFilter])

    if (error) {
        return (
            <div className="loading-screen">
                <div className="loading-card">
                    <div className="section-label">ERROR</div>
                    <p>{error}</p>
                </div>
            </div>
        )
    }

    if (!data) {
        return (
            <div className="loading-screen">
                <div className="loading-card">
                    <div className="section-label">LOADING</div>
                    <p>正在加载角色知识数据…</p>
                </div>
            </div>
        )
    }

    const { domain_tree, actors } = data

    return (
        <div className="knowledge-page">
            <div className="page-header">
                <h2 className="section-label">角色知识</h2>
                <div className="kb-tabs">
                    <button className={`kb-tab ${subTab==='actors'?'active':''}`} onClick={()=>setSubTab('actors')}>角色知识</button>
                    <button className={`kb-tab ${subTab==='library'?'active':''}`} onClick={()=>setSubTab('library')}>公共知识库</button>
                </div>
            </div>

            {subTab === 'library' ? <KnowledgeBasePage /> : (<>
            <div className="knowledge-layout">
                {/* ── 左侧：领域树 ── */}
                <aside className="knowledge-sidebar">
                    <div className="card">
                        <h3 className="card-title">领域体系</h3>
                        <DomainTree
                            tree={domain_tree}
                            expanded={expandedDomains}
                            onToggle={handleDomainToggle}
                        />
                    </div>
                </aside>

                {/* ── 右侧：角色列表 ── */}
                <main className="knowledge-main">
                    <div className="knowledge-toolbar">
                        <ActorFilter
                            actors={actors}
                            value={actorFilter}
                            onChange={handleFilter}
                        />
                        <span className="actor-total-count">
                            共 {filteredActors.length} 位角色
                        </span>
                    </div>

                    {filteredActors.length === 0 ? (
                        <div className="empty-state">
                            <p>暂无角色知识数据</p>
                        </div>
                    ) : (
                        <div className="actor-card-list">
                            {filteredActors.map(actor => (
                                <ActorCard
                                    key={actor.actor_id}
                                    actor={actor}
                                    isExpanded={expandedActors.has(actor.actor_id)}
                                    onToggle={handleActorToggle}
                                    onFilter={handleFilter}
                                />
                            ))}
                        </div>
                    )}
                </main>
            </div>
            </>)}
        </div>
    )
}
