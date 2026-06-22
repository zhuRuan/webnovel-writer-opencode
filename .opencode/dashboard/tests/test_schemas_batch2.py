"""批量测试第 2 批 Pydantic Schema —— memories / character_events / states。"""

from pathlib import Path
import sys

import pytest
from pydantic import ValidationError

# 确保 dashboard 包可被导入
_opencode_dir = Path(__file__).resolve().parents[2]
if str(_opencode_dir) not in sys.path:
    sys.path.insert(0, str(_opencode_dir))

from dashboard.schemas.memories import (
    MemoryCreate,
    MemoryFilter,
    MemoryResponse,
    MemoriesRAGQuery,
    MemoryDecayRequest,
)
from dashboard.schemas.character_events import (
    CharacterEventCreate,
    CharacterEventUpdate,
    CharacterEventFilter,
    CharacterEventResolve,
    CharacterEventResponse,
)
from dashboard.schemas.states import (
    StateUpsert,
    StateFilter,
    StateHistoryFilter,
    StateResponse,
)


# ============================================================
# Memories
# ============================================================

class TestMemorySchemas:
    def test_memory_create_valid(self):
        """有效数据 → MemoryCreate 构造通过，默认值生效。"""
        m = MemoryCreate(actor_id="actor_1", content="一段记忆")
        assert m.actor_id == "actor_1"
        assert m.content == "一段记忆"
        assert m.memory_type == "working"  # 默认值
        assert m.tag is None

    def test_memory_create_full(self):
        """所有字段显式传入。"""
        m = MemoryCreate(
            actor_id="actor_1", content="内容",
            memory_type="episodic", tag="important",
        )
        assert m.memory_type == "episodic"
        assert m.tag == "important"

    def test_memory_create_empty_actor_id(self):
        """空字符串 actor_id → ValidationError。"""
        with pytest.raises(ValidationError):
            MemoryCreate(actor_id="", content="内容")

    def test_memory_create_empty_content(self):
        """空字符串 content → ValidationError。"""
        with pytest.raises(ValidationError):
            MemoryCreate(actor_id="actor_1", content="")

    def test_memory_create_missing_content(self):
        """缺少必填字段 content → ValidationError。"""
        with pytest.raises(ValidationError):
            MemoryCreate(actor_id="actor_1")

    def test_memory_create_missing_actor_id(self):
        """缺少必填字段 actor_id → ValidationError。"""
        with pytest.raises(ValidationError):
            MemoryCreate(content="内容")

    def test_memory_filter_valid(self):
        """MemoryFilter 构造通过，默认值生效。"""
        f = MemoryFilter(actor_id="actor_1")
        assert f.actor_id == "actor_1"
        assert f.limit == 50
        assert f.offset == 0

    def test_memory_filter_empty_actor_id(self):
        """空字符串 actor_id → ValidationError。"""
        with pytest.raises(ValidationError):
            MemoryFilter(actor_id="")

    def test_memory_response_valid(self):
        """MemoryResponse 构造通过，默认值生效。"""
        r = MemoryResponse(
            id=1, actor_id="a1", content="c",
            memory_type="semantic", source_chapter=5,
        )
        assert r.id == 1
        assert r.decay_score == 0.0

    def test_rag_query_valid(self):
        """MemoriesRAGQuery 构造通过，k 默认 10。"""
        q = MemoriesRAGQuery(actor_id="a1", query="测试查询")
        assert q.k == 10
        assert q.query == "测试查询"

    def test_rag_query_empty_query(self):
        """空 query → ValidationError。"""
        with pytest.raises(ValidationError):
            MemoriesRAGQuery(actor_id="a1", query="")

    def test_decay_request_valid(self):
        """MemoryDecayRequest 构造通过。"""
        d = MemoryDecayRequest(current_chapter=10)
        assert d.current_chapter == 10

    def test_decay_request_zero_chapter(self):
        """current_chapter=0（ge=1）→ ValidationError。"""
        with pytest.raises(ValidationError):
            MemoryDecayRequest(current_chapter=0)

    def test_decay_request_negative(self):
        """current_chapter 负数 → ValidationError。"""
        with pytest.raises(ValidationError):
            MemoryDecayRequest(current_chapter=-1)


# ============================================================
# Character Events
# ============================================================

class TestCharacterEventSchemas:
    def test_create_valid(self):
        """有效数据 → CharacterEventCreate 构造通过，默认值生效。"""
        e = CharacterEventCreate(
            actor_id="a1", event_type="need_to_do", description="需要做某事",
        )
        assert e.actor_id == "a1"
        assert e.status == "pending"
        assert e.target_chapter is None

    def test_create_full(self):
        """所有字段显式传入。"""
        e = CharacterEventCreate(
            actor_id="a1", event_type="want_to_do",
            description="想做的事", status="in_progress", target_chapter=10,
        )
        assert e.status == "in_progress"
        assert e.target_chapter == 10

    def test_create_empty_actor_id(self):
        """空字符串 actor_id → ValidationError。"""
        with pytest.raises(ValidationError):
            CharacterEventCreate(actor_id="", event_type="need_to_do", description="desc")

    def test_create_empty_event_type(self):
        """空字符串 event_type → ValidationError。"""
        with pytest.raises(ValidationError):
            CharacterEventCreate(actor_id="a1", event_type="", description="desc")

    def test_create_empty_description(self):
        """空字符串 description → ValidationError。"""
        with pytest.raises(ValidationError):
            CharacterEventCreate(actor_id="a1", event_type="need_to_do", description="")

    def test_create_missing_event_type(self):
        """缺少必填字段 event_type → ValidationError。"""
        with pytest.raises(ValidationError):
            CharacterEventCreate(actor_id="a1", description="desc")

    def test_create_missing_description(self):
        """缺少必填字段 description → ValidationError。"""
        with pytest.raises(ValidationError):
            CharacterEventCreate(actor_id="a1", event_type="need_to_do")

    def test_update_valid(self):
        """CharacterEventUpdate 有效数据。"""
        u = CharacterEventUpdate(status="resolved", urgency=3)
        assert u.status == "resolved"
        assert u.urgency == 3

    def test_update_empty(self):
        """CharacterEventUpdate 全空 → 允许。"""
        u = CharacterEventUpdate()
        assert u.status is None

    def test_filter_valid(self):
        """CharacterEventFilter 默认值。"""
        f = CharacterEventFilter()
        assert f.overdue is False
        assert f.current_chapter == 0

    def test_filter_full(self):
        """CharacterEventFilter 所有字段。"""
        f = CharacterEventFilter(
            actor_id="a1", status="pending", overdue=True, current_chapter=5,
        )
        assert f.actor_id == "a1"
        assert f.overdue is True

    def test_resolve_valid(self):
        """CharacterEventResolve 默认 chapter=None。"""
        r = CharacterEventResolve()
        assert r.chapter is None

    def test_resolve_with_chapter(self):
        """CharacterEventResolve 传 chapter。"""
        r = CharacterEventResolve(chapter=10)
        assert r.chapter == 10

    def test_response_valid(self):
        """CharacterEventResponse 构造通过，默认值生效。"""
        r = CharacterEventResponse(
            id=1, actor_id="a1", event_type="need_to_do",
            description="desc", status="pending", source_chapter=3,
        )
        assert r.urgency == 0


# ============================================================
# States
# ============================================================

class TestStateSchemas:
    def test_upsert_valid(self):
        """StateUpsert 有效数据。"""
        s = StateUpsert(actor_id="a1", state_data={"hp": 100, "mp": 50})
        assert s.actor_id == "a1"
        assert s.state_data["hp"] == 100
        assert s.state_data["mp"] == 50

    def test_upsert_empty_state_data(self):
        """state_data 空 dict → 允许（必填校验仅要求存在，不要求非空）。"""
        s = StateUpsert(actor_id="a1", state_data={})
        assert s.state_data == {}

    def test_upsert_empty_actor_id(self):
        """空字符串 actor_id → ValidationError。"""
        with pytest.raises(ValidationError):
            StateUpsert(actor_id="", state_data={"hp": 100})

    def test_upsert_missing_state_data(self):
        """缺少必填字段 state_data → ValidationError。"""
        with pytest.raises(ValidationError):
            StateUpsert(actor_id="a1")

    def test_upsert_missing_actor_id(self):
        """缺少必填字段 actor_id → ValidationError。"""
        with pytest.raises(ValidationError):
            StateUpsert(state_data={"hp": 100})

    def test_filter_valid(self):
        """StateFilter 构造通过。"""
        f = StateFilter(actor_id="a1")
        assert f.actor_id == "a1"

    def test_filter_empty_actor_id(self):
        """空字符串 actor_id → ValidationError。"""
        with pytest.raises(ValidationError):
            StateFilter(actor_id="")

    def test_history_filter_valid(self):
        """StateHistoryFilter 显式传 change_type。"""
        f = StateHistoryFilter(change_type="battle")
        assert f.change_type == "battle"
        assert f.limit == 20

    def test_history_filter_default(self):
        """StateHistoryFilter 全默认。"""
        f = StateHistoryFilter()
        assert f.change_type is None
        assert f.limit == 20

    def test_history_filter_custom_limit(self):
        """StateHistoryFilter 自定义 limit。"""
        f = StateHistoryFilter(limit=50)
        assert f.limit == 50

    def test_response_valid(self):
        """StateResponse 构造通过。"""
        r = StateResponse(actor_id="a1", state_data={"hp": 100}, chapter=5)
        assert r.chapter == 5
        assert r.updated_at is None
