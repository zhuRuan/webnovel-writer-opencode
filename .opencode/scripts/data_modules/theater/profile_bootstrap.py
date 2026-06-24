#!/usr/bin/env python3
"""从设定集角色卡 markdown 文件引导角色 profile 到 theater/actors/ 目录。

把自由书写的角色设定转为标准化 actor profile 骨架，供 theater pipeline 后续
丰富。不依赖 pypinyin 或任何非标准库。

用法:
    python -X utf8 profile_bootstrap.py --project-root 特级 --all
    python -X utf8 profile_bootstrap.py --project-root 特级 --file 设定集/主角卡.md

输出 (<project-root>/theater/actors/<actor_id>/):
    profile.json         — 综合角色档案（identity / personality / motivation / …）
    current_state.json   — 当前状态（location / mood / health / resources）
    habits.json          — 行为习惯
    secrets.json         — 秘密
    skills.json          — 技能列表
    relationships.json   — 关系字典
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# ── actor_id 映射（汉 → 拼音式 ID，避免依赖 pypinyin） ──────
_ACTOR_ID_MAP: dict[str, str] = {
    "秦异": "qin_yi",
    "白芷": "bai_zhi",
    "程诺": "cheng_nuo",
    "沈北望": "shen_bei_wang",
    "凌毅": "ling_yi",
    "白启": "bai_qi",
    "张姐": "zhang_jie",
}


def _to_actor_id(name: str) -> str:
    """将中文名映射为拼音式 actor_id。"""
    mapped = _ACTOR_ID_MAP.get(name)
    if mapped:
        return mapped
    # 兜底：取前两个字符转小写
    return name[:2].lower()


# ── Markdown 解析工具 ────────────────────────────────────

def _parse_md_sections(text: str) -> dict[str, str]:
    """按 '## ' 标题解析 markdown → {标题: 正文}。"""
    sections: dict[str, str] = {}
    current_heading = ""
    current_lines: list[str] = []

    for line in text.splitlines():
        if line.startswith("## "):
            if current_heading:
                sections[current_heading] = "\n".join(current_lines).strip()
            current_heading = line[3:].strip()
            current_lines = []
        elif current_heading:
            current_lines.append(line)

    if current_heading:
        sections[current_heading] = "\n".join(current_lines).strip()

    return sections


def _bullet_text(text: str) -> str:
    """去掉行首的 '- ' 前缀（含缩进）。"""
    m = re.match(r"^[\s]*[-]\s*(.*)", text)
    return m.group(1).strip() if m else text.strip()


def _extract_bullets(text: str) -> list[str]:
    """从文本中提取所有 '- ' 开头的行内容。"""
    return [
        _bullet_text(line)
        for line in text.splitlines()
        if re.match(r"^\s*-\s", line)
    ]


def _extract_labeled_line(text: str, label: str) -> str:
    """从文本中提取 '- label：值' 或 '- label:值' 的值部分。"""
    for line in text.splitlines():
        m = re.match(
            r"^\s*-\s*" + re.escape(label) + r"[：:]\s*(.+)", line
        )
        if m:
            return m.group(1).strip()
    return ""


def _extract_labeled_lines(text: str, label: str) -> list[str]:
    """从文本中提取 '- label：值1;值2;值3' → [值1, 值2, 值3]"""
    raw = _extract_labeled_line(text, label)
    if not raw:
        return []
    return [p.strip() for p in re.split(r"[；;]", raw) if p.strip()]


def _find_section(sections: dict[str, str], key: str) -> str:
    """从 sections dict 中按前缀匹配查找节内容。

    处理 ``成长弧线（阶段·7卷）`` 匹配 ``成长弧线`` 这样的场景。
    优先精确匹配，退化到前缀匹配。
    """
    if key in sections:
        return sections[key]
    for section_key, content in sections.items():
        if section_key.startswith(key):
            return content
    return ""


def _extract_all_labeled(text: str) -> dict[str, str]:
    """从 bullet 行中提取所有 '键：值' 对。"""
    result: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^\s*-\s*(.+?)[：:]\s*(.+)$", line)
        if m:
            result[m.group(1).strip()] = m.group(2).strip()
    return result


# ── 卡类型判定 ──────────────────────────────────────────

def _detect_tier(filename: str) -> str:
    """根据文件名判定角色 tier。"""
    lower = filename.lower()
    if "主角" in lower and "女主" not in lower:
        return "主角"
    if "女主" in lower or "女配" in lower:
        return "配角"
    if "反派" in lower:
        return "反派"
    if "配角" in lower or "男配" in lower:
        return "配角"
    return "extra"


# ── 角色名提取 ─────────────────────────────────────────

def _find_character_name(filename: str, basic_info_text: str) -> str | None:
    """从基本信息节或文件名中提取角色名。"""
    # 优先从基本信息中的"姓名"字段
    name = _extract_labeled_line(basic_info_text, "姓名")
    if name:
        return name

    # fallback: 从文件名 "女主卡：白芷.md" → "白芷"
    stem = Path(filename).stem
    m = re.match(r".*[：:]\s*(.+)$", stem)
    if m:
        return m.group(1).strip()

    return None


# ── 核心解析 ────────────────────────────────────────────

def parse_character_card(md_path: Path) -> dict[str, Any] | None:
    """解析单张角色卡 markdown 文件。"""
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError:
        log.warning("无法读取文件: %s", md_path)
        return None

    sections = _parse_md_sections(text)

    # 提取各节（使用前缀匹配，支持 "成长弧线（阶段·7卷）" 匹配 "成长弧线"）
    basic = _find_section(sections, "基本信息")
    personality = _find_section(sections, "性格与底色")
    motivation = _find_section(sections, "动机与目标")
    flaws = _find_section(sections, "缺陷与代价")
    relationships = _find_section(sections, "关键关系")
    abilities = _find_section(sections, "当前能力")
    golden_finger = _find_section(sections, "金手指")
    behavioral = _find_section(sections, "行为模式")
    growth_arc = _find_section(sections, "成长弧线")
    ooc = _find_section(sections, "OOC 警戒")
    core_tags = _find_section(sections, "核心标签")
    role_section = _find_section(sections, "角色定位")

    # ── 姓名 & actor_id ──
    name = _find_character_name(md_path.name, basic)
    if not name:
        log.warning("无法从 '%s' 提取角色名，跳过", md_path.name)
        return None

    actor_id = _to_actor_id(name)
    tier = _detect_tier(md_path.name)

    # ── traits ──
    traits: list[str] = []
    core_line = _extract_labeled_line(personality, "核心性格")
    if core_line:
        traits = [t.strip() for t in re.split(r"[、，,]", core_line) if t.strip()]

    # ── background ──
    identity = _extract_labeled_line(basic, "身份")
    starting_state = _extract_labeled_line(basic, "起点状态")
    bg_parts: list[str] = []
    if identity:
        bg_parts.append(identity)
    if starting_state:
        bg_parts.append("起点：" + starting_state)
    background = "；".join(bg_parts) if bg_parts else (identity or "")

    # ── role ──
    role = tier
    if role_section:
        role_text = role_section.strip()
        if role_text:
            role = role_text

    # ── 组装 profile ──
    profile: dict[str, Any] = {
        "actor_id": actor_id,
        "name": name,
        "tier": tier,
        "intro_chapter": 1,
        "traits": traits,
        "background": background,
        "role": role,
    }

    # personality
    p_obj: dict[str, Any] = {}
    if core_line:
        p_obj["core"] = core_line
    bottom_lines = _extract_labeled_lines(personality, "行为底线")
    if bottom_lines:
        p_obj["behavioral_bottom_line"] = bottom_lines
    trigger = _extract_labeled_line(personality, "情绪触发点")
    if trigger:
        p_obj["emotional_triggers"] = trigger
    irritation = _extract_labeled_line(personality, "易激怒点")
    if irritation:
        p_obj["irritation_points"] = irritation
    soft = _extract_labeled_line(personality, "容易心软点")
    if soft:
        p_obj["soft_spots"] = soft
    if p_obj:
        profile["personality"] = p_obj

    # motivation
    labeled_motiv = _extract_all_labeled(motivation)
    m_obj: dict[str, str] = {}
    for k, v in labeled_motiv.items():
        if "短期" in k:
            m_obj["short_term"] = v
        elif "中期" in k:
            m_obj["mid_term"] = v
        elif "长期" in k:
            m_obj["long_term"] = v
        elif "真正渴望" in k:
            m_obj["core_desire"] = v
    if m_obj:
        profile["motivation"] = m_obj

    # flaws
    flaw_bullets = _extract_bullets(flaws)
    f_obj: dict[str, list[str]] = {}
    for bullet in flaw_bullets:
        for label_key in ("性格缺陷", "能力限制", "心理阴影", "代价承受底线"):
            if bullet.startswith(label_key + "：") or bullet.startswith(label_key + ":"):
                f_obj.setdefault(label_key, []).append(
                    bullet[len(label_key) + 1:].strip()
                )
                break
    if f_obj:
        profile["flaws"] = f_obj
    elif flaw_bullets:
        profile["flaws"] = flaw_bullets

    # relationships summary
    rel_bullets = _extract_bullets(relationships)
    if rel_bullets:
        profile["relationships_summary"] = rel_bullets

    # abilities
    labeled_ab = _extract_all_labeled(abilities)
    a_obj: dict[str, Any] = {}
    for k, v in labeled_ab.items():
        if "境界" in k or "等级" in k:
            a_obj["level"] = v
        elif "代表技能" in k or "技能" in k:
            a_obj["skills"] = v
        elif "资源" in k:
            a_obj["resources"] = v
    if a_obj:
        profile["abilities"] = a_obj

    # golden_finger
    labeled_gf = _extract_all_labeled(golden_finger)
    gf_obj: dict[str, str] = {}
    for k, v in labeled_gf.items():
        if "类型" in k:
            gf_obj["type"] = v
        elif "代价" in k or "限制" in k:
            gf_obj["limits"] = v
        elif "核心卖点" in k or "卖点" in k:
            gf_obj["core_appeal"] = v
    if gf_obj:
        profile["golden_finger"] = gf_obj

    # behavioral
    labeled_beh = _extract_all_labeled(behavioral)
    beh_obj: dict[str, str] = {}
    for k, v in labeled_beh.items():
        if "常用" in k:
            beh_obj["common_approach"] = v
        elif "失败" in k:
            beh_obj["failure_response"] = v
        elif "破局" in k:
            beh_obj["unique_strength"] = v
    if beh_obj:
        profile["behavioral"] = beh_obj

    # growth_arc
    if growth_arc:
        profile["growth_arc"] = growth_arc

    # ooc_warnings
    ooc_bullets = _extract_bullets(ooc)
    if ooc_bullets:
        never_do = [b for b in ooc_bullets if "不该做" in b or "不应该" in b or "不应当" in b]
        needs_fs = [b for b in ooc_bullets if "提前铺垫" in b or "铺垫" in b]
        ooc_obj: dict[str, list[str]] = {}
        if never_do:
            ooc_obj["never_do"] = [b.split("：", 1)[-1] if "：" in b else b for b in never_do]
        if needs_fs:
            ooc_obj["needs_foreshadowing"] = [b.split("：", 1)[-1] if "：" in b else b for b in needs_fs]
        if ooc_obj:
            profile["ooc_warnings"] = ooc_obj

    return {
        "actor_id": actor_id,
        "name": name,
        "card_type": tier,
        "profile": profile,
        "sections": sections,
    }


# ── 文件写入 ────────────────────────────────────────────

def _actor_dir(project_root: Path, actor_id: str) -> Path:
    return project_root / "theater" / "actors" / actor_id


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("已创建: %s", path)


def bootstrap_actor_from_markdown(md_path: Path, project_root: Path) -> dict[str, Any] | None:
    """从单张角色卡 markdown 引导 actor profile 到 theater/actors/。

    返回解析结果（含 actor_id / name / profile / sections）或 None 表示跳过。
    """
    result = parse_character_card(md_path)
    if result is None:
        return None

    actor_id = result["actor_id"]
    name = result["name"]
    profile = result["profile"]
    sections = result["sections"]

    # ---- 不覆盖已存在的角色目录 ----
    a_dir = _actor_dir(project_root, actor_id)
    if a_dir.is_dir():
        log.info("角色目录已存在，跳过: %s (%s)", name, actor_id)
        return None

    a_dir.mkdir(parents=True, exist_ok=True)

    # profile.json
    _write_json(a_dir / "profile.json", profile)

    # current_state.json
    basic = sections.get("基本信息", "")
    starting_state = _extract_labeled_line(basic, "起点状态")
    current_state: dict[str, Any] = {
        "actor_id": actor_id,
        "location": starting_state or "",
        "mood": "",
        "health": "",
        "resources": [],
    }
    # 可选附加年龄
    age = _extract_labeled_line(basic, "年龄")
    if age:
        current_state["age"] = age
    _write_json(a_dir / "current_state.json", current_state)

    # habits.json
    behavioral_text = sections.get("行为模式", "")
    habits_raw = _extract_bullets(behavioral_text)
    habits: dict[str, list[dict[str, str]]] = {"habits": []}
    if habits_raw:
        habits["habits"] = [{"description": h, "category": "behavioral"} for h in habits_raw]
    _write_json(a_dir / "habits.json", habits)

    # secrets.json
    _write_json(a_dir / "secrets.json", {})

    # skills.json
    _write_json(a_dir / "skills.json", [])

    # relationships.json
    _write_json(a_dir / "relationships.json", {})

    return result


def bootstrap_all(project_root: Path) -> dict[str, int]:
    """处理 ``设定集/*卡*.md`` 中所有角色卡。"""
    settings_dir = project_root / "设定集"
    if not settings_dir.is_dir():
        log.warning("设定集目录不存在: %s", settings_dir)
        return {"processed": 0, "skipped": 0, "errors": 0}

    md_files = sorted(settings_dir.glob("*卡*.md"))
    if not md_files:
        log.warning("未找到角色卡文件 (*卡*.md) in %s", settings_dir)
        return {"processed": 0, "skipped": 0, "errors": 0}

    results = {"processed": 0, "skipped": 0, "errors": 0}
    actors_created: list[str] = []

    for md_path in md_files:
        log.info("处理: %s", md_path.name)
        try:
            actor_info = bootstrap_actor_from_markdown(md_path, project_root)
            if actor_info is None:
                results["skipped"] += 1
            else:
                results["processed"] += 1
                actors_created.append(f"{actor_info['name']}({actor_info['actor_id']})")
        except Exception:
            log.exception("处理 %s 时出错", md_path.name)
            results["errors"] += 1

    if actors_created:
        log.info("创建的角色: %s", ", ".join(actors_created))
    return results


# ── CLI ─────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="从设定集角色卡 markdown → theater/actors/ actor profile",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  %(prog)s --project-root 特级 --all\n"
            "  %(prog)s --project-root 特级 --file 设定集/主角卡.md\n"
        ),
    )
    ap.add_argument("--project-root", required=True, help="项目根目录")
    ap.add_argument("--all", action="store_true", help="处理所有 *卡*.md 文件")
    ap.add_argument("--file", help="单张角色卡路径（相对于 project-root）")
    return ap


def main() -> None:
    ap = _build_parser()
    args = ap.parse_args()

    project_root = Path(args.project_root)
    if not project_root.is_dir():
        log.error("项目目录不存在: %s", project_root)
        sys.exit(1)

    if args.all and args.file:
        log.error("--all 和 --file 不能同时使用")
        sys.exit(1)

    if args.all:
        r = bootstrap_all(project_root)
        log.info(
            "完成: 处理 %d, 跳过 %d, 错误 %d",
            r["processed"], r["skipped"], r["errors"],
        )
    elif args.file:
        md_path = project_root / args.file
        if not md_path.is_file():
            log.error("文件不存在: %s", md_path)
            sys.exit(1)
        info = bootstrap_actor_from_markdown(md_path, project_root)
        if info:
            log.info("成功创建角色: %s (%s)", info["name"], info["actor_id"])
        else:
            sys.exit(1)
    else:
        log.error("请指定 --all 或 --file")
        sys.exit(1)


if __name__ == "__main__":
    main()
