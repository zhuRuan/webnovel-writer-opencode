# -*- coding: utf-8 -*-
"""
动态词典自动触发测试
"""

import pytest
import tempfile
import time
import threading
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_modules.rag_adapter import RAGAdapter
from data_modules.config import DataModulesConfig
from data_modules.entity_linker import EntityLinker


class StubClient:
    async def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]
    async def embed_batch(self, texts, skip_failures=True):
        return [[1.0, 0.0] for _ in texts]
    async def rerank(self, query, documents, top_n=None):
        top_n = top_n or len(documents)
        return [{"index": i, "relevance_score": 1.0 / (i + 1)} for i in range(min(top_n, len(documents)))]


@pytest.fixture
def temp_project(tmp_path):
    """创建临时项目"""
    (tmp_path / "正文").mkdir()
    (tmp_path / "设定集").mkdir()
    (tmp_path / "大纲").mkdir()
    (tmp_path / ".webnovel").mkdir()
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    (tmp_path / "设定集" / "角色.md").write_text("萧炎 主角\n药老 导师", encoding="utf-8")
    (tmp_path / "大纲" / "卷纲.md").write_text("三年之约", encoding="utf-8")
    
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    return tmp_path, cfg


class TestAutoRebuildDictionary:
    """动态词典自动触发测试"""

    def test_init_auto_rebuild_when_dict_not_exists(self, temp_project):
        """初始化时词典不存在则自动重建"""
        tmp_path, cfg = temp_project
        dict_path = cfg.custom_dict_path
        
        assert not dict_path.exists(), "词典文件不应存在"
        
        with mock.patch("data_modules.rag_adapter.get_client", return_value=StubClient()):
            adapter = RAGAdapter(cfg)
        
        assert dict_path.exists(), "词典应该自动生成"
        content = dict_path.read_text(encoding="utf-8")
        assert "萧炎" in content, "词典应包含设定集中的词汇"

    def test_init_skip_rebuild_when_dict_exists(self, temp_project):
        """初始化时词典已存在则跳过"""
        tmp_path, cfg = temp_project
        dict_path = cfg.custom_dict_path
        
        dict_path.parent.mkdir(parents=True, exist_ok=True)
        dict_path.write_text("已有词典 10 n\n", encoding="utf-8")
        
        with mock.patch("data_modules.rag_adapter.get_client", return_value=StubClient()):
            adapter = RAGAdapter(cfg)
        
        content = dict_path.read_text(encoding="utf-8")
        assert "已有词典" in content, "词典内容不应被覆盖"

    def test_init_skip_when_config_disabled(self, temp_project):
        """配置关闭时初始化不重建"""
        tmp_path, cfg = temp_project
        cfg.tokenizer_auto_rebuild_on_init = False
        dict_path = cfg.custom_dict_path
        
        assert not dict_path.exists()
        
        with mock.patch("data_modules.rag_adapter.get_client", return_value=StubClient()):
            adapter = RAGAdapter(cfg)
        
        assert not dict_path.exists(), "配置关闭时不应自动重建"

    def test_entity_change_triggers_debounce(self, temp_project):
        """实体变更触发防抖"""
        tmp_path, cfg = temp_project
        
        with mock.patch("data_modules.rag_adapter.get_client", return_value=StubClient()):
            adapter = RAGAdapter(cfg)
            linker = EntityLinker(cfg, rag_adapter=adapter)
        
        assert linker._rebuild_pending is False
        
        linker.on_entity_registered("new_entity", "角色")
        
        assert linker._rebuild_pending is True
        assert linker._rebuild_timer is not None

    def test_debounce_prevents_duplicate_timers(self, temp_project):
        """防抖防止重复启动计时器"""
        tmp_path, cfg = temp_project
        cfg.tokenizer_rebuild_debounce_seconds = 1
        
        with mock.patch("data_modules.rag_adapter.get_client", return_value=StubClient()):
            adapter = RAGAdapter(cfg)
            linker = EntityLinker(cfg, rag_adapter=adapter)
        
        assert linker._rebuild_timer is None, "初始无计时器"
        
        linker.on_entity_registered("entity1", "角色")
        first_timer = linker._rebuild_timer
        
        linker.on_entity_registered("entity2", "角色")
        second_timer = linker._rebuild_timer
        
        assert first_timer is second_timer, "连续调用不应创建新计时器"

    def test_rebuild_triggered_after_timer(self, temp_project):
        """计时器触发后执行重建"""
        tmp_path, cfg = temp_project
        cfg.tokenizer_rebuild_debounce_seconds = 0.1
        
        with mock.patch("data_modules.rag_adapter.get_client", return_value=StubClient()):
            adapter = RAGAdapter(cfg)
            linker = EntityLinker(cfg, rag_adapter=adapter)
        
        linker.on_entity_registered("new_entity", "角色")
        
        time.sleep(0.2)
        
        assert linker._rebuild_pending is False, "计时器触发后应重置状态"

    def test_log_suppression_on_small_changes(self, temp_project):
        """小变化时日志抑制"""
        tmp_path, cfg = temp_project
        cfg.tokenizer_log_rebuild_summary = True
        
        with mock.patch("data_modules.rag_adapter.get_client", return_value=StubClient()):
            adapter = RAGAdapter(cfg)
            
            adapter._last_dict_word_count = 100
            
            word_count = adapter.rebuild_custom_dict(reason="test")
            assert word_count > 0

    def test_ignore_non_tracked_entity_types(self, temp_project):
        """忽略非追踪类型的实体"""
        tmp_path, cfg = temp_project
        
        with mock.patch("data_modules.rag_adapter.get_client", return_value=StubClient()):
            adapter = RAGAdapter(cfg)
            linker = EntityLinker(cfg, rag_adapter=adapter)
        
        linker.on_entity_registered("some_id", "未知类型")
        
        assert linker._rebuild_pending is False, "非角色/势力/物品类型不应触发"

    def test_config_env_override(self, temp_project):
        """环境变量覆盖配置"""
        import os
        tmp_path, cfg = temp_project
        
        original = os.environ.get("TOKENIZER_AUTO_REBUILD")
        os.environ["TOKENIZER_AUTO_REBUILD"] = "false"
        
        try:
            cfg2 = DataModulesConfig.from_project_root(tmp_path)
            assert cfg2.tokenizer_auto_rebuild_on_init is False
        finally:
            if original is not None:
                os.environ["TOKENIZER_AUTO_REBUILD"] = original
            else:
                del os.environ["TOKENIZER_AUTO_REBUILD"]


class TestEntityLinkerCallbackIntegration:
    """EntityLinker 回调集成测试"""

    def test_entity_registration_callback_exists(self, temp_project):
        """EntityLinker 具有实体注册回调方法"""
        tmp_path, cfg = temp_project
        
        with mock.patch("data_modules.rag_adapter.get_client", return_value=StubClient()):
            adapter = RAGAdapter(cfg)
            linker = EntityLinker(cfg, rag_adapter=adapter)
        
        assert hasattr(linker, "on_entity_registered")
        assert callable(linker.on_entity_registered)

    def test_callback_creates_timer(self, temp_project):
        """回调创建防抖计时器"""
        tmp_path, cfg = temp_project
        cfg.tokenizer_rebuild_debounce_seconds = 1
        
        with mock.patch("data_modules.rag_adapter.get_client", return_value=StubClient()):
            adapter = RAGAdapter(cfg)
            linker = EntityLinker(cfg, rag_adapter=adapter)
        
        assert linker._rebuild_timer is None
        
        linker.on_entity_registered("test", "角色")
        
        assert isinstance(linker._rebuild_timer, threading.Timer)


class TestRebuildCustomDict:
    """rebuild_custom_dict 方法测试"""

    def test_rebuild_with_reason(self, temp_project):
        """带原因参数的重建"""
        tmp_path, cfg = temp_project
        
        with mock.patch("data_modules.rag_adapter.get_client", return_value=StubClient()):
            adapter = RAGAdapter(cfg)
            
            count1 = adapter.rebuild_custom_dict(reason="init")
            assert count1 > 0
            
            count2 = adapter.rebuild_custom_dict(reason="entity_change")
            assert count2 >= count1

    def test_rebuild_returns_word_count(self, temp_project):
        """重建返回词条数量"""
        tmp_path, cfg = temp_project
        
        with mock.patch("data_modules.rag_adapter.get_client", return_value=StubClient()):
            adapter = RAGAdapter(cfg)
            
            count = adapter.rebuild_custom_dict(reason="test")
            assert isinstance(count, int)
            assert count > 0