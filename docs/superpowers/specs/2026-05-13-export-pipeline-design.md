# 导出模块统一管线重构设计

## 概述

将现有导出模块从"各格式独立解析"重构为"统一 Markdown → AST/HTML 管线"架构，新增 DOCX/HTML/PDF 三种格式，修复现有代码质量问题。

**目标:**
1. 新增 DOCX、HTML、PDF 导出格式（按此优先级实现）
2. 统一 Markdown 解析入口，消除重复的自定义转换器
3. 提供中文网文专属排版（首行缩进、1.8 倍行距、场景分隔）
4. 修复现有代码 8 个已知问题
5. 章节收集器从 state.json 读取卷结构，消除硬编码

## 架构

### 文件结构

```
export_manager/
├── __init__.py              # CLI 入口（精简，仅 argparse + 分发）
├── parser.py                # 统一 Markdown 解析器 (mistune v3)
├── styles.py                # CSS 模板管理
├── chapter_collector.py     # 章节收集 + 校验（从 __init__.py 抽离）
├── formats/
│   ├── __init__.py          # 格式注册表 + dispatch
│   ├── markdown.py          # Markdown 拼接（基本不变）
│   ├── txt.py               # 纯文本（用 mistune text renderer 替换手写正则）
│   ├── html.py              # 新增：单文件 HTML + 内嵌 CSS
│   ├── epub.py              # 重构：复用 parser.py
│   ├── docx.py              # 新增：python-docx 直接构建
│   └── pdf.py               # 新增：weasyprint（可选依赖）
```

### 数据流

```
章节 .md 文件 → chapter_collector → [(章号, 标题, 原文)]
                                         │
                         ┌───────────────┤
                         │               │
                    md/txt 格式      html/epub/docx/pdf 格式
                    (直接操作原文)         │
                                    parser.py (mistune)
                                         │
                              ┌──────────┴──────────┐
                              │                     │
                         AST 输出                HTML 输出
                              │                     │
                          docx.py              html.py / epub.py / pdf.py
```

**关键设计决策:**
- `parser.py` 暴露两个接口：`md_to_html()` 和 `md_to_blocks()`（AST）
- DOCX 走 AST 路径（避免 HTML→结构 的反向解析）
- HTML/EPUB/PDF 走 HTML 路径（CSS 统一控制排版）
- md/txt 不经过 HTML 中间层（无需）
- PDF 为可选功能，weasyprint 未安装时给出安装提示并退出

## 组件详细设计

### parser.py — 统一 Markdown 解析器

依赖：`mistune>=3.0`

接口：
- `md_to_html(text: str) -> str` — 返回 HTML 片段（不含 html/body 包裹）
- `md_to_blocks(text: str) -> list[dict]` — 返回 mistune AST 块列表

自定义渲染规则：
- `---` 分隔线 → `<hr class="scene-break">`
- `# 第N章 标题` → `<h1 class="chapter-title">标题</h1>`
- 段落 → `<p>内容</p>`
- `**粗体**` / `__粗体__` → `<strong>`

输入为纯叙事体 Markdown（标题、段落、粗体、分隔线），无需处理列表、表格、代码块等复杂特性。

### styles.py — CSS 排版模板

提供中文网文排版默认 CSS：

```css
body {
    font-family: "Source Han Serif SC", "Noto Serif CJK SC", "SimSun", serif;
    font-size: 16px;
    max-width: 42em;
    margin: 0 auto;
    padding: 2em;
}
p {
    text-indent: 2em;
    margin: 0.5em 0;
    line-height: 1.8;
}
h1.chapter-title {
    text-align: center;
    margin: 2em 0 1em;
    font-size: 1.5em;
}
hr.scene-break {
    border: none;
    text-align: center;
    margin: 1.5em 0;
}
hr.scene-break::after {
    content: "* * *";
    letter-spacing: 1em;
    color: #666;
}
```

接口：
- `get_default_css() -> str` — 返回默认 CSS
- `load_custom_css(path: Path) -> str` — 读取用户自定义 CSS
- `get_css(custom_path: Optional[Path] = None) -> str` — 优先自定义，回退默认

用户可在项目根放置 `export-style.css` 覆盖默认。

### chapter_collector.py — 章节收集器

从 `__init__.py` 抽离，增强功能：

**卷结构来源优先级:**
1. state.json `volumes[]` 数组 → 精确卷分配
2. 文件系统 `正文/第N卷/` 目录结构 → 按目录归属
3. 回退公式：`(chapter - 1) // chapters_per_volume + 1`（从 state.json 读 `chapters_per_volume`，最终回退 50）

**导出前校验:**
- 缺失章节号（如 1,2,4 缺 3）→ 打印警告，继续导出
- 重复章节号 → 报错退出
- 空文件 → 打印警告，跳过

**标题提取:**
- 跳过文件开头空行
- 正则 `^#{1,3}\s+(.*)` 匹配标题行
- 无匹配时从文件名提取（`第N章 标题` 模式）

**进度反馈:**
- `print(f"  [{i}/{total}] 第{ch}章 {title}")` 每章打印

接口：
- `collect_chapters(project_root, range_spec, volume) -> list[ChapterInfo]`
- `ChapterInfo = namedtuple("ChapterInfo", ["index", "title", "path", "volume"])`

### formats/ — 格式导出器

#### html.py

输入：章节列表 + HTML 片段
输出：单个 `.html` 文件

- 完整 HTML5 文档结构
- 内嵌 CSS（从 styles.py）
- 自动生成目录导航（`<nav>` + 章节锚点）
- `<meta charset="utf-8">`

#### epub.py（重构）

- 替换 `_md_to_html()` 为 `parser.md_to_html()`
- CSS 从 `styles.py` 获取
- 保留 ebooklib 构建逻辑和封面/样式检测
- 修复 `_crop_cover()` 异常处理（精确捕获 `ImportError` + `PIL.UnidentifiedImageError`）

#### docx.py

依赖：`python-docx`

- 使用 `parser.md_to_blocks()` 获取 AST
- 遍历 AST 块，映射到 python-docx 样式：
  - heading → `Heading 1` 样式（居中）
  - paragraph → `Normal` 样式（首行缩进 2 字符，1.8 倍行距）
  - thematic_break → 居中 `* * *` 段落
  - strong → 加粗 Run
- 默认 A4 纸面
- 不生成 Word TOC 字段（python-docx 的 TOC 需 Word 打开后手动刷新，体验差）

#### pdf.py

依赖：`weasyprint`（可选）

- 复用 `html.py` 的 HTML 生成逻辑
- 追加 PDF 专用 CSS：`h1 { page-break-before: always; }` （章节前强制分页）
- weasyprint 未安装时：打印安装提示 + `sys.exit(1)`
- 不为此引入任何必需依赖

#### markdown.py / txt.py

- markdown.py 基本不变（直接拼接原文）
- txt.py 用 mistune 的纯文本输出替换手写 `_strip_markdown()` 正则

### CLI 接口

保持现有子命令结构不变：

```bash
python webnovel.py export list                           # 列出章节
python webnovel.py export export --format epub           # 默认 all
python webnovel.py export export --format docx --range 1-50
python webnovel.py export export --format pdf --volume 1
python webnovel.py export export --format html --range all
```

参数变化：
- `--format` choices 扩展为 `["md", "txt", "epub", "html", "docx", "pdf"]`
- 新增 `--style` — 自定义 CSS 文件路径（覆盖默认排版）
- 去掉不必要的开关（不新增 `--toc`，目录默认行为由格式决定）

### 依赖管理

| 包 | 版本 | 用途 | 必需？ |
|----|------|------|--------|
| `mistune` | >=3.0 | Markdown → HTML/AST | 必需（新增） |
| `python-docx` | >=1.0 | DOCX 生成 | 必需（新增） |
| `ebooklib` | >=0.18 | EPUB 生成 | 必需（已有） |
| `weasyprint` | >=60.0 | PDF 生成 | 可选（新增） |
| `Pillow` | >=9.0 | 封面裁剪 | 可选（已有） |

## 现有代码审查修复清单

| # | 文件 | 问题 | 修复方式 |
|---|------|------|----------|
| 1 | epub.py | `_md_to_html()` 过于简陋 | 用 parser.py 替换 |
| 2 | __init__.py | 硬编码 50 章/卷 | chapter_collector 从 state.json 读取 |
| 3 | __init__.py | 章节收集/解析/CLI 全挤一个文件 | 抽离到 chapter_collector.py |
| 4 | txt.py | `_strip_markdown()` 正则不完整 | 用 mistune text renderer 替代 |
| 5 | epub.py | `_crop_cover()` 裸 except | 精确捕获 ImportError + PIL 异常 |
| 6 | __init__.py | 标题提取不容错（空行开头） | 跳过空行 + 正则匹配 |
| 7 | 测试 | EPUB 正向创建未测试 | 添加 mock 正向测试 |
| 8 | 全局 | 导出大量章节无进度反馈 | chapter_collector 每章打印进度 |

所有问题在重构中自然消解，无需单独修复步骤。

## 测试策略

- 每个格式导出器：至少 2 个测试（正常导出 + 依赖缺失降级）
- parser.py：5+ 单元测试（段落/标题/粗体/分隔线/空输入）
- chapter_collector：复用现有 TestCollectChapters + 新增校验测试
- 集成测试：端到端 CLI 调用验证文件生成

## 实现优先级

1. parser.py + styles.py（基础设施）
2. chapter_collector.py（从 __init__.py 抽离重构）
3. html.py（最简单的新格式，验证管线）
4. epub.py 重构（复用 parser，验证兼容性）
5. docx.py（AST 路径）
6. pdf.py（可选依赖）
7. txt.py 重构（用 mistune 替换手写正则）
8. __init__.py 精简（CLI 入口瘦身）
9. 测试补全
