#!/usr/bin/env python3
"""批量同步章节数据到 index.db，支持两种 summary 格式：
1. 标准格式: # 第N章 标题 - 章节摘要
2. YAML frontmatter 格式: ---\nchapter: 0031\n...
"""
import sqlite3
import re
import json
import hashlib
from pathlib import Path

project_root = Path(r"E:\末世降临：我在地摊买了本成神指南 - 副本")
summaries_dir = project_root / ".webnovel" / "summaries"
db_path = project_root / ".webnovel" / "index.db"
state_path = project_root / ".webnovel" / "state.json"

state = json.loads(state_path.read_text(encoding="utf-8"))
chapter_meta = state.get("chapter_meta", {})

summary_files = sorted(summaries_dir.glob("ch*.md"))
print(f"Found {len(summary_files)} summary files")

chapters_data = []
for sf in summary_files:
    content = sf.read_text(encoding="utf-8")
    first_line = content.split("\n")[0]

    # 格式1: YAML frontmatter
    if first_line.strip() == "---":
        fm_match = re.search(r"chapter:\s*(\d+)", content)
        if not fm_match:
            print(f"WARN: 无法解析章节号 {sf.name}")
            continue
        ch_num = int(fm_match.group(1))

        # 从 state.json 获取标题
        meta = chapter_meta.get(str(ch_num), {})
        if isinstance(meta, dict):
            title = meta.get("title", "")
        else:
            title = ""

        # 提取摘要（从 ## 剧情摘要 到下一个 ##）
        summary_match = re.search(r"## 剧情摘要\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
        summary = summary_match.group(1).strip() if summary_match else ""

        # 提取 location
        loc_match = re.search(r'location:\s*"([^"]+)"', content)
        location = loc_match.group(1) if loc_match else ""

        # 提取 characters
        chars_match = re.search(r'characters:\s*\[([^\]]+)\]', content)
        if chars_match:
            chars_raw = chars_match.group(1)
            characters = [c.strip().strip('"').strip("'") for c in chars_raw.split(",")]
        else:
            characters = []

    # 格式2: 标准 markdown 标题
    else:
        m = re.match(r"# 第(\d+)章 (.+?)(?: - 章节摘要)?$", first_line)
        if not m:
            print(f"WARN: 无法解析 {sf.name}: {first_line[:60]}")
            continue

        ch_num = int(m.group(1))
        title = m.group(2).strip()
        location = ""
        characters = []

        summary_match = re.search(r"## 本章发生了什么\n\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
        summary = summary_match.group(1).strip() if summary_match else ""

    # 从 state.json 获取字数
    meta_entry = chapter_meta.get(str(ch_num), {})
    wc = meta_entry.get("word_count", 0) if isinstance(meta_entry, dict) else 0

    chapters_data.append({
        "chapter": ch_num,
        "title": title,
        "summary": summary,
        "word_count": wc,
        "location": location,
        "characters": characters,
    })

print(f"Parsed {len(chapters_data)} chapters")

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# 添加缺失列
for col_sql in [
    "ALTER TABLE chapters ADD COLUMN content_hash TEXT",
    "ALTER TABLE chapters ADD COLUMN updated_at TIMESTAMP",
]:
    try:
        cursor.execute(col_sql)
    except sqlite3.OperationalError:
        pass

for c in chapters_data:
    content_hash = hashlib.md5(
        f"{c['title']}|{c['location']}|{c['word_count']}|{c['summary']}|{len(c['characters'])}".encode("utf-8")
    ).hexdigest()
    cursor.execute(
        """
        INSERT OR REPLACE INTO chapters
        (chapter, title, location, word_count, characters, summary, content_hash, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            c["chapter"],
            c["title"],
            c["location"],
            c["word_count"],
            json.dumps(c["characters"], ensure_ascii=False),
            c["summary"],
            content_hash,
        ),
    )

conn.commit()
count = cursor.execute("SELECT COUNT(*) FROM chapters").fetchone()[0]
print(f"Inserted/updated {len(chapters_data)} chapters. Total in DB: {count}")

# 验证
rows = cursor.execute("SELECT chapter, title, word_count, location FROM chapters ORDER BY chapter ASC").fetchall()
for r in rows[:5]:
    print(f"  Ch{r[0]}: {r[1]} ({r[2]}字, {r[3]})")
print("  ...")
for r in rows[-3:]:
    print(f"  Ch{r[0]}: {r[1]} ({r[2]}字, {r[3]})")

conn.close()
