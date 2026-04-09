# -*- coding: utf-8 -*-
"""
分词增强效果测试脚本

用于验证 jieba 分词 + 数字归一化 相比单字符分词的效果提升。
运行方式: python test_tokenizer_improvement.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_modules.rag_adapter import RAGAdapter, SearchResult
from data_modules.config import DataModulesConfig


class ABComparisonResult:
    """A/B 测试结果"""
    def __init__(self, query: str, old_results: list, new_results: list):
        self.query = query
        self.old_results = old_results
        self.new_results = new_results


def create_test_adapter(temp_path: Path) -> RAGAdapter:
    """创建测试用的 RAGAdapter"""
    import data_modules.rag_adapter as rag_module
    
    class StubClient:
        async def embed(self, texts):
            return [[1.0, 0.0] for _ in texts]
        async def embed_batch(self, texts, skip_failures=True):
            return [[1.0, 0.0] for _ in texts]
        async def rerank(self, query, documents, top_n=None):
            top_n = top_n or len(documents)
            return [{"index": i, "relevance_score": 1.0 / (i + 1)} for i in range(min(top_n, len(documents)))]
    
    import unittest.mock as mock
    cfg = DataModulesConfig.from_project_root(temp_path)
    cfg.ensure_dirs()
    
    with mock.patch.object(rag_module, 'get_client', return_value=StubClient()):
        adapter = RAGAdapter(cfg)
    
    return adapter


async def prepare_test_data(adapter: RAGAdapter):
    """准备测试数据"""
    chunks = [
        {"chapter": 1, "scene_index": 1, "content": "萧炎是天云宗弟子，在迦南学院修炼斗气"},
        {"chapter": 2, "scene_index": 1, "content": "药老苏醒后，传授萧炎三年之约的秘密"},
        {"chapter": 3, "scene_index": 1, "content": "三年之约到期，萧炎在乌坦城大战"},
        {"chapter": 4, "scene_index": 1, "content": "萧炎突破到斗师境界，实力大增"},
        {"chapter": 5, "scene_index": 1, "content": "迦南学院的院长亲自接见萧炎"},
        {"chapter": 6, "scene_index": 1, "content": "萧炎与药老在魔兽山脉探险"},
        {"chapter": 7, "scene_index": 1, "content": "十年之约提前到来，萧炎做好战斗准备"},
    ]
    await adapter.store_chunks(chunks)


async def run_ab_test(adapter: RAGAdapter, queries: list) -> list:
    """运行 A/B 测试"""
    results = []
    for query in queries:
        bm25_results = adapter.bm25_search(query, top_k=5)
        results.append({
            'query': query,
            'results': bm25_results
        })
    return results


def main():
    import tempfile
    
    print("=" * 60)
    print("Tokenization Enhancement Test - A/B Comparison")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmp:
        temp_path = Path(tmp)
        adapter = create_test_adapter(temp_path)
        
        asyncio.run(prepare_test_data(adapter))
        
        test_queries = [
            ("Single Name", "萧炎"),
            ("Multi-char Entity", "迦南学院"),
            ("Modified Entity", "重伤的萧炎"),
            ("Number Normalization", "3年之约"),
            ("Number Normalization", "十年之约"),
            ("Chapter Search", "第3章"),
        ]
        
        results = asyncio.run(run_ab_test(adapter, [q[1] for q in test_queries]))
        
        print("\nTest Results:")
        print("=" * 60)
        
        for (label, query), result in zip(test_queries, results):
            print(f"\n[{label}] Query: '{query}'")
            print("-" * 50)
            if result['results']:
                for i, res in enumerate(result['results'][:3], 1):
                    relevance = "[OK]" if query in res.content else "[?]"
                    print(f"  {i}. [Chapter {res.chapter}] {res.content[:30]}... {relevance}")
            else:
                print("  (No results)")
        
        print("\n" + "=" * 60)
        print("Test Complete")
        print("\nNote: Install jieba for full effect: pip install jieba>=0.42.1")
        print("Dictionary: .opencode/dicts/webnovel_dict.txt")


if __name__ == "__main__":
    main()
