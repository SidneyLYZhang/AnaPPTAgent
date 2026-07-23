# PPT 生成流程

## 概述

PPT 生成是 AnaPPTAgent 六阶段流水线的最后一步（S6），负责将 S5 生成的分析报告转化为 HTML 幻灯片演示文稿。该阶段使用 `DashiPPTBridge` 组件，通过子进程调用 `dashi-ppt-skill` 完成 HTML 渲染与 PPTX/PDF 导出。

dashi-ppt-skill 通过 `anappt setup` 命令安装到 `~/.anappt/skills/dashi-ppt/`，入口文件为 `SKILL.md`。S6 把 skill 真正当作一个 Agent skill 来使用：将 SKILL.md 加载为 LLM 系统提示，由 LLM 构造 `goal.json`，再调用 skill 提供的渲染脚本与导出脚本生成最终产物。

## 流程图

```
output/final_report.md (S5 产物)
        │
        ▼
┌──────────────────────┐
│         S6           │
│     PPT 生成         │
│     writing 模型     │
│                      │
│   7 步工作流：       │
│    1. skill 检查     │
│    2. 加载 SKILL.md  │
│    3. 选择 themePack │
│    4. 构造 goal.json │
│    5. 渲染 HTML      │
│    6. 导出 PPTX      │
│    7. 等待审核       │
└──────────────────────┘
        │
        ▼
output/ppt/presentation.html
        │
        ▼
   [审核门控]
   /confirm
```

## 前置依赖

| 依赖 | 必需性 | 说明 |
|------|--------|------|
| Node.js ≥ 20 | 必需 | skill 的渲染与导出脚本依赖 Node.js |
| npm | 必需 | 通过 `npm run export:pptx` / `export:pdf` 调用导出脚本 |
| Chrome / Chromium / Edge | 可选 | PPTX/PDF 导出需要无头浏览器；HTML 生成不受影响 |
| dashi-ppt-skill | 必需 | 通过 `anappt setup` 命令安装，或 `anappt new` 时自动尝试安装。skill 安装到 `~/.anappt/skills/dashi-ppt/`，入口文件为 `SKILL.md` |

若 `anappt setup` 检测到环境不满足（Node.js 缺失或版本过低），会给出相应提示；浏览器缺失仅影响 PPTX/PDF 导出，不影响 HTML 生成。

## S6: PPT 生成

**模型角色**：writing（写作型）

**输入**：`output/final_report.md`（S5 分析报告）+ `report.yaml`

**输出**：

- `output/ppt/presentation.html`（主产物：自包含 HTML 演示文稿）
- `output/ppt/goal.json`（中间产物：LLM 构造的幻灯片结构定义）
- `output/ppt/presentation.pptx`（可选产物：仅当 `delivery.formats` 含 `pptx` 时生成）

## 7 步工作流

S6 阶段由 LLM 在对话中按 `S6_SYSTEM_PROMPT_FRAGMENT` 驱动 7 步，完整流程如下：

### 步骤 1：前置 skill 检查

- 检查 `ctx.skill_manager` 是否注入到流水线上下文
- 调用 `skill_manager.locate_skill()` 查找已安装的 dashi-ppt-skill
- 若 `SkillManager` 未注入或 `locate_skill()` 返回 `None`，打印 `s6.skill_not_installed` 提示并返回 `next_action="retry"`，提示用户运行 `anappt setup` 安装 skill

### 步骤 2：加载 SKILL.md

- 调用 `DashiPPTBridge.load_skill_md(skill_root)` 读取 `~/.anappt/skills/dashi-ppt/SKILL.md`
- 将其文本作为后续 LLM 调用的 system prompt，使 LLM 按 skill 的渲染规则与主题系统构造 `goal.json`
- 若 SKILL.md 不存在，返回 `next_action="retry"`

### 步骤 3：主题选择

- 读取 `report.yaml` 中的 `delivery.theme_preference`
- **已设置**（如 `theme03`）：直接使用该 themePack，跳过交互
- **未设置**：
  1. 以 SKILL.md 作为 system prompt，向 writing 模型发送 `s6.theme_selection_prompt`，LLM 输出 12 套 themePack（theme01-theme12）的列表（序号 + 主题名 + 简短描述）
  2. 提示用户输入主题包名称（默认 `theme01`）
  3. 校验输入格式必须为 `theme` 后跟两位数字（如 `theme03`），否则回退到 `theme01`

### 步骤 4：构造 goal.json

- LLM 在 writing 角色下，以 SKILL.md 为 system prompt，结合以下信息构造 goal.json：
  - 报告内容（`output/final_report.md` 全文）
  - themePack 名称
  - 项目名（`config.project.name`）
  - 页数（`config.delivery.ppt_pages`，默认 10）
- LLM 返回的 JSON 文本会去除 ` ``` ` 代码块包裹
- 解析为 dict 后写入 `output/ppt/goal.json`
- 若 JSON 解析失败，返回 `next_action="retry"`

### 步骤 5：渲染 HTML

- 调用 `DashiPPTBridge.render_deck(goal_json_path, output_html_path, skill_root)`
- bridge 在 Windows 下调用 `scripts/render_goal_deck.ps1`，Unix 下调用 `scripts/render_goal_deck.sh`
- 渲染结果写入 `output/ppt/presentation.html`
- 若脚本缺失或返回非零退出码，返回 `next_action="retry"`

### 步骤 6：可选导出 PPTX

- 仅当 `delivery.formats` 列表包含 `pptx` 时执行
- 调用 `DashiPPTBridge.export(deck_dir, format="pptx", output_file, skill_root)`
- bridge 执行 `npm --prefix <skill_root>/project run export:pptx -- <deck_dir>/ppt <output_file>`
- 导出文件写入 `output/ppt/presentation.pptx`，并加入产物列表
- 导出失败仅打印警告（`s6.export_failed_warning`），不影响 HTML 产物

### 步骤 7：返回 awaiting_review

- 打印预览地址 `http://127.0.0.1:5200/`（`s6.preview_url`）
- 提示用户在浏览器中访问该地址编辑确认，完成后回 CLI 输入 `/confirm`
- 返回 `StageOutput(success=True, next_action="confirm")`，由编排器进入审核门控

## SKILL.md 与 goal.json

**SKILL.md**：dashi-ppt-skill 的入口文件，定义渲染规则、主题系统、goal.json schema 等。S6 将其全文作为 LLM 系统提示，使 LLM 知晓如何根据报告内容生成合法的 goal.json。

**goal.json**：由 LLM 在 S6 步骤 4 构造的中间产物，描述幻灯片的结构化定义（如幻灯片列表、每张幻灯片的内容与布局、themePack 等）。goal.json 作为 `render_deck` 的输入，由 skill 的渲染脚本读取并生成 HTML。

## 主题选择

dashi-ppt-skill 提供 12 套 themePack（theme01-theme12），取代了旧版的 5 套内置主题。

**配置文件指定**：在 `report.yaml` 中设置：

```yaml
delivery:
  theme_preference: "theme03"
```

**交互式选择**：若未设置 `theme_preference`，S6 会以 SKILL.md 为 system prompt 让 LLM 列出 12 套 themePack 供用户选择，用户输入 themePack 名称（如 `theme03`，默认 `theme01`）。

## DashiPPTBridge API

`DashiPPTBridge` 是一个子进程桥接层，不直接生成 HTML，所有渲染与导出均委托给 skill 的脚本。实际暴露 3 个静态方法：

| 方法 | 说明 |
|------|------|
| `load_skill_md(skill_root)` | 静态方法，读取 `skill_root/SKILL.md` 内容作为 LLM 系统提示 |
| `render_deck(goal_json_path, output_html_path, skill_root)` | 静态方法，调用 skill 子进程脚本（Windows: `render_goal_deck.ps1`，Unix: `render_goal_deck.sh`）将 goal.json 渲染为 HTML |
| `export(deck_dir, format, output_file, skill_root)` | 静态方法，通过 `npm run export:pptx` 或 `export:pdf` 导出 PPTX/PDF |

## 产物文件

| 文件 | 说明 |
|------|------|
| `output/ppt/presentation.html` | 主产物：自包含 HTML 演示文稿 |
| `output/ppt/goal.json` | 中间产物：LLM 构造的幻灯片结构定义 |
| `output/ppt/presentation.pptx` | 可选产物：PPTX 文件（当 `delivery.formats` 含 `pptx` 时） |

## 打开演示文稿

浏览器直接打开 `output/ppt/presentation.html`，或访问预览地址 `http://127.0.0.1:5200/`。

```bash
# Windows
start output/ppt/presentation.html

# macOS
open output/ppt/presentation.html

# Linux
xdg-open output/ppt/presentation.html
```

## 导出为 PDF

在浏览器中打开演示文稿后，使用浏览器的打印功能导出 PDF：

1. 打开 `output/ppt/presentation.html` 或访问 `http://127.0.0.1:5200/`
2. 按 `Ctrl+P`（Windows）或 `Cmd+P`（macOS）
3. 选择"保存为 PDF"作为目标
4. 建议设置：
   - 纸张方向：横向（Landscape）
   - 边距：无（None）
   - 缩放：100%

## 审核要点

S6 完成后，用户应在浏览器中检查：

- themePack 是否合适（与演示场景匹配）
- HTML 是否成功渲染（无空白页或脚本错误）
- PPTX 是否导出（若 `delivery.formats` 含 `pptx`）
- 浏览器预览是否正常（幻灯片数量、布局、内容）
- `goal.json` 是否合理（页数与 `delivery.ppt_pages` 接近、内容覆盖报告要点）

如果不满意，可以：

1. 在对话内以自由文本反馈修改意见，LLM 修订 goal.json 后重渲
2. 修改 `output/final_report.md` 后重新运行 S6
3. 手动编辑 `output/ppt/goal.json` 后单独运行渲染脚本
