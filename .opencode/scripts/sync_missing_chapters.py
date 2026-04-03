#!/usr/bin/env python3
"""从正文文件补充缺失章节到 index.db"""
import sqlite3
import re
import json
import hashlib
from pathlib import Path

project_root = Path(r"E:\末世降临：我在地摊买了本成神指南 - 副本")
zhengwen_dir = project_root / "正文" / "第1卷"
db_path = project_root / ".webnovel" / "index.db"

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# 获取已有章节
existing = set(r[0] for r in cursor.execute("SELECT chapter FROM chapters").fetchall())

# 扫描所有正文文件
md_files = sorted(zhengwen_dir.glob("第*.md"))
print(f"Found {len(md_files)} chapter files")

added = 0
for mf in md_files:
    m = re.match(r"第(\d+)章", mf.name)
    if not m:
        continue
    ch_num = int(m.group(1))
    
    if ch_num in existing:
        continue
    
    content = mf.read_text(encoding="utf-8")
    
    # 从第一行提取标题: # 第N章 标题
    first_line = content.split("\n")[0]
    title_match = re.match(r"# 第\d+章 (.+)", first_line)
    title = title_match.group(1).strip() if title_match else ""
    
    # 计算字数
    lines = content.split("\n")
    text_lines = [l for l in lines if l.strip() and not l.strip().startswith("#")]
    word_count = sum(len(re.findall(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]", line)) for line in text_lines)
    
    # 提取正文前500字作为摘要
    body_start = content.find("\n\n", content.find("\n", content.find("\n") + 1) + 1)
    if body_start == -1:
        body_start = 0
    else:
        body_start += 2
    summary = content[body_start:body_start+500].strip().replace("\n", " ")
    
    content_hash = hashlib.md5(
        f"{title}||{word_count}|{summary}|0".encode("utf-8")
    ).hexdigest()
    
    cursor.execute(
        """
        INSERT OR REPLACE INTO chapters
        (chapter, title, location, word_count, characters, summary, content_hash, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (ch_num, title, "", word_count, "[]", summary, content_hash),
    )
    added += 1
    print(f"  Added Ch{ch_num}: {title} ({word_count}字)")

conn.commit()
total = cursor.execute("SELECT COUNT(*) FROM chapters").fetchone()[0]
print(f"\nAdded {added} chapters. Total in DB: {total}")
conn.close()
