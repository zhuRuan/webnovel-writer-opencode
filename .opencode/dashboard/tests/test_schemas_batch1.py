"""Test batch 1 Pydantic schemas — project / entities / chapters / contracts."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

# 确保 .opencode/ 在 sys.path 上（与 conftest.py 相同逻辑）
_opencode_dir = Path(__file__).resolve().parents[2]
if str(_opencode_dir) not in sys.path:
    sys.path.insert(0, str(_opencode_dir))

from dashboard.schemas.project import ProjectInfo, StoryRuntimeHealth
from dashboard.schemas.entities import EntityFilter, EntityResponse, EntityKnowledge, EntityTimeline
from dashboard.schemas.chapters import ChapterList, ChapterSearch, ChapterContractResponse
from dashboard.schemas.contracts import ContractSummary, ContractsListResponse


# ========================================================================
# ProjectInfo
# ========================================================================

class TestProjectInfo:
    def test_empty_dict(self):
        """extra=allow 允许空输入。"""
        obj = ProjectInfo()
        assert obj.project_info is None
        assert obj.progress is None
        assert obj.strand_tracker is None

    def test_with_project_info(self):
        obj = ProjectInfo(project_info={"title": "foo", "author": "bar"})
        assert obj.project_info["title"] == "foo"

    def test_extra_fields_allowed(self):
        """extra=allow 应忽略未声明字段。"""
        obj = ProjectInfo(unknown_field=42, progress={"current_chapter": 5})
        assert obj.progress["current_chapter"] == 5
        # 未声明字段不会在 model_dump 中出现
        dumped = obj.model_dump(exclude_unset=True)
        assert "progress" in dumped

    def test_broad_acceptance(self):
        """state.json 可能包含任意嵌套，extra=allow 确保不拒绝。"""
        obj = ProjectInfo(**{
            "project_info": {"title": "测试", "author": "作者", "version": 2},
            "progress": {"current_chapter": 12, "current_volume": 1},
            "strand_tracker": {"history": []},
            "extra_key": "should_be_ignored",
        })
        assert obj.project_info["title"] == "测试"


# ========================================================================
# StoryRuntimeHealth
# ========================================================================

class TestStoryRuntimeHealth:
    def test_defaults(self):
        obj = StoryRuntimeHealth()
        assert obj.chapter == 0
        assert obj.mainline_ready is False
        assert obj.fallback_sources == []
        assert obj.latest_commit_status == "missing"
        assert obj.primary_write_source == "chapter_commit"
        assert obj.display_text is None

    def test_valid_full(self):
        obj = StoryRuntimeHealth(
            chapter=5,
            mainline_ready=True,
            fallback_sources=["source_a"],
            latest_commit_status="draft",
            primary_write_source="chapter_commit",
            display_text="第5章",
        )
        assert obj.chapter == 5
        assert obj.display_text == "第5章"

    def test_invalid_chapter_type(self):
        with pytest.raises(ValidationError):
            StoryRuntimeHealth(chapter="abc")

    def test_invalid_mainline_ready_type(self):
        with pytest.raises(ValidationError):
            StoryRuntimeHealth(mainline_ready=[1, 2, 3])


# ========================================================================
# EntityFilter
# ========================================================================

class TestEntityFilter:
    def test_defaults(self):
        obj = EntityFilter()
        assert obj.entity_type is None
        assert obj.include_archived is False

    def test_with_type_and_archived(self):
        obj = EntityFilter(type="character", include_archived=True)  # noqa
        assert obj.entity_type == "character"
        assert obj.include_archived is True

    def test_invalid_include_archived(self):
        with pytest.raises(ValidationError):
            EntityFilter(include_archived=[1, 2, 3])


# ========================================================================
# EntityResponse
# ========================================================================

class TestEntityResponse:
    def test_minimal(self):
        obj = EntityResponse(id="e1", type="character")
        assert obj.id == "e1"
        assert obj.type == "character"

    def test_full(self):
        obj = EntityResponse(
            id="e2",
            type="faction",
            canonical_name="测试势力",
            tier="天",
            desc="描述文本",
            current_json={"key": "val"},
            first_appearance=1,
            last_appearance=5,
            is_protagonist=False,
            is_archived=False,
        )
        assert obj.canonical_name == "测试势力"
        assert obj.current_json == {"key": "val"}

    def test_missing_id_raises(self):
        with pytest.raises(ValidationError):
            EntityResponse(type="character")

    def test_missing_type_raises(self):
        with pytest.raises(ValidationError):
            EntityResponse(id="e3")

    def test_extra_fields_allowed(self):
        """theater actor 扩展字段不应被拒绝。"""
        obj = EntityResponse(id="e4", type="character", extra_field="hello")
        assert obj.id == "e4"


# ========================================================================
# EntityKnowledge
# ========================================================================

class TestEntityKnowledge:
    def test_defaults(self):
        obj = EntityKnowledge()
        assert obj.id is None
        assert obj.source == "entity_only"
        assert obj.traits == []
        assert obj.known_domains == {}
        assert obj.skills == []

    def test_valid_full(self):
        obj = EntityKnowledge(
            id="e5",
            canonical_name="角色名",
            source="theater",
            core_desire="变强",
            traits=["勇敢", "智慧"],
            known_domains={"修仙": 0.8, "炼丹": 0.5},
            skills=[{"name": "火球术", "level": 3}],
        )
        assert obj.core_desire == "变强"
        assert len(obj.skills) == 1

    def test_invalid_traits_type(self):
        with pytest.raises(ValidationError):
            EntityKnowledge(traits="not_a_list")

    def test_extra_fields_allowed(self):
        obj = EntityKnowledge(unknown_extra=123)
        # extra=allow 不会报错
        assert True

    def test_invalid_known_domains_type(self):
        with pytest.raises(ValidationError):
            EntityKnowledge(known_domains="not_a_dict")


# ========================================================================
# EntityTimeline
# ========================================================================

class TestEntityTimeline:
    def test_defaults(self):
        obj = EntityTimeline()
        assert obj.changes == []
        assert obj.appearances == []

    def test_with_data(self):
        obj = EntityTimeline(
            state_changes=[{"field": "level", "new_value": "5", "chapter": 3}],
            appearances=[{"chapter": 3, "location": "城镇"}],
        )
        assert len(obj.changes) == 1
        assert len(obj.appearances) == 1
        assert obj.changes[0]["field"] == "level"

    def test_invalid_changes_type(self):
        with pytest.raises(ValidationError):
            EntityTimeline(changes="not_a_list")

    def test_invalid_appearances_type(self):
        with pytest.raises(ValidationError):
            EntityTimeline(appearances="not_a_list")


# ========================================================================
# ChapterList
# ========================================================================

class TestChapterList:
    def test_minimal(self):
        obj = ChapterList(chapter=1)
        assert obj.chapter == 1
        assert obj.title is None
        assert obj.word_count == 0
        assert obj.characters == []

    def test_full(self):
        obj = ChapterList(
            chapter=5,
            title="第五章",
            content="正文内容",
            word_count=1200,
            characters=["甲", "乙"],
        )
        assert obj.title == "第五章"
        assert obj.characters == ["甲", "乙"]

    def test_missing_chapter_raises(self):
        with pytest.raises(ValidationError):
            ChapterList()

    def test_invalid_chapter_type(self):
        with pytest.raises(ValidationError):
            ChapterList(chapter="abc")

    def test_invalid_word_count_type(self):
        with pytest.raises(ValidationError):
            ChapterList(chapter=1, word_count="很多")


# ========================================================================
# ChapterSearch
# ========================================================================

class TestChapterSearch:
    def test_valid_minimal(self):
        obj = ChapterSearch(query="keyword")
        assert obj.query == "keyword"
        assert obj.exclude == 0
        assert obj.limit == 5

    def test_valid_full(self):
        obj = ChapterSearch(query="测试", exclude=10, limit=20)
        assert obj.query == "测试"
        assert obj.exclude == 10
        assert obj.limit == 20

    def test_empty_query_raises(self):
        with pytest.raises(ValidationError):
            ChapterSearch(query="")

    def test_negative_exclude_raises(self):
        with pytest.raises(ValidationError):
            ChapterSearch(query="ok", exclude=-1)

    def test_limit_too_low_raises(self):
        with pytest.raises(ValidationError):
            ChapterSearch(query="ok", limit=0)

    def test_limit_too_high_raises(self):
        with pytest.raises(ValidationError):
            ChapterSearch(query="ok", limit=100)

    def test_missing_query_raises(self):
        with pytest.raises(ValidationError):
            ChapterSearch()


# ========================================================================
# ChapterContractResponse
# ========================================================================

class TestChapterContractResponse:
    def test_minimal(self):
        obj = ChapterContractResponse(chapter=3)
        assert obj.chapter == 3
        assert obj.has_volume_contract is False
        assert obj.has_commit is False

    def test_full(self):
        obj = ChapterContractResponse(
            chapter=5,
            has_volume_contract=True,
            has_chapter_contract=True,
            has_review=True,
            has_commit=False,
        )
        assert obj.has_review is True
        assert obj.has_commit is False

    def test_missing_chapter_raises(self):
        with pytest.raises(ValidationError):
            ChapterContractResponse()

    def test_invalid_chapter_type(self):
        with pytest.raises(ValidationError):
            ChapterContractResponse(chapter="abc")


# ========================================================================
# ContractSummary
# ========================================================================

class TestContractSummary:
    def test_defaults(self):
        obj = ContractSummary(chapter=0, current_volume=0)
        assert obj.chapter == 0
        assert obj.current_volume == 0
        assert obj.master.exists is False
        assert obj.master.primary_genre == ""
        assert obj.counts.volumes == 0
        assert obj.current_contracts.volume is False

    def test_valid_full(self):
        obj = ContractSummary(
            chapter=10,
            current_volume=2,
            master={"exists": True, "primary_genre": "玄幻", "core_tone": "热血"},
            counts={"volumes": 5, "chapters": 42, "reviews": 8, "commits": 40},
            current_contracts={"volume": True, "chapter": True, "review": True, "commit": True},
        )
        assert obj.master.primary_genre == "玄幻"
        assert obj.counts.chapters == 42
        assert obj.current_contracts.commit is True

    def test_missing_chapter_raises(self):
        with pytest.raises(ValidationError):
            ContractSummary()

    def test_invalid_chapter_type(self):
        with pytest.raises(ValidationError):
            ContractSummary(chapter="abc", current_volume=1)


# ========================================================================
# ContractsListResponse
# ========================================================================

class TestContractsListResponse:
    def test_defaults(self):
        obj = ContractsListResponse()
        assert obj.summary is None
        assert obj.items == []

    def test_with_summary(self):
        summary = ContractSummary(chapter=3, current_volume=1)
        obj = ContractsListResponse(summary=summary, items=[{"a": 1}])
        assert obj.summary is not None
        assert obj.summary.chapter == 3
        assert obj.items == [{"a": 1}]

    def test_invalid_summary_type(self):
        with pytest.raises(ValidationError):
            ContractsListResponse(summary="not_a_summary")
