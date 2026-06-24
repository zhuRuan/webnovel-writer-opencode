const BASE = ''

export async function fetchJSON(path, params = {}) {
    const url = new URL(`${BASE}${path}`, window.location.origin)
    for (const [key, value] of Object.entries(params)) {
        if (value !== undefined && value !== null && value !== '') {
            url.searchParams.set(key, value)
        }
    }

    const response = await fetch(url.toString())
    if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`)
    }
    return response.json()
}

export function fetchProjectInfo() {
    return fetchJSON('/api/project/info')
}

export function fetchProjects() {
    return fetchJSON('/api/projects')
}

export function switchProject(path) {
    return apiPost('/api/projects/switch', { path })
}

export function fetchStoryRuntimeHealth() {
    return fetchJSON('/api/story-runtime/health')
}

export function fetchChapterTrend(params = {}) {
    return fetchJSON('/api/stats/chapter-trend', params)
}

export function fetchChapters(params = {}) {
    return fetchJSON('/api/chapters', params)
}

export function fetchChapterContent(chapterId) {
    return fetchJSON(`/api/chapters/${chapterId}/content`)
}

export function fetchEntities(params = {}) {
    return fetchJSON('/api/entities', params)
}

export function fetchStateChanges(params = {}) {
    return fetchJSON('/api/state-changes', params)
}

export function fetchRelationships(params = {}) {
    return fetchJSON('/api/relationships', params)
}

export function fetchRelationshipEvents(params = {}) {
    return fetchJSON('/api/relationship-events', params)
}

export function fetchCommits(params = {}) {
    return fetchJSON('/api/commits', params)
}

export function fetchContractsSummary() {
    return fetchJSON('/api/contracts/summary')
}

export function fetchEnvStatus() {
    return fetchJSON('/api/env-status')
}

export function probeEnvStatus() {
    return fetchJSON('/api/env-status/probe')
}

export function fetchFilesTree() {
    return fetchJSON('/api/files/tree')
}

export function fetchFileContent(path) {
    return fetchJSON('/api/files/read', { path })
}

export function saveFileContent(path, content) {
    return apiPut('/api/files/write', { path, content })
}

// --- 写入 helper ---

export async function apiPost(path, body = {}) {
    const response = await fetch(`${BASE}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    })
    if (!response.ok) {
        const err = await response.json().catch(() => ({}))
        throw new Error(err.detail || `${response.status} ${response.statusText}`)
    }
    return response.json()
}

export async function apiPut(path, body = {}) {
    const response = await fetch(`${BASE}${path}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    })
    if (!response.ok) {
        const err = await response.json().catch(() => ({}))
        throw new Error(err.detail || `${response.status} ${response.statusText}`)
    }
    return response.json()
}

export async function apiDelete(path) {
    const response = await fetch(`${BASE}${path}`, { method: 'DELETE' })
    if (!response.ok) {
        const err = await response.json().catch(() => ({}))
        throw new Error(err.detail || `${response.status} ${response.statusText}`)
    }
    return response.json()
}

// --- 文风 API ---

export function fetchMasterSetting() {
    return fetchJSON('/api/style/master-setting')
}

export function updateMasterSetting(masterConstraints) {
    return apiPut('/api/style/master-setting', { master_constraints: masterConstraints })
}

export function fetchAntiPatterns() {
    return fetchJSON('/api/style/anti-patterns')
}

export function addAntiPattern(text) {
    return apiPost('/api/style/anti-patterns', { text })
}

export function deleteAntiPattern(text) {
    return apiDelete(`/api/style/anti-patterns?text=${encodeURIComponent(text)}`)
}

// --- 写作技法 CRUD ---

export function createTechnique(data) {
    return apiPost('/api/techniques', data)
}

export function updateTechnique(id, data) {
    return apiPut(`/api/techniques/${id}`, data)
}

export function deleteTechnique(id) {
    return apiDelete(`/api/techniques/${id}`)
}

export function fetchChapterContracts() {
    return fetchJSON('/api/style/chapters')
}

export function fetchChapterContract(chapter) {
    return fetchJSON(`/api/style/chapters/${chapter}`)
}

export function fetchReviewerChecklist() {
    return fetchJSON('/api/style/reviewer-checklist')
}

export function fetchPrompts() {
    return fetchJSON('/api/style/prompts')
}

export function createPrompt(name, content) {
    return apiPost('/api/style/prompts', { name, content })
}

export function updatePrompt(filename, content) {
    return apiPut(`/api/style/prompts/${encodeURIComponent(filename)}`, { content })
}

export function deletePrompt(filename) {
    return apiDelete(`/api/style/prompts/${encodeURIComponent(filename)}`)
}

// --- 导演文风规则 (director_style DB) ---

export function fetchDirectorStyles() {
    return fetchJSON('/api/director/styles')
}

export function toggleDirectorStyle(styleId, isActive) {
    return apiPost(`/api/director/styles/${styleId}/toggle`, { is_active: isActive })
}

export function upsertDirectorStyle(data) {
    return apiPost('/api/director/styles', data)
}

// --- 名家技法采集 CRUD ---

export function updateCollectedChapter(chapterId, data) {
    return apiPut(`/api/collect/chapters/${chapterId}`, data)
}

export function retryAnalyzeChapter(chapterId) {
    return apiPost(`/api/collect/chapters/${chapterId}/retry`)
}

export function deleteCollectedChapter(chapterId) {
    return apiDelete(`/api/collect/chapters/${chapterId}`)
}

export function deleteCollectedChaptersBatch(author) {
    return apiPost('/api/collect/chapters/delete-batch', { author })
}

export function deleteStyleSummary(summaryId) {
    return apiDelete(`/api/collect/summaries/${summaryId}`)
}

export function deleteCollectionReport(reportId) {
    return apiDelete(`/api/collect/reports/${reportId}`)
}

export function deleteFailedCollectionReports() {
    return apiDelete('/api/collect/reports/batch/failed')
}

export function retryStyleSummary(summaryId) {
    return apiPost(`/api/collect/summaries/${summaryId}/retry`)
}

export function reanalyzeAuthorChapters(author, data = {}) {
    return apiPost(`/api/collect/authors/${encodeURIComponent(author)}/reanalyze`, data)
}

// --- 章节文风总结 ---

export function summarizeChapterStyle(chapter) {
    return apiPost('/api/style/summarize-chapter', { chapter })
}

export function fetchContextHealth(chapter) {
    return fetchJSON(`/api/context/health/${chapter}`)
}

export function fetchContextHistory(limit = 20) {
    return fetchJSON('/api/context/history', { limit })
}

export function fetchEntityTimeline(entityId) {
    return fetchJSON(`/api/entities/${encodeURIComponent(entityId)}/timeline`)
}

export function fetchConsistencyAnomalies(chapter) {
    const params = chapter ? { chapter } : {}
    return fetchJSON('/api/consistency/anomalies', params)
}

export function fetchReviewAnalytics(limit = 50) {
    return fetchJSON('/api/review/analytics', { limit })
}

export async function fetchReviewReports() {
    const res = await fetch('/api/review-reports')
    return res.json()
}

export async function fetchReviewReport(chapter) {
    const res = await fetch(`/api/review-report?chapter=${chapter}`)
    if (!res.ok) throw new Error('not found')
    return res.json()
}

export function fetchForeshadowingReminders(threshold = 5) {
    return fetchJSON('/api/foreshadowing/reminders', { threshold })
}

export function runBatchAction(action, chapters, confirm = false) {
    return apiPost(`/api/batch/${action}`, { chapters, confirm })
}

export function fetchActorKnowledge(actorId) {
    const params = actorId ? { actor_id: actorId } : {}
    return fetchJSON('/api/theater/knowledge', params)
}

export function fetchSkillsCatalog() {
    return fetchJSON('/api/skills/catalog')
}

export function fetchActorSkills(actorId) {
    return fetchJSON(`/api/skills/actor/${encodeURIComponent(actorId)}`)
}

// --- PATCH helper ---

export async function apiPatch(path, body = {}) {
    const response = await fetch(`${BASE}${path}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    })
    if (!response.ok) {
        const err = await response.json().catch(() => ({}))
        throw new Error(err.detail || `${response.status} ${response.statusText}`)
    }
    return response.json()
}

// --- Character Events ---

export function fetchCharacterEvents(actorId, status) {
    const params = {}
    if (actorId) params.actor_id = actorId
    if (status) params.status = status
    return fetchJSON('/api/character-events', params)
}

export function fetchOverdueEvents(currentChapter) {
    return fetchJSON('/api/character-events', { overdue: true, current_chapter: currentChapter })
}

export function createCharacterEvent(data) {
    return apiPost('/api/character-events', data)
}

export function updateCharacterEvent(id, data) {
    return apiPut(`/api/character-events/${id}`, data)
}

export function deleteCharacterEvent(id) {
    return apiDelete(`/api/character-events/${id}`)
}

export function resolveCharacterEvent(id, chapter) {
    const params = chapter ? { chapter } : {}
    return apiPatch(`/api/character-events/${id}/resolve`, params)
}

// --- Factions ---

export function fetchFactions() {
    return fetchJSON('/api/factions')
}

export function fetchFactionDetail(id) {
    return fetchJSON(`/api/factions/${id}`)
}

// --- Normalize ---

export function normalizeFile(path) {
    return apiPost('/api/files/normalize', { path })
}

// --- Entity Knowledge ---

export function fetchEntityKnowledge(entityId) {
    return fetchJSON(`/api/entities/${encodeURIComponent(entityId)}/knowledge`)
}

export async function fetchMemories(actorId, type, limit = 20) {
    const params = new URLSearchParams({ actor_id: actorId, limit: String(limit) })
    if (type) params.set('memory_type', type)
    const res = await fetch(`/api/memories?${params}`)
    return res.json()
}

export function subscribeSSE(onMessage, handlers = {}) {
    const { onOpen, onError } = handlers
    const eventSource = new EventSource(`${BASE}/api/events`)

    eventSource.onopen = () => {
        if (onOpen) onOpen()
    }

    eventSource.onmessage = event => {
        try {
            onMessage(JSON.parse(event.data))
        } catch { /* ignore non-JSON messages */ }
    }

    eventSource.onerror = error => {
        if (onError) onError(error)
    }

    return () => eventSource.close()
}
