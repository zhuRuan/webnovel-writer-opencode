#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RAG Adapter - RAG 检索适配模块

封装向量检索功能：
- 向量嵌入 (调用 Modal API)
- 语义搜索
- 重排序
- 混合检索 (向量 + BM25)
"""

import asyncio
import sqlite3
import json
import math
from logging import getLogger
import shutil
import hashlib
from pathlib import Path

from runtime_compat import enable_windows_utf8_stdio
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from collections import Counter
import re
from contextlib import contextmanager
import itertools
import time
from datetime import datetime

from .config import get_config
from .api_client import get_client
from .index_manager import IndexManager
from .query_router import QueryRouter
from .observability import safe_append_perf_timing, safe_log_tool_call
from .temporal_graph import TemporalGraphIndex


logger = getLogger(__name__)

RAG_SCHEMA_VERSION = "3"
VECTOR_REQUIRED_COLUMNS = (
    "chunk_id",
    "chapter",
    "scene_index",
    "content",
    "embedding",
    "parent_chunk_id",
    "chunk_type",
    "source_file",
    "content_hash",
    "created_at",
    "updated_at",
)


@dataclass
class SearchResult:
    """搜索结果"""
    chunk_id: str
    chapter: int
    scene_index: int
    content: str
    score: float
    source: str  # "vector" | "bm25" | "hybrid"
    parent_chunk_id: str | None = None
    chunk_type: str | None = None
    source_file: str | None = None


class RAGAdapter:
    """RAG 检索适配器"""

    _jieba_loaded: bool = False
    _jieba_initialized: bool = False

    def __init__(self, config=None):
        self.config = config or get_config()
        self.api_client = get_client(config)
        self.index_manager = IndexManager(self.config)
        self.query_router = QueryRouter()
        self._degraded_mode_reason: Optional[str] = None
        self._temporal_graph: Optional[TemporalGraphIndex] = None
        self._last_dict_word_count: int = 0
        self._rebuild_timer: Optional[Any] = None
        self._init_db()
        self._init_jieba()
        self._init_temporal_graph()

    def _init_jieba(self):
        """初始化 jieba 分词器（懒加载单例 + 自动重建）"""
        if RAGAdapter._jieba_initialized:
            return
        try:
            import jieba
            
            dict_path = self.config.custom_dict_path
            
            # 自动重建（初始化时）
            if self.config.tokenizer_auto_rebuild_on_init and not dict_path.exists():
                word_count = self.rebuild_custom_dict()
                if word_count > 0 and self.config.tokenizer_log_rebuild_summary:
                    logger.info("[分词词典] 初始化重建完成: %d 词条", word_count)
            
            # 加载词典
            if dict_path.exists():
                jieba.load_userdict(str(dict_path))
                logger.info("jieba 项目词典加载完成: %s", dict_path)
            else:
                framework_dict = self.config.framework_dict_path
                if framework_dict.exists():
                    jieba.load_userdict(str(framework_dict))
                    logger.info("jieba 框架词典加载完成: %s", framework_dict)
                else:
                    logger.warning("jieba 词典不存在，跳过")
            
            RAGAdapter._jieba_loaded = True
        except ImportError:
            logger.warning("jieba 未安装，使用单字符分词降级")
        except Exception as e:
            logger.warning("jieba 初始化失败，使用单字符分词降级: %s", e)
        finally:
            RAGAdapter._jieba_initialized = True

    def rebuild_custom_dict(self, reason: str = "manual") -> int:
        """
        从项目设定集和实体自动生成自定义词典
        
        Args:
            reason: 触发原因 (init/entity_change/manual)
        
        Returns:
            生成的词条数量
        """
        try:
            import jieba
            
            words: set = set()
            
            words.update(self._extract_keywords_from_settings())
            words.update(self._extract_keywords_from_entities())
            words.update(self._extract_keywords_from_outline())
            
            if not words:
                logger.info("未提取到任何关键词，跳过词典生成")
                return 0
            
            dict_path = self.config.custom_dict_path
            dict_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(dict_path, "w", encoding="utf-8") as f:
                f.write(f"# 动态生成的 jieba 词典\n")
                f.write(f"# 由 RAGAdapter.rebuild_custom_dict() 自动生成\n")
                f.write(f"# 触发原因: {reason}\n")
                for word in sorted(words):
                    if word and len(word) >= 2:
                        f.write(f"{word} 10 n\n")
            
            if RAGAdapter._jieba_loaded:
                jieba.load_userdict(str(dict_path))
            
            # 记录词条数量，用于日志抑制
            self._last_dict_word_count = len(words)
            
            if self.config.tokenizer_log_rebuild_summary:
                logger.info("[分词词典] 重建完成: %d 词条, 原因: %s", len(words), reason)
            
            return len(words)
        except ImportError:
            logger.warning("jieba 未安装，无法生成词典")
            return 0
        except Exception as e:
            logger.warning("词典生成失败: %s", e)
            return 0

    def _extract_keywords_from_settings(self) -> set:
        """从设定集目录提取关键词"""
        words: set = set()
        settings_dir = self.config.settings_dir
        
        if not settings_dir.exists():
            return words
        
        for file in settings_dir.glob("*.md"):
            try:
                content = file.read_text(encoding="utf-8")
                words.update(self._extract_chinese_words(content))
            except Exception as e:
                logger.debug("读取设定集失败 %s: %s", file.name, e)
        
        return words

    def _extract_keywords_from_entities(self) -> set:
        """从索引实体提取关键词"""
        words: set = set()
        
        try:
            for entity in self.index_manager.get_core_entities():
                name = entity.get("canonical_name", "")
                if name:
                    words.add(name)
                
                for alias in self.index_manager.get_entity_aliases(entity.get("id", "")):
                    if alias:
                        words.add(alias)
        except Exception as e:
            logger.debug("提取实体关键词失败: %s", e)
        
        return words

    def _extract_keywords_from_outline(self) -> set:
        """从大纲目录提取关键词"""
        words: set = set()
        outline_dir = self.config.outline_dir
        
        if not outline_dir.exists():
            return words
        
        for file in outline_dir.glob("*.md"):
            try:
                content = file.read_text(encoding="utf-8")
                words.update(self._extract_chinese_words(content))
            except Exception as e:
                logger.debug("读取大纲失败 %s: %s", file.name, e)
        
        return words

    def _extract_chinese_words(self, text: str) -> set:
        """从文本中提取可能的中文专有名词"""
        import re
        words: set = set()
        
        chinese_patterns = [
            r'[\u4e00-\u9fff]{2,6}',  # 2-6个连续汉字
        ]
        
        for pattern in chinese_patterns:
            matches = re.findall(pattern, text)
            words.update(matches)
        
        filter_words = {
            "的", "了", "在", "是", "我", "有", "和", "就", "不", "人",
            "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去",
            "你", "会", "着", "没有", "看", "好", "自己", "这", "那",
        }
        
        return {w for w in words if w not in filter_words and len(w) >= 2}

    def _init_temporal_graph(self):
        """初始化时序图索引（优先从 DB 加载，若无则重建）"""
        self._temporal_graph = TemporalGraphIndex(decay_base=0.9)
        
        db_path = str(self.config.index_db)
        loaded = self._temporal_graph.load_from_db(db_path)
        
        if loaded:
            logger.info("时序图从 DB 加载: %s", self._temporal_graph.get_stats())
        else:
            logger.info("时序图 DB 无数据，执行全量重建...")
            self._load_relationships_to_graph()
            self._temporal_graph.save_to_db(db_path)
            logger.info("时序图已保存到 DB")
        
        self._save_temporal_graph_timer()

    def _save_temporal_graph_timer(self):
        """定时保存时序图（避免频繁写入）"""
        import threading
        if self._temporal_graph and self._temporal_graph.edge_count > 0:
            def delayed_save():
                try:
                    db_path = str(self.config.index_db)
                    self._temporal_graph.save_to_db(db_path)
                    logger.info("时序图定时保存完成")
                except Exception as e:
                    logger.warning("时序图定时保存失败: %s", e)
            
            timer = threading.Timer(300, delayed_save)  # 5分钟后保存
            timer.daemon = True
            timer.start()
    
    def _load_relationships_to_graph(self):
        """从关系数据加载到时序图"""
        if not self._temporal_graph:
            return
        
        try:
            relationships = self.index_manager.get_recent_relationships(limit=1000)
            for rel in relationships:
                self._temporal_graph.add_edge(
                    src=rel.get("from_entity", ""),
                    rel=rel.get("type", "相关"),
                    tgt=rel.get("to_entity", ""),
                    chapter=rel.get("chapter", 0),
                    weight=1.0
                )
            logger.info("时序图加载完成: %s", self._temporal_graph.get_stats())
        except Exception as e:
            logger.warning("时序图加载失败: %s", e)
    
    def get_temporal_graph(self) -> Optional[TemporalGraphIndex]:
        """获取时序图索引"""
        return self._temporal_graph

    @property
    def _jieba_available(self) -> bool:
        """检查 jieba 是否可用"""
        return RAGAdapter._jieba_loaded

    def _normalize_numbers(self, text: str) -> str:
        """数字归一化：阿拉伯数字转中文"""
        def _number_to_chinese(num_str: str) -> str:
            if not num_str:
                return num_str
            digits = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九']
            
            try:
                num = int(num_str)
                if num == 0:
                    return '零'
                
                if num < 10:
                    return digits[num]
                
                if num < 20:
                    return '十' if num == 10 else '十' + digits[num % 10]
                
                if num < 100:
                    tens = num // 10
                    ones = num % 10
                    result = digits[tens] + '十'
                    if ones > 0:
                        result += digits[ones]
                    return result
                
                if num < 1000:
                    hundreds = num // 100
                    remainder = num % 100
                    result = digits[hundreds] + '百'
                    if remainder > 0:
                        if remainder < 10:
                            result += '零' + digits[remainder]
                        else:
                            result += _number_to_chinese(str(remainder))
                    return result
                
                return num_str
            except ValueError:
                return num_str

        text = re.sub(r'(\d+)年', lambda m: _number_to_chinese(m.group(1)) + '年', text)
        text = re.sub(r'第(\d+)章', lambda m: '第' + _number_to_chinese(m.group(1)) + '章', text)
        text = re.sub(r'(\d+)段', lambda m: _number_to_chinese(m.group(1)) + '段', text)
        text = re.sub(r'第(\d+)次', lambda m: '第' + _number_to_chinese(m.group(1)) + '次', text)
        return text

    @property
    def degraded_mode_reason(self) -> Optional[str]:
        return self._degraded_mode_reason

    def _update_degraded_mode(self) -> None:
        self._degraded_mode_reason = None
        embed_client = getattr(self.api_client, "_embed_client", None)
        status = getattr(embed_client, "last_error_status", None)
        if status == 401:
            self._degraded_mode_reason = "embedding_auth_failed"

    def _init_db(self):
        """初始化向量数据库"""
        self.config.ensure_dirs()
        needs_migration, existing_cols = self._inspect_vectors_schema()
        if needs_migration:
            backup_path = self._backup_vector_db(reason="schema_migration")
            try:
                with self._get_conn() as conn:
                    cursor = conn.cursor()
                    self._rebuild_vectors_table(cursor, existing_cols)
                    conn.commit()
                logger.warning(
                    "vectors 表结构已迁移（备份: %s）",
                    str(backup_path),
                )
            except Exception as migrate_err:
                try:
                    self._restore_vector_db_from_backup(backup_path)
                    logger.exception("vectors 表迁移失败，已从备份恢复")
                except Exception as restore_exc:
                    logger.exception("vectors 表迁移失败，且恢复备份失败")
                raise

        with self._get_conn() as conn:
            cursor = conn.cursor()
            self._ensure_schema_meta(cursor)
            self._ensure_tables(cursor)
            conn.commit()

    def _table_exists(self, cursor, table_name: str) -> bool:
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        return cursor.fetchone() is not None

    def _table_columns(self, cursor, table_name: str) -> set[str]:
        cursor.execute(f"PRAGMA table_info({table_name})")
        return {row[1] for row in cursor.fetchall()}

    def _inspect_vectors_schema(self) -> tuple[bool, set[str]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if not self._table_exists(cursor, "vectors"):
                return False, set()
            cols = self._table_columns(cursor, "vectors")
            required_cols = set(VECTOR_REQUIRED_COLUMNS)
            return (not required_cols.issubset(cols), cols)

    def _backup_vector_db(self, reason: str) -> Path:
        db_path = Path(self.config.vector_db)
        if not db_path.exists():
            raise FileNotFoundError(f"vectors.db 不存在: {db_path}")
        backup_dir = self.config.webnovel_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"vectors.db.{reason}.v{RAG_SCHEMA_VERSION}.{timestamp}.bak"
        shutil.copy2(db_path, backup_path)
        return backup_path

    def _restore_vector_db_from_backup(self, backup_path: Path) -> None:
        db_path = Path(self.config.vector_db)
        shutil.copy2(backup_path, db_path)

    def _rebuild_vectors_table(self, cursor, existing_cols: set[str]) -> None:
        if not self._table_exists(cursor, "vectors"):
            return

        cursor.execute("DROP TABLE IF EXISTS vectors_migrating")
        cursor.execute("""
            CREATE TABLE vectors_migrating (
                chunk_id TEXT PRIMARY KEY,
                chapter INTEGER,
                scene_index INTEGER,
                content TEXT,
                embedding BLOB,
                parent_chunk_id TEXT,
                chunk_type TEXT DEFAULT 'scene',
                source_file TEXT,
                content_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        copy_columns = [
            col
            for col in VECTOR_REQUIRED_COLUMNS
            if col in existing_cols
        ]
        if copy_columns:
            cols_sql = ", ".join(copy_columns)
            cursor.execute(
                f"INSERT OR REPLACE INTO vectors_migrating ({cols_sql}) SELECT {cols_sql} FROM vectors"
            )

        cursor.execute("DROP TABLE vectors")
        cursor.execute("ALTER TABLE vectors_migrating RENAME TO vectors")

    def _ensure_schema_meta(self, cursor) -> None:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rag_schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute(
            """
            INSERT INTO rag_schema_meta (key, value, updated_at)
            VALUES ('schema_version', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (RAG_SCHEMA_VERSION,),
        )

    def _ensure_tables(self, cursor) -> None:
        # 向量存储表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vectors (
                chunk_id TEXT PRIMARY KEY,
                chapter INTEGER,
                scene_index INTEGER,
                content TEXT,
                embedding BLOB,
                parent_chunk_id TEXT,
                chunk_type TEXT DEFAULT 'scene',
                source_file TEXT,
                content_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # BM25 倒排索引表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bm25_index (
                term TEXT,
                chunk_id TEXT,
                tf REAL,
                PRIMARY KEY (term, chunk_id)
            )
        """)

        # 文档统计表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS doc_stats (
                chunk_id TEXT PRIMARY KEY,
                doc_length INTEGER
            )
        """)

        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vectors_chapter ON vectors(chapter)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vectors_parent ON vectors(parent_chunk_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vectors_type ON vectors(chunk_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bm25_term ON bm25_index(term)")

    @contextmanager
    def _get_conn(self):
        """获取数据库连接（确保关闭，避免 Windows 下文件句柄泄漏）"""
        conn = sqlite3.connect(str(self.config.vector_db))
        try:
            yield conn
        finally:
            conn.close()

    def _get_vectors_count(self) -> int:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM vectors")
            row = cursor.fetchone()
            return int(row[0] or 0) if row else 0

    def _get_recent_chunk_ids(
        self,
        limit: int,
        chunk_type: str | None = None,
        chapter: int | None = None,
    ) -> List[str]:
        if limit <= 0:
            return []
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if chunk_type and chapter is not None:
                cursor.execute(
                    """
                    SELECT chunk_id
                    FROM vectors
                    WHERE chunk_type = ? AND chapter <= ?
                    ORDER BY chapter DESC, scene_index DESC
                    LIMIT ?
                """,
                    (chunk_type, int(chapter), int(limit)),
                )
            elif chunk_type:
                cursor.execute(
                    """
                    SELECT chunk_id
                    FROM vectors
                    WHERE chunk_type = ?
                    ORDER BY chapter DESC, scene_index DESC
                    LIMIT ?
                """,
                    (chunk_type, int(limit)),
                )
            elif chapter is not None:
                cursor.execute(
                    """
                    SELECT chunk_id
                    FROM vectors
                    WHERE chapter <= ?
                    ORDER BY chapter DESC, scene_index DESC
                    LIMIT ?
                """,
                    (int(chapter), int(limit)),
                )
            else:
                cursor.execute(
                    "SELECT chunk_id FROM vectors ORDER BY chapter DESC, scene_index DESC LIMIT ?",
                    (int(limit),),
                )
            return [str(r[0]) for r in cursor.fetchall() if r and r[0]]

    def _fetch_vectors_by_chunk_ids(self, chunk_ids: List[str]) -> List[Tuple]:
        if not chunk_ids:
            return []

        # SQLite 参数数量限制（默认 999），这里做分片查询
        def _chunks(xs: List[str], size: int = 500):
            it = iter(xs)
            while True:
                batch = list(itertools.islice(it, size))
                if not batch:
                    break
                yield batch

        rows: List[Tuple] = []
        with self._get_conn() as conn:
            cursor = conn.cursor()
            for batch in _chunks(chunk_ids):
                placeholders = ",".join(["?"] * len(batch))
                cursor.execute(
                    f"SELECT chunk_id, chapter, scene_index, content, embedding, parent_chunk_id, chunk_type, source_file FROM vectors WHERE chunk_id IN ({placeholders})",
                    tuple(batch),
                )
                rows.extend(cursor.fetchall())
        return rows

    def _vector_search_rows(
        self,
        query_embedding: List[float],
        rows: List[Tuple],
        *,
        top_k: int,
    ) -> List[SearchResult]:
        results: List[SearchResult] = []
        for row in rows:
            (
                chunk_id,
                chapter,
                scene_index,
                content,
                embedding_bytes,
                parent_chunk_id,
                chunk_type,
                source_file,
            ) = row
            if not embedding_bytes:
                continue
            embedding = self._deserialize_embedding(embedding_bytes)
            score = self._cosine_similarity(query_embedding, embedding)
            results.append(
                SearchResult(
                    chunk_id=chunk_id,
                    chapter=chapter,
                    scene_index=scene_index,
                    content=content,
                    score=score,
                    source="vector",
                    parent_chunk_id=parent_chunk_id,
                    chunk_type=chunk_type,
                    source_file=source_file,
                )
            )

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    # ==================== 向量存储 ====================

    def _compute_content_hash(self, content: str) -> str:
        """计算内容哈希（用于增量检测）"""
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    def _get_chunk_hash(self, chunk_id: str) -> Optional[str]:
        """获取已有 chunk 的哈希"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT content_hash FROM vectors WHERE chunk_id = ?", (chunk_id,))
            row = cursor.fetchone()
            return row[0] if row else None

    async def store_chunks(
        self,
        chunks: List[Dict],
        incremental: bool = True,
    ) -> int:
        """
        存储场景切片的向量

        Args:
            chunks: 切片列表
            incremental: 是否启用增量检测（默认 True）

        chunks 格式:
        [
            {
                "chapter": 100,
                "scene_index": 1,
                "content": "场景内容...",
                "chunk_type": "scene",
                "parent_chunk_id": "ch0100_summary",
                "source_file": "正文/第0100章.md#scene_1"
            }
        ]

        返回存储数量
        """
        if not chunks:
            return 0

        filtered_chunks = []
        if incremental:
            for chunk in chunks:
                chunk_type = chunk.get("chunk_type") or "scene"
                chunk_id = chunk.get("chunk_id")
                if not chunk_id:
                    if chunk_type == "summary":
                        chunk_id = f"ch{int(chunk['chapter']):04d}_summary"
                    else:
                        chunk_id = f"ch{int(chunk['chapter']):04d}_s{int(chunk['scene_index'])}"
                content = chunk.get("content", "")
                new_hash = self._compute_content_hash(content)
                existing_hash = self._get_chunk_hash(chunk_id)
                if existing_hash and existing_hash == new_hash:
                    continue
                filtered_chunks.append(chunk)
        else:
            filtered_chunks = chunks

        if not filtered_chunks:
            return 0

        contents = [c.get("content", "") for c in filtered_chunks]
        embeddings = await self.api_client.embed_batch(contents)

        if not embeddings:
            return 0

        stored = 0
        skipped = 0
        errors = []
        with self._get_conn() as conn:
            cursor = conn.cursor()

            for chunk, embedding in zip(filtered_chunks, embeddings):
                chunk_type = chunk.get("chunk_type") or "scene"
                chunk_id = chunk.get("chunk_id")
                if not chunk_id:
                    if chunk_type == "summary":
                        chunk_id = f"ch{int(chunk['chapter']):04d}_summary"
                    else:
                        chunk_id = f"ch{int(chunk['chapter']):04d}_s{int(chunk['scene_index'])}"

                content = chunk.get("content", "")
                content_hash = self._compute_content_hash(content)

                if embedding is None:
                    skipped += 1
                    try:
                        self._update_bm25_index(cursor, chunk_id, content)
                    except Exception as e:
                        errors.append(f"BM25 index failed for {chunk_id}: {e}")
                    continue

                embedding_bytes = self._serialize_embedding(embedding)

                cursor.execute("""
                    INSERT OR REPLACE INTO vectors
                    (chunk_id, chapter, scene_index, content, embedding, parent_chunk_id, chunk_type, source_file, content_hash, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    chunk_id,
                    chunk["chapter"],
                    chunk.get("scene_index", 0) if chunk_type == "scene" else 0,
                    content,
                    embedding_bytes,
                    chunk.get("parent_chunk_id"),
                    chunk_type,
                    chunk.get("source_file"),
                    content_hash,
                ))

                try:
                    self._update_bm25_index(cursor, chunk_id, content)
                except Exception as e:
                    errors.append(f"BM25 index failed for {chunk_id}: {e}")

                stored += 1

            try:
                conn.commit()
            except Exception as e:
                logger.error("SQLite commit failed: %s", e)
                errors.append(f"SQLite commit failed: {e}")

        if skipped > 0:
            logger.warning(
                "Vector embedding: %s stored, %s skipped (embedding failed)",
                stored,
                skipped,
            )
        if errors:
            for err in errors[:5]:
                logger.warning("%s", err)

        return stored

    def _serialize_embedding(self, embedding: List[float]) -> bytes:
        """序列化向量"""
        import struct
        return struct.pack(f"{len(embedding)}f", *embedding)

    def _deserialize_embedding(self, data: bytes) -> List[float]:
        """反序列化向量"""
        import struct
        count = len(data) // 4
        return list(struct.unpack(f"{count}f", data))

    def _log_query(
        self,
        query: str,
        query_type: str,
        results: List[SearchResult],
        latency_ms: int,
        chapter: int | None = None,
    ) -> None:
        try:
            hit_sources = Counter([r.chunk_type or "unknown" for r in results])
            self.index_manager.log_rag_query(
                query=query,
                query_type=query_type,
                results_count=len(results),
                hit_sources=json.dumps(hit_sources, ensure_ascii=False),
                latency_ms=latency_ms,
                chapter=chapter,
            )
        except Exception as exc:
            logger.warning("failed to log rag query: %s", exc)

    # ==================== BM25 索引 ====================

    def _tokenize(self, text: str) -> List[str]:
        """智能分词（中文 jieba + 数字归一化 + 英文单词）"""
        text = self._normalize_numbers(text)

        if self._jieba_available:
            try:
                import jieba
                chinese = list(jieba.cut(text))
            except Exception:
                chinese = list(text)
        else:
            chinese = list(text)

        english = re.findall(r'[a-zA-Z]+', text.lower())
        return [w for w in chinese + english if w.strip() and not w.isspace()]

    def _update_bm25_index(self, cursor, chunk_id: str, content: str):
        """更新 BM25 索引"""
        # 删除旧索引
        cursor.execute("DELETE FROM bm25_index WHERE chunk_id = ?", (chunk_id,))
        cursor.execute("DELETE FROM doc_stats WHERE chunk_id = ?", (chunk_id,))

        # 分词
        tokens = self._tokenize(content)
        doc_length = len(tokens)

        # 计算词频
        tf_counter = Counter(tokens)

        # 插入倒排索引
        for term, count in tf_counter.items():
            tf = count / doc_length if doc_length > 0 else 0
            cursor.execute("""
                INSERT INTO bm25_index (term, chunk_id, tf)
                VALUES (?, ?, ?)
            """, (term, chunk_id, tf))

        # 更新文档统计
        cursor.execute("""
            INSERT INTO doc_stats (chunk_id, doc_length)
            VALUES (?, ?)
        """, (chunk_id, doc_length))

    # ==================== 向量检索 ====================

    async def vector_search(
        self,
        query: str,
        top_k: int = None,
        chunk_type: str | None = None,
        log_query: bool = True,
        chapter: int | None = None,
    ) -> List[SearchResult]:
        """向量相似度搜索"""
        top_k = top_k or self.config.vector_top_k
        start_time = time.perf_counter()

        # 获取查询向量
        query_embeddings = await self.api_client.embed([query])
        if not query_embeddings:
            self._update_degraded_mode()
            return []

        self._degraded_mode_reason = None

        query_embedding = query_embeddings[0]

        # 从数据库读取所有向量并计算相似度
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if chunk_type and chapter is not None:
                cursor.execute(
                    """
                    SELECT chunk_id, chapter, scene_index, content, embedding, parent_chunk_id, chunk_type, source_file
                    FROM vectors
                    WHERE chunk_type = ? AND chapter <= ?
                """,
                    (chunk_type, int(chapter)),
                )
            elif chunk_type:
                cursor.execute(
                    "SELECT chunk_id, chapter, scene_index, content, embedding, parent_chunk_id, chunk_type, source_file FROM vectors WHERE chunk_type = ?",
                    (chunk_type,),
                )
            elif chapter is not None:
                cursor.execute(
                    """
                    SELECT chunk_id, chapter, scene_index, content, embedding, parent_chunk_id, chunk_type, source_file
                    FROM vectors
                    WHERE chapter <= ?
                """,
                    (int(chapter),),
                )
            else:
                cursor.execute(
                    "SELECT chunk_id, chapter, scene_index, content, embedding, parent_chunk_id, chunk_type, source_file FROM vectors"
                )

            results = []
            for row in cursor.fetchall():
                (
                    chunk_id,
                    chapter,
                    scene_index,
                    content,
                    embedding_bytes,
                    parent_chunk_id,
                    chunk_type_value,
                    source_file,
                ) = row
                if not embedding_bytes:
                    continue
                embedding = self._deserialize_embedding(embedding_bytes)

                # 计算余弦相似度
                score = self._cosine_similarity(query_embedding, embedding)

                results.append(SearchResult(
                    chunk_id=chunk_id,
                    chapter=chapter,
                    scene_index=scene_index,
                    content=content,
                    score=score,
                    source="vector",
                    parent_chunk_id=parent_chunk_id,
                    chunk_type=chunk_type_value,
                    source_file=source_file,
                ))

        # 排序并返回 top_k
        results.sort(key=lambda x: x.score, reverse=True)
        results = results[:top_k]
        if log_query:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            self._log_query(query, "vector", results, latency_ms, chapter=chapter)
        return results

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """计算余弦相似度"""
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)

    # ==================== BM25 检索 ====================

    def bm25_search(
        self,
        query: str,
        top_k: int = None,
        k1: float = 1.5,
        b: float = 0.75,
        chunk_type: str | None = None,
        log_query: bool = True,
        chapter: int | None = None,
    ) -> List[SearchResult]:
        """BM25 关键词搜索"""
        top_k = top_k or self.config.bm25_top_k
        start_time = time.perf_counter()

        query_terms = self._tokenize(query)
        if not query_terms:
            return []

        with self._get_conn() as conn:
            cursor = conn.cursor()

            # 获取文档总数和平均长度
            cursor.execute("SELECT COUNT(*), AVG(doc_length) FROM doc_stats")
            row = cursor.fetchone()
            total_docs = row[0] or 1
            avg_doc_length = row[1] or 1

            # 计算每个文档的 BM25 分数
            doc_scores = {}

            for term in set(query_terms):
                # 获取包含该词的文档
                cursor.execute("""
                    SELECT b.chunk_id, b.tf, d.doc_length
                    FROM bm25_index b
                    JOIN doc_stats d ON b.chunk_id = d.chunk_id
                    WHERE b.term = ?
                """, (term,))

                docs_with_term = cursor.fetchall()
                df = len(docs_with_term)

                if df == 0:
                    continue

                # IDF
                idf = math.log((total_docs - df + 0.5) / (df + 0.5) + 1)

                for chunk_id, tf, doc_length in docs_with_term:
                    # BM25 公式
                    score = idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_length / avg_doc_length))

                    if chunk_id not in doc_scores:
                        doc_scores[chunk_id] = 0
                    doc_scores[chunk_id] += score

            # 获取文档内容
            results = []
            for chunk_id, score in doc_scores.items():
                if chunk_type and chapter is not None:
                    cursor.execute(
                        """
                        SELECT chapter, scene_index, content, parent_chunk_id, chunk_type, source_file
                        FROM vectors
                        WHERE chunk_id = ? AND chunk_type = ? AND chapter <= ?
                    """,
                        (chunk_id, chunk_type, int(chapter)),
                    )
                elif chunk_type:
                    cursor.execute(
                        """
                        SELECT chapter, scene_index, content, parent_chunk_id, chunk_type, source_file
                        FROM vectors
                        WHERE chunk_id = ? AND chunk_type = ?
                    """,
                        (chunk_id, chunk_type),
                    )
                elif chapter is not None:
                    cursor.execute(
                        """
                        SELECT chapter, scene_index, content, parent_chunk_id, chunk_type, source_file
                        FROM vectors
                        WHERE chunk_id = ? AND chapter <= ?
                    """,
                        (chunk_id, int(chapter)),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT chapter, scene_index, content, parent_chunk_id, chunk_type, source_file
                        FROM vectors
                        WHERE chunk_id = ?
                    """,
                        (chunk_id,),
                    )
                row = cursor.fetchone()
                if row:
                    results.append(SearchResult(
                        chunk_id=chunk_id,
                        chapter=row[0],
                        scene_index=row[1],
                        content=row[2],
                        score=score,
                        source="bm25",
                        parent_chunk_id=row[3],
                        chunk_type=row[4],
                        source_file=row[5],
                    ))

        results.sort(key=lambda x: x.score, reverse=True)
        results = results[:top_k]
        if log_query:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            self._log_query(query, "bm25", results, latency_ms, chapter=chapter)
        return results

    def _extract_query_seed_entities(self, query: str) -> List[str]:
        """从查询中提取种子实体（通过别名和实体 ID 匹配）。"""
        tokens = set(re.findall(r"[\u4e00-\u9fff]{2,8}|[A-Za-z][A-Za-z0-9_]{1,24}", query))
        entity_ids: List[str] = []
        for token in tokens:
            if len(entity_ids) >= int(self.config.graph_rag_max_expanded_entities):
                break

            # 1) 通过别名匹配
            alias_hits = self.index_manager.get_entities_by_alias(token)
            for hit in alias_hits:
                entity_id = str(hit.get("id") or "").strip()
                if entity_id and entity_id not in entity_ids:
                    entity_ids.append(entity_id)

            if len(entity_ids) >= int(self.config.graph_rag_max_expanded_entities):
                break

            # 2) 通过实体 ID 直匹配
            entity = self.index_manager.get_entity(token)
            if entity:
                entity_id = str(entity.get("id") or "").strip()
                if entity_id and entity_id not in entity_ids:
                    entity_ids.append(entity_id)

        return entity_ids[: int(self.config.graph_rag_max_expanded_entities)]

    def _normalize_entity_ids(self, candidates: List[str]) -> List[str]:
        """将输入实体候选（名称/别名/ID）规范化为实体 ID 列表。"""
        ids: List[str] = []
        for token in candidates:
            candidate = str(token or "").strip()
            if not candidate:
                continue
            direct = self.index_manager.get_entity(candidate)
            if direct and direct.get("id"):
                entity_id = str(direct.get("id"))
                if entity_id not in ids:
                    ids.append(entity_id)
                continue

            for hit in self.index_manager.get_entities_by_alias(candidate):
                entity_id = str(hit.get("id") or "").strip()
                if entity_id and entity_id not in ids:
                    ids.append(entity_id)
        return ids[: int(self.config.graph_rag_max_expanded_entities)]

    def _expand_related_entities(self, seed_entities: List[str], hops: int | None = None) -> List[str]:
        """基于关系图扩展相关实体。"""
        max_entities = int(self.config.graph_rag_max_expanded_entities)
        hops = max(1, int(hops or self.config.graph_rag_expand_hops))
        expanded: List[str] = []
        for seed in seed_entities:
            if seed not in expanded:
                expanded.append(seed)
            if len(expanded) >= max_entities:
                break
            graph = self.index_manager.build_relationship_subgraph(
                center_entity=seed,
                depth=hops,
                top_edges=max(20, int(self.config.graph_rag_candidate_limit)),
            )
            for node in graph.get("nodes", []):
                entity_id = str(node.get("id") or "").strip()
                if entity_id and entity_id not in expanded:
                    expanded.append(entity_id)
                if len(expanded) >= max_entities:
                    break
            if len(expanded) >= max_entities:
                break
        return expanded[:max_entities]

    def _expand_related_entities_temporal(
        self,
        seed_entities: List[str],
        current_chapter: int | None = None,
        hops: int | None = None,
    ) -> List[str]:
        """
        使用时序图扩展相关实体（增强版）
        
        Args:
            seed_entities: 种子实体列表
            current_chapter: 当前章节
            hops: 跳数
        
        Returns:
            扩展后的实体列表（按时序权重排序）
        """
        if not self._temporal_graph:
            return self._expand_related_entities(seed_entities, hops)
        
        max_entities = int(self.config.graph_rag_max_expanded_entities)
        hops = max(1, int(hops or self.config.graph_rag_expand_hops))
        
        if current_chapter is None:
            try:
                current_chapter = int(self.get_stats().get("max_chapter") or 1)
            except Exception:
                current_chapter = 1
        
        expanded: List[str] = []
        for seed in seed_entities:
            if seed not in expanded:
                expanded.append(seed)
            if len(expanded) >= max_entities:
                break
            
            results = self._temporal_graph.query_expand(
                entity=seed,
                current_chapter=current_chapter,
                max_hops=hops,
                max_entities=max_entities
            )
            
            for r in results:
                if r.entity and r.entity not in expanded:
                    expanded.append(r.entity)
                if len(expanded) >= max_entities:
                    break
            
            if len(expanded) >= max_entities:
                break
        
        return expanded[:max_entities]

    def _collect_graph_candidate_chunk_ids(
        self,
        entity_ids: List[str],
        *,
        chapter: int | None = None,
        limit: int | None = None,
    ) -> List[str]:
        """根据实体名称/别名在向量库正文中筛选候选 chunk。"""
        if not entity_ids:
            return []

        limit = int(limit or self.config.graph_rag_candidate_limit)
        entity_terms: Dict[str, set[str]] = {}
        for entity_id in entity_ids:
            terms: set[str] = set()
            entity = self.index_manager.get_entity(entity_id)
            if entity:
                canonical_name = str(entity.get("canonical_name") or "").strip()
                if canonical_name:
                    terms.add(canonical_name)
            for alias in self.index_manager.get_entity_aliases(entity_id):
                alias_text = str(alias or "").strip()
                if alias_text:
                    terms.add(alias_text)
            if terms:
                entity_terms[entity_id] = terms

        if not entity_terms:
            return []

        with self._get_conn() as conn:
            cursor = conn.cursor()
            if chapter is None:
                cursor.execute(
                    "SELECT chunk_id, chapter, content FROM vectors ORDER BY chapter DESC, scene_index DESC"
                )
            else:
                cursor.execute(
                    """
                    SELECT chunk_id, chapter, content
                    FROM vectors
                    WHERE chapter <= ?
                    ORDER BY chapter DESC, scene_index DESC
                """,
                    (int(chapter),),
                )
            rows = cursor.fetchall()

        scored: List[Tuple[str, int, int]] = []
        for chunk_id, chapter_no, content in rows:
            text = str(content or "")
            if not text:
                continue
            hit_score = 0
            for terms in entity_terms.values():
                hit_score += sum(1 for term in terms if term and term in text)
            if hit_score > 0:
                scored.append((str(chunk_id), int(chapter_no or 0), hit_score))

        scored.sort(key=lambda x: (x[2], x[1]), reverse=True)
        return [chunk_id for chunk_id, _chapter, _score in scored[:limit]]

    async def _vector_search_by_chunk_ids(
        self,
        query: str,
        chunk_ids: List[str],
        *,
        top_k: int,
        chunk_type: str | None = None,
    ) -> List[SearchResult]:
        """在指定候选 chunk 范围内执行向量检索。"""
        if not chunk_ids:
            return []

        query_embeddings = await self.api_client.embed([query])
        if not query_embeddings:
            self._update_degraded_mode()
            return []
        self._degraded_mode_reason = None

        query_embedding = query_embeddings[0]
        rows = await asyncio.to_thread(self._fetch_vectors_by_chunk_ids, chunk_ids)
        if chunk_type:
            rows = [r for r in rows if len(r) > 6 and r[6] == chunk_type]
        return await asyncio.to_thread(
            self._vector_search_rows,
            query_embedding,
            rows,
            top_k=top_k,
        )

    def _apply_graph_priors(
        self,
        result: SearchResult,
        *,
        seed_terms: set[str],
        related_terms: set[str],
        max_chapter: int,
    ) -> float:
        """为图谱候选增加先验分。"""
        score = float(result.score)
        content = str(result.content or "")

        if any(term and term in content for term in seed_terms):
            score += float(self.config.graph_rag_boost_same_entity)
        elif any(term and term in content for term in related_terms):
            score += float(self.config.graph_rag_boost_related_entity)

        if max_chapter > 0 and result.chapter is not None:
            gap = max(0, max_chapter - int(result.chapter))
            recency = max(0.0, 1.0 - min(gap, 100) / 100.0)
            score += recency * float(self.config.graph_rag_boost_recency)

        return score

    async def graph_hybrid_search(
        self,
        query: str,
        top_k: int = 5,
        *,
        chunk_type: str | None = None,
        chapter: int | None = None,
        center_entities: Optional[List[str]] = None,
        log_query: bool = True,
    ) -> List[SearchResult]:
        """
        图谱增强混合检索：
        1) 先走现有 hybrid 作为基础召回；
        2) 基于实体关系图扩展候选；
        3) 向量重算 + 图谱先验融合；
        4) rerank 产出最终结果。
        """
        start_time = time.perf_counter()

        base_results = await self.hybrid_search(
            query=query,
            vector_top_k=max(top_k * 3, int(self.config.vector_top_k)),
            bm25_top_k=max(top_k * 3, int(self.config.bm25_top_k)),
            rerank_top_n=max(top_k * 2, int(self.config.rerank_top_n)),
            chunk_type=chunk_type,
            chapter=chapter,
            log_query=False,
        )
        if not bool(self.config.graph_rag_enabled):
            final = list(base_results)[:top_k]
            if log_query:
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                self._log_query(query, "graph_hybrid_fallback", final, latency_ms, chapter=chapter)
            return final

        seeds = self._normalize_entity_ids([s for s in (center_entities or []) if str(s).strip()])
        if not seeds:
            seeds = self._extract_query_seed_entities(query)

        if not seeds:
            final = list(base_results)[:top_k]
            if log_query:
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                self._log_query(query, "graph_hybrid_no_seed", final, latency_ms, chapter=chapter)
            return final

        if self._temporal_graph:
            expanded_entities = self._expand_related_entities_temporal(
                seed_entities=seeds,
                current_chapter=chapter,
            )
        else:
            expanded_entities = self._expand_related_entities(seeds)
        
        candidate_chunk_ids = self._collect_graph_candidate_chunk_ids(
            expanded_entities,
            chapter=chapter,
            limit=max(top_k * 8, int(self.config.graph_rag_candidate_limit)),
        )

        graph_vector_results = await self._vector_search_by_chunk_ids(
            query,
            candidate_chunk_ids,
            top_k=max(top_k * 4, int(self.config.rerank_top_n) * 2),
            chunk_type=chunk_type,
        )

        # 构建实体术语集用于先验分
        seed_terms: set[str] = set()
        related_terms: set[str] = set()
        for idx, entity_id in enumerate(expanded_entities):
            entity = self.index_manager.get_entity(entity_id)
            canonical_name = str((entity or {}).get("canonical_name") or "").strip()
            aliases = [str(a).strip() for a in self.index_manager.get_entity_aliases(entity_id)]
            terms = {t for t in [canonical_name, *aliases] if t}
            if idx < len(seeds):
                seed_terms.update(terms)
            else:
                related_terms.update(terms)

        max_chapter = 0
        try:
            max_chapter = int(self.get_stats().get("max_chapter") or 0)
        except Exception:
            max_chapter = 0
        if chapter is not None:
            try:
                max_chapter = int(chapter)
            except (TypeError, ValueError):
                pass

        merged: Dict[str, SearchResult] = {}
        for result in base_results:
            result.source = "graph_hybrid"
            merged[result.chunk_id] = result

        for result in graph_vector_results:
            adjusted = self._apply_graph_priors(
                result,
                seed_terms=seed_terms,
                related_terms=related_terms,
                max_chapter=max_chapter,
            )
            result.score = adjusted
            result.source = "graph_hybrid"
            existing = merged.get(result.chunk_id)
            if existing is None or result.score > existing.score:
                merged[result.chunk_id] = result

        sorted_candidates = sorted(merged.values(), key=lambda r: r.score, reverse=True)
        candidates = sorted_candidates[: max(top_k * 3, int(self.config.rerank_top_n) * 2)]
        if not candidates:
            if log_query:
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                self._log_query(query, "graph_hybrid", [], latency_ms, chapter=chapter)
            return []

        rerank_top_n = max(top_k, int(self.config.rerank_top_n))
        rerank_input = [c.content for c in candidates]
        rerank_results = await self.api_client.rerank(query, rerank_input, top_n=rerank_top_n)

        final_results: List[SearchResult] = []
        if rerank_results:
            for item in rerank_results:
                idx = int(item.get("index", 0))
                if idx < 0 or idx >= len(candidates):
                    continue
                picked = candidates[idx]
                picked.score = float(item.get("relevance_score", picked.score))
                picked.source = "graph_hybrid"
                final_results.append(picked)
        else:
            final_results = candidates[:rerank_top_n]

        final_results = final_results[:top_k]
        if log_query:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            self._log_query(query, "graph_hybrid", final_results, latency_ms, chapter=chapter)
        return final_results

    async def search(
        self,
        query: str,
        top_k: int = 5,
        *,
        strategy: str = "auto",
        chunk_type: str | None = None,
        chapter: int | None = None,
        center_entities: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """统一检索入口。"""
        strategy = str(strategy or "auto").lower()
        if filters and chapter is None:
            try:
                chapter = int((filters or {}).get("to_chapter") or 0) or None
            except (TypeError, ValueError):
                chapter = None

        if strategy == "auto":
            intent_payload = self.query_router.route_intent(query)
            if bool(self.config.graph_rag_enabled) and bool(intent_payload.get("needs_graph")):
                strategy = "graph_hybrid"
                if not center_entities:
                    center_entities = list(intent_payload.get("entities") or [])
            else:
                strategy = "hybrid"

        if strategy not in {"vector", "bm25", "backtrack", "graph_hybrid", "hybrid"}:
            # 未知策略统一降级 hybrid，避免调用方传错参数导致中断。
            strategy = "hybrid"

        if strategy == "vector":
            return await self.vector_search(query, top_k=top_k, chunk_type=chunk_type, chapter=chapter)
        if strategy == "bm25":
            return self.bm25_search(query, top_k=top_k, chunk_type=chunk_type, chapter=chapter)
        if strategy == "backtrack":
            return await self.search_with_backtrack(query, top_k=top_k)
        if strategy == "graph_hybrid":
            return await self.graph_hybrid_search(
                query=query,
                top_k=top_k,
                chunk_type=chunk_type,
                chapter=chapter,
                center_entities=center_entities,
            )
        return await self.hybrid_search(
            query=query,
            vector_top_k=top_k,
            bm25_top_k=top_k,
            rerank_top_n=top_k,
            chunk_type=chunk_type,
            chapter=chapter,
        )

    # ==================== 混合检索 ====================

    async def hybrid_search(
        self,
        query: str,
        vector_top_k: int = None,
        bm25_top_k: int = None,
        rerank_top_n: int = None,
        chunk_type: str | None = None,
        chapter: int | None = None,
        log_query: bool = True,
    ) -> List[SearchResult]:
        """
        混合检索：向量 + BM25 + RRF 融合 + Rerank

        步骤:
        1. 向量检索 top_k
        2. BM25 检索 top_k
        3. RRF 融合
        4. Rerank 精排
        """
        vector_top_k = vector_top_k or self.config.vector_top_k
        bm25_top_k = bm25_top_k or self.config.bm25_top_k
        rerank_top_n = rerank_top_n or self.config.rerank_top_n
        start_time = time.perf_counter()

        # 小规模：全表向量扫描（召回更稳）；大规模：预筛选避免 O(n) 扫描拖慢
        vectors_count = await asyncio.to_thread(self._get_vectors_count)
        use_full_scan = vectors_count <= int(self.config.vector_full_scan_max_vectors)

        if use_full_scan:
            # 并行执行向量和 BM25 检索
            vector_results, bm25_results = await asyncio.gather(
                self.vector_search(query, vector_top_k, chunk_type=chunk_type, log_query=False, chapter=chapter),
                asyncio.to_thread(self.bm25_search, query, bm25_top_k, 1.5, 0.75, chunk_type, False, chapter),
            )
        else:
            bm25_candidates = max(
                int(self.config.vector_prefilter_bm25_candidates),
                int(bm25_top_k),
                int(vector_top_k) * 5,
                int(rerank_top_n) * 10,
            )
            recent_candidates = max(
                int(self.config.vector_prefilter_recent_candidates),
                int(vector_top_k) * 5,
                int(rerank_top_n) * 10,
            )

            bm25_task = asyncio.to_thread(
                self.bm25_search,
                query,
                bm25_candidates,
                1.5,
                0.75,
                chunk_type,
                False,
                chapter,
            )
            recent_task = asyncio.to_thread(self._get_recent_chunk_ids, recent_candidates, chunk_type, chapter)
            embed_task = self.api_client.embed([query])

            bm25_candidates_results, recent_ids, query_embeddings = await asyncio.gather(
                bm25_task,
                recent_task,
                embed_task,
            )

            if not query_embeddings:
                self._update_degraded_mode()
                return []
            self._degraded_mode_reason = None
            query_embedding = query_embeddings[0]

            candidate_ids = {r.chunk_id for r in bm25_candidates_results}
            candidate_ids.update(recent_ids)

            rows = await asyncio.to_thread(self._fetch_vectors_by_chunk_ids, list(candidate_ids))
            if chunk_type:
                rows = [r for r in rows if len(r) > 6 and r[6] == chunk_type]
            if chapter is not None:
                rows = [r for r in rows if len(r) > 1 and int(r[1] or 0) <= int(chapter)]
            vector_results = await asyncio.to_thread(
                self._vector_search_rows,
                query_embedding,
                rows,
                top_k=int(vector_top_k),
            )

            # BM25 结果用于融合时只取 top_k
            bm25_results = list(bm25_candidates_results)[: int(bm25_top_k)]

        # RRF 融合
        rrf_scores = {}
        k = self.config.rrf_k

        for rank, result in enumerate(vector_results):
            if result.chunk_id not in rrf_scores:
                rrf_scores[result.chunk_id] = {"result": result, "score": 0}
            rrf_scores[result.chunk_id]["score"] += 1 / (k + rank + 1)

        for rank, result in enumerate(bm25_results):
            if result.chunk_id not in rrf_scores:
                rrf_scores[result.chunk_id] = {"result": result, "score": 0}
            rrf_scores[result.chunk_id]["score"] += 1 / (k + rank + 1)

        # 按 RRF 分数排序
        sorted_results = sorted(
            rrf_scores.values(),
            key=lambda x: x["score"],
            reverse=True
        )

        # 取 top candidates 进行 rerank
        candidates = [item["result"] for item in sorted_results[:rerank_top_n * 2]]

        if not candidates:
            final_results: List[SearchResult] = []
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            if log_query:
                self._log_query(query, "hybrid", final_results, latency_ms, chapter=chapter)
            return final_results

        # 调用 Rerank API
        documents = [c.content for c in candidates]
        rerank_results = await self.api_client.rerank(query, documents, top_n=rerank_top_n)

        if not rerank_results:
            # Rerank 失败，返回 RRF 结果
            final_results = [item["result"] for item in sorted_results[:rerank_top_n]]
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            if log_query:
                self._log_query(query, "hybrid", final_results, latency_ms, chapter=chapter)
            return final_results

        # 组装最终结果
        final_results = []
        for r in rerank_results:
            idx = r.get("index", 0)
            if idx < len(candidates):
                result = candidates[idx]
                result.score = r.get("relevance_score", 0)
                result.source = "hybrid"
                final_results.append(result)

        latency_ms = int((time.perf_counter() - start_time) * 1000)
        if log_query:
            self._log_query(query, "hybrid", final_results, latency_ms, chapter=chapter)
        return final_results

    def _get_chunks_by_ids(self, chunk_ids: List[str]) -> List[SearchResult]:
        rows = self._fetch_vectors_by_chunk_ids(chunk_ids)
        results: List[SearchResult] = []
        for row in rows:
            (
                chunk_id,
                chapter,
                scene_index,
                content,
                _embedding_bytes,
                parent_chunk_id,
                chunk_type,
                source_file,
            ) = row
            results.append(
                SearchResult(
                    chunk_id=chunk_id,
                    chapter=chapter,
                    scene_index=scene_index,
                    content=content,
                    score=0.0,
                    source="parent",
                    parent_chunk_id=parent_chunk_id,
                    chunk_type=chunk_type,
                    source_file=source_file,
                )
            )
        return results

    def _merge_results(
        self,
        parents: List[SearchResult],
        children: List[SearchResult],
    ) -> List[SearchResult]:
        parent_map = {p.chunk_id: p for p in parents}
        merged: List[SearchResult] = []
        seen = set()
        for child in children:
            parent_id = child.parent_chunk_id
            if parent_id and parent_id in parent_map and parent_id not in seen:
                merged.append(parent_map[parent_id])
                seen.add(parent_id)
            merged.append(child)
        return merged

    async def search_with_backtrack(self, query: str, top_k: int = 5) -> List[SearchResult]:
        start_time = time.perf_counter()
        child_results = await self.hybrid_search(
            query,
            vector_top_k=top_k * 2,
            bm25_top_k=top_k * 2,
            rerank_top_n=top_k,
            chunk_type="scene",
            log_query=False,
        )
        parent_ids = sorted({r.parent_chunk_id for r in child_results if r.parent_chunk_id})
        parents = self._get_chunks_by_ids(parent_ids) if parent_ids else []
        merged = self._merge_results(parents, child_results[:top_k])
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        self._log_query(query, "backtrack", merged, latency_ms)
        return merged

    # ==================== 统计 ====================

    def get_stats(self) -> Dict[str, int]:
        """获取 RAG 统计"""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM vectors")
            vectors = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(DISTINCT term) FROM bm25_index")
            terms = cursor.fetchone()[0]

            cursor.execute("SELECT MAX(chapter) FROM vectors")
            max_chapter = cursor.fetchone()[0] or 0

            return {
                "vectors": vectors,
                "terms": terms,
                "max_chapter": max_chapter
            }


# ==================== CLI 接口 ====================

def main():
    import argparse
    import sys
    from .cli_output import print_success, print_error
    from .cli_args import normalize_global_project_root, load_json_arg

    parser = argparse.ArgumentParser(description="RAG Adapter CLI")
    parser.add_argument("--project-root", type=str, help="项目根目录")

    subparsers = parser.add_subparsers(dest="command")

    # 获取统计
    subparsers.add_parser("stats")

    # 写入索引
    index_parser = subparsers.add_parser("index-chapter")
    index_parser.add_argument("--chapter", type=int, required=True)
    index_parser.add_argument("--scenes", required=True, help="JSON 格式的场景列表")
    index_parser.add_argument("--summary", required=False, help="章节摘要文本")
    index_parser.add_argument(
        "--incremental",
        dest="incremental",
        action="store_true",
        default=True,
        help="启用增量索引（默认开启）",
    )
    index_parser.add_argument(
        "--no-incremental",
        dest="incremental",
        action="store_false",
        help="禁用增量索引（全量重建）",
    )

    # 搜索
    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument(
        "--mode",
        choices=["auto", "vector", "bm25", "hybrid", "graph_hybrid", "backtrack"],
        default="hybrid",
    )
    search_parser.add_argument("--top-k", type=int, default=5)
    search_parser.add_argument("--chunk-type", choices=["scene", "summary"], default=None)
    search_parser.add_argument(
        "--center-entities",
        required=False,
        help="中心实体列表（JSON 数组或逗号分隔）",
    )

    # 重建词典
    subparsers.add_parser("rebuild-dict")

    argv = normalize_global_project_root(sys.argv[1:])
    args = parser.parse_args(argv)
    command_started_at = time.perf_counter()

    # 初始化
    config = None
    if args.project_root:
        # 允许传入“工作区根目录”，统一解析到真正的 book project_root（必须包含 .webnovel/state.json）
        from project_locator import resolve_project_root
        from .config import DataModulesConfig

        resolved_root = resolve_project_root(args.project_root)
        config = DataModulesConfig.from_project_root(resolved_root)

    adapter = RAGAdapter(config)
    tool_name = f"rag_adapter:{args.command or 'unknown'}"

    def _append_timing(success: bool, *, error_code: str | None = None, error_message: str | None = None, chapter: int | None = None):
        elapsed_ms = int((time.perf_counter() - command_started_at) * 1000)
        safe_append_perf_timing(
            adapter.config.project_root,
            tool_name=tool_name,
            success=success,
            elapsed_ms=elapsed_ms,
            chapter=chapter,
            error_code=error_code,
            error_message=error_message,
        )

    def emit_success(data=None, message: str = "ok", chapter: int | None = None):
        print_success(data, message=message)
        safe_log_tool_call(adapter.index_manager, tool_name=tool_name, success=True)
        _append_timing(True, chapter=chapter)

    def emit_error(code: str, message: str, suggestion: str | None = None, chapter: int | None = None):
        print_error(code, message, suggestion=suggestion)
        safe_log_tool_call(
            adapter.index_manager,
            tool_name=tool_name,
            success=False,
            error_code=code,
            error_message=message,
        )
        _append_timing(False, error_code=code, error_message=message, chapter=chapter)

    if args.command == "stats":
        stats = adapter.get_stats()
        emit_success(stats, message="stats")

    elif args.command == "index-chapter":
        scenes = load_json_arg(args.scenes)
        chunks = []

        # summary chunk
        summary_text = args.summary
        if not summary_text and config:
            summary_path = config.webnovel_dir / "summaries" / f"ch{args.chapter:04d}.md"
            if summary_path.exists():
                summary_text = summary_path.read_text(encoding="utf-8")

        parent_chunk_id = None
        if summary_text:
            parent_chunk_id = f"ch{args.chapter:04d}_summary"
            chunks.append(
                {
                    "chapter": args.chapter,
                    "scene_index": 0,
                    "content": summary_text,
                    "chunk_type": "summary",
                    "chunk_id": parent_chunk_id,
                    "source_file": f"summaries/ch{args.chapter:04d}.md",
                }
            )

        for s in scenes:
            scene_index = s.get("index", 0)
            chunk_id = f"ch{args.chapter:04d}_s{int(scene_index)}"
            chunks.append(
                {
                    "chapter": args.chapter,
                    "scene_index": scene_index,
                    "content": s.get("content", ""),
                    "chunk_type": "scene",
                    "parent_chunk_id": parent_chunk_id,
                    "chunk_id": chunk_id,
                    "source_file": f"正文/第{args.chapter:04d}章.md#scene_{int(scene_index)}",
                }
            )

        stored = asyncio.run(adapter.store_chunks(chunks, incremental=args.incremental))
        skipped = len(chunks) - stored
        result = {"stored": stored, "skipped": skipped, "total": len(chunks), "incremental": args.incremental}
        if skipped > 0:
            emit_success(result, message="indexed_with_warnings", chapter=args.chapter)
        else:
            emit_success(result, message="indexed", chapter=args.chapter)

    elif args.command == "search":
        center_entities: List[str] | None = None
        if getattr(args, "center_entities", None):
            raw = str(args.center_entities).strip()
            if raw:
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        center_entities = [str(x).strip() for x in parsed if str(x).strip()]
                except Exception:
                    center_entities = [x.strip() for x in re.split(r"[，,;；\s]+", raw) if x.strip()]

        if args.mode == "vector":
            results = asyncio.run(adapter.vector_search(args.query, args.top_k, chunk_type=args.chunk_type))
        elif args.mode == "bm25":
            results = adapter.bm25_search(args.query, args.top_k, chunk_type=args.chunk_type)
        elif args.mode == "backtrack":
            results = asyncio.run(adapter.search_with_backtrack(args.query, args.top_k))
        elif args.mode == "graph_hybrid":
            results = asyncio.run(
                adapter.graph_hybrid_search(
                    args.query,
                    args.top_k,
                    chunk_type=args.chunk_type,
                    center_entities=center_entities,
                )
            )
        elif args.mode == "auto":
            results = asyncio.run(
                adapter.search(
                    args.query,
                    args.top_k,
                    strategy="auto",
                    chunk_type=args.chunk_type,
                    center_entities=center_entities,
                )
            )
        else:
            results = asyncio.run(adapter.hybrid_search(args.query, args.top_k, args.top_k, args.top_k, chunk_type=args.chunk_type))

        payload = [r.__dict__ for r in results]
        degraded_reason = adapter.degraded_mode_reason
        if degraded_reason:
            warnings = [{"code": "DEGRADED_MODE", "reason": degraded_reason}]
            print_success(payload, message="search_results", warnings=warnings)
            safe_log_tool_call(adapter.index_manager, tool_name=tool_name, success=True)
            _append_timing(True)
        else:
            emit_success(payload, message="search_results")

    elif args.command == "rebuild-dict":
        count = adapter.rebuild_custom_dict()
        emit_success({"words_count": count}, message="dict_rebuilt")

    else:
        emit_error("UNKNOWN_COMMAND", "未指定有效命令", suggestion="请查看 --help")


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        enable_windows_utf8_stdio()
    main()
