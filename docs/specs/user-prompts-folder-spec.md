# 用户自定义提示词文件夹 — 架构分析与规范

## 1. 背景

用户反馈：自己制作了一套提示词放到小说目录里，让 AI 调用，基本解决了文风控制问题。不需要可视化编辑器，只需要一个文件夹入口。

## 2. 现有架构分析

### 2.1 上下文组装链路

```
context_manager.build_context(chapter)
  → _build_pack(chapter)
      → 加载 17 个 section（core/scene/global/...）
      → context_ranker.rank_pack() 排序裁剪
  → _assemble_json_payload(pack, template)
      → 按 TEMPLATE_WEIGHTS 权重分配 token 预算
      → 写入 .webnovel/runtime/chapter-NNN.context.json
```

### 2.2 现有的"用户配置"注入点

| 注入点 | 文件 | 格式 | 位置 |
|--------|------|------|------|
| `preferences` | `.webnovel/preferences.json` | JSON | pack 的一个 section |
| `global.worldview_skeleton` | `设定集/世界观.md` | Markdown | global 子字段 |
| `global.power_system_skeleton` | `设定集/力量体系.md` | Markdown | global 子字段 |
| `global.style_contract_ref` | `设定集/风格契约.md` | Markdown | global 子字段 |
| `master_constraints` | `.story-system/MASTER_SETTING.json` | JSON | 注入写作任务书 |
| `anti_patterns` | `.story-system/anti_patterns.json` | JSON | 注入审查上下文 |
| `dynamic_context` | `.story-system/chapters/chapter_NNN.json` | JSON | BM25 检索注入 |

### 2.3 权重体系

```python
# 3 个权重组
TEMPLATE_WEIGHTS = {
    "plot":       {"core": 0.40, "scene": 0.35, "global": 0.25},
    "battle":     {"core": 0.35, "scene": 0.45, "global": 0.20},
    "emotion":    {"core": 0.45, "scene": 0.35, "global": 0.20},
    "transition": {"core": 0.50, "scene": 0.25, "global": 0.25},
}

# EXTRA_SECTIONS 不受权重裁剪，始终包含
EXTRA_SECTIONS = {"story_skeleton", "memory", "long_term_memory", "preferences"}
```

### 2.4 `_load_setting()` 已有模式

```python
def _load_setting(self, keyword: str) -> str:
    settings_dir = self.config.settings_dir  # → 设定集/
    candidates = [settings_dir / f"{keyword}.md"]
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8")
    matches = list(settings_dir.glob(f"*{keyword}*.md"))
    if matches:
        return matches[0].read_text(encoding="utf-8")
    return f"[{keyword}设定未找到]"
```

这个模式可以复用来加载 `设定集/prompts/*.md`。

## 3. 方案设计

### 3.1 文件夹位置

```
书项目/
├── 设定集/
│   ├── 世界观.md
│   ├── 力量体系.md
│   ├── 风格契约.md
│   └── prompts/          ← 新增
│       ├── 文风.md        # 全局文风约束
│       ├── 对话风格.md    # 对话专项
│       └── 禁忌.md        # 禁忌清单
```

选择 `设定集/prompts/` 而非 `.webnovel/prompts/` 的原因：
- 用户已经习惯在 `设定集/` 里放配置文件
- `.webnovel/` 是系统目录，用户不应该直接编辑
- 与 `世界观.md`、`力量体系.md` 同级，概念一致

### 3.2 文件格式

纯 Markdown，无特殊格式要求。每个文件是一个独立的"约束包"。

```markdown
# 文风

- 对话要口语化，像真人说话，不要书面语
- 动作描写要短促有力，不要冗长的形容词堆砌
- 每段不超过 3 句话
- 禁止使用"缓缓""淡淡""微微"
```

系统按文件名排序后拼接，注入 `global` 权重组。

### 3.3 注入位置

在 `_build_pack()` 中，扩展 `global_ctx`：

```python
global_ctx = {
    "worldview_skeleton": self._load_setting("世界观"),
    "power_system_skeleton": self._load_setting("力量体系"),
    "style_contract_ref": self._load_setting("风格契约"),
    "user_prompts": self._load_user_prompts(),  # 新增
}
```

`user_prompts` 是一个字符串，由所有 `.md` 文件按文件名排序拼接而成。

### 3.4 优先级

用户提示词的优先级应**高于**系统自动生成的 `master_constraints`，因为用户明确表达的意图应优先。但**低于**章级合同的 `forbidden_zones`（硬约束）。

实际注入顺序（写作任务书中）：
1. 章级约束（chapter_directive.goal, forbidden_zones）— 最高
2. **用户自定义提示词** — 高于系统推导
3. master_constraints（系统自动生成）— 中等
4. dynamic_context（BM25 检索的写作技法）— 参考

### 3.5 与现有机制的关系

| 机制 | 用途 | 与 prompts/ 的关系 |
|------|------|-------------------|
| `master_constraints` | 系统自动生成的全局文风 | prompts/ 可覆盖/补充 |
| `anti_patterns` | 系统提取的禁止模式 | prompts/ 可追加 |
| `风格契约.md` | 设定集中的风格参考 | 共存，prompts/ 更灵活 |
| `preferences.json` | 用户偏好（JSON 格式） | prompts/ 替代其文风部分 |
| `polish-guide.md` | 润色阶段的 AI 味规则 | 不冲突，prompts/ 是写作阶段 |

## 4. 实现方案

### 4.1 context_manager.py 改动

```python
def _load_user_prompts(self) -> str:
    """加载设定集/prompts/ 下的所有 .md 文件，按文件名排序拼接。"""
    prompts_dir = self.config.settings_dir / "prompts"
    if not prompts_dir.is_dir():
        return ""
    parts = []
    for f in sorted(prompts_dir.glob("*.md")):
        try:
            text = f.read_text(encoding="utf-8").strip()
            if text:
                parts.append(f"## {f.stem}\n\n{text}")
        except Exception:
            continue
    return "\n\n---\n\n".join(parts)
```

在 `_build_pack()` 中调用：
```python
global_ctx = {
    "worldview_skeleton": self._load_setting("世界观"),
    "power_system_skeleton": self._load_setting("力量体系"),
    "style_contract_ref": self._load_setting("风格契约"),
    "user_prompts": self._load_user_prompts(),
}
```

### 4.2 权重处理

`user_prompts` 属于 `global` 权重组，与 `worldview_skeleton` 等共享 token 预算。不需要新增权重，因为：

- `global` 的权重（0.20-0.35）已经分配了足够空间
- 用户提示词通常很短（几百字），不会挤占其他 section
- 如果用户写了很长的提示词，context_ranker 会自动裁剪

### 4.3 Dashboard 集成

Dashboard 的文风编辑器（`/style` 页面）可以新增一个 Tab：

| Tab | 数据源 | 读写 |
|-----|--------|------|
| 用户提示词 | `设定集/prompts/*.md` | 读写（编辑+新增+删除） |

这样用户既可以直接编辑文件，也可以通过 Dashboard 编辑。

## 5. 验证标准

- [ ] `设定集/prompts/` 目录下的 `.md` 文件被自动加载
- [ ] 文件按文件名排序拼接
- [ ] 注入到 `global` 权重组，与其他 global section 共享 token 预算
- [ ] 空目录或不存在时不影响正常流程
- [ ] 用户提示词在写作任务书中出现在 master_constraints 之前
- [ ] 测试用例覆盖：有文件/无文件/空文件/编码错误
