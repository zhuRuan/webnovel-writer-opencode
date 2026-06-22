import csv
import io
import json
from pathlib import Path

from .base import BaseDAO


class DirectorDAO(BaseDAO):
    """导演文风与写作技法 DAO — director_style / chapter_techniques / writing_techniques"""

    _PRIMARY_CATEGORY_MAP = {
        '对话': '对话', '对白': '对话', '潜台词': '对话',
        '情感': '情感', '情绪': '情感',
        '场景': '场景', '环境': '场景', '描写': '场景', '感官': '场景',
        '节奏': '节奏', '连载': '节奏', '高潮': '节奏',
        '情节': '情节', '冲突': '情节', '战斗': '情节', '反转': '情节', '悬疑': '情节', '推理': '情节',
        '布局': '情节', '伏笔': '情节', '智斗': '情节', '结局': '情节',
        '人物': '人物', '动作': '人物', '表现': '人物',
        '文笔': '文笔', '修辞': '文笔', '句法': '文笔', '文体': '文笔', '叙事': '文笔',
        '设定': '情节', '设定执行': '情节', '规则': '情节',
        '种田': '情节', '快穿': '情节', '仙侠': '情节', '幻言': '情节', '年代': '情节',
        '历史': '情节', '游戏': '情节', '科幻': '情节', '短篇': '情节', '古言': '情节', '世情': '情节',
        '视角': '文笔', '章纲': '情节', '大纲': '情节', '整合': '情节', '衍生': '情节', '结构': '情节',
        '修行': '情节', '竞技': '情节', '经营': '情节', '恐怖': '情节',
    }

    def _ensure_tables(self):
        """确保相关表存在（兼容旧 index.db）"""
        self._execute("""CREATE TABLE IF NOT EXISTS director_style (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            rules TEXT NOT NULL,
            priority INTEGER DEFAULT 5,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        self._execute("""CREATE TABLE IF NOT EXISTS chapter_techniques (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chapter INTEGER NOT NULL,
            technique_name TEXT NOT NULL,
            technique_category TEXT NOT NULL,
            usage_context TEXT,
            effectiveness TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        self._execute("""CREATE TABLE IF NOT EXISTS writing_techniques (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            primary_category TEXT DEFAULT '',
            sub_category TEXT,
            description TEXT NOT NULL,
            when_to_use TEXT,
            example TEXT,
            anti_pattern TEXT,
            difficulty INTEGER DEFAULT 5,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        # Migration: add primary_category column if upgrading from old schema
        try:
            self._execute("ALTER TABLE writing_techniques ADD COLUMN primary_category TEXT DEFAULT ''")
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════
    # CSV Import
    # ═══════════════════════════════════════════════════════════

    def import_from_csv(self, csv_path: str | Path | None = None) -> dict:
        """从 CSV 导入写作技法到 writing_techniques 表"""
        self._ensure_tables()  # 兼容旧 index.db
        if csv_path is None:
            csv_path = (
                Path(__file__).resolve().parents[3]
                / "references"
                / "csv"
                / "写作技法.csv"
            )
        else:
            csv_path = Path(csv_path)
        
        if not csv_path.exists():
            # Try alternative path
            alt = Path('/home/li/webnovel-writer-opencode/.opencode/references/csv/写作技法.csv')
            if alt.exists():
                csv_path = alt
            else:
                return {"imported": 0, "error": f"CSV not found: {csv_path}, also tried: {alt}"}

        content = csv_path.read_text(encoding="utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))

        imported = 0
        skipped = 0

        difficulty_map = {
            "提醒": 3,
            "知识补充": 5,
            "核心规则": 7,
            "强制": 9,
        }

        for row in reader:
            technique_name = row.get("技法名称", "").strip()
            if not technique_name:
                skipped += 1
                continue

            name = technique_name
            category = row.get("分类", "其他").strip()  # 对话/情感/场景/节奏/情节/人物/文笔
            primary_category = self._PRIMARY_CATEGORY_MAP.get(category, category)
            sub_category = row.get("技法类型", "").strip()  # 二级分类
            description = row.get("核心摘要", "").strip()
            when_to_use = row.get("适用场景", "").strip()
            anti_pattern = row.get("毒点", "").strip()

            pos = row.get("正例", "").strip()
            neg = row.get("反例", "").strip()
            example = (
                f"✅ {pos}\n❌ {neg}" if pos and neg else (pos or neg)
            )

            level = row.get("层级", "知识补充").strip()
            difficulty = difficulty_map.get(level, 5)

            try:
                self._execute(
                    """INSERT OR REPLACE INTO writing_techniques
                       (name, category, primary_category, sub_category, description,
                        when_to_use, example, anti_pattern, difficulty)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        name,
                        category,
                        primary_category,
                        sub_category,
                        description,
                        when_to_use,
                        example,
                        anti_pattern,
                        difficulty,
                    ),
                )
                imported += 1
            except Exception:
                skipped += 1

        return {"imported": imported, "skipped": skipped, "total": imported + skipped}

    # ═══════════════════════════════════════════════════════════
    # Director Style
    # ═══════════════════════════════════════════════════════════

    def list_styles(self, category=None, active_only=True):
        where = ["1=1"]
        params = []
        if active_only:
            where.append("is_active = 1")
        if category:
            where.append("category = ?")
            params.append(category)
        where_clause = " AND ".join(where)
        return self._fetch(
            f"SELECT * FROM director_style WHERE {where_clause} ORDER BY priority DESC, id ASC",
            tuple(params),
        )

    def upsert_style(self, data):
        style_id = data.get("id")
        if style_id and self._exists("director_style", "id = ?", (style_id,)):
            set_fields = []
            set_params = []
            for col in ("name", "category", "description", "rules", "priority", "is_active"):
                if col in data:
                    set_fields.append(f"{col} = ?")
                    set_params.append(data[col])
            if set_fields:
                set_params.append(style_id)
                self._execute(
                    f"UPDATE director_style SET {', '.join(set_fields)} WHERE id = ?",
                    tuple(set_params),
                )
            rows = self._fetch("SELECT * FROM director_style WHERE id = ?", (style_id,))
            return rows[0] if rows else {}
        else:
            rowid = self._execute(
                """INSERT INTO director_style (name, category, description, rules, priority, is_active)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    data.get("name", ""),
                    data.get("category", ""),
                    data.get("description", ""),
                    data.get("rules", "[]"),
                    data.get("priority", 5),
                    data.get("is_active", 1),
                ),
            )
            rows = self._fetch("SELECT * FROM director_style WHERE id = ?", (rowid,))
            return rows[0] if rows else {}

    def get_active_styles_prompt(self):
        styles = self.list_styles(active_only=True)
        if not styles:
            return ""

        lines = ["## 导演文风规则\n"]
        for s in styles:
            name = s["name"]
            desc = s["description"]
            lines.append(f"- **{name}**: {desc}")
            try:
                rules = json.loads(s.get("rules", "[]"))
            except (json.JSONDecodeError, TypeError):
                rules = []
            for r in rules:
                if isinstance(r, dict):
                    rule_text = r.get("rule", "")
                    example_bad = r.get("example_bad", "")
                    example_good = r.get("example_good", "")
                    lines.append(f"  - {rule_text}")
                    if example_bad:
                        lines.append(f"    - ❌ 反面: {example_bad}")
                    if example_good:
                        lines.append(f"    - ✅ 正面: {example_good}")
            lines.append("")
        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════
    # Writing Techniques
    # ═══════════════════════════════════════════════════════════

    def list_techniques(self, category=None):
        if category:
            return self._fetch(
                "SELECT * FROM writing_techniques WHERE category = ? ORDER BY name",
                (category,),
            )
        return self._fetch("SELECT * FROM writing_techniques ORDER BY category, name")

    def search_techniques(self, query, category=None):
        if category:
            return self._fetch(
                """SELECT * FROM writing_techniques
                   WHERE category = ? AND (name LIKE ? OR description LIKE ?)
                   ORDER BY name""",
                (category, f"%{query}%", f"%{query}%"),
            )
        return self._fetch(
            """SELECT * FROM writing_techniques
               WHERE name LIKE ? OR description LIKE ?
               ORDER BY category, name""",
            (f"%{query}%", f"%{query}%"),
        )

    def list_by_primary_category(self) -> list[dict]:
        """按 7 大主分类列出技法，每个主分类下融合展示"""
        self._ensure_tables()
        rows = self._fetch("""
            SELECT primary_category, category, sub_category, name, description,
                   when_to_use, example, anti_pattern, difficulty
            FROM writing_techniques
            ORDER BY primary_category, difficulty DESC
        """)

        groups = {}
        for r in rows:
            pc = r['primary_category'] or '其他'
            if pc not in groups:
                groups[pc] = {'primary_category': pc, 'techniques': [], 'sub_categories': set()}
            groups[pc]['techniques'].append(dict(r))
            groups[pc]['sub_categories'].add(r['sub_category'])

        result = []
        for pc in ['对话', '情感', '场景', '节奏', '情节', '人物', '文笔']:
            if pc in groups:
                g = groups[pc]
                g['sub_categories'] = list(g['sub_categories'])
                g['count'] = len(g['techniques'])
                result.append(g)

        return result

    # ═══════════════════════════════════════════════════════════
    # Chapter Technique Tracking
    # ═══════════════════════════════════════════════════════════

    def track_technique(self, chapter, name, category, context=""):
        rowid = self._execute(
            """INSERT INTO chapter_techniques
               (chapter, technique_name, technique_category, usage_context)
               VALUES (?, ?, ?, ?)""",
            (chapter, name, category, context),
        )
        rows = self._fetch("SELECT * FROM chapter_techniques WHERE id = ?", (rowid,))
        return rows[0] if rows else {}

    def get_chapter_techniques(self, chapter):
        return self._fetch(
            "SELECT * FROM chapter_techniques WHERE chapter = ? ORDER BY id",
            (chapter,),
        )

    # ═══════════════════════════════════════════════════════════
    # Seed Defaults
    # ═══════════════════════════════════════════════════════════

    def seed_defaults(self):
        """首次初始化：导入 CSV 技法 + 种子默认风格规则"""
        self.seed_style_rules()
        self.seed_techniques()

    def seed_style_rules(self):
        """种子默认导演风格规则"""
        row = self._fetch("SELECT COUNT(*) as c FROM director_style")
        count = row[0]["c"] if row else 0
        if count > 0:
            return

        defaults = [
            (
                "冷峻克制", "叙事语调",
                "描述时避免情绪化词汇，用动作和生理反应表达情绪",
                json.dumps([
                    {"rule": "禁止直白情绪词", "example_bad": "他很愤怒", "example_good": "他的手指在扳机上收紧，指节发白"}
                ], ensure_ascii=False),
                9,
            ),
            (
                "展示不告知", "描写风格",
                "不要告诉读者角色的感受，展示他们的行为",
                json.dumps([
                    {"rule": "用动作替代形容词", "example_bad": "她感到害怕", "example_good": "她的手在颤抖"}
                ], ensure_ascii=False),
                9,
            ),
            (
                "对话驱动叙事", "对话风格",
                "让对话成为叙事的骨架，动作和内心独白围绕对话展开",
                json.dumps([
                    {"rule": "对话+前置动作", "example_bad": "他说：...", "example_good": "他看着窗外，缓缓说道：..."}
                ], ensure_ascii=False),
                8,
            ),
            (
                "短句加速节奏", "节奏控制",
                "动作用短句，环境用中长句，内心独白穿插",
                json.dumps([
                    {"rule": "战斗场景句长不超过15字", "example_bad": "他迅速转身躲过了敌人的攻击", "example_good": "转身。闪避。反击。"}
                ], ensure_ascii=False),
                7,
            ),
            (
                "潜台词优先", "对话风格",
                "角色说的≠想的，对话和真实意图间应有空隙",
                json.dumps([
                    {"rule": "拒绝直白对话", "example_bad": "我恨你", "example_good": "你走吧。——他说的是走，眼神说的是留下来"}
                ], ensure_ascii=False),
                8,
            ),
        ]
        for name, cat, desc, rules, priority in defaults:
            self._execute(
                """INSERT INTO director_style (name, category, description, rules, priority, is_active)
                   VALUES (?, ?, ?, ?, ?, 1)""",
                (name, cat, desc, rules, priority),
            )

    def seed_techniques(self):
        """从 CSV 导入技法（若表为空则首次导入，否则清空重导以修正分类）"""
        self._ensure_tables()
        row = self._fetch("SELECT COUNT(*) as c FROM writing_techniques")
        count = row[0]["c"] if row else 0
        if count > 0:
            self._execute("DELETE FROM writing_techniques")
        self.import_from_csv()

    def verify_techniques(self) -> dict:
        """验证技法导入状态"""
        total_row = self._fetch("SELECT COUNT(*) as c FROM writing_techniques")
        total = total_row[0]["c"] if total_row else 0
        by_cat = self._fetch(
            "SELECT category, COUNT(*) as c FROM writing_techniques GROUP BY category"
        )
        return {
            "total": total,
            "by_category": {r["category"]: r["c"] for r in by_cat},
            "categories": len(by_cat),
        }
