import { useEffect, useState } from 'react'
import { fetchSkillsCatalog } from '../api.js'

const LABEL_CLASS = "kb-label"
const VALUE_CLASS = "kb-value"

export default function KnowledgeBasePage() {
    const [catalog, setCatalog] = useState(null)
    const [expanded, setExpanded] = useState(new Set(['战斗']))

    useEffect(() => {
        fetchSkillsCatalog().then(setCatalog).catch(() => {})
    }, [])

    if (!catalog?.categories) return null

    const toggle = k => setExpanded(p => { const n = new Set(p); n.has(k) ? n.delete(k) : n.add(k); return n })
    const cats = catalog.categories

    return (
        <div className="kb-container">
            <div className="kb-categories">
                {Object.entries(cats).map(([catName, catData]) => (
                    <section key={catName} className="kb-cat-section">
                        <div className="kb-cat-bar" onClick={() => toggle(catName)}>
                            <span className="kb-cat-icon">{catData.icon || ''}</span>
                            <span className="kb-cat-title">{catName}</span>
                            <span className={`kb-cat-arrow ${expanded.has(catName) ? 'open' : ''}`}>▾</span>
                        </div>
                        {expanded.has(catName) && (
                            <div className="kb-cat-content">
                                {Object.entries(catData.sub || {}).map(([subName, subData]) => {
                                    const skills = Object.entries(subData.skills || {})
                                    const subKey = `${catName}/${subName}`
                                    return (
                                    <div key={subName} className="kb-sub-group">
                                        <div className="kb-sub-bar" onClick={() => toggle(subKey)}>
                                            <span className={`kb-sub-arrow ${expanded.has(subKey) ? 'open' : ''}`}>▶</span>
                                            <span className="kb-sub-title">{subName}</span>
                                            <span className="kb-sub-count">{skills.length}项</span>
                                        </div>
                                        {expanded.has(subKey) && (
                                        <div className="kb-skill-list">
                                        {skills.map(([skillName, skill]) => (
                                            <article key={skillName} className="kb-skill">
                                                <div className="kb-skill-header">
                                                    <span className="kb-skill-name">{skillName}</span>
                                                    <span className="kb-skill-desc">{skill.description}</span>
                                                </div>
                                                <div className="kb-skill-body">
                                                    {skill.techniques && <div className="kb-skill-row"><span className={LABEL_CLASS}>技法</span><span className={VALUE_CLASS}>{skill.techniques}</span></div>}
                                                    {skill.styles && <div className="kb-skill-row"><span className={LABEL_CLASS}>流派</span><span className={VALUE_CLASS}>{skill.styles}</span></div>}
                                                    {skill.features && <div className="kb-skill-row"><span className={LABEL_CLASS}>特点</span><span className={VALUE_CLASS}>{skill.features}</span></div>}
                                                    {skill.counter && <div className="kb-skill-row"><span className={LABEL_CLASS}>克制</span><span className={VALUE_CLASS}>{skill.counter}</span></div>}
                                                </div>
                                            </article>
                                        ))}
                                        </div>
                                        )}
                                    </div>
                                    )
                                })}
                            </div>
                        )}
                    </section>
                ))}
            </div>
        </div>
    )
}
