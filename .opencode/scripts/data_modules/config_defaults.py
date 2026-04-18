#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置默认值

从 config.py 提取的默认值，便于集中管理和测试。
"""


DEFAULT_VALUES = {
    "embed_api_type": "openai",
    "embed_base_url": "https://api-inference.modelscope.cn/v1",
    "embed_model": "Qwen/Qwen3-Embedding-8B",
    "embed_concurrency": 64,
    "embed_batch_size": 64,

    "rerank_api_type": "openai",
    "rerank_base_url": "https://api.jina.ai/v1",
    "rerank_model": "jina-reranker-v3",
    "rerank_concurrency": 32,

    "image_base_url": "https://api-inference.modelscope.cn/v1",
    "image_model": "Qwen/Qwen-Image-2512",
    "image_size": "1:1",

    "cold_start_timeout": 300,
    "normal_timeout": 180,

    "api_max_retries": 3,
    "api_retry_delay": 1.0,

    "vector_top_k": 30,
    "bm25_top_k": 20,
    "rerank_top_n": 10,
    "rrf_k": 60,

    "query_recent_chapters_limit": 10,
    "query_recent_appearances_limit": 20,
    "query_similar_chunks_limit": 10,

    "max_disambiguation_warnings": 50,
    "max_disambiguation_pending": 20,

    "context_extra_section_budget": 0,
    "context_ranker_enabled": True,
    "context_memory_cache_enabled": True,

    "max_entities_per_chapter": 100,
    "max_state_changes_per_chapter": 50,

    "backup_max_count": 10,
    "archive_max_count": 50,

    "sync_interval_seconds": 300,

    "index_reading_power_window": 30,
    "index_pattern_stats_window": 20,
    "index_hook_stats_window": 20,
    "index_review_trend_window": 50,

    "default_template": "plot",
    "default_tier": "装饰",
    "default_entity_tier": "次要",
}