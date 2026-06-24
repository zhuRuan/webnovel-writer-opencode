import csv
import io
import json
from pathlib import Path

from .base import BaseDAO


class DirectorDAO(BaseDAO):
    """导演文风与写作技法 DAO — director_style / chapter_techniques / writing_techniques"""

    _PRIMARY_CATEGORY_MAP = {
        # === 对话 (3) ===
        '对话': '对话', '对白': '对话', '潜台词': '对话',
        # === 情感 (2) ===
        '情感': '情感', '情绪': '情感',
        # === 节奏 (4) ===
        '节奏': '节奏', '连载': '节奏', '高潮': '节奏', '逆转': '节奏',
        # === 场景 (5) ===
        '场景': '场景', '环境': '场景', '仪式': '场景', '描写': '场景', '感官': '场景',
        # === 文笔 (8) ===
        '文笔': '文笔', '修辞': '文笔', '句法': '文笔', '文体': '文笔', '叙事': '文笔', '视角': '文笔', '笔法': '文笔',
        '句式风格': '文笔',
        # === 人物 (31) ===
        '人物': '人物', '主角': '人物', '配角': '人物', '反派': '人物', '女主': '人物', '男主': '人物',
        '群像': '人物', '天才': '人物', '普通人': '人物', '白月光': '人物',
        '守护者': '人物', '导师': '人物', '盟友': '人物', '前辈': '人物', '副手': '人物', '队友': '人物',
        '幸存者': '人物', '执行者': '人物', '观察者': '人物', '分析者': '人物', '破局者': '人物', '军师': '人物',
        '冒险者': '人物', '人设': '人物', '关系': '人物', '家庭': '人物', '家族': '人物', '长辈': '人物',
        '反派体系': '人物', '角色': '人物', '动作': '人物', '表现': '人物',
        # === 情节 (63) ===
        '情节': '情节', '对决': '情节', '对峙': '情节', '战争': '情节', '复仇': '情节',
        '团战': '情节', '翻盘': '情节', '开篇': '情节', '收束': '情节', '抉择': '情节',
        '探险': '情节', '推演': '情节', '搜证': '情节', '演武': '情节', '谍战': '情节',
        '黑市': '情节', '交易': '情节', '奖励': '情节', '反转': '情节', '悬疑': '情节',
        '桥段': '情节', '梦境': '情节', '回望': '情节', '回顾': '情节', '余波': '情节',
        '日常': '情节', '番外': '情节', '重逢': '情节', '离别': '情节', '终章': '情节',
        '节庆': '情节', '审判': '情节', '审讯': '情节', '校园': '情节', '娱乐圈': '情节',
        '女频': '情节', '玄幻': '情节', '赛博': '情节', '诡异': '情节', '军事': '情节',
        '守夜': '情节', '爽点': '情节', '虐点': '情节', '诊脉': '情节', '爽点与节奏': '情节',
        '冲突': '情节', '战斗': '情节', '布局': '情节', '伏笔': '情节', '智斗': '情节',
        '结局': '情节', '设定': '情节', '规则': '情节', '推理': '情节',
        '种田': '情节', '快穿': '情节', '仙侠': '情节', '幻言': '情节', '年代': '情节',
        '历史': '情节', '游戏': '情节', '科幻': '情节', '短篇': '情节', '古言': '情节', '世情': '情节',
        '修行': '情节', '竞技': '情节', '经营': '情节', '恐怖': '情节',
        '章纲': '情节', '大纲': '情节', '整合': '情节', '衍生': '情节', '结构': '情节', '设定执行': '情节',
        '替身': '情节', '舆论': '情节', '诊断': '情节',
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
        # Migration: add source_csv column
        try:
            self._execute("ALTER TABLE writing_techniques ADD COLUMN source_csv TEXT DEFAULT ''")
        except Exception:
            pass
        # Migration: add full CSV import columns
        migrations = [
            "ALTER TABLE writing_techniques ADD COLUMN keywords TEXT DEFAULT ''",
            "ALTER TABLE writing_techniques ADD COLUMN intent_synonyms TEXT DEFAULT ''",
            "ALTER TABLE writing_techniques ADD COLUMN applicable_genres TEXT DEFAULT ''",
            "ALTER TABLE writing_techniques ADD COLUMN model_instruction TEXT DEFAULT ''",
            "ALTER TABLE writing_techniques ADD COLUMN detailed_description TEXT DEFAULT ''",
            "ALTER TABLE writing_techniques ADD COLUMN skill_tags TEXT DEFAULT ''",
            "ALTER TABLE writing_techniques ADD COLUMN code TEXT DEFAULT ''",
            "ALTER TABLE writing_techniques ADD COLUMN level_name TEXT DEFAULT ''",
            "ALTER TABLE writing_techniques ADD COLUMN positive_example TEXT DEFAULT ''",
            "ALTER TABLE writing_techniques ADD COLUMN negative_example TEXT DEFAULT ''",
        ]
        for m in migrations:
            try:
                self._execute(m)
            except Exception:
                pass
        # reference_entries: 场景写法/桥段套路/人设与关系/爽点与节奏/金手指与设定
        self._execute("""CREATE TABLE IF NOT EXISTS reference_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            source_csv TEXT NOT NULL,
            category TEXT DEFAULT '',
            sub_category TEXT DEFAULT '',
            description TEXT NOT NULL,
            keywords TEXT DEFAULT '',
            intent_synonyms TEXT DEFAULT '',
            applicable_genres TEXT DEFAULT '',
            model_instruction TEXT DEFAULT '',
            detailed_description TEXT DEFAULT '',
            level_name TEXT DEFAULT '',
            code TEXT DEFAULT '',
            skill_tags TEXT DEFAULT '',
            positive_example TEXT DEFAULT '',
            negative_example TEXT DEFAULT '',
            anti_pattern TEXT DEFAULT '',
            difficulty INTEGER DEFAULT 5,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        # Migration: anti_patterns table (replaces anti_patterns.json)
        self._execute("""CREATE TABLE IF NOT EXISTS anti_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            source TEXT DEFAULT '',
            category TEXT DEFAULT '禁写',
            genre TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

    # ═══════════════════════════════════════════════════════════
    # CSV Import
    # ═══════════════════════════════════════════════════════════

    def import_from_csv(self, csv_path: str | Path | None = None, source_label: str = "") -> dict:
        """从 CSV 导入写作技法到 writing_techniques 表。
        支持 9 种 CSV 格式：自动检测名称列，表专属列合并到 detailed_description。
        """
        self._ensure_tables()
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
            alt = Path('/home/li/webnovel-writer-opencode/.opencode/references/csv') / csv_path.name
            if alt.exists():
                csv_path = alt
            else:
                return {"imported": 0, "error": f"CSV not found: {csv_path}"}

        content = csv_path.read_text(encoding="utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        if reader.fieldnames is None:
            return {"imported": 0, "error": "CSV has no headers"}

        # Auto-detect which column holds the technique/item name
        name_candidates = [
            "技法名称", "人设类型", "模式名称", "桥段名称",
            "节奏类型", "设定类型", "命名对象", "题材/流派", "题材",
        ]
        name_col = None
        for cand in name_candidates:
            if cand in reader.fieldnames:
                name_col = cand
                break
        if name_col is None:
            return {"imported": 0, "error": f"No name column found; headers: {reader.fieldnames}"}

        # Columns present in ALL 9 CSVs (always mapped to dedicated fields)
        common_cols = {
            "编号", "适用技能", "分类", "层级", "关键词", "意图与同义词",
            "适用题材", "大模型指令", "核心摘要", "详细展开",
        }
        # Columns that get mapped to dedicated fields (may be absent in some CSVs)
        mapped_cols = {"技法类型", "适用场景", "毒点", "正例", "反例"}

        imported = 0
        skipped = 0

        difficulty_map = {
            "提醒": 3, "缺陷补偿": 4, "知识补充": 5, "核心规则": 7, "强制": 9,
        }

        for row in reader:
            technique_name = row.get(name_col, "").strip()
            if not technique_name:
                skipped += 1
                continue

            code = row.get("编号", "").strip()
            # Append code to name for global uniqueness (codes like NR-001, WT-001 are unique)
            name = f"{technique_name} ({code})" if code else technique_name
            category = row.get("分类", "其他").strip()
            primary_category = self._PRIMARY_CATEGORY_MAP.get(category, category)
            sub_category = row.get("技法类型", "").strip()
            description = row.get("核心摘要", "").strip()
            when_to_use = row.get("适用场景", "").strip()
            anti_pattern = row.get("毒点", "").strip()

            positive_example = row.get("正例", "").strip()
            negative_example = row.get("反例", "").strip()
            example = (f"✅ {positive_example}\n❌ {negative_example}" 
                       if positive_example and negative_example 
                       else (positive_example or negative_example))

            level_name = row.get("层级", "知识补充").strip()
            difficulty = difficulty_map.get(level_name, 5)

            keywords = row.get("关键词", "").strip()
            intent_synonyms = row.get("意图与同义词", "").strip()
            applicable_genres = row.get("适用题材", "").strip()
            model_instruction = row.get("大模型指令", "").strip()
            detailed_description = row.get("详细展开", "").strip()
            skill_tags = row.get("适用技能", "").strip()

            # Collect table-specific extra columns → append to detailed_description
            extra_parts = []
            for k, v in row.items():
                if k in common_cols or k in mapped_cols or k == name_col:
                    continue
                if v.strip():
                    extra_parts.append(f"【{k}】{v.strip()}")
            if extra_parts:
                extras = "\n".join(extra_parts)
                detailed_description = (
                    f"{detailed_description}\n\n{extras}" if detailed_description else extras
                )

            try:
                self._execute(
                    """INSERT OR IGNORE INTO writing_techniques
                       (name, source_csv, category, primary_category, sub_category,
                        description, when_to_use, example, anti_pattern, difficulty,
                        keywords, intent_synonyms, applicable_genres, model_instruction,
                        detailed_description, skill_tags, code, level_name,
                        positive_example, negative_example)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        name, source_label, category, primary_category, sub_category,
                        description, when_to_use, example, anti_pattern, difficulty,
                        keywords, intent_synonyms, applicable_genres, model_instruction,
                        detailed_description, skill_tags, code, level_name,
                        positive_example, negative_example,
                    ),
                )
                imported += 1
            except Exception:
                skipped += 1

        return {"imported": imported, "skipped": skipped, "total": imported + skipped}

    def import_to_reference(self, csv_path: "str | Path", source_label: str = "") -> dict:
        """从 CSV 导入到 reference_entries 表（场景写法/桥段套路/人设/爽点/金手指）。"""
        import csv as csv_module
        import io as io_module
        from pathlib import Path as Path_cls
        csv_path = Path_cls(csv_path)
        content = csv_path.read_text(encoding="utf-8-sig")
        reader = csv_module.DictReader(io_module.StringIO(content))

        name_candidates = ["技法名称", "模式名称", "桥段名称", "人设类型", "节奏类型", "设定类型",
                          "命名对象", "题材/流派", "题材"]
        name_col = None
        for cand in name_candidates:
            if cand in reader.fieldnames:
                name_col = cand
                break
        if name_col is None:
            return {"imported": 0, "error": f"No name column in {csv_path.name}"}

        imported = 0
        for row in reader:
            name = (row.get(name_col) or "").strip()
            if not name:
                continue
            code = row.get("编号", "").strip()
            display_name = f"{name} ({code})" if code else name

            positive_example = row.get("正例", "") or row.get("示例片段", "") or ""
            negative_example = row.get("反例", "") or row.get("反面写法", "") or ""
            anti_pattern = row.get("毒点", "") or row.get("忌讳写法", "") or row.get("常见崩盘误区", "") or ""
            description = row.get("核心摘要", "") or row.get("说明", "") or row.get("核心爽点", "") or ""
            detailed_description = row.get("详细展开", "") or ""
            model_instruction = row.get("大模型指令", "") or ""
            keywords = row.get("关键词", "") or ""
            intent_synonyms = row.get("意图与同义词", "") or ""
            applicable_genres = row.get("适用题材", "") or ""
            skill_tags = row.get("适用技能", "") or ""
            category = row.get("分类", "") or ""
            level_name = row.get("层级", "知识补充") or ""

            # Collect table-specific extra columns → append to detailed_description
            # (mirrors import_from_csv extra_parts logic)
            extra_parts = []
            common_cols = {"编号", "适用技能", "分类", "层级", "关键词", "意图与同义词",
                           "适用题材", "大模型指令", "核心摘要", "详细展开"}
            mapped_cols = {"毒点", "忌讳写法", "常见崩盘误区", "正例", "反例", "示例片段",
                           "反面写法", "说明", "核心爽点", "模式名称", "桥段名称",
                           "人设类型", "节奏类型", "设定类型", "技法名称", "命名对象", "规则"}
            for k, v in row.items():
                if k in common_cols or k in mapped_cols or (name_col and k == name_col):
                    continue
                if v and v.strip():
                    extra_parts.append(f"【{k}】{v.strip()}")
            if extra_parts:
                extras = "\n".join(extra_parts)
                detailed_description = f"{detailed_description}\n\n{extras}" if detailed_description else extras

            self._execute(
                """INSERT OR IGNORE INTO reference_entries
                   (name, source_csv, category, description, keywords, intent_synonyms,
                    applicable_genres, model_instruction, detailed_description,
                    level_name, code, skill_tags,
                    positive_example, negative_example, anti_pattern, difficulty)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (display_name, source_label, category, description, keywords, intent_synonyms,
                 applicable_genres, model_instruction, detailed_description,
                 level_name, code, skill_tags,
                 positive_example, negative_example, anti_pattern, 5),
            )
            imported += 1

        return {"imported": imported, "source": source_label}

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

    def toggle_style(self, style_id, is_active=None):
        """切换或设置 director_style 的激活状态。is_active=None 时自动反转到当前状态。"""
        if is_active is None:
            rows = self._fetch("SELECT is_active FROM director_style WHERE id = ?", (style_id,))
            if not rows:
                return None
            is_active = 0 if rows[0]["is_active"] else 1
        else:
            is_active = int(is_active)
        self._execute("UPDATE director_style SET is_active = ? WHERE id = ?", (is_active, style_id))
        rows = self._fetch("SELECT * FROM director_style WHERE id = ?", (style_id,))
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
            SELECT id, primary_category, category, sub_category, name, description,
                   when_to_use, example, anti_pattern, difficulty,
                   keywords, intent_synonyms, applicable_genres, model_instruction,
                   detailed_description, skill_tags, code, level_name, source_csv,
                   positive_example, negative_example
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

        # Primary 7 categories first, then remaining sorted alphabetically
        primary_order = ['对话', '情感', '场景', '节奏', '情节', '人物', '文笔']
        result = []
        for pc in primary_order:
            if pc in groups:
                g = groups[pc]
                g['sub_categories'] = list(g['sub_categories'])
                g['count'] = len(g['techniques'])
                result.append(g)
        # Include all other categories (e.g. 桥段套路, 金手指与设定, etc.)
        for pc in sorted(groups):
            if pc not in primary_order:
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

    def seed_techniques(self, force=False):
        """从 CSV 导入写作技法到 writing_techniques（仅 写作技法.csv）。
        其余 5 个 CSV 导入到 reference_entries 表。
        """
        self._ensure_tables()
        row = self._fetch("SELECT COUNT(*) as c FROM writing_techniques")
        count = row[0]["c"] if row else 0
        if count > 0:
            if force:
                self._execute("DELETE FROM writing_techniques")
            else:
                self.seed_references()
                return

        csv_dir = Path(__file__).resolve().parents[3] / "references" / "csv"
        if not csv_dir.exists():
            csv_dir = Path('/home/li/webnovel-writer-opencode/.opencode/references/csv')

        wt_csv = csv_dir / "写作技法.csv"
        total_imported = 0
        if wt_csv.exists():
            result = self.import_from_csv(str(wt_csv), source_label="写作技法")
            total_imported += result.get("imported", 0)

        self.seed_references(force=True)

        # Clean non-WT entries from writing_techniques
        self._execute("DELETE FROM writing_techniques WHERE source_csv != '写作技法' AND source_csv != ''")
        return total_imported

    def seed_references(self, force: bool = False):
        self._ensure_tables()
        row = self._fetch("SELECT COUNT(*) as c FROM reference_entries")
        count = row[0]["c"] if row else 0
        if count > 0:
            if force:
                self._execute("DELETE FROM reference_entries")
            else:
                return

        csv_dir = Path(__file__).resolve().parents[3] / "references" / "csv"
        if not csv_dir.exists():
            csv_dir = Path('/home/li/webnovel-writer-opencode/.opencode/references/csv')

        sources = [
            ("场景写法", "场景写法.csv"),
            ("桥段套路", "桥段套路.csv"),
            ("人设与关系", "人设与关系.csv"),
            ("爽点与节奏", "爽点与节奏.csv"),
            ("金手指与设定", "金手指与设定.csv"),
            ("命名规则", "命名规则.csv"),
            ("题材与调性推理", "题材与调性推理.csv"),
            ("裁决规则", "裁决规则.csv"),
        ]
        for label, filename in sources:
            csv_path = csv_dir / filename
            if csv_path.exists():
                self.import_to_reference(str(csv_path), label)

    def create_technique(self, data: dict) -> dict:
        """手动创建单条写作技法."""
        self._ensure_tables()
        name = (data.get("name") or "").strip()
        if not name:
            raise ValueError("name 不能为空")
        primary_category = (data.get("primary_category") or "").strip()
        sub_category = (data.get("sub_category") or "").strip()
        description = (data.get("description") or "").strip()
        source_csv = (data.get("source_csv") or "").strip()
        category = primary_category  # category mirrors primary_category for simplicity

        rowid = self._execute(
            """INSERT INTO writing_techniques
               (name, source_csv, category, primary_category, sub_category,
                description, difficulty)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, source_csv, category, primary_category, sub_category, description, 5),
        )
        rows = self._fetch("SELECT * FROM writing_techniques WHERE id = ?", (rowid,))
        return rows[0] if rows else {}

    def update_technique(self, tech_id: int, data: dict) -> dict:
        """更新单条写作技法."""
        self._ensure_tables()
        existing = self._fetch("SELECT * FROM writing_techniques WHERE id = ?", (tech_id,))
        if not existing:
            raise ValueError(f"技法不存在: id={tech_id}")

        updates = {}
        for field in ("name", "description", "sub_category", "primary_category", "source_csv",
                       "when_to_use", "applicable_genres", "keywords", "detailed_description",
                       "model_instruction", "example", "anti_pattern"):
            if field in data and data[field] is not None:
                updates[field] = data[field].strip() if isinstance(data[field], str) else data[field]

        if "primary_category" in updates:
            updates["category"] = updates["primary_category"]

        if not updates:
            return existing[0]

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values())
        values.append(tech_id)

        self._execute(f"UPDATE writing_techniques SET {set_clause} WHERE id = ?", tuple(values))
        rows = self._fetch("SELECT * FROM writing_techniques WHERE id = ?", (tech_id,))
        return rows[0] if rows else {}

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

    # ═══════════════════════════════════════════════════════════
    # Anti-Patterns (replaces anti_patterns.json)
    # ═══════════════════════════════════════════════════════════

    def list_anti_patterns(self) -> list[dict]:
        return self._fetch("SELECT * FROM anti_patterns ORDER BY id ASC")

    def add_anti_pattern(self, text: str, source: str = "", category: str = "禁写", genre: str = "") -> dict:
        text = text.strip()
        if not text:
            raise ValueError("text 不能为空")
        existing = self._fetch("SELECT id FROM anti_patterns WHERE text = ?", (text,))
        if existing:
            raise ValueError("该反模式已存在")
        row_id = self._execute(
            "INSERT INTO anti_patterns (text, source, category, genre) VALUES (?, ?, ?, ?)",
            (text, source, category, genre),
        )
        rows = self._fetch("SELECT * FROM anti_patterns WHERE id = ?", (row_id,))
        return rows[0] if rows else {"ok": True}

    def get_anti_patterns_count(self) -> int:
        row = self._fetch("SELECT COUNT(*) as c FROM anti_patterns")
        return row[0]["c"] if row else 0

    def add_anti_patterns_from_csv(self, csv_path=None) -> dict:
        import csv
        import io
        from pathlib import Path
        if csv_path is None:
            csv_path = Path(__file__).resolve().parents[3] / "references" / "csv" / "裁决规则.csv"
        if not Path(csv_path).is_file():
            return {"imported": 0, "error": "File not found"}
        content = Path(csv_path).read_text(encoding="utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        imported = 0
        for row in reader:
            ap = (row.get("反模式") or "").strip()
            genre = (row.get("分类") or "通用").strip()
            if ap:
                for item in ap.split("|"):
                    item = item.strip()
                    if item:
                        self._execute(
                            "INSERT OR IGNORE INTO anti_patterns (text, source, category, genre) VALUES (?, ?, ?, ?)",
                            (item, "裁决规则.csv", "禁写", genre),
                        )
                        imported += 1
        return {"imported": imported}

    def delete_anti_pattern(self, pattern_id: int) -> dict:
        self._execute("DELETE FROM anti_patterns WHERE id=?", (pattern_id,))
        return {"deleted": True}
