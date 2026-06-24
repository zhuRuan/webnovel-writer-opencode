import { startTransition, useEffect, useMemo, useRef, useState } from 'react'
import { useDashboardContext } from '../App.jsx'
import {
    fetchEntities,
    fetchRelationships,
    fetchRelationshipEvents,
    fetchStateChanges,
    fetchEntityTimeline,
    fetchConsistencyAnomalies,
    fetchFactions,
    fetchCharacterEvents,
    createCharacterEvent,
    updateCharacterEvent,
    deleteCharacterEvent,
    resolveCharacterEvent,
    fetchOverdueEvents,
    fetchEntityKnowledge,
    fetchMemories,
} from '../api.js'
import Badge from '../components/Badge.jsx'
import ChartWrapper from '../components/ChartWrapper.jsx'
import DataTable from '../components/DataTable.jsx'
import { formatChapterLabel, formatJSONText } from '../lib/format.js'
import { getLatestChapter } from '../lib/story.js'

const TYPE_COLORS = {
    角色: '#26a8ff',
    势力: '#7f5af0',
    地点: '#2ec27e',
    法宝: '#f5a524',
}

const RELATIONSHIP_TYPE_COLORS = {
    亲属: '#f5a524',
    敌对: '#e5484d',
    合作: '#0090ff',
    其他: '#8f7f5c',
}

const RELATIONSHIP_TYPE_LABELS = {
    亲属: '亲属',
    敌对: '敌对',
    合作: '合作/同僚',
    其他: '其他',
}

const EVENT_TYPE_LABELS = { need_to_do: '待做', want_to_do: '想做', planned: '计划', promise: '承诺', prerequisite: '前置条件' }
const STATUS_LABELS = { pending: '待执行', in_progress: '进行中', resolved: '已完成', abandoned: '已放弃' }

const ANOMALY_TYPE_LABELS = { value_conflict: '数值冲突', chapter_gap: '章节跳跃', state_reversal: '状态回退' }
const ANOMALY_TYPE_COLORS = { value_conflict: 'red', chapter_gap: 'amber', state_reversal: 'purple' }

// 三角洲行动收藏品颜色等级: 白→绿→蓝→紫→金→红
// 三角洲收藏品颜色等级: 白→绿→蓝→紫→金→红→深红→暗红
function PROFICIENCY_COLOR(level) {
    if (level >= 12) return '#991b1b' // 至圣-暗红
    if (level >= 11) return '#dc2626' // 宗师-深红
    if (level >= 10) return '#ef4444' // 大师-红
    if (level >= 9)  return '#eab308' // 金
    if (level >= 7)  return '#8b5cf6' // 紫
    if (level >= 5)  return '#3b82f6' // 蓝
    if (level >= 3)  return '#22c55e' // 绿
    return '#9ca3af'                   // 灰
}
function DOMAIN_COLOR(level) {
    if (level >= 1.0)  return 'red'
    if (level >= 0.9)  return 'red'
    if (level >= 0.7)  return 'purple'
    if (level >= 0.5)  return 'blue'
    if (level >= 0.3)  return 'green'
    return 'gray'
}

const CATEGORY_NAMES = ['角色', '势力', '地点', '其他']

function parseTraits(entity) {
    if (!entity?.current_json) return []
    try {
        const parsed = typeof entity.current_json === 'string'
            ? JSON.parse(entity.current_json)
            : entity.current_json
        const traits = parsed?.traits
        return Array.isArray(traits) ? traits : []
    } catch {
        return []
    }
}

function detectRelationshipType(description) {
    if (!description) return '其他'
    const text = String(description)
    if (/亲|妹妹|姐姐|哥哥|弟弟|父亲|母亲|儿子|女儿|兄弟|姐妹|妻子|丈夫|配偶|兄妹|姐弟|母女|父子|母子/.test(text)) return '亲属'
    if (/敌|仇|杀|恨|憎|决裂|背叛|出卖/.test(text)) return '敌对'
    if (/同僚|合作|信任|盟友|伙伴|搭档|同志/.test(text)) return '合作'
    return '其他'
}

function parsePositiveChapter(value) {
    const number = Number(value)
    return Number.isFinite(number) && number > 0 ? number : null
}

function resolveCategory(type) {
    if (type === '角色') return '角色'
    if (type === '势力') return '势力'
    if (type === '地点') return '地点'
    return '其他'
}

function buildGraphData(entities, relationships, events, currentChapter, factionMemberMap = null) {
    const eventRows = [...events]
        .filter(row => (parsePositiveChapter(row.chapter) || 0) <= currentChapter)
        .sort((left, right) => (parsePositiveChapter(left.chapter) || 0) - (parsePositiveChapter(right.chapter) || 0))

    const latestEventByPair = new Map()
    for (const row of eventRows) {
        if (!row?.from_entity || !row?.to_entity) continue
        latestEventByPair.set(`${row.from_entity}|${row.to_entity}`, row)
    }

    const baseRelationships = [...relationships]
        .filter(row => (parsePositiveChapter(row.chapter) || 0) <= currentChapter)
        .sort((left, right) => (parsePositiveChapter(left.chapter) || 0) - (parsePositiveChapter(right.chapter) || 0))

    const linkMap = new Map()
    for (const row of baseRelationships) {
        if (!row?.from_entity || !row?.to_entity) continue
        const key = `${row.from_entity}|${row.to_entity}`
        linkMap.set(key, row)
    }
    for (const [key, row] of latestEventByPair.entries()) {
        linkMap.set(key, row)
    }

    const visibleEntityMap = new Map()
    for (const entity of entities) {
        const firstAppearance = parsePositiveChapter(entity?.first_appearance)
        if (!firstAppearance || firstAppearance <= currentChapter) {
            visibleEntityMap.set(entity.id, entity)
        }
    }

    for (const row of linkMap.values()) {
        const fromEntity = entities.find(entity => entity.id === row.from_entity)
        const toEntity = entities.find(entity => entity.id === row.to_entity)
        if (fromEntity) visibleEntityMap.set(fromEntity.id, fromEntity)
        if (toEntity) visibleEntityMap.set(toEntity.id, toEntity)
    }

    const nodes = [...visibleEntityMap.values()].map(entity => {
        const category = resolveCategory(entity.type)
        let symbolSize = entity.is_protagonist ? 34 : entity.tier === 'S' ? 30 : entity.tier === 'A' ? 26 : 22
        let nodeItemStyle = {
            color: entity.is_protagonist ? '#f5a524' : TYPE_COLORS[category] || '#00b8d4',
            borderColor: '#2a220f',
            borderWidth: 2,
        }
        if (entity.type === '势力' && factionMemberMap) {
            const memberCount = factionMemberMap.get(entity.id) || 0
            symbolSize = Math.min(50, 20 + memberCount * 5)
            nodeItemStyle = {
                color: TYPE_COLORS['势力'],
                borderColor: '#7f5af0',
                borderWidth: 2,
                shadowBlur: 10,
                shadowColor: 'rgba(127,90,240,0.4)',
            }
        }
        return {
            id: entity.id,
            name: entity.canonical_name || entity.id,
            value: entity.tier || '',
            category: CATEGORY_NAMES.indexOf(category),
            symbolSize,
            itemStyle: nodeItemStyle,
            label: {
                show: true,
                color: '#2a220f',
                fontSize: 11,
                fontWeight: 600,
            },
            type: entity.type,
            firstAppearance: entity.first_appearance,
        }
    })

    const links = [...linkMap.values()]
        .filter(row => visibleEntityMap.has(row.from_entity) && visibleEntityMap.has(row.to_entity))
        .map(row => {
            const description = row.description || row.event_type || row.type || '关联'
            const relType = detectRelationshipType(row.description || row.description_text || '')
            const relColor = RELATIONSHIP_TYPE_COLORS[relType] || RELATIONSHIP_TYPE_COLORS.其他
            const fromEntity = visibleEntityMap.get(row.from_entity)
            const toEntity = visibleEntityMap.get(row.to_entity)
            const isFactionLink = fromEntity?.type === '势力' && toEntity?.type === '势力'
            return {
                source: row.from_entity,
                target: row.to_entity,
                name: description,
                relType,
                lineStyle: {
                    color: isFactionLink ? '#7f5af0' : relColor,
                    width: isFactionLink ? 3 : 2,
                    curveness: 0.1,
                },
                label: {
                    show: true,
                    color: '#5d5035',
                    fontSize: 11,
                },
            }
        })

    return { nodes, links }
}

function buildGraphOption(data) {
    return {
        tooltip: {
            formatter: params => {
                if (params.dataType === 'edge') {
                    return params.data?.name || '关系'
                }
                return `${params.data?.name || '实体'}<br/>${params.data?.type || '未知类型'}`
            },
        },
        legend: {
            bottom: 0,
            data: CATEGORY_NAMES,
        },
        series: [
            {
                type: 'graph',
                layout: 'force',
                roam: true,
                symbol: 'rect',
                animationDuration: 300,
                animationEasingUpdate: 'cubicOut',
                categories: CATEGORY_NAMES.map(name => ({
                    name,
                    itemStyle: { color: TYPE_COLORS[name] || '#00b8d4' },
                })),
                force: {
                    repulsion: 360,
                    edgeLength: [120, 200],
                    gravity: 0.08,
                },
                lineStyle: {
                    color: '#8f7f5c',
                    width: 2,
                    curveness: 0.1,
                },
                edgeLabel: {
                    show: true,
                    formatter: params => params.data?.name || '',
                    color: '#5d5035',
                    fontSize: 11,
                },
                emphasis: {
                    focus: 'adjacency',
                    label: { show: true },
                },
                data: data.nodes,
                links: data.links,
            },
        ],
    }
}

function buildFactionGraphData(entities, relationships, factions) {
    const factionIds = new Set(factions.map(f => f.id))
    const memberMap = new Map()
    for (const f of factions) {
        memberMap.set(f.id, f.member_count || 0)
    }

    const nodeMap = new Map()
    for (const entity of entities) {
        if (factionIds.has(entity.id)) {
            const memberCount = memberMap.get(entity.id) || 0
            nodeMap.set(entity.id, {
                id: entity.id,
                name: entity.canonical_name || entity.id,
                memberCount,
                symbolSize: Math.min(50, 20 + memberCount * 5),
                category: CATEGORY_NAMES.indexOf('势力'),
                itemStyle: {
                    color: TYPE_COLORS['势力'],
                    borderColor: '#7f5af0',
                    borderWidth: 2,
                    shadowBlur: 10,
                    shadowColor: 'rgba(127,90,240,0.4)',
                },
                label: { show: true, fontSize: 12, fontWeight: 700 },
                type: entity.type,
            })
        }
    }

    const links = []
    const entityLookup = new Map(entities.map(e => [e.id, e]))
    const seenLinkKeys = new Set()

    for (const rel of relationships) {
        const fromIsFaction = factionIds.has(rel.from_entity)
        const toIsFaction = factionIds.has(rel.to_entity)
        if (!fromIsFaction && !toIsFaction) continue

        const linkKey = `${rel.from_entity}|${rel.to_entity}`
        if (seenLinkKeys.has(linkKey)) continue
        seenLinkKeys.add(linkKey)

        if (!fromIsFaction && !nodeMap.has(rel.from_entity)) {
            const entity = entityLookup.get(rel.from_entity)
            if (entity) {
                const category = resolveCategory(entity.type)
                nodeMap.set(entity.id, {
                    id: entity.id,
                    name: entity.canonical_name || entity.id,
                    symbolSize: 16,
                    category: CATEGORY_NAMES.indexOf(category),
                    itemStyle: { color: TYPE_COLORS[category] || '#00b8d4' },
                    label: { show: true, fontSize: 10, color: '#5d5035' },
                    type: entity.type,
                })
            }
        }
        if (!toIsFaction && !nodeMap.has(rel.to_entity)) {
            const entity = entityLookup.get(rel.to_entity)
            if (entity) {
                const category = resolveCategory(entity.type)
                nodeMap.set(entity.id, {
                    id: entity.id,
                    name: entity.canonical_name || entity.id,
                    symbolSize: 16,
                    category: CATEGORY_NAMES.indexOf(category),
                    itemStyle: { color: TYPE_COLORS[category] || '#00b8d4' },
                    label: { show: true, fontSize: 10, color: '#5d5035' },
                    type: entity.type,
                })
            }
        }

        const isPureFactionLink = fromIsFaction && toIsFaction
        links.push({
            source: rel.from_entity,
            target: rel.to_entity,
            name: rel.description || rel.type || '关联',
            lineStyle: {
                color: isPureFactionLink ? '#7f5af0' : '#8f7f5c',
                width: isPureFactionLink ? 3 : 1,
                type: isPureFactionLink ? 'solid' : 'dashed',
                curveness: 0.15,
            },
        })
    }

    return { nodes: [...nodeMap.values()], links }
}

function buildFactionGraphOption(data) {
    return {
        tooltip: {
            formatter: params => {
                if (params.dataType === 'edge') {
                    return params.data?.name || '关系'
                }
                return `${params.data?.name || '势力'}<br/>成员: ${params.data?.memberCount || 0}`
            },
        },
        series: [
            {
                type: 'graph',
                layout: 'force',
                roam: true,
                symbol: 'circle',
                animationDuration: 300,
                force: {
                    repulsion: 200,
                    edgeLength: [80, 180],
                    gravity: 0.15,
                },
                emphasis: {
                    focus: 'adjacency',
                },
                data: data.nodes,
                links: data.links,
            },
        ],
    }
}

const MATRIX_TYPE_COLORS = {
    敌对: '#e5484d',
    同盟: '#2ec27e',
    合作: '#0090ff',
    中立: '#6b6b6b',
}

function buildFactionMatrix(factions, relationships) {
    if (!factions.length) return { factionNames: [], matrix: [] }
    const factionIds = new Set(factions.map(f => f.id))
    const factionNames = factions.map(f => f.canonical_name || f.name || f.id)
    const factionIndexMap = new Map(factions.map((f, i) => [f.id, i]))
    const n = factions.length

    const matrix = Array.from({ length: n }, () => Array(n).fill('中立'))
    for (let i = 0; i < n; i++) matrix[i][i] = '—'

    const relMap = new Map()
    for (const rel of relationships) {
        if (!factionIds.has(rel.from_entity) || !factionIds.has(rel.to_entity)) continue
        const key = `${rel.from_entity}|${rel.to_entity}`
        if (!relMap.has(key)) relMap.set(key, rel)
    }

    for (const [key, rel] of relMap.entries()) {
        const [from, to] = key.split('|')
        const fi = factionIndexMap.get(from)
        const tj = factionIndexMap.get(to)
        if (fi === undefined || tj === undefined) continue
        const type = detectRelationshipType(rel.description || '')
        const label = type === '合作' ? '合作' : type === '敌对' ? '敌对' : '同盟'
        matrix[fi][tj] = label
    }

    return { factionNames, matrix }
}

function TypeFilter({ types, value, onChange }) {
    return (
        <div className="filter-group">
            <button
                type="button"
                className={`filter-btn ${value === '' ? 'active' : ''}`.trim()}
                onClick={() => onChange('')}
            >
                全部
            </button>
            {types.map(type => (
                <button
                    key={type}
                    type="button"
                    className={`filter-btn ${value === type ? 'active' : ''}`.trim()}
                    onClick={() => onChange(type)}
                >
                    {type}
                </button>
            ))}
        </div>
    )
}

function EntityListTable({ rows, selectedId, onSelect }) {
    if (!rows.length) {
        return (
            <div className="empty-state">
                <p>暂无实体数据</p>
            </div>
        )
    }

    return (
        <div className="table-wrap">
            <table className="data-table entity-table">
                <thead>
                    <tr>
                        <th>名称</th>
                        <th>类型</th>
                        <th>性格特质</th>
                        <th>首现</th>
                        <th>末现</th>
                    </tr>
                </thead>
                <tbody>
                    {rows.map(entity => (
                        <tr
                            key={entity.id}
                            className={`entity-row ${selectedId === entity.id ? 'selected' : ''}`.trim()}
                            onClick={() => onSelect(entity)}
                        >
                            <td className={`entity-name ${entity.is_protagonist ? 'protagonist' : ''}`.trim()}>
                                {entity.canonical_name}
                            </td>
                            <td>
                                <Badge tone="blue">{entity.type || '未知'}</Badge>
                            </td>
                            <td>
                                {(() => {
                                    const traits = parseTraits(entity)
                                    if (!traits.length) return '—'
                                    return (
                                        <span style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                                            {traits.slice(0, 2).map((trait, index) => (
                                                <Badge key={index} tone="purple">{trait}</Badge>
                                            ))}
                                            {traits.length > 2 && (
                                                <Badge tone="neutral">+{traits.length - 2}</Badge>
                                            )}
                                        </span>
                                    )
                                })()}
                            </td>
                            <td>{formatChapterLabel(entity.first_appearance)}</td>
                            <td>{formatChapterLabel(entity.last_appearance)}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    )
}

export default function CharactersPage() {
    const { projectInfo, refreshToken } = useDashboardContext()
    const [tab, setTab] = useState('list')
    const [entities, setEntities] = useState([])
    const [relationships, setRelationships] = useState([])
    const [relationshipEvents, setRelationshipEvents] = useState([])
    const [typeFilter, setTypeFilter] = useState('')
    const [selected, setSelected] = useState(null)
    const [changes, setChanges] = useState([])
    const [timeline, setTimeline] = useState(null)
    const [anomalies, setAnomalies] = useState([])
    const [factions, setFactions] = useState([])
    const [selectedFaction, setSelectedFaction] = useState(null)
    const [entityKnowledge, setEntityKnowledge] = useState(null)
    const [playing, setPlaying] = useState(false)
    const [characterEvents, setCharacterEvents] = useState([])
    const [memories, setMemories] = useState([])
    const [loadingMemories, setLoadingMemories] = useState(false)
    const [eventsFilter, setEventsFilter] = useState('all')
    const [showCreateModal, setShowCreateModal] = useState(false)
    const [newEvent, setNewEvent] = useState({ event_type: 'need_to_do', description: '', urgency: 5, target_chapter: '' })
    const latestChapter = getLatestChapter(projectInfo)
    const [graphChapter, setGraphChapter] = useState(latestChapter)

    useEffect(() => {
        setGraphChapter(latestChapter)
    }, [latestChapter, refreshToken])

    useEffect(() => {
        let cancelled = false

        Promise.allSettled([
            fetchEntities(),
            fetchRelationships({ limit: 1000 }),
            fetchRelationshipEvents({ limit: 5000 }),
            fetchConsistencyAnomalies(),
            fetchFactions(),
        ]).then(results => {
            if (cancelled) return

            const entityRows = results[0].status === 'fulfilled' ? results[0].value : []
            setEntities(entityRows)
            setRelationships(results[1].status === 'fulfilled' ? results[1].value : [])
            setRelationshipEvents(results[2].status === 'fulfilled' ? results[2].value : [])
            setAnomalies(results[3].status === 'fulfilled' ? (results[3].value.anomalies || []) : [])
            setFactions(results[4].status === 'fulfilled' ? (results[4].value.factions || []) : [])

            if (entityRows.length) {
                setSelected(current => current || entityRows[0])
            }
        })

        return () => {
            cancelled = true
        }
    }, [refreshToken])

    useEffect(() => {
        if (!selected?.id) {
            setChanges([])
            setTimeline(null)
            return
        }

        let cancelled = false
        fetchStateChanges({ entity: selected.id, limit: 30 })
            .then(payload => {
                if (!cancelled) setChanges(payload)
            })
            .catch(() => {
                if (!cancelled) setChanges([])
            })

        fetchEntityTimeline(selected.id)
            .then(payload => {
                if (!cancelled) setTimeline(payload)
            })
            .catch(() => {
                if (!cancelled) setTimeline(null)
            })

        return () => {
            cancelled = true
        }
    }, [selected])

    useEffect(() => {
        if (selected?.id) {
            fetchEntityKnowledge(selected.id).then(d => setEntityKnowledge(d))
        } else {
            setEntityKnowledge(null)
        }
    }, [selected])

    useEffect(() => {
        if (!selected?.id) {
            setCharacterEvents([])
            return
        }
        let cancelled = false
        const status = eventsFilter === 'all' ? undefined : eventsFilter
        fetchCharacterEvents(selected.id, status)
            .then(data => {
                if (!cancelled) setCharacterEvents(data.events || [])
            })
            .catch(() => {
                if (!cancelled) setCharacterEvents([])
            })
        return () => { cancelled = true }
    }, [selected, eventsFilter])

    const advanceGraphRef = useRef(null)
    advanceGraphRef.current = () => {
        setGraphChapter(current => {
            if (current >= latestChapter) {
                setPlaying(false)
                return latestChapter
            }
            return Math.min(latestChapter, current + 5)
        })
    }

    useEffect(() => {
        if (!playing) return undefined
        const timer = window.setInterval(() => advanceGraphRef.current(), 120)
        return () => window.clearInterval(timer)
    }, [playing])

    const types = useMemo(() => {
        return [...new Set(entities.map(entity => entity.type).filter(Boolean))].sort()
    }, [entities])

    const filteredEntities = useMemo(() => {
        return typeFilter ? entities.filter(entity => entity.type === typeFilter) : entities
    }, [entities, typeFilter])

    useEffect(() => {
        if (selected && filteredEntities.some(entity => entity.id === selected.id)) return
        setSelected(filteredEntities[0] || null)
    }, [filteredEntities, selected])

    const graphData = useMemo(() => {
        const factionMemberMap = new Map()
        for (const f of factions) {
            factionMemberMap.set(f.id, f.member_count || 0)
        }
        const filteredNodes = typeFilter ? entities.filter(entity => entity.type === typeFilter) : entities
        const filteredIds = new Set(filteredNodes.map(e => e.id))
        const filteredRels = relationships.filter(r =>
            filteredIds.has(r.from_entity) || filteredIds.has(r.to_entity)
        )
        return buildGraphData(filteredNodes, filteredRels, relationshipEvents, graphChapter, factionMemberMap)
    }, [entities, typeFilter, graphChapter, relationshipEvents, relationships, factions])

    const factionGraphData = useMemo(() => {
        if (!factions.length) return { nodes: [], links: [] }
        return buildFactionGraphData(entities, relationships, factions)
    }, [entities, relationships, factions])

    const factionMatrixData = useMemo(() => {
        return buildFactionMatrix(factions, relationships)
    }, [factions, relationships])

    const filteredEvents = useMemo(() => {
        if (eventsFilter === 'all') return characterEvents
        return characterEvents.filter(e => e.status === eventsFilter)
    }, [characterEvents, eventsFilter])

    const overdueEvents = useMemo(() => {
        const GRACE = 10
        return characterEvents.filter(e => {
            const target = Number(e.target_chapter)
            if (!target) return false
            return target + GRACE < latestChapter && (e.status === 'pending' || e.status === 'in_progress')
        })
    }, [characterEvents, latestChapter])

    function buildGanttOption(events, currentCh) {
        const GRACE = 10
        const data = events
            .filter(e => Number(e.target_chapter) > 0)
            .map(e => {
                const target = Number(e.target_chapter)
                const isOverdue = currentCh > target + GRACE && (e.status === 'pending' || e.status === 'in_progress')
                const color = e.status === 'resolved' ? '#2ec27e'
                    : e.status === 'abandoned' ? '#8f7f5c'
                    : isOverdue ? '#d7263d'
                    : e.status === 'in_progress' ? '#26a8ff'
                    : '#f5a524'
                return {
                    name: (e.description || e.event_type || '?').slice(0, 24),
                    value: target,
                    itemStyle: { color, borderRadius: 4 },
                }
            })
            .sort((a, b) => a.value - b.value)

        return {
            tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
            grid: { left: 140, right: 50, top: 12, bottom: 40 },
            xAxis: { type: 'value', name: '章节', min: 0 },
            yAxis: {
                type: 'category',
                data: data.map(d => d.name),
                inverse: true,
                axisLabel: { width: 130, overflow: 'truncate' },
            },
            series: [{
                type: 'bar',
                data,
                label: { show: true, position: 'right', formatter: p => `第${p.value}章` },
            }],
        }
    }

    function handleCreateEvent() {
        if (!selected?.id) return
        const payload = {
            actor_id: selected.id,
            event_type: newEvent.event_type,
            description: newEvent.description,
            urgency: Number(newEvent.urgency) || 5,
            target_chapter: newEvent.target_chapter ? Number(newEvent.target_chapter) : null,
        }
        createCharacterEvent(payload).then(() => {
            setShowCreateModal(false)
            setNewEvent({ event_type: 'need_to_do', description: '', urgency: 5, target_chapter: '' })
            if (selected?.id) {
                const status = eventsFilter === 'all' ? undefined : eventsFilter
                fetchCharacterEvents(selected.id, status)
                    .then(data => setCharacterEvents(data.events || []))
                    .catch(() => setCharacterEvents([]))
            }
        }).catch(err => {
            alert('创建失败: ' + (err?.message || '未知错误'))
        })
    }

    return (
        <section className="dashboard-page">
            <header className="page-header">
                <h2>角色图鉴</h2>
                <Badge tone="green">{filteredEntities.length} / {entities.length} 个实体</Badge>
            </header>

            <TypeFilter types={types} value={typeFilter} onChange={setTypeFilter} />

            <div className="tab-strip">
                <button
                    type="button"
                    className={`tab-btn ${tab === 'list' ? 'active' : ''}`.trim()}
                    onClick={() => setTab('list')}
                >
                    实体列表
                </button>
                <button
                    type="button"
                    className={`tab-btn ${tab === 'graph' ? 'active' : ''}`.trim()}
                    onClick={() => setTab('graph')}
                >
                    关系图谱
                </button>
                <button
                    type="button"
                    className={`tab-btn ${tab === 'timeline' ? 'active' : ''}`.trim()}
                    onClick={() => setTab('timeline')}
                >
                    时间线
                    {anomalies.length > 0 && <Badge tone="red" style={{ marginLeft: 4 }}>{anomalies.length}</Badge>}
                </button>
                <button
                    type="button"
                    className={`tab-btn ${tab === 'plans' ? 'active' : ''}`.trim()}
                    onClick={() => setTab('plans')}
                >
                    角色计划
                    {overdueEvents.length > 0 && <Badge tone="red" style={{ marginLeft: 4 }}>{overdueEvents.length}</Badge>}
                </button>
                <button
                    type="button"
                    className={`tab-btn ${tab === 'factions' ? 'active' : ''}`.trim()}
                    onClick={() => setTab('factions')}
                >
                    势力图谱
                </button>
            </div>

            {tab === 'list' ? (
                <div className="split-layout">
                    <div className="split-main">
                        <article className="card">
                            <div className="card-header">
                                <div>
                                    <div className="section-label">ENTITY INDEX</div>
                                    <div className="card-title">实体列表</div>
                                </div>
                                <Badge tone="cyan">{typeFilter || '全部类型'}</Badge>
                            </div>
                            <EntityListTable
                                rows={filteredEntities}
                                selectedId={selected?.id}
                                onSelect={setSelected}
                            />
                        </article>
                    </div>

                    <div className="split-side">
                        <article className="card sticky-card">
                            <div className="card-header">
                                <div>
                                    <div className="section-label">ENTITY DETAIL</div>
                                    <div className="card-title">{selected?.canonical_name || '未选择实体'}</div>
                                </div>
                                {selected?.tier ? (
                                    (() => {
                                        const traits = parseTraits(selected)
                                        if (!traits.length) return <Badge tone="purple">{selected.tier}</Badge>
                                        return (
                                            <span style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                                                {traits.map((trait, index) => (
                                                    <Badge key={index} tone="purple">{trait}</Badge>
                                                ))}
                                            </span>
                                        )
                                    })()
                                ) : null}
                            </div>
                            {selected ? (
                                <div className="entity-detail">
                                    <p><strong>类型：</strong>{selected.type || '未知'}</p>
                                    <p><strong>ID：</strong><code>{selected.id}</code></p>
                                    <p><strong>首现：</strong>{formatChapterLabel(selected.first_appearance)}</p>
                                    <p><strong>末现：</strong>{formatChapterLabel(selected.last_appearance)}</p>
                                    {selected.desc ? <p className="entity-desc">{selected.desc}</p> : null}
                                    {selected.current_json ? (
                                        <div className="entity-current-block">
                                            <div className="mini-label">当前状态</div>
                                            <pre className="code-block">{formatJSONText(selected.current_json)}</pre>
                                        </div>
                                    ) : null}
                                </div>
                            ) : (
                                <div className="empty-state compact">
                                    <p>从左侧选择一个实体查看详情</p>
                                </div>
                            )}

                            {characterEvents.length > 0 && (
                                <div style={{ display:'flex', gap:6, flexWrap:'wrap', padding: '8px 16px' }}>
                                    <span style={{fontSize:11,color:'var(--text-sub)'}}>活跃计划:</span>
                                    {characterEvents.filter(e => e.status === 'pending' || e.status === 'in_progress').slice(0,3).map(e => (
                                        <Badge key={e.id} tone={e.urgency >= 8 ? 'red' : e.urgency >= 5 ? 'amber' : 'blue'} style={{fontSize:11}}>
                                            {EVENT_TYPE_LABELS[e.event_type]}: {e.description.slice(0,20)}{e.description.length>20?'…':''}
                                        </Badge>
                                    ))}
                                </div>
                            )}

                            {entityKnowledge && (
                                <article className="card" style={{ marginTop: 16 }}>
                                    <div className="card-header">
                                        <div>
                                            <div className="section-label">CHARACTER KNOWLEDGE</div>
                                            <div className="card-title">角色知识</div>
                                        </div>
                                    </div>

                                    {entityKnowledge.core_desire && (
                                        <div style={{ padding: '0 16px 12px' }}>
                                            <div className="section-label" style={{ fontSize: 11 }}>核心欲望</div>
                                            <div style={{ fontSize: 14, color: 'var(--text-main)' }}>{entityKnowledge.core_desire}</div>
                                        </div>
                                    )}

                                    {entityKnowledge.traits?.length > 0 && (
                                        <div style={{ padding: '0 16px 12px' }}>
                                            <div className="section-label" style={{ fontSize: 11 }}>性格特质</div>
                                            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                                                {entityKnowledge.traits.map((t, i) => <Badge key={i} tone="purple">{t}</Badge>)}
                                            </div>
                                        </div>
                                    )}

                                    {entityKnowledge.known_domains && Object.keys(entityKnowledge.known_domains).length > 0 && (
                                        <div style={{ padding: '0 16px 12px' }}>
                                            <div className="section-label" style={{ fontSize: 11 }}>知识领域</div>
                                            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                                                {Object.entries(entityKnowledge.known_domains).map(([domain, level]) => (
                                                    <Badge key={domain} tone={DOMAIN_COLOR(level)}>
                                                        {domain} ({Math.round(level * 100)}%)
                                                    </Badge>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {entityKnowledge.skills?.length > 0 && (
                                        <div style={{ padding: '0 16px 16px' }}>
                                            <div className="section-label" style={{ fontSize: 11 }}>技能</div>
                                            {entityKnowledge.skills.map(s => (
                                                <div key={s.name} style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '4px 0' }}>
                                                    <span style={{ fontSize: 13, flex: '0 0 100px' }}>{s.label || s.name}</span>
                                                    <div style={{ flex: 1, height: 6, background: 'var(--border)', borderRadius: 3, overflow: 'hidden' }}>
                                                        <div style={{ width: `${(s.proficiency || 0) * 10}%`, height: '100%', background: PROFICIENCY_COLOR(s.proficiency || 0), borderRadius: 3 }} />
                                                    </div>
                                                    <span style={{ fontSize: 11, color: 'var(--text-sub)', width: 20 }}>{s.proficiency}</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </article>
                            )}

                            {!entityKnowledge && selected && (
                                <div style={{ padding: 16, color: 'var(--text-sub)', fontSize: 13 }}>暂无知识记录</div>
                            )}

                            {/* Character Memories */}
                            {selected && (
                                <article className="card" style={{marginTop: 16}}>
                                    <div className="card-header">
                                        <div className="section-label">CHARACTER MEMORIES</div>
                                        <div className="card-title">角色记忆</div>
                                    </div>
                                    <button className="page-btn" style={{margin:'8px 16px'}} onClick={async () => {
                                        if (!selected?.id) return
                                        setLoadingMemories(true)
                                        try {
                                            const data = await fetchMemories(selected.id, null, 10)
                                            setMemories(data.memories || [])
                                        } catch { setMemories([]) }
                                        setLoadingMemories(false)
                                    }}>加载记忆</button>
                                    {loadingMemories && <div style={{padding:16,color:'var(--text-sub)',fontSize:13}}>加载中...</div>}
                                    {!loadingMemories && memories.length === 0 && (
                                        <div style={{padding:16,color:'var(--text-sub)',fontSize:13}}>暂无记忆</div>
                                    )}
                                    {memories.map((m, i) => {
                                        const typeColors = {episodic:'#3b82f6', semantic:'#22c55e', relational:'#eab308', decision:'#8b5cf6'}
                                        const typeLabels = {episodic:'经历', semantic:'知识', relational:'印象', decision:'决策'}
                                        return (
                                            <div key={i} style={{padding:'8px 16px',borderBottom:'1px solid var(--border)',fontSize:12}}>
                                                <div style={{display:'flex',gap:6,marginBottom:4}}>
                                                    <span style={{background:typeColors[m.memory_type]||'#888',color:'#fff',padding:'1px 6px',borderRadius:3,fontSize:10,fontWeight:600}}>
                                                        {typeLabels[m.memory_type]||m.memory_type}
                                                    </span>
                                                    <span style={{color:'var(--text-sub)'}}>第{m.when_chapter||m.source_chapter}章</span>
                                                    <span style={{color:'var(--text-sub)'}}>留存: {(m.retention*100).toFixed(0)}%</span>
                                                </div>
                                                <div style={{lineHeight:1.5}}>{m.content}</div>
                                            </div>
                                        )
                                    })}
                                </article>
                            )}

                            <div className="detail-divider" />

                            <div className="card-header compact-header">
                                <div>
                                    <div className="section-label">STATE CHANGES</div>
                                    <div className="card-title">状态变化历史</div>
                                </div>
                                <Badge tone="amber">{changes.length} 条</Badge>
                            </div>
                            <DataTable
                                columns={[
                                    {
                                        key: 'chapter',
                                        label: '章',
                                        render: row => formatChapterLabel(row.chapter),
                                    },
                                    { key: 'field', label: '字段' },
                                    {
                                        key: 'change',
                                        label: '变化',
                                        render: row => `${row.old_value ?? '—'} → ${row.new_value ?? '—'}`,
                                    },
                                ]}
                                rows={changes}
                                rowKey={(row, index) => `${row.entity_id || 'entity'}-${row.chapter || 0}-${index}`}
                                pageSize={6}
                                emptyText="暂无状态变化记录"
                                minWidth={420}
                            />
                        </article>
                    </div>
                </div>
            ) : tab === 'graph' ? (
                <article className="card">
                    <div className="card-header">
                        <div>
                            <div className="section-label">RELATION GRAPH</div>
                            <div className="card-title">关系图谱</div>
                        </div>
                        <Badge tone="blue">ECharts graph · 力导向 · 时间轴</Badge>
                    </div>

                    <div className="graph-toolbar">
                        <button
                            type="button"
                            className="page-btn icon-btn"
                            onClick={() => {
                                if (playing) {
                                    setPlaying(false)
                                    return
                                }
                                if (graphChapter >= latestChapter) {
                                    setGraphChapter(1)
                                }
                                setPlaying(true)
                            }}
                        >
                            {playing ? '暂停' : '播放'}
                        </button>
                        <span className="range-label">第 1 章</span>
                        <input
                            className="timeline-slider"
                            type="range"
                            min="1"
                            max={String(Math.max(1, latestChapter))}
                            value={graphChapter}
                            onChange={event => {
                                const nextChapter = Number(event.target.value)
                                startTransition(() => {
                                    setGraphChapter(nextChapter)
                                })
                            }}
                        />
                        <span className="range-label">{formatChapterLabel(latestChapter)}</span>
                        <Badge tone="blue">{formatChapterLabel(graphChapter)}</Badge>
                        <Badge tone="green">{graphData.nodes.length} 节点</Badge>
                        <Badge tone="purple">{graphData.links.length} 关系</Badge>
                    </div>

                    {graphData.nodes.length ? (
                        <>
                            <ChartWrapper
                                className="tall"
                                height={420}
                                option={buildGraphOption(graphData)}
                            />
                            <div style={{
                                display: 'flex',
                                gap: 20,
                                justifyContent: 'center',
                                padding: '12px 16px 4px',
                                fontSize: 13,
                            }}>
                                {Object.entries(RELATIONSHIP_TYPE_COLORS).map(([type, color]) => (
                                    <span key={type} style={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: 6,
                                        color: 'var(--text-sub)',
                                    }}>
                                        <span style={{
                                            display: 'inline-block',
                                            width: 10,
                                            height: 10,
                                            borderRadius: '50%',
                                            backgroundColor: color,
                                            flexShrink: 0,
                                        }} />
                                        {RELATIONSHIP_TYPE_LABELS[type]}
                                    </span>
                                ))}
                            </div>
                        </>
                    ) : (
                        <div className="empty-state">
                            <p>当前章节窗口没有可视化关系</p>
                        </div>
                    )}
                </article>
            ) : tab === 'timeline' ? (
                /* 时间线 Tab */
                <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                    {/* 异常告警 */}
                    {anomalies.length > 0 && (() => {
                        const classified = anomalies.map(a => ({
                            ...a,
                            entity: entities.find(e => e.id === a.entity_id),
                            severity: (() => {
                                const entity = entities.find(e => e.id === a.entity_id)
                                const isCore = ['canonical_name', 'type', 'tier'].includes(a.field)
                                if (entity?.is_protagonist || isCore) return 'fatal'
                                if (entity?.tier === 'supporting' || entity?.type === '配角') return 'severe'
                                return 'minor'
                            })()
                        }))

                        const fatal = classified.filter(a => a.severity === 'fatal')
                        const severe = classified.filter(a => a.severity === 'severe')
                        const minor = classified.filter(a => a.severity === 'minor')

                        return (
                            <article className="card" style={{ borderLeft: '3px solid var(--accent-red)' }}>
                                <div className="card-header">
                                    <span className="card-title" style={{ color: 'var(--accent-red)' }}>⚠ 状态一致性异常</span>
                                    <Badge tone="red">{anomalies.length}</Badge>
                                </div>

                                <div style={{ display: 'flex', gap: 20, padding: '12px 16px', borderBottom: '1px solid var(--border)' }}>
                                    {fatal.length > 0 && <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ width: 10, height: 10, borderRadius: '50%', background: '#ef4444', display: 'inline-block' }} /><span style={{ fontWeight: 600 }}>致命</span><Badge tone="red">{fatal.length}</Badge></div>}
                                    {severe.length > 0 && <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ width: 10, height: 10, borderRadius: '50%', background: '#f97316', display: 'inline-block' }} /><span style={{ fontWeight: 600 }}>严重</span><Badge tone="amber">{severe.length}</Badge></div>}
                                    {minor.length > 0 && <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ width: 10, height: 10, borderRadius: '50%', background: '#eab308', display: 'inline-block' }} /><span style={{ fontWeight: 600 }}>轻微</span><Badge tone="yellow">{minor.length}</Badge></div>}
                                </div>

                                {[...fatal, ...severe, ...minor].map((a, i) => {
                                    const entityName = a.entity?.canonical_name || a.entity_id
                                    const colors = { fatal: { bg: 'rgba(239,68,68,0.08)', border: '#ef4444', label: '致命' }, severe: { bg: 'rgba(249,115,22,0.05)', border: '#f97316', label: '严重' }, minor: { bg: 'transparent', border: '#eab308', label: '轻微' } }
                                    const c = colors[a.severity]
                                    return (
                                        <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '10px 16px', borderBottom: '1px solid var(--border)', background: c.bg }}>
                                            <span style={{ color: c.border, fontWeight: 700, fontSize: 12, flexShrink: 0, marginTop: 2 }}>{c.label}</span>
                                            <div style={{ flex: 1, minWidth: 0 }}>
                                                <div style={{ fontSize: 13 }}><strong>{entityName}</strong><span style={{ color: 'var(--text-sub)', margin: '0 4px' }}>·</span><Badge tone="amber">{a.field}</Badge><span style={{ color: 'var(--text-sub)', margin: '0 4px' }}>·</span>第{typeof a.chapter === 'number' ? a.chapter : a.chapter}章</div>
                                                <div style={{ fontSize: 12, color: 'var(--text-sub)', marginTop: 2 }}>{a.field}字段存在不一致的多个值，可能跨章节设定矛盾</div>
                                            </div>
                                        </div>
                                    )
                                })}
                            </article>
                        )
                    })()}

                    {/* 实体时间线 */}
                    {selected && timeline ? (
                        <>
                            <article className="card">
                                <div className="card-header">
                                    <span className="card-title">{selected.canonical_name} — 状态变化时间线</span>
                                    <Badge tone="blue">{timeline.changes.length} 次变化</Badge>
                                </div>
                                {timeline.changes.length === 0 ? (
                                    <div className="empty-state compact">暂无状态变化记录</div>
                                ) : (
                                    <div className="table-wrap">
                                        <table className="data-table">
                                            <thead>
                                                <tr>
                                                    <th>章节</th>
                                                    <th>字段</th>
                                                    <th>旧值</th>
                                                    <th>新值</th>
                                                    <th>原因</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {timeline.changes.map((c, i) => (
                                                    <tr key={i}>
                                                        <td style={{ fontWeight: 700 }}>{formatChapterLabel(c.chapter)}</td>
                                                        <td><Badge tone="neutral">{c.field}</Badge></td>
                                                        <td style={{ color: 'var(--text-sub)' }}>{c.old_value ?? '—'}</td>
                                                        <td style={{ fontWeight: 600 }}>{c.new_value ?? '—'}</td>
                                                        <td style={{ fontSize: 13, color: 'var(--text-mute)' }}>{c.reason || '—'}</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                )}
                            </article>

                            <article className="card">
                                <div className="card-header">
                                    <span className="card-title">{selected.canonical_name} — 出场记录</span>
                                    <Badge tone="green">{timeline.appearances.length} 个场景</Badge>
                                </div>
                                {timeline.appearances.length === 0 ? (
                                    <div className="empty-state compact">暂无出场记录</div>
                                ) : (
                                    <div className="table-wrap">
                                        <table className="data-table">
                                            <thead>
                                                <tr>
                                                    <th>章节</th>
                                                    <th>场景</th>
                                                    <th>地点</th>
                                                    <th>概要</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {timeline.appearances.map((a, i) => (
                                                    <tr key={i}>
                                                        <td style={{ fontWeight: 700 }}>{formatChapterLabel(a.chapter)}</td>
                                                        <td>#{a.scene_index}</td>
                                                        <td>{a.location || '—'}</td>
                                                        <td style={{ fontSize: 13, color: 'var(--text-sub)' }}>
                                                            {(a.summary || '').slice(0, 60)}{(a.summary || '').length > 60 ? '...' : ''}
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                )}
                            </article>
                        </>
                    ) : selected ? (
                        <div className="empty-state">加载时间线数据中...</div>
                    ) : (
                        <div className="empty-state">请先选择一个实体</div>
                    )}
                </div>
            ) : tab === 'factions' ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                    <div style={{ display: 'flex', gap: 16, minHeight: 420 }}>
                        <div className="split-side" style={{ width: 280, flexShrink: 0 }}>
                            <article className="card" style={{ height: '100%', overflow: 'auto' }}>
                                <div className="card-header">
                                    <div className="section-label">FACTIONS</div>
                                    <div className="card-title">势力列表</div>
                                    <Badge tone="purple">{factions.length} 个</Badge>
                                </div>
                                {factions.length ? factions.map(f => (
                                    <div key={f.id}
                                        onClick={() => setSelectedFaction(f)}
                                        style={{
                                            padding: '8px 12px',
                                            cursor: 'pointer',
                                            background: selectedFaction?.id === f.id ? 'var(--hover-bg)' : 'transparent',
                                            borderRadius: 6,
                                            marginBottom: 4,
                                        }}
                                    >
                                        <strong>{f.canonical_name || f.name || f.id}</strong>
                                        <div style={{ fontSize: 12, color: 'var(--text-sub)', marginTop: 2 }}>
                                            成员:{f.member_count || 0} · 敌对:{f.enemies || 0} · 联盟:{f.allies || 0}
                                        </div>
                                    </div>
                                )) : (
                                    <div className="empty-state compact">暂无势力数据</div>
                                )}
                            </article>
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                            <article className="card" style={{ height: '100%' }}>
                                <div className="card-header">
                                    <div className="section-label">FACTION GRAPH</div>
                                    <div className="card-title">势力关系图</div>
                                    <Badge tone="purple">{factionGraphData.nodes.length} 节点 · {factionGraphData.links.length} 关系</Badge>
                                </div>
                                {factionGraphData.nodes.length ? (
                                    <ChartWrapper
                                        className="tall"
                                        height={380}
                                        option={buildFactionGraphOption(factionGraphData)}
                                    />
                                ) : (
                                    <div className="empty-state" style={{ height: 380 }}>
                                        <p>暂无势力关系数据</p>
                                    </div>
                                )}
                            </article>
                        </div>
                    </div>
                    {factionMatrixData.factionNames.length > 1 && (
                        <article className="card">
                            <div className="card-header">
                                <div className="section-label">RELATIONSHIP MATRIX</div>
                                <div className="card-title">势力关系矩阵</div>
                            </div>
                            <div className="table-wrap" style={{ overflow: 'auto', maxHeight: 400 }}>
                                <table className="data-table">
                                    <thead>
                                        <tr>
                                            <th style={{ position: 'sticky', left: 0, background: 'var(--bg-main)' }}></th>
                                            {factionMatrixData.factionNames.map((name, i) => (
                                                <th key={i}>{name}</th>
                                            ))}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {factionMatrixData.matrix.map((row, ri) => (
                                            <tr key={ri}>
                                                <td style={{ fontWeight: 700, position: 'sticky', left: 0, background: 'var(--bg-main)' }}>
                                                    {factionMatrixData.factionNames[ri]}
                                                </td>
                                                {row.map((cell, ci) => (
                                                    <td key={ci} style={{
                                                        color: MATRIX_TYPE_COLORS[cell] || 'var(--text-sub)',
                                                        fontWeight: cell === '敌对' || cell === '同盟' ? 700 : 400,
                                                        textAlign: 'center',
                                                    }}>
                                                        {cell}
                                                    </td>
                                                ))}
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </article>
                    )}
                </div>
            ) : tab === 'plans' ? (
                <article className="card">
                    <div className="card-header">
                        <div className="section-label">CHARACTER PLANS</div>
                        <div className="card-title">角色计划</div>
                        <Badge tone="yellow">事件驱动 · 逾期预警</Badge>
                    </div>

                    {/* Filter bar */}
                    <div style={{ display: 'flex', gap: 8, padding: '12px 16px', flexWrap: 'wrap' }}>
                        {['all', 'pending', 'in_progress', 'resolved', 'abandoned'].map(s => (
                            <button
                                key={s}
                                className={`page-btn ${eventsFilter === s ? 'active' : ''}`.trim()}
                                onClick={() => setEventsFilter(s)}
                            >
                                {s === 'all' ? '全部' : s === 'pending' ? '待执行' : s === 'in_progress' ? '进行中' : s === 'resolved' ? '已完成' : '已放弃'}
                            </button>
                        ))}
                        <button className="page-btn" onClick={() => setShowCreateModal(true)}>+ 新建事件</button>
                    </div>

                    {!selected ? (
                        <div className="empty-state">请先选择一个角色</div>
                    ) : (
                        <>
                            {/* Event list */}
                            <DataTable
                                columns={[
                                    { key: 'event_type', label: '类型', render: r => EVENT_TYPE_LABELS[r.event_type] || r.event_type },
                                    { key: 'description', label: '描述' },
                                    { key: 'urgency', label: '紧急度', render: r => '🔥'.repeat(Math.min(r.urgency || 0, 5)) },
                                    { key: 'status', label: '状态', render: r => STATUS_LABELS[r.status] || r.status },
                                    { key: 'target_chapter', label: '目标章', render: r => r.target_chapter ? `第${r.target_chapter}章` : '—' },
                                ]}
                                rows={filteredEvents}
                                rowKey={r => r.id}
                                pageSize={8}
                                emptyText="暂无角色计划"
                            />

                            {/* Gantt chart */}
                            {filteredEvents.some(e => Number(e.target_chapter) > 0) && (
                                <ChartWrapper height={300} option={buildGanttOption(filteredEvents, latestChapter)} />
                            )}

                            {/* Overdue alerts */}
                            {overdueEvents.length > 0 && (
                                <div style={{ background: 'var(--error-bg)', padding: 12, margin: 12, borderRadius: 8 }}>
                                    <strong>⚠️ 超期预警</strong> ({overdueEvents.length} 项计划已超期)
                                    {overdueEvents.map(e => (
                                        <div key={e.id} style={{ margin: '4px 0', fontSize: 13 }}>
                                            • {e.description} (目标第{e.target_chapter}章, 当前第{latestChapter}章)
                                        </div>
                                    ))}
                                </div>
                            )}
                        </>
                    )}
                </article>
            ) : null}

            {/* Create Event Modal */}
            {showCreateModal && (
                <div style={{
                    position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
                    background: 'rgba(0,0,0,0.5)', display: 'flex',
                    alignItems: 'center', justifyContent: 'center', zIndex: 1000,
                }} onClick={() => setShowCreateModal(false)}>
                    <article className="card" style={{ width: 480, maxWidth: '90vw' }} onClick={e => e.stopPropagation()}>
                        <div className="card-header">
                            <div className="section-label">NEW EVENT</div>
                            <div className="card-title">新建角色计划</div>
                            <Badge tone="yellow">{selected?.canonical_name || '未选择'}</Badge>
                        </div>
                        <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
                            <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 13 }}>
                                事件类型
                                <select value={newEvent.event_type}
                                    onChange={e => setNewEvent(prev => ({ ...prev, event_type: e.target.value }))}
                                    style={{ padding: '6px 8px', border: '1px solid var(--border-color)', borderRadius: 4 }}>
                                    {Object.entries(EVENT_TYPE_LABELS).map(([k, v]) => (
                                        <option key={k} value={k}>{v}</option>
                                    ))}
                                </select>
                            </label>
                            <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 13 }}>
                                描述
                                <textarea value={newEvent.description}
                                    onChange={e => setNewEvent(prev => ({ ...prev, description: e.target.value }))}
                                    rows={3} style={{ padding: '6px 8px', border: '1px solid var(--border-color)', borderRadius: 4, resize: 'vertical' }} />
                            </label>
                            <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 13 }}>
                                紧急度 (1-10)
                                <input type="number" min="1" max="10" value={newEvent.urgency}
                                    onChange={e => setNewEvent(prev => ({ ...prev, urgency: e.target.value }))}
                                    style={{ padding: '6px 8px', border: '1px solid var(--border-color)', borderRadius: 4 }} />
                            </label>
                            <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 13 }}>
                                目标章节 (可选)
                                <input type="number" min="1" value={newEvent.target_chapter}
                                    onChange={e => setNewEvent(prev => ({ ...prev, target_chapter: e.target.value }))}
                                    style={{ padding: '6px 8px', border: '1px solid var(--border-color)', borderRadius: 4 }} />
                            </label>
                            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 8 }}>
                                <button className="page-btn" onClick={() => setShowCreateModal(false)}>取消</button>
                                <button className="page-btn active" onClick={handleCreateEvent}>创建</button>
                            </div>
                        </div>
                    </article>
                </div>
            )}
        </section>
    )
}
