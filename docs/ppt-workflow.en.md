# PPT Generation Workflow

## Overview

PPT generation is the final stage (S6) of AnaPPTAgent's six-stage pipeline. It transforms the S5 analysis report into an HTML slide presentation using the `DashiPPTBridge` component, which invokes the `dashi-ppt-skill` via subprocess to perform HTML rendering and PPTX/PDF export.

The dashi-ppt-skill is installed to `~/.anappt/skills/dashi-ppt/` via the `anappt setup` command, with `SKILL.md` as its entry file. S6 treats the skill as a real Agent skill: it loads SKILL.md as the LLM system prompt, lets the LLM construct `goal.json`, and then invokes the skill's render and export scripts to produce the final artifacts.

## Flow Diagram

```
output/final_report.md (S5 output)
        │
        ▼
┌──────────────────────┐
│         S6           │
│   PPT Generation     │
│    writing model     │
│                      │
│  7-step workflow:    │
│   1. skill check     │
│   2. load SKILL.md   │
│   3. choose themePack│
│   4. build goal.json │
│   5. render HTML     │
│   6. export PPTX     │
│   7. await review    │
└──────────────────────┘
        │
        ▼
output/ppt/presentation.html
        │
        ▼
   [Review Gate]
   confirm
```

## Prerequisites

| Dependency | Required | Description |
|------------|----------|-------------|
| Node.js ≥ 20 | Required | The skill's render and export scripts depend on Node.js |
| npm | Required | Invokes export scripts via `npm run export:pptx` / `export:pdf` |
| Chrome / Chromium / Edge | Optional | PPTX/PDF export requires a headless browser; HTML generation is unaffected |
| dashi-ppt-skill | Required | Installed via the `anappt setup` command, or auto-installed during `anappt new`. The skill is installed to `~/.anappt/skills/dashi-ppt/`, with `SKILL.md` as its entry file |

If `anappt setup` detects that the environment does not meet the requirements (missing Node.js or version too old), it prints a corresponding hint. A missing browser only affects PPTX/PDF export, not HTML generation.

## S6: PPT Generation

**Model Role**: writing

**Input**: `output/final_report.md` (S5 analysis report) + `report.yaml`

**Output**:

- `output/ppt/presentation.html` (main artifact: self-contained HTML presentation)
- `output/ppt/goal.json` (intermediate artifact: slide structure definition constructed by the LLM)
- `output/ppt/presentation.pptx` (optional artifact: only generated when `delivery.formats` contains `pptx`)

## 7-Step Workflow

S6 is driven by the LLM in conversation following `S6_SYSTEM_PROMPT_FRAGMENT`. The full flow is as follows:

### Step 1: Skill Pre-check

- Check whether `ctx.skill_manager` is injected into the pipeline context
- Call `skill_manager.locate_skill()` to locate the installed dashi-ppt-skill
- If `SkillManager` is not injected or `locate_skill()` returns `None`, print `s6.skill_not_installed` and return `next_action="retry"`, prompting the user to run `anappt setup` to install the skill

### Step 2: Load SKILL.md

- Call `DashiPPTBridge.load_skill_md(skill_root)` to read `~/.anappt/skills/dashi-ppt/SKILL.md`
- Use its text as the system prompt for subsequent LLM calls, so the LLM follows the skill's rendering rules and theme system when constructing `goal.json`
- If SKILL.md is missing, return `next_action="retry"`

### Step 3: Theme Selection

- Read `delivery.theme_preference` from `report.yaml`
- **Already set** (e.g., `theme03`): use that themePack directly, skipping the interactive prompt
- **Not set**:
  1. Using SKILL.md as the system prompt, send `s6.theme_selection_prompt` to the writing model; the LLM outputs a list of 12 themePacks (theme01-theme12) with index, name, and a short description
  2. Prompt the user to input a themePack name (defaults to `theme01`)
  3. Validate that the input matches the pattern `theme` followed by two digits (e.g., `theme03`); otherwise fall back to `theme01`

### Step 4: Construct goal.json

- The LLM, acting in the writing role with SKILL.md as system prompt, constructs goal.json from:
  - The full report content (`output/final_report.md`)
  - The themePack name
  - The project name (`config.project.name`)
  - The page count (`config.delivery.ppt_pages`, default 10)
- The returned JSON text is stripped of any ` ``` ` code-block wrapper
- Parsed into a dict and written to `output/ppt/goal.json`
- If JSON parsing fails, return `next_action="retry"`

### Step 5: Render HTML

- Call `DashiPPTBridge.render_deck(goal_json_path, output_html_path, skill_root)`
- The bridge invokes `scripts/render_goal_deck.ps1` on Windows or `scripts/render_goal_deck.sh` on Unix
- The render output is written to `output/ppt/presentation.html`
- If the script is missing or exits with a non-zero code, return `next_action="retry"`

### Step 6: Optional PPTX Export

- Only executed when `delivery.formats` contains `pptx`
- Call `DashiPPTBridge.export(deck_dir, format="pptx", output_file, skill_root)`
- The bridge runs `npm --prefix <skill_root>/project run export:pptx -- <deck_dir>/ppt <output_file>`
- The export is written to `output/ppt/presentation.pptx` and added to the artifact list
- Export failure only prints a warning (`s6.export_failed_warning`) and does not affect the HTML artifact

### Step 7: Return awaiting_review

- Print the preview URL `http://127.0.0.1:5200/` (`s6.preview_url`)
- Prompt the user to open it in a browser, edit and confirm, then return to the CLI and type `confirm`
- Return `StageOutput(success=True, next_action="confirm")`; the orchestrator enters the review gate

## SKILL.md and goal.json

**SKILL.md**: The entry file of dashi-ppt-skill. It defines the rendering rules, theme system, and goal.json schema. S6 uses its full text as the LLM system prompt so the LLM knows how to produce a valid goal.json from the report content.

**goal.json**: An intermediate artifact constructed by the LLM in Step 4 of S6. It describes the structured definition of the slides (e.g., slide list, content and layout of each slide, themePack, etc.). goal.json is the input to `render_deck` and is read by the skill's render script to generate HTML.

## Theme Selection

dashi-ppt-skill provides 12 themePacks (theme01-theme12), replacing the legacy 5 built-in themes.

**Config-file specification**: Set in `report.yaml`:

```yaml
delivery:
  theme_preference: "theme03"
```

**Interactive selection**: If `theme_preference` is not set, S6 uses SKILL.md as the system prompt and asks the LLM to list the 12 themePacks for the user to choose from. The user inputs a themePack name (e.g., `theme03`; defaults to `theme01`).

## DashiPPTBridge API

`DashiPPTBridge` is a subprocess bridge layer. It does not generate HTML directly—all rendering and exporting is delegated to the skill's scripts. It exposes 3 static methods:

| Method | Description |
|--------|-------------|
| `load_skill_md(skill_root)` | Static method, reads `skill_root/SKILL.md` content as the LLM system prompt |
| `render_deck(goal_json_path, output_html_path, skill_root)` | Static method, invokes the skill's subprocess script (Windows: `render_goal_deck.ps1`, Unix: `render_goal_deck.sh`) to render goal.json into HTML |
| `export(deck_dir, format, output_file, skill_root)` | Static method, exports PPTX/PDF via `npm run export:pptx` or `export:pdf` |

## Artifacts

| File | Description |
|------|-------------|
| `output/ppt/presentation.html` | Main artifact: self-contained HTML presentation |
| `output/ppt/goal.json` | Intermediate artifact: slide structure definition constructed by the LLM |
| `output/ppt/presentation.pptx` | Optional artifact: PPTX file (when `delivery.formats` contains `pptx`) |

## Opening the Presentation

Open `output/ppt/presentation.html` directly in a browser, or visit the preview URL `http://127.0.0.1:5200/`.

```bash
# Windows
start output/ppt/presentation.html

# macOS
open output/ppt/presentation.html

# Linux
xdg-open output/ppt/presentation.html
```

## Exporting to PDF

After opening the presentation in a browser, use the browser's print function to export a PDF:

1. Open `output/ppt/presentation.html` or visit `http://127.0.0.1:5200/`
2. Press `Ctrl+P` (Windows) or `Cmd+P` (macOS)
3. Select "Save as PDF" as the destination
4. Recommended settings:
   - Orientation: Landscape
   - Margins: None
   - Scale: 100%

## Review Checklist

After S6 completes, the user should review in the browser:

- Whether the themePack is appropriate (matches the presentation context)
- Whether the HTML rendered successfully (no blank pages or script errors)
- Whether the PPTX was exported (if `delivery.formats` contains `pptx`)
- Whether the browser preview works correctly (slide count, layout, content)
- Whether `goal.json` is reasonable (page count close to `delivery.ppt_pages`, content covers the report's key points)

If unsatisfied, you can:

1. Provide revision feedback as free text in the conversation; the LLM revises goal.json and re-renders
2. Modify `output/final_report.md` and re-run S6
3. Manually edit `output/ppt/goal.json` and run the render script separately
