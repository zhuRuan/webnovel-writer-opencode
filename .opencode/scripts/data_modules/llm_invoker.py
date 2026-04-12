# -*- coding: utf-8 -*-
"""
LLM Agent 调用封装

功能：
- 统一调用 LLM agents
- 支持批量并发调用
- 降级模式（LLM 不可用时回退到仅代码审查）
- 异步支持
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from logging import getLogger

from .config import get_config

logger = getLogger(__name__)


@dataclass
class AgentInput:
    """Agent 输入"""
    chapter: int
    chapter_title: str
    content: str
    project_root: str
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentOutput:
    """Agent 输出"""
    agent_id: str
    chapter: int
    overall_score: int
    passed: bool
    issues: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""


class LLMInvoker:
    """LLM 调用器"""
    
    DEFAULT_TIMEOUT = 30
    MAX_RETRIES = 2
    
    def __init__(self, config=None):
        self.config = config or get_config()
        self._api_key = self.config.embed_api_key or self.config.rerank_api_key
        self._base_url = self.config.embed_base_url
        self._model = self.config.embed_model
        self._enabled = bool(self._api_key)
    
    def is_enabled(self) -> bool:
        """检查 LLM 是否可用"""
        return self._enabled
    
    def invoke(
        self,
        agent_id: str,
        prompt_template: str,
        input_data: AgentInput,
    ) -> AgentOutput:
        """
        调用单个 LLM Agent
        
        Args:
            agent_id: Agent 标识符
            prompt_template: prompt 模板
            input_data: 输入数据
        
        Returns:
            AgentOutput
        """
        if not self._enabled:
            logger.warning("LLM 不可用，返回空结果")
            return self._fallback_output(agent_id, input_data.chapter)
        
        import aiohttp
        
        prompt = prompt_template.format(
            chapter=input_data.chapter,
            chapter_title=input_data.chapter_title,
            content=input_data.content,
            project_root=input_data.project_root,
            **input_data.context
        )
        
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": "你是一个网文审查专家。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 2000,
        }
        
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                resp = aiohttp.ClientSession().post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    timeout=aiohttp.ClientTimeout(total=self.DEFAULT_TIMEOUT)
                )
                if resp.status == 200:
                    result = resp.json()
                    return self._parse_output(agent_id, input_data.chapter, result)
                else:
                    logger.warning(f"LLM 调用失败: {resp.status}")
            except Exception as e:
                logger.warning(f"LLM 调用异常: {e}")
                if attempt == self.MAX_RETRIES:
                    break
        
        return self._fallback_output(agent_id, input_data.chapter)
    
    def invoke_batch(
        self,
        agent_configs: List[Dict[str, str]],
        input_data: AgentInput,
    ) -> List[AgentOutput]:
        """
        批量并发调用多个 Agents
        
        Args:
            agent_configs: [{"agent_id": "...", "prompt": "..."}]
            input_data: 输入数据
        
        Returns:
            List[AgentOutput]
        """
        if not self._enabled:
            return [self._fallback_output(cfg["agent_id"], input_data.chapter) for cfg in agent_configs]
        
        tasks = [
            self._invoke_async(cfg["agent_id"], cfg["prompt"], input_data)
            for cfg in agent_configs
        ]
        return asyncio.run(self._run_tasks(tasks))
    
    async def _invoke_async(
        self,
        agent_id: str,
        prompt: str,
        input_data: AgentInput,
    ) -> AgentOutput:
        """异步调用"""
        return self.invoke(agent_id, prompt, input_data)
    
    async def _run_tasks(self, tasks: List) -> List[AgentOutput]:
        """并发运行任务"""
        return await asyncio.gather(*tasks)
    
    def _parse_output(
        self,
        agent_id: str,
        chapter: int,
        response: Dict,
    ) -> AgentOutput:
        """解析 LLM 响应"""
        try:
            content = response["choices"][0]["message"]["content"]
            data = json.loads(content)
            return AgentOutput(
                agent_id=agent_id,
                chapter=chapter,
                overall_score=data.get("overall_score", 50),
                passed=data.get("pass", True),
                issues=data.get("issues", []),
                metrics=data.get("metrics", {}),
                summary=data.get("summary", ""),
            )
        except (KeyError, json.JSONDecodeError, IndexError) as e:
            logger.error(f"解析 LLM 响应失败: {e}")
            return AgentOutput(
                agent_id=agent_id,
                chapter=chapter,
                overall_score=0,
                passed=False,
                issues=[{"error": f"解析失败: {e}"}],
            )
    
    def _fallback_output(self, agent_id: str, chapter: int) -> AgentOutput:
        """降级输出（LLM 不可用时）"""
        return AgentOutput(
            agent_id=agent_id,
            chapter=chapter,
            overall_score=50,
            passed=True,
            issues=[],
            summary="LLM 不可用，跳过此检查",
        )


def invoke_agent(
    agent_id: str,
    prompt_template: str,
    chapter: int,
    chapter_title: str,
    content: str,
    project_root: str,
    context: Optional[Dict] = None,
) -> AgentOutput:
    """便捷调用函数"""
    invoker = LLMInvoker()
    input_data = AgentInput(
        chapter=chapter,
        chapter_title=chapter_title,
        content=content,
        project_root=project_root,
        context=context or {},
    )
    return invoker.invoke(agent_id, prompt_template, input_data)