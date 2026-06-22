"""Batch 3 Schema 测试：style / techniques / director。

使用 pydantic.BaseModel 的 .model_validate() 直接验证字典，
不依赖数据库或 HTTP 服务。
"""

import re

import pytest
from pydantic import ValidationError

from dashboard.schemas.style import (
    AntiPatternCreate,
    AntiPatternResponse,
    MasterSettingResponse,
    MasterSettingUpdate,
    PromptCreate,
    PromptResponse,
    PromptUpdate,
    ReviewerChecklistResponse,
)
from dashboard.schemas.techniques import (
    TechniqueFilter,
    TechniqueGroupedResponse,
    TechniqueResponse,
    TechniqueTrack,
)
from dashboard.schemas.director import (
    DirectorStyleFilter,
    DirectorStyleUpsert,
    StylePromptResponse,
)


# ============================================================
# style.py
# ============================================================

class TestMasterSetting:
    def test_response_extra_fields_allowed(self):
        """MasterSettingResponse 应当接受额外字段。"""
        data = {
            "master_constraints": {"key": "val"},
            "override_policy": {"locked": []},
            "some_unknown_field": True,
        }
        obj = MasterSettingResponse.model_validate(data)
        assert obj.master_constraints == {"key": "val"}
        assert obj.some_unknown_field is True

    def test_response_empty_allowed(self):
        """空字典不应报错。"""
        obj = MasterSettingResponse.model_validate({})
        assert obj.master_constraints is None

    def test_update_requires_master_constraints(self):
        """master_constraints 缺失应引发 ValidationError。"""
        with pytest.raises(ValidationError):
            MasterSettingUpdate.model_validate({})

    def test_update_empty_dict_valid(self):
        """空的 dict 值应通过。"""
        obj = MasterSettingUpdate.model_validate({"master_constraints": {}})
        assert obj.master_constraints == {}


class TestAntiPattern:
    def test_create_valid(self):
        """有效 text 应通过。"""
        obj = AntiPatternCreate.model_validate({"text": "禁止使用华丽辞藻"})
        assert obj.text == "禁止使用华丽辞藻"

    def test_create_empty_text_raises(self):
        """空字符串 text 应引发 ValidationError。"""
        with pytest.raises(ValidationError):
            AntiPatternCreate.model_validate({"text": ""})

    def test_create_missing_text_raises(self):
        """缺少 text 字段应引发 ValidationError。"""
        with pytest.raises(ValidationError):
            AntiPatternCreate.model_validate({})

    def test_response_full(self):
        """完整反模式条目应通过。"""
        data = {
            "text": "禁止使用华丽辞藻",
            "source_table": "dashboard_manual",
            "source_id": "manual_1718000000",
            "added_at": "2024-06-10T12:00:00+00:00",
        }
        obj = AntiPatternResponse.model_validate(data)
        assert obj.text == "禁止使用华丽辞藻"
        assert obj.source_table == "dashboard_manual"


class TestPrompt:
    def test_create_valid(self):
        """有效 name + content 应通过。"""
        obj = PromptCreate.model_validate({"name": "test-prompt", "content": "请保持冷峻风格"})
        assert obj.name == "test-prompt"
        assert obj.content == "请保持冷峻风格"

    def test_create_missing_name_raises(self):
        """缺 name 应引发 ValidationError。"""
        with pytest.raises(ValidationError):
            PromptCreate.model_validate({"content": "请保持冷峻风格"})

    def test_create_missing_content_raises(self):
        """缺 content 应引发 ValidationError。"""
        with pytest.raises(ValidationError):
            PromptCreate.model_validate({"name": "test-prompt"})

    def test_create_empty_name_raises(self):
        """name 为空字符串应引发 ValidationError。"""
        with pytest.raises(ValidationError):
            PromptCreate.model_validate({"name": "", "content": "内容"})

    def test_update_valid(self):
        """有效 content 应通过。"""
        obj = PromptUpdate.model_validate({"content": "更新后的内容"})
        assert obj.content == "更新后的内容"

    def test_update_empty_content_raises(self):
        """content 为空字符串应引发 ValidationError。"""
        with pytest.raises(ValidationError):
            PromptUpdate.model_validate({"content": ""})

    def test_response_full(self):
        """完整提示词记录应通过。"""
        data = {"name": "test", "filename": "test.md", "content": "内容"}
        obj = PromptResponse.model_validate(data)
        assert obj.filename == "test.md"


class TestReviewerChecklist:
    def test_response_structure(self):
        """checklist 和 anti_patterns 列表应通过。"""
        data = {
            "checklist": [
                {
                    "dimension": "设定一致性",
                    "content": "角色状态与 state.json 一致",
                    "format": "[设定]: pass",
                    "must_bash": True,
                }
            ],
            "anti_patterns": [
                {
                    "text": "禁止啰嗦",
                    "source_table": "dashboard_manual",
                    "source_id": "m1",
                    "added_at": "2024-01-01",
                }
            ],
        }
        obj = ReviewerChecklistResponse.model_validate(data)
        assert len(obj.checklist) == 1
        assert obj.checklist[0]["dimension"] == "设定一致性"
        assert len(obj.anti_patterns) == 1


# ============================================================
# techniques.py
# ============================================================

class TestTechniqueFilter:
    def test_defaults(self):
        """未传任何值时所有字段应为 None/默认。"""
        obj = TechniqueFilter.model_validate({})
        assert obj.category is None
        assert obj.search is None

    def test_full(self):
        """传入全部字段应被正确解析。"""
        obj = TechniqueFilter.model_validate({"category": "对话", "search": "潜台词"})
        assert obj.category == "对话"
        assert obj.search == "潜台词"


class TestTechniqueTrack:
    def test_valid(self):
        """有效请求体应通过。"""
        obj = TechniqueTrack.model_validate(
            {"chapter": 5, "name": "潜台词", "category": "对话", "context": "第 3 段对话"}
        )
        assert obj.chapter == 5
        assert obj.name == "潜台词"
        assert obj.context == "第 3 段对话"

    def test_context_defaults_to_empty(self):
        """context 不传时默认为空字符串。"""
        obj = TechniqueTrack.model_validate({"chapter": 5, "name": "潜台词", "category": "对话"})
        assert obj.context == ""

    def test_missing_chapter_raises(self):
        """缺 chapter 应引发 ValidationError。"""
        with pytest.raises(ValidationError):
            TechniqueTrack.model_validate({"name": "潜台词", "category": "对话"})


class TestTechniqueResponse:
    def test_minimal(self):
        """最少必填字段应通过。"""
        obj = TechniqueResponse.model_validate(
            {"id": 1, "name": "潜台词", "category": "对话", "description": "示例描述"}
        )
        assert obj.id == 1
        assert obj.difficulty == 5

    def test_full(self):
        """全部字段应通过。"""
        data = {
            "id": 10,
            "name": "展示不告知",
            "category": "文笔",
            "primary_category": "文笔",
            "sub_category": "表现手法",
            "description": "用动作替代形容词",
            "when_to_use": "情感表达场景",
            "example": "✅ 他的手在抖\n❌ 他很害怕",
            "anti_pattern": "避免直白情绪词",
            "difficulty": 9,
            "created_at": "2024-01-01 00:00:00",
        }
        obj = TechniqueResponse.model_validate(data)
        assert obj.primary_category == "文笔"
        assert obj.difficulty == 9


class TestTechniqueGroupedResponse:
    def test_structure(self):
        """分组结构应通过。"""
        data = {
            "primary_category": "对话",
            "techniques": [{"id": 1, "name": "潜台词", "category": "对话", "description": "xxx"}],
            "sub_categories": ["对白", "潜台词"],
            "count": 1,
        }
        obj = TechniqueGroupedResponse.model_validate(data)
        assert obj.primary_category == "对话"
        assert obj.count == 1
        assert len(obj.techniques) == 1


# ============================================================
# director.py
# ============================================================

class TestDirectorStyleFilter:
    def test_defaults(self):
        """默认值应正确。"""
        obj = DirectorStyleFilter.model_validate({})
        assert obj.category is None
        assert obj.active_only is True

    def test_full(self):
        """传入全部字段应被正确解析。"""
        obj = DirectorStyleFilter.model_validate({"category": "叙事语调", "active_only": False})
        assert obj.category == "叙事语调"
        assert obj.active_only is False


class TestDirectorStyleUpsert:
    def test_empty_valid(self):
        """空字典应通过（所有字段可选）。"""
        obj = DirectorStyleUpsert.model_validate({})
        assert obj.id is None

    def test_full(self):
        """全部字段应通过。"""
        data = {
            "id": 1,
            "name": "冷峻克制",
            "category": "叙事语调",
            "description": "用动作表达情绪",
            "rules": '[{"rule": "test"}]',
            "priority": 9,
            "is_active": 1,
        }
        obj = DirectorStyleUpsert.model_validate(data)
        assert obj.name == "冷峻克制"
        assert obj.priority == 9

    def test_priority_out_of_range(self):
        """priority 超出 1-10 范围应引发 ValidationError。"""
        with pytest.raises(ValidationError):
            DirectorStyleUpsert.model_validate({"priority": 99})


class TestStylePromptResponse:
    def test_default(self):
        """prompt 为空字符串时默认值应正确。"""
        obj = StylePromptResponse.model_validate({})
        assert obj.prompt == ""

    def test_with_text(self):
        """有效 prompt 文本应通过。"""
        obj = StylePromptResponse.model_validate({"prompt": "## 导演文风规则\n- 冷峻克制"})
        assert "冷峻克制" in obj.prompt
