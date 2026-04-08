#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data Modules - LLM 调用工具 (v5.5)

提供统一的 LLM 调用接口，支持 OpenAI 兼容 API。
"""

import os
import re
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from .config import get_config

logger = logging.getLogger(__name__)

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api-inference.modelscope.cn/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "Qwen/Qwen2.5-72B-Instruct")

_agents_dir = Path(__file__).resolve().parent.parent.parent / "agents"


def call_agent(
    agent_name: str,
    input_text: str = "",
    **kwargs
) -> str:
    """
    调用指定的子代理，返回 LLM 响应。

    参数:
        agent_name: Agent 文件名（不含 .md），例如 'extract_events'
        input_text: 输入文本，将替换提示词中的 {input} 或 {chapter_text}
        **kwargs: 覆盖默认参数（temperature, max_tokens, model）

    返回:
        LLM 返回的原始文本

    用法:
        response = call_agent("extract_events", chapter_text)
        events = call_agent("extract_events", chapter_text, temperature=0.1)
    """
    agent_path = _agents_dir / f"{agent_name}.md"
    if not agent_path.exists():
        raise FileNotFoundError(f"Agent definition not found: {agent_path}")

    content = agent_path.read_text(encoding="utf-8")

    frontmatter_match = re.match(r'^---\n(.*?)\n---\n(.*)', content, re.DOTALL)
    if frontmatter_match:
        try:
            import yaml
            meta = yaml.safe_load(frontmatter_match.group(1)) or {}
        except Exception:
            meta = {}
        template = frontmatter_match.group(2)
    else:
        meta = {}
        template = content

    prompt = template.replace("{input}", input_text)
    prompt = prompt.replace("{chapter_text}", input_text)

    temperature = kwargs.pop("temperature", meta.get("temperature", 0.2))
    max_tokens = kwargs.pop("max_tokens", 2000)

    return call_llm(prompt, temperature=temperature, max_tokens=max_tokens, **kwargs)


def call_llm(
    prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> str:
    """
    调用 LLM 生成文本。

    Args:
        prompt: 输入提示词
        temperature: 温度参数，控制随机性
        max_tokens: 最大 token 数
        model: 模型名称（默认使用环境变量 LLM_MODEL）
        api_key: API 密钥（默认使用环境变量 LLM_API_KEY）
        base_url: API 地址（默认使用环境变量 LLM_BASE_URL）

    Returns:
        LLM 生成的文本
    """
    try:
        import openai
    except ImportError:
        raise ImportError("请安装 openai 库: pip install openai")

    api_key = api_key or LLM_API_KEY
    base_url = base_url or LLM_BASE_URL
    model = model or LLM_MODEL

    if not api_key:
        raise ValueError("LLM_API_KEY 未设置")

    client = openai.OpenAI(api_key=api_key, base_url=base_url)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "你是一个专业的网络小说写作助手。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.warning(f"LLM 调用失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise


def call_llm_json(
    prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 2000,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    调用 LLM 并期望返回 JSON 格式的结果。

    Args:
        prompt: 输入提示词
        temperature: 温度参数
        max_tokens: 最大 token 数
        model: 模型名称

    Returns:
        解析后的 JSON 对象
    """
    import json
    response = call_llm(prompt, temperature=temperature, max_tokens=max_tokens, model=model)
    import re
    json_match = re.search(r'\{[\s\S]*\}|\[[\s\S]*\]', response)
    if json_match:
        return json.loads(json_match.group())
    raise ValueError(f"无法从 LLM 响应中解析 JSON: {response[:200]}")
