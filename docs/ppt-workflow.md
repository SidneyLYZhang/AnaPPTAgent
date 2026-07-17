# PPT 生成流程 / PPT Generation Workflow

---

## 中文

### 概述

PPT 生成是 AnaPPTAgent 六阶段流水线的最后一步（S6），负责将 S5 生成的分析报告转化为 HTML 幻灯片演示文稿。该阶段使用 `DashiPPTBridge` 组件完成转换，支持多种主题和交互式导航。

### 流程图

```
output/report.md (S5 产物)
        │
        ▼
┌───────────────────┐
│       S6          │
│   PPT 生成        │
│   writing 模型    │
│                   │
│  1. 读取报告      │
│  2. 选择主题      │
│  3. 解析 Markdown │
│  4. 生成 HTML     │
│  5. 写入文件      │
└───────────────────┘
        │
        ▼
output/ppt/presentation.html
        │
        ▼
  [审核门控]
  confirm / revise
```

### S6: PPT 生成

**模型角色**：writing（写作型）

**输入**：`output/report.md`（S5 生成的分析报告）

**处理过程**：

1. **读取报告**：加载 `output/report.md` 的 Markdown 内容
2. **确定主题**：
   - 如果 `report.yaml` 中 `delivery.theme_preference` 已设置且有效，直接使用该主题
   - 否则，进入交互式主题选择，显示主题列表供用户选择
3. **创建 Bridge 实例**：初始化 `DashiPPTBridge`，设置输出目录和主题
4. **Markdown 解析**：将报告内容解析为幻灯片列表
5. **HTML 生成**：将幻灯片渲染为自包含的 HTML 文件
6. **写入文件**：保存到 `output/ppt/presentation.html`

**输出产物**：`output/ppt/presentation.html`

### 主题系统

提供 5 种内置主题：

| 主题 | 名称 | 描述 |
|------|------|------|
| `default` | 默认主题 | 白色背景，蓝色强调色 |
| `dark` | 深色主题 | 深色背景，浅色文字 |
| `corporate` | 企业主题 | 专业蓝色风格 |
| `minimal` | 极简主题 | 黑白简约风格 |
| `vibrant` | 活力主题 | 渐变彩色背景 |

**主题选择方式**：

1. **配置文件指定**：在 `report.yaml` 中设置：
   ```yaml
   delivery:
     theme_preference: "dark"
   ```

2. **交互式选择**：如果不设置 `theme_preference`，S6 执行时会显示：
   ```
   请选择主题:
   # | Theme     | Description
   --+-----------+--------------------------------------------
   1 | default   | Default - Clean white background with blue accents
   2 | dark      | Dark - Dark background with light text
   3 | corporate | Corporate - Professional blue theme
   4 | minimal   | Minimal - Simple black and white
   5 | vibrant   | Vibrant - Colorful with gradients
   >
   ```

   输入数字选择对应主题（默认为 `default`）。

### Markdown 解析规则

DashiPPTBridge 按以下规则将 Markdown 转换为幻灯片：

| Markdown 元素 | 幻灯片处理 |
|---------------|-----------|
| `# 标题` (H1) | 开始新幻灯片，作为幻灯片标题 |
| `## 标题` (H2) | 开始新幻灯片，作为幻灯片标题 |
| `- 项目` 或 `* 项目` | 提取为当前幻灯片的要点列表 |
| 其他文本行 | 作为当前幻灯片的内容块 |
| `### 标题` (H3) | 不触发新幻灯片，作为内容 |
| 空行 | 忽略 |

**示例**：
```markdown
# 执行摘要

本报告分析了 2024 年 Q3 的销售数据。

- 总销售额增长 15%
- 新客户增长 22%
- 客单价下降 3%

## 关键发现

- 华东地区贡献最大
- 移动端转化率最高
```

解析结果：
- 幻灯片 1：标题"执行摘要"，内容"本报告分析了..."，要点：总销售额、新客户、客单价
- 幻灯片 2：标题"关键发现"，要点：华东地区、移动端转化率

### HTML 输出特性

生成的 `presentation.html` 是一个完全自包含的文件（无外部依赖）：

**结构**：
- `<section class="slide">` — 每张幻灯片
- 第一个幻灯片默认显示（`active` 类）
- 导航按钮（Prev/Next）
- 幻灯片计数器（当前/总数）

**CSS 主题化**：
- 使用 CSS 变量（`--accent`, `--bg-alt`）实现主题切换
- 响应式全屏布局（100vw x 100vh）
- 幻灯片标题使用强调色 + 下划线
- 要点列表使用自定义标记符号

**JavaScript 交互**：
```javascript
// 键盘导航
ArrowRight / Space → 下一张
ArrowLeft          → 上一张

// 按钮导航
点击 "Next →" → 下一张
点击 "← Prev" → 上一张
```

### 键盘快捷键

| 按键 | 功能 |
|------|------|
| `→` (右箭头) | 下一张幻灯片 |
| `Space` (空格键) | 下一张幻灯片 |
| `←` (左箭头) | 上一张幻灯片 |

### 打开演示文稿

直接在浏览器中打开 HTML 文件即可：

```bash
# Windows
start output/ppt/presentation.html

# macOS
open output/ppt/presentation.html

# Linux
xdg-open output/ppt/presentation.html
```

### 导出为 PDF

在浏览器中打开演示文稿后，使用浏览器的打印功能导出 PDF：

1. 打开 `presentation.html`
2. 按 `Ctrl+P`（Windows）或 `Cmd+P`（macOS）
3. 选择"保存为 PDF"作为目标
4. 建议设置：
   - 纸张方向：横向（Landscape）
   - 边距：无（None）
   - 缩放：100%

### PPTX 导出

DashiPPTBridge 提供 `generate_pptx()` 方法，可通过 python-pptx 生成 PPTX 文件：

**使用 python-pptx（如果已安装）**：
```python
from anappt.bridge.dashi_ppt import DashiPPTBridge

bridge = DashiPPTBridge(output_dir="output/ppt", theme="corporate")
bridge.generate_pptx(
    markdown_content=report_content,
    title="Sales Analysis Report",
    filename="presentation.pptx"
)
```

**dashi-ppt-skill 集成**（需要 Node.js）：

如需使用 dashi-ppt-skill 进行更高级的 PPTX 导出：

1. 安装 Node.js >= 20
2. 安装 Chrome/Chromium/Edge 浏览器
3. 全局安装 dashi-ppt-skill：
   ```bash
   npm install -g dashi-ppt-skill
   ```

如果 Node.js 不可用，AnaPPTAgent 会自动回退为仅输出 HTML 格式。

### 自定义主题

开发者可以通过修改 `src/anappt/bridge/dashi_ppt.py` 中的 `_THEMES` 和 `_THEME_CSS` 字典来添加自定义主题：

```python
_THEMES = {
    "default": "Default - Clean white background with blue accents",
    "dark": "Dark - Dark background with light text",
    "corporate": "Corporate - Professional blue theme",
    "minimal": "Minimal - Simple black and white",
    "vibrant": "Vibrant - Colorful with gradients",
    # 添加自定义主题
    "ocean": "Ocean - Blue gradient with white text",
}

_THEME_CSS = {
    # ... 现有主题 ...
    "ocean": """
        background: linear-gradient(135deg, #006994, #48cae4);
        color: #ffffff; --accent: #ffd700; --bg-alt: rgba(255,255,255,0.15);
    """,
}
```

### DashiPPTBridge API

| 方法 | 说明 |
|------|------|
| `list_themes()` | 静态方法，返回所有可用主题字典 |
| `validate_markdown(content)` | 静态方法，验证 Markdown 是否可转换为幻灯片 |
| `parse_markdown_to_slides(markdown)` | 将 Markdown 解析为 SlideContent 列表 |
| `generate_html(slides, title)` | 从幻灯片列表生成 HTML 字符串 |
| `generate_ppt(markdown, theme, title, filename)` | 完整流程：解析 + 生成 HTML 文件 |
| `generate_pptx(markdown, theme, title, filename)` | 生成 PPTX 文件（回退为 HTML） |

### SlideContent 数据结构

```python
class SlideContent:
    title: str          # 幻灯片标题
    bullets: list[str]  # 要点列表
    content: str        # 原始内容块
    image_path: str     # 图片路径（保留字段）
    layout: str         # 布局类型: 'title' | 'content' | 'image' | 'section'
```

### 审核要点

S6 完成后，用户应检查：

- 幻灯片数量是否合理（参考 `delivery.ppt_pages` 配置）
- 每张幻灯片的内容是否完整
- 主题是否适合演示场景
- 是否有内容被截断或丢失
- 标题层级是否正确

如果不满意，可以：
1. 提供修改意见，重新生成
2. 修改 `output/report.md` 后重新运行 S6
3. 手动编辑生成的 HTML 文件

---

## English

### Overview

PPT generation is the final stage (S6) of AnaPPTAgent's six-stage pipeline. It transforms the S5 analysis report into an HTML slide presentation using the `DashiPPTBridge` component, with multiple themes and interactive navigation.

### Flow Diagram

```
output/report.md (S5 output)
        │
        ▼
┌───────────────────┐
│       S6          │
│  PPT Generation   │
│  writing model    │
│                   │
│  1. Read report   │
│  2. Select theme  │
│  3. Parse Markdown│
│  4. Generate HTML │
│  5. Write file    │
└───────────────────┘
        │
        ▼
output/ppt/presentation.html
        │
        ▼
  [Review Gate]
  confirm / revise
```

### S6: PPT Generation

**Model Role**: writing

**Input**: `output/report.md` (S5 analysis report)

**Process**:
1. **Read report**: Load Markdown content from `output/report.md`
2. **Determine theme**:
   - If `delivery.theme_preference` is set and valid in `report.yaml`, use it directly
   - Otherwise, enter interactive theme selection
3. **Create Bridge**: Initialize `DashiPPTBridge` with output directory and theme
4. **Parse Markdown**: Convert report content into a list of slides
5. **Generate HTML**: Render slides into a self-contained HTML file
6. **Write file**: Save to `output/ppt/presentation.html`

**Output**: `output/ppt/presentation.html`

### Theme System

5 built-in themes:

| Theme | Name | Description |
|-------|------|-------------|
| `default` | Default | White background, blue accents |
| `dark` | Dark | Dark background, light text |
| `corporate` | Corporate | Professional blue style |
| `minimal` | Minimal | Black and white simplicity |
| `vibrant` | Vibrant | Colorful gradient background |

**Theme Selection Methods**:

1. **Config file**: Set in `report.yaml`:
   ```yaml
   delivery:
     theme_preference: "dark"
   ```

2. **Interactive**: If `theme_preference` is not set, S6 displays a theme table for selection. Enter the number to choose (defaults to `default`).

### Markdown Parsing Rules

| Markdown Element | Slide Handling |
|-----------------|---------------|
| `# Heading` (H1) | Starts new slide, becomes slide title |
| `## Heading` (H2) | Starts new slide, becomes slide title |
| `- item` or `* item` | Extracted as bullet points for current slide |
| Other text lines | Content block for current slide |
| `### Heading` (H3) | Does not trigger new slide, treated as content |
| Empty lines | Ignored |

### HTML Output Features

The generated `presentation.html` is fully self-contained (no external dependencies):

- `<section class="slide">` — Each slide
- First slide visible by default (`active` class)
- Navigation buttons (Prev/Next)
- Slide counter (current/total)
- CSS variables for theme switching
- Responsive fullscreen layout (100vw x 100vh)
- Custom bullet markers with accent color

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `→` (Right Arrow) | Next slide |
| `Space` | Next slide |
| `←` (Left Arrow) | Previous slide |

### Opening the Presentation

Open the HTML file directly in a browser:

```bash
# Windows
start output/ppt/presentation.html

# macOS
open output/ppt/presentation.html

# Linux
xdg-open output/ppt/presentation.html
```

### Exporting to PDF

After opening in a browser, use the browser's print function:

1. Open `presentation.html`
2. Press `Ctrl+P` (Windows) or `Cmd+P` (macOS)
3. Select "Save as PDF" as destination
4. Recommended settings: Landscape orientation, No margins, 100% scale

### PPTX Export

DashiPPTBridge provides `generate_pptx()` using python-pptx (falls back to HTML if not installed):

```python
from anappt.bridge.dashi_ppt import DashiPPTBridge

bridge = DashiPPTBridge(output_dir="output/ppt", theme="corporate")
bridge.generate_pptx(
    markdown_content=report_content,
    title="Sales Analysis Report",
    filename="presentation.pptx"
)
```

**dashi-ppt-skill Integration** (requires Node.js):
1. Install Node.js >= 20
2. Install Chrome/Chromium/Edge browser
3. Install dashi-ppt-skill globally: `npm install -g dashi-ppt-skill`

If Node.js is not available, AnaPPTAgent automatically falls back to HTML-only output.

### Custom Themes

Developers can add custom themes by modifying `_THEMES` and `_THEME_CSS` in `src/anappt/bridge/dashi_ppt.py`:

```python
_THEMES["ocean"] = "Ocean - Blue gradient with white text"

_THEME_CSS["ocean"] = """
    background: linear-gradient(135deg, #006994, #48cae4);
    color: #ffffff; --accent: #ffd700; --bg-alt: rgba(255,255,255,0.15);
"""
```

### DashiPPTBridge API

| Method | Description |
|--------|-------------|
| `list_themes()` | Static method, returns all available themes |
| `validate_markdown(content)` | Static method, validates Markdown for slide generation |
| `parse_markdown_to_slides(markdown)` | Parses Markdown into SlideContent list |
| `generate_html(slides, title)` | Generates HTML string from slide list |
| `generate_ppt(markdown, theme, title, filename)` | Full pipeline: parse + generate HTML file |
| `generate_pptx(markdown, theme, title, filename)` | Generates PPTX file (falls back to HTML) |

### Review Checklist

After S6 completes, check:
- Slide count is reasonable (refer to `delivery.ppt_pages`)
- Content is complete on each slide
- Theme suits the presentation context
- No content is truncated or missing
- Heading hierarchy is correct

If unsatisfied:
1. Provide revision feedback to regenerate
2. Modify `output/report.md` and re-run S6
3. Manually edit the generated HTML file
