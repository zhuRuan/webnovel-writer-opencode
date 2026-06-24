# Character Gallery API Specification

> New endpoints for character event tracking, faction management, file path normalization, character memory, and character state.
> All endpoints are prefixed with `/api`.

---

## 1. Character Events

### 1.1 GET /api/character-events

List character events with optional filters.

**Query Parameters**

| Param     | Type   | Required | Description                                      |
|-----------|--------|----------|--------------------------------------------------|
| actor_id  | string | No       | Filter by actor entity ID                        |
| status    | string | No       | Filter by status: `pending`, `in_progress`, `resolved`, `abandoned` |
| overdue   | bool   | No       | If true, return only events past their target_chapter |

**Response** `200 OK`

```json
{
  "events": [
    {
      "id": "evt_abc123",
      "actor_id": "actor_x",
      "event_type": "need_to_do",
      "description": "Find the lost artifact in the Shadow Valley",
      "source_chapter": "ch_012",
      "target_chapter": "ch_020",
      "urgency": 7,
      "status": "pending",
      "prerequisites": ["evt_def456"],
      "trigger_condition": "When the party reaches the valley entrance",
      "created_at": "2026-06-17T10:00:00Z",
      "updated_at": "2026-06-17T10:00:00Z"
    }
  ],
  "total": 1
}
```

---

### 1.2 POST /api/character-events

Create a new character event.

**Request Body** (JSON)

| Field            | Type   | Required | Description                                      |
|------------------|--------|----------|--------------------------------------------------|
| actor_id         | string | Yes      | Actor entity ID                                  |
| event_type       | string | Yes      | One of: `need_to_do`, `want_to_do`, `planned`, `promise`, `prerequisite` |
| description      | string | Yes      | Human-readable description of the event          |
| source_chapter   | string | Yes      | Chapter where this event originates              |
| target_chapter   | string | No       | Chapter by which this should be resolved         |
| urgency          | int    | No       | Priority 1-10 (default: 5)                       |
| prerequisites    | array  | No       | JSON array of prerequisite event IDs             |
| trigger_condition| string | No       | Narrative condition that triggers this event     |

**Example Request**

```json
{
  "actor_id": "actor_x",
  "event_type": "need_to_do",
  "description": "Find the lost artifact in the Shadow Valley",
  "source_chapter": "ch_012",
  "target_chapter": "ch_020",
  "urgency": 7,
  "prerequisites": ["evt_def456"],
  "trigger_condition": "When the party reaches the valley entrance"
}
```

**Response** `201 Created`

```json
{
  "id": "evt_abc123",
  "actor_id": "actor_x",
  "event_type": "need_to_do",
  "description": "Find the lost artifact in the Shadow Valley",
  "source_chapter": "ch_012",
  "target_chapter": "ch_020",
  "urgency": 7,
  "status": "pending",
  "prerequisites": ["evt_def456"],
  "trigger_condition": "When the party reaches the valley entrance",
  "created_at": "2026-06-17T10:00:00Z",
  "updated_at": "2026-06-17T10:00:00Z"
}
```

**Error Codes**

| Code   | Meaning                        |
|--------|--------------------------------|
| 400    | Missing required field or invalid event_type |
| 404    | actor_id not found             |

---

### 1.3 PUT /api/character-events/{event_id}

Update an existing character event. Only provided fields are updated.

**Path Parameters**

| Param    | Type   | Description    |
|----------|--------|----------------|
| event_id | string | Event ID       |

**Request Body** (JSON, all fields optional)

| Field          | Type   | Description                              |
|----------------|--------|------------------------------------------|
| status         | string | New status                               |
| urgency        | int    | New urgency (1-10)                       |
| description    | string | Updated description                      |
| target_chapter | string | Updated target chapter                   |

**Response** `200 OK`

```json
{
  "id": "evt_abc123",
  "actor_id": "actor_x",
  "event_type": "need_to_do",
  "description": "Find the lost artifact in the Shadow Valley",
  "source_chapter": "ch_012",
  "target_chapter": "ch_025",
  "urgency": 9,
  "status": "in_progress",
  "prerequisites": ["evt_def456"],
  "trigger_condition": "When the party reaches the valley entrance",
  "created_at": "2026-06-17T10:00:00Z",
  "updated_at": "2026-06-17T11:00:00Z"
}
```

**Error Codes**

| Code   | Meaning          |
|--------|------------------|
| 400    | Invalid field value |
| 404    | Event not found  |

---

### 1.4 DELETE /api/character-events/{event_id}

Delete a character event.

**Path Parameters**

| Param    | Type   | Description    |
|----------|--------|----------------|
| event_id | string | Event ID       |

**Response** `200 OK`

```json
{
  "ok": true
}
```

**Error Codes**

| Code   | Meaning          |
|--------|------------------|
| 404    | Event not found  |

---

### 1.5 PATCH /api/character-events/{event_id}/resolve

Mark an event as resolved. Automatically sets `status` to `resolved` and records the resolving chapter.

**Path Parameters**

| Param    | Type   | Description    |
|----------|--------|----------------|
| event_id | string | Event ID       |

**Query Parameters**

| Param   | Type   | Required | Description                              |
|---------|--------|----------|------------------------------------------|
| chapter | string | No       | Chapter where resolution occurs (defaults to current chapter) |

**Response** `200 OK`

```json
{
  "id": "evt_abc123",
  "actor_id": "actor_x",
  "event_type": "need_to_do",
  "description": "Find the lost artifact in the Shadow Valley",
  "source_chapter": "ch_012",
  "target_chapter": "ch_025",
  "urgency": 9,
  "status": "resolved",
  "resolved_chapter": "ch_018",
  "prerequisites": ["evt_def456"],
  "trigger_condition": "When the party reaches the valley entrance",
  "created_at": "2026-06-17T10:00:00Z",
  "updated_at": "2026-06-17T12:00:00Z"
}
```

**Error Codes**

| Code   | Meaning          |
|--------|------------------|
| 404    | Event not found  |

---

## 2. Factions

### 2.1 GET /api/factions

List all factions with summary information.

**Response** `200 OK`

```json
{
  "factions": [
    {
      "id": "faction_001",
      "name": "Shadow Guild",
      "type": "organization",
      "member_count": 12,
      "enemies": ["faction_002"],
      "allies": ["faction_003"],
      "first_appearance": "ch_003",
      "last_appearance": "ch_045",
      "relationships": [
        {
          "target_id": "faction_002",
          "type": "hostile",
          "description": "Territorial dispute over the eastern trade routes"
        },
        {
          "target_id": "faction_003",
          "type": "allied",
          "description": "Mutual defense pact signed in ch_030"
        }
      ]
    }
  ]
}
```

---

### 2.2 GET /api/factions/{faction_id}

Get detailed information about a single faction, including its member list.

**Path Parameters**

| Param      | Type   | Description  |
|------------|--------|--------------|
| faction_id | string | Faction ID   |

**Response** `200 OK`

```json
{
  "id": "faction_001",
  "name": "Shadow Guild",
  "type": "organization",
  "description": "A secretive network of assassins and spies operating across the continent.",
  "headquarters": "Undercity, Sector 7",
  "founded_chapter": "ch_003",
  "member_count": 12,
  "members": [
    {
      "entity_id": "actor_x",
      "name": "Kael",
      "role": "Guild Master",
      "joined_chapter": "ch_003"
    },
    {
      "entity_id": "actor_y",
      "name": "Mira",
      "role": "Senior Operative",
      "joined_chapter": "ch_005"
    }
  ],
  "enemies": ["faction_002"],
  "allies": ["faction_003"],
  "first_appearance": "ch_003",
  "last_appearance": "ch_045",
  "relationships": [
    {
      "target_id": "faction_002",
      "type": "hostile",
      "description": "Territorial dispute over the eastern trade routes"
    }
  ]
}
```

**Error Codes**

| Code   | Meaning            |
|--------|--------------------|
| 404    | Faction not found  |

---

## 3. File Normalization

### 3.1 POST /api/files/normalize

Normalize entity file path references. Scans the given file for entity references and updates any paths that have changed (e.g., after a chapter rename or reorganization).

**Request Body** (JSON)

| Field | Type   | Required | Description                          |
|-------|--------|----------|--------------------------------------|
| path  | string | Yes      | File path relative to project root (e.g., `正文/ch_012.md`) |

**Example Request**

```json
{
  "path": "正文/ch_012.md"
}
```

**Response** `200 OK`

```json
{
  "ok": true,
  "changes": [
    {
      "entity_id": "actor_x",
      "field": "source_chapter",
      "old_value": "正文/ch_010.md",
      "new_value": "正文/ch_010-rewrite.md"
    }
  ],
  "warning": "2 entity references could not be resolved"
}
```

| Field    | Type    | Description                                          |
|----------|---------|------------------------------------------------------|
| ok       | bool    | True if normalization completed                      |
| changes  | array   | List of changes applied (empty if none)              |
| warning  | string  | Present only if some references could not be resolved |

**Error Codes**

| Code   | Meaning              |
|--------|----------------------|
| 400    | Missing `path` field |
| 404    | File not found       |

---

## 4. Character Memory

### 4.1 GET /api/memories

List character memories with optional filters.

**Query Parameters**

| Param       | Type   | Required | Description                                      |
|-------------|--------|----------|--------------------------------------------------|
| actor_id    | string | Yes      | Filter by actor entity ID                        |
| memory_type | string | No       | Filter by type: `episodic`, `semantic`, `relational`, `decision` |
| tag         | string | No       | Filter by tag (exact match on memory_tags)       |
| limit       | int    | No       | Max results to return (default: 50)              |
| offset      | int    | No       | Pagination offset (default: 0)                   |

**Response** `200 OK`

```json
{
  "memories": [
    {
      "id": 42,
      "actor_id": "actor_x",
      "memory_type": "episodic",
      "content": "林战在废墟小镇被铁牙的追捕队截住，因为赵铁山下了追捕令",
      "who": "铁牙, 赵铁山",
      "what": "被追捕队截住",
      "when_chapter": 3,
      "where_place": "废墟小镇",
      "why_reason": "赵铁山下了追捕令",
      "importance": 7.2,
      "retention": 0.85,
      "retrieval_count": 3,
      "tags": ["战斗", "铁牙", "赵铁山", "追捕"],
      "source_chapter": 3,
      "created_at": "2026-06-17T10:00:00Z"
    }
  ],
  "total": 1
}
```

---

### 4.2 GET /api/memories/{memory_id}

Get a single memory by ID with all fields.

**Path Parameters**

| Param     | Type | Description |
|-----------|------|-------------|
| memory_id | int  | Memory ID   |

**Response** `200 OK`

```json
{
  "id": 42,
  "actor_id": "actor_x",
  "memory_type": "episodic",
  "content": "林战在废墟小镇被铁牙的追捕队截住，因为赵铁山下了追捕令",
  "who": "铁牙, 赵铁山",
  "what": "被追捕队截住",
  "when_chapter": 3,
  "where_place": "废墟小镇",
  "why_reason": "赵铁山下了追捕令",
  "importance": 7.2,
  "emotional_weight": 8.0,
  "personal_relevance": 7.0,
  "novelty": 6.0,
  "consequence": 7.0,
  "retention": 0.85,
  "retrieval_count": 3,
  "tags": ["战斗", "铁牙", "赵铁山", "追捕"],
  "source_chapter": 3,
  "created_at": "2026-06-17T10:00:00Z",
  "updated_at": "2026-06-17T12:00:00Z"
}
```

**Error Codes**

| Code | Meaning          |
|------|------------------|
| 404  | Memory not found |

---

### 4.3 POST /api/memories

Create a new character memory. Importance is auto-computed if not provided.

**Request Body** (JSON)

| Field             | Type   | Required | Description                                      |
|-------------------|--------|----------|--------------------------------------------------|
| actor_id          | string | Yes      | Actor entity ID                                  |
| memory_type       | string | Yes      | One of: `episodic`, `semantic`, `relational`, `decision` |
| content           | string | Yes      | Memory content in natural language               |
| source_chapter    | int    | Yes      | Chapter where this memory originates             |
| who               | string | No       | Who was involved                                 |
| what              | string | No       | What happened                                    |
| when_chapter      | int    | No       | When it happened (chapter number)                |
| where_place       | string | No       | Where it happened                                |
| why_reason        | string | No       | Why it happened                                  |
| tags              | array  | No       | Tags for categorization (e.g. `["战斗", "铁牙"]`) |
| importance        | float  | No       | Importance 0-10 (auto-computed if omitted)       |
| emotional_weight  | float  | No       | Emotional intensity 0-10 (default: 5.0)          |
| personal_relevance| float  | No       | Relevance to character goals 0-10 (default: 5.0) |

**Importance Auto-Computation**

When `importance` is not provided, it is calculated as:

```
importance = emotional_weight × 0.4 + personal_relevance × 0.3 + novelty × 0.2 + consequence × 0.1
```

`novelty` and `consequence` default to 5.0 if not provided. `retention` is initialized to 1.0.

**Example Request**

```json
{
  "actor_id": "actor_x",
  "memory_type": "episodic",
  "content": "林战在废墟小镇被铁牙的追捕队截住，因为赵铁山下了追捕令",
  "source_chapter": 3,
  "who": "铁牙, 赵铁山",
  "what": "被追捕队截住",
  "when_chapter": 3,
  "where_place": "废墟小镇",
  "why_reason": "赵铁山下了追捕令",
  "tags": ["战斗", "铁牙", "赵铁山", "追捕"],
  "emotional_weight": 8.0,
  "personal_relevance": 7.0
}
```

**Response** `201 Created`

```json
{
  "id": 42,
  "actor_id": "actor_x",
  "memory_type": "episodic",
  "content": "林战在废墟小镇被铁牙的追捕队截住，因为赵铁山下了追捕令",
  "who": "铁牙, 赵铁山",
  "what": "被追捕队截住",
  "when_chapter": 3,
  "where_place": "废墟小镇",
  "why_reason": "赵铁山下了追捕令",
  "importance": 7.2,
  "emotional_weight": 8.0,
  "personal_relevance": 7.0,
  "novelty": 5.0,
  "consequence": 5.0,
  "retention": 1.0,
  "retrieval_count": 0,
  "tags": ["战斗", "铁牙", "赵铁山", "追捕"],
  "source_chapter": 3,
  "created_at": "2026-06-17T10:00:00Z",
  "updated_at": "2026-06-17T10:00:00Z"
}
```

**Error Codes**

| Code | Meaning                        |
|------|--------------------------------|
| 400  | Missing required field or invalid memory_type |
| 404  | actor_id not found             |

---

### 4.4 DELETE /api/memories/{memory_id}

Delete a character memory.

**Path Parameters**

| Param     | Type | Description |
|-----------|------|-------------|
| memory_id | int  | Memory ID   |

**Response** `200 OK`

```json
{
  "ok": true
}
```

**Error Codes**

| Code | Meaning          |
|------|------------------|
| 404  | Memory not found |

---

### 4.5 GET /api/memories/rag

Semantic RAG retrieval: search character memories by natural language query, ranked by hybrid score.

**Query Parameters**

| Param    | Type   | Required | Description                                      |
|----------|--------|----------|--------------------------------------------------|
| actor_id | string | Yes      | Actor entity ID                                  |
| query    | string | Yes      | Natural language search query                    |
| k        | int    | No       | Number of top results to return (default: 10)    |

**Hybrid Scoring**

Results are ranked by a weighted hybrid score:

```
hybrid_score = similarity × 0.5 + retention × 0.3 + importance × 0.2
```

- **similarity**: cosine similarity between query embedding and `memory_embeddings`
- **retention**: current retention score (Wickelgren decay applied)
- **importance**: stored importance score

Memories with `retention < 0.3` are excluded (considered "forgotten"). Each returned memory has its `retrieval_count` incremented (retrieval reinforcement).

**Response** `200 OK`

```json
{
  "memories": [
    {
      "id": 42,
      "actor_id": "actor_x",
      "memory_type": "episodic",
      "content": "林战在废墟小镇被铁牙的追捕队截住，因为赵铁山下了追捕令",
      "who": "铁牙, 赵铁山",
      "what": "被追捕队截住",
      "when_chapter": 3,
      "where_place": "废墟小镇",
      "why_reason": "赵铁山下了追捕令",
      "importance": 7.2,
      "retention": 0.85,
      "retrieval_count": 4,
      "tags": ["战斗", "铁牙", "赵铁山", "追捕"],
      "source_chapter": 3,
      "hybrid_score": 0.91
    }
  ],
  "total": 1
}
```

**Error Codes**

| Code | Meaning              |
|------|----------------------|
| 400  | Missing actor_id or query |
| 404  | actor_id not found   |

---

### 4.6 POST /api/memories/decay

Admin endpoint: recalculate retention scores for all character memories using the Wickelgren decay formula.

**No request body required.**

**Decay Formula**

```
retention = importance × e^(-λ × chapters_elapsed / memory_strength)
```

- `λ`: decay constant (default: 0.1)
- `chapters_elapsed`: current chapter minus `when_chapter`
- `memory_strength`: character's memory strength attribute (1-10, default: 5)

After decay, retrieval reinforcement is applied:

```
retention = retention × (1.2 ^ retrieval_count)
```

Memories with `retention < 0.3` are marked as forgotten.

**Response** `200 OK`

```json
{
  "updated": 142,
  "forgotten": 8
}
```

| Field     | Type | Description                                |
|-----------|------|--------------------------------------------|
| updated   | int  | Number of memories whose retention was recalculated |
| forgotten | int  | Number of memories now below the 0.3 threshold |

---

## 5. Character State

### 5.1 GET /api/state/{actor_id}

Get the current state snapshot for a character.

**Path Parameters**

| Param    | Type   | Description    |
|----------|--------|----------------|
| actor_id | string | Actor entity ID |

**Response** `200 OK`

```json
{
  "actor_id": "actor_x",
  "health": {
    "hp": 85,
    "max_hp": 100,
    "injuries": ["左臂轻度擦伤"],
    "status_effects": ["肾上腺素过量"]
  },
  "equipment": [
    {
      "name": "钛合金左臂",
      "slot": "左臂",
      "grade": "T2",
      "effects": ["力量+30%", "耐久+50%"]
    },
    {
      "name": "战术匕首",
      "slot": "副手",
      "grade": "标准",
      "effects": ["近战伤害+15"]
    }
  ],
  "inventory": [
    {
      "name": "急救包",
      "quantity": 2,
      "description": "标准军用急救包，含止血剂和绷带"
    },
    {
      "name": "能量电池",
      "quantity": 5,
      "description": "T2级通用能量电池"
    }
  ],
  "location": "废墟小镇·废弃仓库",
  "chapter": 12,
  "updated_at": "2026-06-17T14:00:00Z"
}
```

**Error Codes**

| Code | Meaning              |
|------|----------------------|
| 404  | No state recorded for this actor |

---

### 5.2 PUT /api/state/{actor_id}

Update a character's state. Only provided fields are updated; JSON fields (`health`, `equipment`, `inventory`) are merged with existing data.

**Path Parameters**

| Param    | Type   | Description    |
|----------|--------|----------------|
| actor_id | string | Actor entity ID |

**Request Body** (JSON, all fields optional except `chapter`)

| Field     | Type   | Required | Description                                      |
|-----------|--------|----------|--------------------------------------------------|
| health    | object | No       | JSON object: `{hp, max_hp, injuries, status_effects}` |
| equipment | array  | No       | JSON array of equipment objects                  |
| inventory | array  | No       | JSON array of inventory objects                  |
| location  | string | No       | Current location description                     |
| chapter   | int    | Yes      | Chapter number this update corresponds to        |

**Example Request**

```json
{
  "health": {
    "hp": 72,
    "max_hp": 100,
    "injuries": ["左臂轻度擦伤", "肋骨骨裂"],
    "status_effects": []
  },
  "location": "废墟小镇·地下通道",
  "chapter": 13
}
```

**Response** `200 OK`

```json
{
  "actor_id": "actor_x",
  "health": {
    "hp": 72,
    "max_hp": 100,
    "injuries": ["左臂轻度擦伤", "肋骨骨裂"],
    "status_effects": []
  },
  "equipment": [
    {
      "name": "钛合金左臂",
      "slot": "左臂",
      "grade": "T2",
      "effects": ["力量+30%", "耐久+50%"]
    }
  ],
  "inventory": [
    {
      "name": "急救包",
      "quantity": 2,
      "description": "标准军用急救包，含止血剂和绷带"
    }
  ],
  "location": "废墟小镇·地下通道",
  "chapter": 13,
  "updated_at": "2026-06-17T15:00:00Z"
}
```

**Error Codes**

| Code | Meaning              |
|------|----------------------|
| 400  | Missing `chapter` field |
| 404  | actor_id not found   |

---

### 5.3 GET /api/state/{actor_id}/history

Get the state change history for a character, ordered by most recent first.

**Path Parameters**

| Param    | Type   | Description    |
|----------|--------|----------------|
| actor_id | string | Actor entity ID |

**Query Parameters**

| Param       | Type   | Required | Description                                      |
|-------------|--------|----------|--------------------------------------------------|
| limit       | int    | No       | Max results to return (default: 20)              |
| change_type | string | No       | Filter by type: `health`, `equipment`, `inventory`, `location`, `description`, `trait` |

**Response** `200 OK`

```json
{
  "history": [
    {
      "change_type": "health",
      "field": "hp",
      "old_value": "85",
      "new_value": "72",
      "chapter": 13,
      "reason": "地下通道坍塌受伤",
      "created_at": "2026-06-17T15:00:00Z"
    },
    {
      "change_type": "location",
      "field": "location",
      "old_value": "废墟小镇·废弃仓库",
      "new_value": "废墟小镇·地下通道",
      "chapter": 13,
      "reason": "追击铁牙进入地下通道",
      "created_at": "2026-06-17T14:30:00Z"
    },
    {
      "change_type": "equipment",
      "field": "equipment",
      "old_value": null,
      "new_value": "获得战术匕首",
      "chapter": 10,
      "reason": "从敌人身上缴获",
      "created_at": "2026-06-17T12:00:00Z"
    }
  ],
  "total": 3
}
```

**Error Codes**

| Code | Meaning              |
|------|----------------------|
| 404  | actor_id not found   |
