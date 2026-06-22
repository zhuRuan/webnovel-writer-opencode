"""
文风分析服务 —— 调用本地 Ollama API 对章节文本进行 9 维度文风分析。

9 维度体系：
  Primary 5: 句式特征、叙事视角、节奏控制、情感张力、对白风格
  Secondary 4: 词汇质地、修辞手法、描写偏好、人物塑造

每个维度返回 summary (文本描述) + score (0-1 浮点数)。
返回值使用英文字段名，与 schemas/analysis.py AnalysisResult 对齐。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os as _os
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── Ollama 配置 ──────────────────────────────────────────────

def _get_ollama_generate_url() -> str:
    """从项目配置文件读取 Ollama API 地址。

    优先级：DataModulesConfig（.env 文件） > os.environ > 默认值。
    """
    # 尝试通过 DataModulesConfig 读取（项目级 .env）
    try:
        from data_modules.config import DataModulesConfig
        from dashboard.core.config import get_project_root
        cfg = DataModulesConfig.from_project_root(get_project_root())
        return cfg.ollama_generate_url
    except Exception:
        pass
    # 回退：直接读环境变量（.env 已由 _load_dotenv 加载到 os.environ）
    return _os.environ.get("OLLAMA_HOST", "http://192.168.160.1:11434").rstrip("/") + "/api/generate"


def _get_ollama_chat_url() -> str:
    """与 _get_ollama_generate_url 相同，但返回 /api/chat 路径。"""
    try:
        from data_modules.config import DataModulesConfig
        from dashboard.core.config import get_project_root
        cfg = DataModulesConfig.from_project_root(get_project_root())
        return cfg.ollama_generate_url.replace("/api/generate", "/api/chat")
    except Exception:
        pass
    return _os.environ.get("OLLAMA_HOST", "http://192.168.160.1:11434").rstrip("/") + "/api/chat"

OLLAMA_URL = _get_ollama_generate_url()
OLLAMA_CHAT_URL = _get_ollama_chat_url()
OLLAMA_MODEL = "qwen3.5_9B_Q4"
DEFAULT_TIMEOUT = 120
MAX_TEXT_CHARS = 12000  # 截断上限，避免 prompt 超长

# ── 9 维度中文名 → 英文字段名映射 ───────────────────────────
_CN_TO_EN: dict[str, str] = {
    "句式特征": "sentence_style",
    "叙事视角": "narrative_pov",
    "节奏控制": "pacing_control",
    "情感张力": "emotional_tension",
    "对白风格": "dialogue_style",
    "词汇质地": "word_texture",
    "修辞手法": "rhetoric_devices",
    "描写偏好": "description_preference",
    "人物塑造": "character_portrayal",
}

# 反向映射（供内部使用）
_EN_TO_CN: dict[str, str] = {v: k for k, v in _CN_TO_EN.items()}

# 全维度英文字段名列表
ALL_DIMENSIONS: list[str] = list(_CN_TO_EN.values())

# ── Prompt 模板 ─────────────────────────────────────────────
_ANALYSIS_PROMPT = """你是一位资深文学评论家。请仔细阅读以下小说片段，从以下 9 个维度分析其文风特征。

## 主要维度（5 个）
1. 句式特征：分析句长分布和断句风格。短句主导→快节奏、紧张；长句主导→绵密细腻、舒缓。注意排比、对仗、长短句交替的使用。
2. 叙事视角：人称选择（第一/二/三人称）、全知/限知程度、叙述者参与度、视角切换频率。
3. 节奏控制：章节内快慢段落分布、叙事密度、高潮密度、场景切换节奏、爽点间距。
4. 情感张力：情绪强度曲线、高潮铺垫方式、冲突强度、爽点密度与分布、情绪起伏节奏。
5. 对白风格：对白占全文比例、对白方式（直接引语/间接引语）、对白推动剧情的程度、人物语言的个性化程度。

## 次要维度（4 个）
6. 词汇质地：用词偏好（古风/现代/口语/书面语）、词汇丰富度、成语和俗语使用频率。
7. 修辞手法：比喻、拟人、排比、反复、夸张、反问等修辞手法的使用频率和多样性。
8. 描写偏好：环境描写、动作描写、心理描写、外貌描写的比例倾向。
9. 人物塑造：角色的出场方式、通过行动/对白/心理/外貌展现性格的手法、侧面烘托技巧。

## 输出要求
请严格按以下 JSON 格式输出，不要包含任何其他内容（不要 markdown 代码块标记）：
{{
  "句式特征": {{"summary": "分析总结文本，50-200字", "score": 0.75}},
  "叙事视角": {{"summary": "分析总结文本，50-200字", "score": 0.60}},
  "节奏控制": {{"summary": "分析总结文本，50-200字", "score": 0.80}},
  "情感张力": {{"summary": "分析总结文本，50-200字", "score": 0.70}},
  "对白风格": {{"summary": "分析总结文本，50-200字", "score": 0.65}},
  "词汇质地": {{"summary": "分析总结文本，50-200字", "score": 0.55}},
  "修辞手法": {{"summary": "分析总结文本，50-200字", "score": 0.50}},
  "描写偏好": {{"summary": "分析总结文本，50-200字", "score": 0.60}},
  "人物塑造": {{"summary": "分析总结文本，50-200字", "score": 0.65}}
}}

score 为 0-1 之间的浮点数，表示该维度在文中的表现强度 / 特征鲜明度。

## 待分析文本
{text}"""


# ── 公开 API ────────────────────────────────────────────────


async def analyze_chapter_text(
    text: str,
    dimensions: list[str] | None = None,
    *,
    model: str = OLLAMA_MODEL,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, dict[str, Any]]:
    """对单章文本进行 9 维度文风分析。

    Args:
        text: 章节正文文本（建议 1000-8000 字，超长自动截断至 {MAX_TEXT_CHARS} 字）。
        dimensions: 需要返回的维度列表（英文字段名），None 表示全部 9 维度。
        model: Ollama 模型名（默认 qwen3.5_9B_Q4）。
        timeout: 超时秒数（默认 120s）。

    Returns:
        dict: 英文字段名 → {{"summary": str, "score": float}}。
              解析失败 / 超时 / 空文本返回空 dict。
    """
    text = text.strip()
    if not text:
        logger.debug("analyze_chapter_text: 空文本，跳过分析")
        return {}

    # 截断过长文本
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]

    prompt = _ANALYSIS_PROMPT.format(text=text)

    try:
        proc = await asyncio.create_subprocess_exec(
            "curl", "-s", OLLAMA_CHAT_URL,
            "-d", json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "think": False,
            }, ensure_ascii=False),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout,
        )
        raw_response = stdout.decode("utf-8", errors="replace")
        data = json.loads(raw_response)
        response_text = data.get("message", {}).get("content", "")

        # 提取 JSON 并映射到英文字段
        cn_result = _parse_analysis_json(response_text)
        mapped = _map_cn_to_en(cn_result)

        # 维度筛选
        if dimensions is not None:
            mapped = {k: v for k, v in mapped.items() if k in dimensions}

        return mapped

    except asyncio.TimeoutError:
        logger.warning("Ollama 分析超时 (%ds)", timeout)
    except json.JSONDecodeError:
        logger.warning("Ollama 返回非 JSON 响应")
    except Exception:
        logger.exception("Ollama 分析异常")

    return {}


async def batch_analyze(
    chapters: list[dict],
    progress_callback: Callable[[int, int, dict], None] | None = None,
    *,
    model: str = OLLAMA_MODEL,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[dict]:
    """批量分析多章文本（串行，避免并发轰炸 Ollama）。

    Args:
        chapters: 章节列表，每项至少含 "text" 字段。
        progress_callback: 进度回调 callback(current, total, chapter_meta)。
                           current 从 1 开始。
        model: Ollama 模型名。
        timeout: 单章超时秒数。

    Returns:
        list[dict]: 每章含 chapter_index / chapter / result 三个字段。
                    分析失败的章节 result 为空 dict。
    """
    results: list[dict] = []
    total = len(chapters)

    for idx, chapter in enumerate(chapters):
        text = chapter.get("text", "")
        analysis = await analyze_chapter_text(
            text, model=model, timeout=timeout,
        )
        results.append({
            "chapter_index": idx,
            "chapter": chapter,
            "result": analysis,
        })

        if progress_callback is not None:
            try:
                progress_callback(idx + 1, total, chapter)
            except Exception:
                logger.exception("progress_callback 异常")

    return results


# ── 内部工具函数 ────────────────────────────────────────────


def _parse_analysis_json(raw: str) -> dict:
    """从模型返回的原始文本中提取 JSON 分析结果。

    策略（按优先级）：
      1. 直接 json.loads 整个字符串
      2. 提取第一个 `{` 到最后一个 `}` 之间的内容（处理 markdown 包裹）
      3. 逐维度正则提取（最后兜底）
    """
    raw = raw.strip()
    if not raw:
        return {}

    # 策略 1：整体解析
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and _has_known_dimension(parsed):
            return parsed
    except json.JSONDecodeError:
        pass

    # 策略 2：提取 JSON 块
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(raw[start:end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # 策略 3：正则逐维度兜底
    return _parse_dimensions_regex(raw)


def _parse_dimensions_regex(raw: str) -> dict:
    """使用正则逐维度提取（最后兜底方案）。"""
    import re

    result: dict = {}
    for cn_key in _CN_TO_EN:
        pattern = rf'"{cn_key}"\s*:\s*\{{[^}}]*\}}'
        match = re.search(pattern, raw, re.DOTALL)
        if match:
            try:
                sub = json.loads("{" + match.group(0) + "}")
                result[cn_key] = sub[cn_key]
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
    return result


def _has_known_dimension(parsed: dict) -> bool:
    """检查 dict 是否至少包含一个已知维度 key。"""
    return any(k in _CN_TO_EN for k in parsed)


def _map_cn_to_en(cn_result: dict) -> dict[str, dict[str, Any]]:
    """将中文 key 的分析结果映射为英文字段名。

    score 范围裁剪到 [0, 1]，缺失字段用默认值填充。
    """
    mapped: dict[str, dict[str, Any]] = {}
    for cn_key, en_key in _CN_TO_EN.items():
        if cn_key not in cn_result:
            continue
        item = cn_result[cn_key]
        if not isinstance(item, dict):
            continue
        try:
            score = float(item.get("score", 0.5))
        except (TypeError, ValueError):
            score = 0.5
        mapped[en_key] = {
            "summary": str(item.get("summary", "")),
            "score": max(0.0, min(1.0, score)),
        }
    return mapped
