#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data Modules - ModelScope 文生图客户端

支持功能:
- 小说封面生成
- 单角色图片生成
- 批量角色图片生成

API 调用流程:
1. POST /v1/images/generations + X-ModelScope-Async-Mode: true
2. 轮询 GET /v1/tasks/{task_id} (每5秒, 最多120次)
3. 下载图片到本地
"""

import asyncio
import aiohttp
import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from .config import get_config
from logger import get_logger, setup_logging

logger = get_logger(__name__)


SUPPORTED_SIZES = {
    "3:4": "600x800",      # 番茄小说标准尺寸
    "1:1": "1328x1328",   # 方形
    "16:9": "1664x928",   # 横向
    "9:16": "928x1664",   # 竖向
    "4:3": "1472x1104",
}

DEFAULT_STYLES = {
    "xianxia": "Chinese ink painting style, traditional Chinese fantasy, elegant",
    "fantasy": "Western fantasy style, detailed, magical atmosphere",
    "urban": "Modern style, realistic, urban background, post-apocalyptic",
    "scifi": "Sci-fi style, futuristic, high-tech",
    "wuxia": "Chinese wuxia style, martial arts, ancient Chinese",
}

CHAR_FILE_PATTERNS = (
    "主角卡.md",
    "女主卡.md",
    "反派设计.md",
    "角色库/",
)

EXCLUDE_DIRS = (
    "物品库",
    "其他设定",
    "力量体系",
    "世界观",
    "金手指",
    "复合题材",
)


@dataclass
class ImageGenStats:
    """图片生成统计"""
    total: int = 0
    success: int = 0
    errors: int = 0


class ImageGenerator:
    """ModelScope 文生图客户端"""

    def __init__(self, config=None):
        self.config = config or get_config()
        self.stats = ImageGenStats()
        self._session: Optional[aiohttp.ClientSession] = None
        self._style = DEFAULT_STYLES.get(self.config.world_preset, DEFAULT_STYLES["xianxia"])

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=10)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _build_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "X-ModelScope-Async-Mode": "true"
        }
        if self.config.image_api_key:
            headers["Authorization"] = f"Bearer {self.config.image_api_key}"
        return headers

    def _build_url(self) -> str:
        base = self.config.image_base_url.rstrip("/")
        if "/v1" in base:
            return f"{base}/images/generations"
        return f"{base}/v1/images/generations"

    def _validate_size(self, size: str) -> str:
        """验证并转换尺寸格式"""
        # 支持如 "1:1" 格式或直接的 "1328x1328" 格式
        if size in SUPPORTED_SIZES:
            return SUPPORTED_SIZES[size]
        # 已经是像素格式
        for key, val in SUPPORTED_SIZES.items():
            if size == val:
                return size
        logger.warning(f"Unsupported size {size}, using default {self.config.image_size}")
        return self.config.image_size

    async def _submit_task(self, session: aiohttp.ClientSession, prompt: str, size: str) -> Optional[str]:
        """提交生成任务，返回 task_id 或图片URL（同步模式）"""
        url = self._build_url()
        headers = self._build_headers()
        
        # 官方API格式
        payload = {
            "model": self.config.image_model,
            "prompt": prompt
        }

        for attempt in range(self.config.api_max_retries):
            try:
                async with session.post(
                    url,
                    data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.config.normal_timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        # 官方API: task_id 直接在顶层
                        task_id = data.get("task_id")
                        if task_id:
                            logger.info(f"Async task submitted: {task_id}")
                            return task_id
                        
                        logger.error(f"Unexpected response format: {data}")
                        return None
                    
                    # 打印错误信息帮助调试
                    err_text = await resp.text()
                    logger.error("Submit task failed %s: %s", resp.status, err_text[:500])
                    
                    if resp.status in (429, 500, 502, 503, 504) and attempt < self.config.api_max_retries - 1:
                        delay = self.config.api_retry_delay * (2 ** attempt)
                        logger.warning(f"Submit task %s, retrying in %.1fs", resp.status, delay)
                        await asyncio.sleep(delay)
                        continue
                    
                    return None

            except Exception as e:
                if attempt < self.config.api_max_retries - 1:
                    delay = self.config.api_retry_delay * (2 ** attempt)
                    logger.warning(f"Submit task error: {e}, retrying in %.1fs", delay)
                    await asyncio.sleep(delay)
                    continue
                logger.error("Submit task failed: %s", e)
                return None

        return None

    async def _poll_task(self, session: aiohttp.ClientSession, task_id: str) -> Optional[str]:
        """轮询任务状态，返回图片 URL"""
        base = self.config.image_base_url.rstrip("/")
        url = f"{base}/v1/tasks/{task_id}"
        headers = {
            "X-ModelScope-Task-Type": "image_generation"
        }
        if self.config.image_api_key:
            headers["Authorization"] = f"Bearer {self.config.image_api_key}"
        
        max_attempts = self.config.image_max_polls
        poll_interval = self.config.image_poll_interval

        for attempt in range(max_attempts):
            try:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        status = data.get("task_status", "").upper()
                        
                        if status == "SUCCEED":
                            output_images = data.get("output_images", [])
                            if output_images and isinstance(output_images[0], str):
                                return output_images[0]
                            elif output_images and isinstance(output_images[0], dict):
                                return output_images[0].get("url")
                            return data.get("output_url")
                        
                        elif status == "FAIL":
                            logger.error("Task failed: %s", data.get("message", "Unknown error"))
                            return None
                        
                        elif status == "RUNNING" or status == "PENDING":
                            # 优化日志：只在关键节点打印
                            if attempt == 0:
                                logger.info(f"Task {task_id} status: {status}, waiting...")
                            elif attempt % 24 == 0:  # 每2分钟打印一次
                                waited_sec = attempt * poll_interval
                                logger.info(f"Task {task_id} still {status}, waited {waited_sec}s...")
                            await asyncio.sleep(poll_interval)
                            continue
                        
                        else:
                            await asyncio.sleep(poll_interval)
                            continue
                    
                    elif resp.status in (429, 500, 502, 503, 504):
                        await asyncio.sleep(poll_interval)
                        continue
                    
                    else:
                        err_text = await resp.text()
                        logger.error("Poll task failed %s: %s", resp.status, err_text[:200])
                        return None

            except asyncio.TimeoutError:
                logger.warning("Poll task timeout, retrying")
                await asyncio.sleep(poll_interval)
                continue
            except Exception as e:
                logger.warning("Poll task error: %s, retrying", e)
                await asyncio.sleep(poll_interval)
                continue

        logger.error("Task polling timeout after %d attempts", max_attempts)
        return None

    async def _download_image(self, session: aiohttp.ClientSession, image_url: str, output_path: Path) -> bool:
        """下载图片到本地"""
        try:
            async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(output_path, "wb") as f:
                        f.write(content)
                    logger.info(f"Image saved: {output_path}")
                    return True
                else:
                    logger.error("Download image failed: %s", resp.status)
                    return False
        except Exception as e:
            logger.error("Download image error: %s", e)
            return False

    async def generate(
        self,
        prompt: str,
        output_path: Path,
        size: Optional[str] = None
    ) -> Optional[Path]:
        """生成图片并保存到本地"""
        if not self.config.image_api_key:
            logger.error("IMAGE_API_KEY not configured")
            return None

        size = self._validate_size(size or self.config.image_size)
        
        session = await self._get_session()
        
        # 1. 提交任务（可能直接返回图片URL或task_id）
        result = await self._submit_task(session, prompt, size)
        if not result:
            self.stats.errors += 1
            self.stats.total += 1
            return None
        
        # 2. 判断返回类型：直接图片URL 或 task_id
        # task_id 是字符串且包含字母数字，图片URL通常以 http 开头
        image_url = None
        if result.startswith("http"):
            # 同步模式：直接返回图片URL
            image_url = result
        else:
            # 异步模式：需要轮询
            image_url = await self._poll_task(session, result)
        
        if not image_url:
            self.stats.errors += 1
            self.stats.total += 1
            return None

        # 3. 下载图片
        success = await self._download_image(session, image_url, output_path)
        
        self.stats.total += 1
        if success:
            self.stats.success += 1
            return output_path
        else:
            self.stats.errors += 1
            return None

    # 负面提示词（自动注入以保持风格）
    NEGATIVE_PROMPT_EN = "no romance, no smiling faces, no bright daylight, no cartoon style, no anime, no disney"
    NEGATIVE_PROMPT_ZH = "无恋爱、无笑容、无 bright daylight、无卡通风格、无动漫、无迪士尼"

    @staticmethod
    def _convert_to_pinyin(name: str) -> str:
        """将中文名转换为拼音（静态方法）"""
        try:
            from pypinyin import lazy_pinyin
            return "".join(lazy_pinyin(name))
        except ImportError:
            return name


    def to_pinyin(self, name: str) -> str:
        """中文名转拼音"""
        if not name:
            return name
        return self._convert_to_pinyin(name)


    def load_novel_info_from_files(self, project_root: Path) -> dict:
        """从大纲和设定集读取小说信息"""
        info = {
            "title": "",
            "one_sentence": "",
            "tags": "",
            "genre": "",
            "style": "",
        }
        
        # 读取总纲
        zonggang_path = project_root / "大纲" / "总纲.md"
        if zonggang_path.exists():
            content = zonggang_path.read_text(encoding="utf-8")
            lines = content.split("\n")
            for i, line in enumerate(lines):
                line = line.strip()
                if "故事一句话" in line:
                    # 找到下一个非空行作为故事一句话
                    for j in range(i+1, min(i+5, len(lines))):
                        next_line = lines[j].strip()
                        if next_line:
                            info["one_sentence"] = next_line
                            break
            
            # 检测题材
            if "冰河" in content:
                info["genre"] = "ice age apocalypse"
            if "古法" in content or "修炼" in content:
                info["style"] = "ancient Chinese cultivation"
            if "末世" in content:
                info["genre"] = "post-apocalyptic"
        
        # 读取世界观
        world_path = project_root / "设定集" / "世界观.md"
        if world_path.exists():
            content = world_path.read_text(encoding="utf-8")
            if "末世" in content and not info["genre"]:
                info["genre"] = "post-apocalyptic"
            if "古法修炼" in content or "异能" in content:
                if "supernatural" not in info["style"]:
                    info["style"] += ", supernatural powers"
        
        # 读取主角卡
        char_path = project_root / "设定集" / "主角卡.md"
        if char_path.exists():
            content = char_path.read_text(encoding="utf-8")
            lines = content.split("\n")
            for i, line in enumerate(lines):
                line = line.strip()
                if "3个关键词" in line:
                    # 提取关键词
                    for j in range(i+1, min(i+3, len(lines))):
                        next_line = lines[j].strip()
                        if next_line and "-" in next_line:
                            tags = next_line.split("-", 1)[-1].strip()
                            if tags:
                                info["tags"] = tags
                                break
                    break
        
        return info

    def extract_character_visuals(self, project_root: Path) -> dict:
        """从主角卡、金手指等提取角色视觉元素"""
        visuals = {
            "name": "",
            "pinyin_name": "",
            "age": "",
            "appearance": "",
            "tech_elements": [],
            "emotion": [],
            "outfit": "",
        }
        
        char_path = project_root / "设定集" / "主角卡.md"
        if char_path.exists():
            content = char_path.read_text(encoding="utf-8")
            lines = content.split("\n")
            for i, line in enumerate(lines):
                line = line.strip()
                if "姓名" in line and ("：" in line or ":" in line):
                    name = line.split(":", 1)[-1].strip().split("：", 1)[-1].strip()
                    visuals["name"] = name
                    visuals["pinyin_name"] = self.to_pinyin(name.replace(" ", ""))
                if "年龄" in line and ("：" in line or ":" in line):
                    age = line.split(":", 1)[-1].strip().split("：", 1)[-1].strip()
                    age = age.replace("岁", "").replace("（退役军人）", "").replace("(退役军人)", "").strip()
                    visuals["age"] = age
                if "身份" in line and ("：" in line or ":" in line):
                    appearance = line.split(":", 1)[-1].strip().split("：", 1)[-1].strip()
                    visuals["appearance"] = appearance
                if "核心标签" in line or "3个关键词" in line:
                    for j in range(i+1, min(i+5, len(lines))):
                        next_line = lines[j].strip()
                        if next_line and "-" in next_line:
                            tag = next_line.split("-", 1)[-1].strip()
                            visuals["emotion"].append(tag)
                            break
        
        golden_path = project_root / "设定集" / "金手指设计.md"
        if golden_path.exists():
            content = golden_path.read_text(encoding="utf-8")
            if "太阳穴" in content or "发光" in content:
                visuals["tech_elements"].append("neural implant glowing at temple/neck")
            if "蓝色" in content or "电弧" in content:
                visuals["tech_elements"].append("blue energy arcs")
            if "能量刃" in content:
                visuals["tech_elements"].append("energy blades from forearms")
            if "碳纤维" in content or "内甲" in content:
                visuals["outfit"] = "carbon fiber armor"
        
        return visuals

    def extract_scene_visuals(self, project_root: Path) -> dict:
        """从世界观、总纲提取场景视觉元素"""
        visuals = {
            "environment": [],
            "sky_elements": [],
            "atmosphere": [],
            "style_keywords": [],
        }
        
        world_path = project_root / "设定集" / "世界观.md"
        if world_path.exists():
            content = world_path.read_text(encoding="utf-8")
            if "废墟" in content:
                visuals["environment"].append("post-apocalyptic ruins")
            if "悬浮" in content or "山" in content:
                visuals["environment"].append("floating shattered mountains")
            if "宗门" in content:
                visuals["environment"].append("ancient cultivation temple")
            if "天衍宗" in content:
                visuals["environment"].append("Tianyan Sect")
            if "伤痕" in content:
                visuals["sky_elements"].append("eternal scar in sky")
        
        zonggang_path = project_root / "大纲" / "总纲.md"
        if zonggang_path.exists():
            content = zonggang_path.read_text(encoding="utf-8")
            if "伤痕" in content:
                visuals["sky_elements"].append("chaotic lightning wound")
        
        fusion_path = project_root / "设定集" / "复合题材-融合逻辑.md"
        if fusion_path.exists():
            content = fusion_path.read_text(encoding="utf-8")
            if "硬核科幻" in content:
                visuals["style_keywords"].append("hard sci-fi")
            if "脑机接口" in content:
                visuals["style_keywords"].append("neural interface")
            if "赛博" in content:
                visuals["style_keywords"].append("cyberpunk")
        
        visuals["atmosphere"] = ["tragic heroism", "cold blue tones", "dark violet", "dramatic lighting"]
        
        return visuals

    def build_enhanced_cover_prompt(
        self, 
        project_root: Path,
        title: Optional[str] = None,
        description: Optional[str] = None,
        author: Optional[str] = None
    ) -> dict:
        """构建增强版封面提示词（中英文双版本）
        
        Args:
            project_root: 项目根目录
            title: 小说标题
            description: 小说描述（可选）
            author: 作者名（可选）
        """
        char_visuals = self.extract_character_visuals(project_root)
        scene_visuals = self.extract_scene_visuals(project_root)
        
        if not title:
            title = "小说封面"
        
        char_info = []
        if char_visuals["pinyin_name"]:
            char_info.append(char_visuals["pinyin_name"])
        if char_visuals["age"]:
            char_info.append(f"{char_visuals['age']}-year-old")
        if char_visuals["appearance"]:
            char_info.append(char_visuals["appearance"])
        
        char_desc_en = ", ".join(char_info) if char_info else "warrior"
        char_desc_zh = char_visuals["name"] or "主角"
        if char_visuals["age"]:
            char_desc_zh += f"，{char_visuals['age']}岁"
        if char_visuals["appearance"]:
            char_desc_zh += f"，{char_visuals['appearance']}"
        
        tech_en = ", ".join(char_visuals["tech_elements"]) if char_visuals["tech_elements"] else ""
        scene_en = ", ".join(scene_visuals["environment"]) if scene_visuals["environment"] else "shattered land"
        
        sky_en = ""
        if scene_visuals["sky_elements"]:
            sky_en = f", sky with {', '.join(scene_visuals['sky_elements'])}"
        
        style_en = ", ".join(scene_visuals["style_keywords"]) if scene_visuals["style_keywords"] else "xianxia cyberpunk fusion"
        atmos_en = ", ".join(scene_visuals["atmosphere"]) if scene_visuals["atmosphere"] else "epic atmosphere"
        
        author_text = f" by {author}" if author else ""
        
        prompt_en = f"""Japanese anime style, detailed manga illustration. Novel cover for "{title}"{author_text}. Main character: {char_desc_en}. {tech_en}. Background: {scene_en}{sky_en}. Atmosphere: {atmos_en}. Style: {style_en} in anime aesthetic. No text, no words, no letters, no character text except cover title and author name. Cold blue and dark violet tones, dramatic lighting, high quality anime artwork. --ar 2:3"""
        
        tech_zh = "，".join(char_visuals["tech_elements"]) if char_visuals["tech_elements"] else ""
        scene_zh = "，".join(scene_visuals["environment"]) if scene_visuals["environment"] else "废墟"
        sky_zh = ""
        if scene_visuals["sky_elements"]:
            sky_zh = f"，天空有{'，'.join(scene_visuals['sky_elements'])}"
        style_zh = "，".join(scene_visuals["style_keywords"]) if scene_visuals["style_keywords"] else "修仙赛博朋克融合"
        atmos_zh = "，".join(scene_visuals["atmosphere"]) if scene_visuals["atmosphere"] else "史诗氛围"
        
        author_text_zh = f" 作者：{author}" if author else ""
        
        prompt_zh = f"""日本动漫风格，精细漫画插画。小说封面《{title}》{author_text_zh}。主角：{char_desc_zh}。{tech_zh}。背景：{scene_zh}{sky_zh}。氛围：{atmos_zh}。风格：{style_zh}，动漫美学。图片中不能出现任何文字（除封面书名和作者名外）。冷蓝暗紫色调，戏剧性光影，高品质动漫插画。--ar 2:3"""
        
        return {
            "en": prompt_en,
            "zh": prompt_zh,
            "char_visuals": char_visuals,
            "scene_visuals": scene_visuals,
            "title": title,
            "author": author,
        }

    def build_cover_prompt(self, info: dict) -> str:
        """根据小说信息构建封面 prompt"""
        parts = []
        
        # 题材
        genre = info.get("genre", "")
        if genre:
            parts.append(f"{genre} novel cover")
        else:
            parts.append("Chinese fantasy novel cover")
        
        # 故事一句话
        one_sentence = info.get("one_sentence", "")
        if one_sentence:
            # 截取关键信息，避免过长
            parts.append(one_sentence[:200])
        
        # 核心标签
        tags = info.get("tags", "")
        if tags:
            parts.append(tags)
        
        # 风格
        style = info.get("style", "")
        if style:
            parts.append(style)
        
        parts.append("dramatic scene, high detail, cinematic")
        
        return ", ".join(parts)

    def _build_prompt(self, subject: str, description: str, style: Optional[str] = None) -> str:
        """构建完整的 prompt"""
        parts = [subject, description]
        if style:
            parts.append(style)
        else:
            parts.append(self._style)
        return ", ".join(parts)

    async def generate_cover(
        self,
        novel_title: str,
        description: str,
        output_dir: Optional[Path] = None,
        author: Optional[str] = None
    ) -> Optional[Path]:
        """生成小说封面"""
        if output_dir is None:
            output_dir = self.config.project_root / "图片" / "封面"
        
        enhanced = self.build_enhanced_cover_prompt(
            self.config.project_root,
            title=novel_title,
            description=description,
            author=author
        )
        
        prompt = enhanced["en"]
        novel_title = novel_title or "小说封面"
        
        logger.info("=" * 40)
        logger.info("[封面提示词 - 英文]")
        logger.info(enhanced["en"])
        logger.info("=" * 40)
        logger.info("[封面提示词 - 中文]")
        logger.info(enhanced["zh"])
        logger.info("=" * 40)
        
        filename = f"{novel_title.replace(' ', '_')}_cover.png"
        output_path = output_dir / filename
        
        return await self.generate(prompt, output_path)

    async def generate_character(
        self,
        name: str,
        description: str,
        output_dir: Optional[Path] = None,
        style: Optional[str] = None
    ) -> Optional[Path]:
        """生成角色图片"""
        if output_dir is None:
            output_dir = self.config.project_root / "图片" / "角色"
        
        filename = f"{name.replace(' ', '_')}.png"
        output_path = output_dir / filename
        
        prompt = self._build_prompt(
            f"Portrait of character {name}",
            description,
            style
        )
        
        return await self.generate(prompt, output_path)

    async def batch_generate_characters(
        self,
        characters: List[Dict[str, str]],
        output_dir: Optional[Path] = None,
        max_count: int = 20,
        style: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """批量生成角色图片"""
        if output_dir is None:
            output_dir = self.config.project_root / "图片" / "角色"

        results = []
        characters = characters[:max_count]
        
        for i, char in enumerate(characters):
            name = char.get("name", f"character_{i}")
            desc = char.get("description", "")
            
            logger.info(f"[{i+1}/{len(characters)}] Generating: {name}")
            
            result = await self.generate_character(name, desc, output_dir, style)
            
            results.append({
                "name": name,
                "success": result is not None,
                "path": str(result) if result else None
            })
            
            # 避免 API 过载
            if i < len(characters) - 1:
                await asyncio.sleep(1)
        
        return results

    def load_characters_from_md(self, file_path: Path) -> List[Dict[str, str]]:
        """从 Markdown 文件加载角色列表（解析角色卡模板格式）"""
        characters = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            name = ""
            keywords = ""
            first_impression = ""
            
            lines = content.split("\n")
            for line in lines:
                line = line.strip()
                
                # 匹配姓名
                if "姓名：" in line or "姓名:" in line:
                    name = line.split("姓名", 1)[1].split("：", 1)[-1].split(":")[-1].strip()
                
                # 匹配关键词
                elif "3个关键词" in line or "3个关键词：" in line:
                    keywords = line.split("关键词", 1)[-1].split("：", 1)[-1].split(":")[-1].strip()
                
                # 匹配读者第一印象
                elif "读者第一印象" in line or "读者第一印象：" in line:
                    first_impression = line.split("印象", 1)[-1].split("：", 1)[-1].split(":")[-1].strip()
            
            if name:
                description = f"{keywords}, {first_impression}".strip(", ")
                characters.append({"name": name, "description": description})
            
        except Exception as e:
            logger.error("Failed to parse MD file %s: %s", file_path, e)
        
        return characters

    def scan_characters_in_dir(self, dir_path: Path, max_count: int = 20) -> List[Dict[str, str]]:
        """扫描设定集目录，识别所有角色文件并提取角色"""
        characters = []
        
        if not dir_path.is_dir():
            logger.warning("Directory not found: %s", dir_path)
            return characters
        
        # 递归扫描所有 MD 文件
        for md_file in dir_path.rglob("*.md"):
            # 跳过排除的目录
            if any(exclude in md_file.parts for exclude in EXCLUDE_DIRS):
                continue
            
            # 检查是否是角色文件
            is_char_file = any(pattern in str(md_file) for pattern in CHAR_FILE_PATTERNS)
            
            if is_char_file:
                logger.info("Scanning character file: %s", md_file.name)
                chars = self.load_characters_from_md(md_file)
                characters.extend(chars)
                
                if len(characters) >= max_count:
                    break
        
        logger.info("Found %d characters in %s", len(characters), dir_path)
        return characters[:max_count]

    def print_stats(self):
        logger.info("[IMAGE GEN] total=%d, success=%d, errors=%d",
                    self.stats.total, self.stats.success, self.stats.errors)


# 全局客户端
_client: Optional[ImageGenerator] = None


def get_image_generator(config=None) -> ImageGenerator:
    global _client
    if _client is None or config is not None:
        _client = ImageGenerator(config)
    return _client


def main():
    """CLI 入口"""
    import argparse
    
    setup_logging()
    parser = argparse.ArgumentParser(description="ModelScope Image Generator")
    parser.add_argument("--project-root", help="项目根目录")
    
    sub = parser.add_subparsers(dest="cmd", required=True)
    
    # gencover - 生成封面
    p_cover = sub.add_parser("gencover", help="生成小说封面（自动从大纲/设定集读取）")
    p_cover.add_argument("--novel", help="小说标题（可选，不提供时自动从文件读取）")
    p_cover.add_argument("--author", help="作者名（可选，不提供时交互式询问）")
    p_cover.add_argument("--desc", help="小说描述（可选，不提供时自动从文件读取）")
    p_cover.add_argument("--size", default="16:9", help="图片尺寸，默认 16:9")
    
# genchar - 单角色生成
    p_char = sub.add_parser("genchar", help="生成单个角色图片")
    p_char.add_argument("--name", required=True, help="角色名")
    p_char.add_argument("--desc", required=True, help="角色描述")
    p_char.add_argument("--size", default="3:4", help="图片尺寸，默认 3:4")
    
    # genchars - 批量角色生成
    p_chars = sub.add_parser("genchars", help="批量生成角色图片")
    p_chars.add_argument("--file", help="单个角色文件 (MD)")
    p_chars.add_argument("--dir", help="设定集目录（自动扫描角色）")
    p_chars.add_argument("--max", type=int, default=20, help="最大生成数量")
    p_chars.add_argument("--size", default="3:4", help="图片尺寸，默认 3:4")
    
    args = parser.parse_args()
    
    # 加载配置 - 使用 DataModulesConfig.from_project_root 以确保加载项目级 .env
    from project_locator import resolve_project_root
    from data_modules.config import DataModulesConfig
    
    if args.project_root:
        root = resolve_project_root(args.project_root)
    else:
        root = resolve_project_root()
    
    # 使用 from_project_root 加载项目 .env
    config = DataModulesConfig.from_project_root(root)
    generator = get_image_generator(config)
    
    async def run():
        if args.cmd == "gencover":
            author = args.author
            if not author:
                try:
                    author = input("请输入作者名（或直接回车跳过）: ").strip() or None
                except EOFError:
                    author = None
            
            result = await generator.generate_cover(args.novel, args.desc, author=author)
            if result:
                print(f"Cover saved: {result}")
            else:
                print("Cover generation failed")
        
        elif args.cmd == "genchar":
            result = await generator.generate_character(args.name, args.desc)
            if result:
                print(f"Character image saved: {result}")
            else:
                print("Character generation failed")
        
        elif args.cmd == "genchars":
            if args.dir:
                chars = generator.scan_characters_in_dir(Path(args.dir), max_count=args.max)
            elif args.file:
                chars = generator.load_characters_from_md(Path(args.file))
            else:
                print("Please specify --file or --dir")
                return
            
            if not chars:
                print("No characters found")
                return
            
            print(f"Found {len(chars)} characters:")
            for c in chars:
                print(f"  - {c['name']}: {c['description'][:50]}...")
            
            results = await generator.batch_generate_characters(chars, max_count=args.max)
            
            print(f"\n[RESULTS] {len(results)} characters:")
            for r in results:
                status = "OK" if r["success"] else "FAIL"
                print(f"  {r['name']}: {status}")
                if r["path"]:
                    print(f"    -> {r['path']}")
            
            generator.print_stats()
        
        await generator.close()
    
    asyncio.run(run())


if __name__ == "__main__":
    main()