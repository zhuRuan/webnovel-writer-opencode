# -*- coding: utf-8 -*-
"""
直接测试分词器和数字归一化
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
os.environ["PYTHONPATH"] = str(Path(__file__).parent.parent.parent)

from data_modules.rag_adapter import RAGAdapter
from data_modules.config import DataModulesConfig


def test_tokenizer():
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmp:
        temp_path = Path(tmp)
        cfg = DataModulesConfig.from_project_root(temp_path)
        cfg.ensure_dirs()
        
        adapter = RAGAdapter(cfg)
        
        print("=" * 60)
        print("Tokenizer Test")
        print("=" * 60)
        
        print(f"\n[jieba status] Available: {adapter._jieba_available}")
        
        test_cases = [
            "萧炎",
            "迦南学院",
            "重伤的萧炎",
            "3年之约",
            "十年之约",
            "第3章",
            "斗气三段",
            "第100章",
        ]
        
        print("\nTokenization Results:")
        for text in test_cases:
            tokens = adapter._tokenize(text)
            print(f"\n  Input: {text}")
            print(f"  Tokens: {tokens}")
            
            normalized = adapter._normalize_numbers(text)
            if normalized != text:
                print(f"  Normalized: {normalized}")


if __name__ == "__main__":
    test_tokenizer()