# Analysis Report Generation Workflow

### Overview

The analysis report is generated through five stages (S1-S5), orchestrated by the conversation-driven TUI `ConversationRunner`. Each stage uses a different LLM model role, produces specific artifacts via conversation, and includes a human review gate (`/confirm`) between stages. S6 (PPT generation) is documented in `ppt-workflow.en.md` and is out of scope for this document.

### Flow Diagram

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│   S1    │────▶│   S2    │────▶│   S3    │────▶│   S4    │────▶│   S5    │
│  Topic  │     │  Data   │     │  Data   │     │  Data   │     │ Report  │
│reasoning│     │reasoning│     │reasoning│     │analysis │     │ writing │
└─────────┘     └─────────┘     └─────────┘     └─────────┘     └─────────┘
     │               │               │               │               │
     ▼               ▼               ▼               ▼               ▼
 report.yaml   s2_data_req.md  s3_data_profile.md  s4_analysis.md  output/final_report.md
 + s1_topic.md
     │               │               │               │               │
     ▼               ▼               ▼               ▼               ▼
 [Review Gate]   [Review Gate]   [Review Gate]    [Review Gate]    [Review Gate]
   /confirm        /confirm        /confirm         /confirm         /confirm
```

### S1: Topic & Goal Definition

**Model Role**: reasoning

**Conversation Goal**: Collect topic/motivation/audience/objectives/success-criteria/delivery via conversation, and produce `report.yaml` (project root) + `.anappt/s1_topic.md`

**Process**:
1. Collect via conversation in sequence:
   - Report topic and motivation (background, business problem to solve)
   - Target audience (decision-makers / executors / external clients, may be multiple)
   - Report objectives (decisions to support, specific questions to answer)
   - Success criteria (what makes a "good" report)
   - Delivery format (expected PPT pages, whether PDF/HTML is needed, theme preference)
2. Call `write_artifact("report.yaml", <YAML>)` to write `report.yaml` at the project root. The YAML structure contains `project`/`report`/`delivery` sections
3. Call `write_artifact(".anappt/s1_topic.md", <content>)` to write the refined topic document, expanding on topic background, motivation, target audience, report objectives, success criteria, and suggested analysis approach
4. Prompt the user to review both artifacts, then input `/confirm` to proceed. Users may also provide revision feedback directly in the conversation; the LLM updates the artifacts and waits for `/confirm` again

**Output**:
- `report.yaml` — project root report specification
- `.anappt/s1_topic.md` — refined topic document (referenced by S2/S4)

**Tool Subset**: `read_file`/`write_artifact`/`read_memory`/`read_history`

**is_ready Check**:
- `report.yaml` exists and parses successfully via `ReportConfig.from_yaml`
- `report.topic`, `report.motivation`, and `report.objectives` are all non-empty
- `.anappt/s1_topic.md` exists

**Review Focus**:
- Topic direction accuracy
- Clarity and feasibility of analysis objectives
- Reasonableness of suggested approach

### S2: Data Requirement Analysis

**Model Role**: reasoning

**Conversation Goal**: Derive the data requirement list needed to complete the analysis from `report.yaml` and data files, and produce `.anappt/s2_data_requirement.md`

**Input**: S1 output (`report.yaml` + `.anappt/s1_topic.md`) + existing data files list and documentation in `data/` directory (optional)

**Process**:
1. Use `read_file` to read `report.yaml` and `.anappt/s1_topic.md` as the basis for derivation
2. If `data/` contains user-provided tracking docs, schema specs, or data dictionaries (e.g. `data/README.md`, `data/schema.md`), read them with `read_file` as reference. If not present, derive purely from analysis needs
3. LLM derives the data requirement list; each entry includes at least:
   - Metric name and calculation logic
   - Required dimension breakdowns
   - Data time range
   - Minimum data granularity
   - Estimated data volume
   - Data source
4. Call `write_artifact(".anappt/s2_data_requirement.md", <content>)` to write the list
5. Prompt the user to review the artifact, then input `/confirm`; revisions can be proposed in the conversation

> **Important**: This is the key moment for users to prepare data. After reviewing S2, users should place data files (CSV, Excel, SQLite, DuckDB, Parquet) into the `data/` directory, then confirm to proceed to S3.

**Output**: `.anappt/s2_data_requirement.md`

**Tool Subset**: `read_file`/`write_artifact`/`read_memory`/`read_history`

**is_ready Check**: `.anappt/s2_data_requirement.md` exists and contains at least one Markdown heading or list item

**Review Focus**:
- Data requirements reasonably cover analysis objectives
- No missing key data
- Users can prepare and add data files to `data/` at this stage

### S3: Data Loading & Validation

**Model Role**: reasoning (conversation path is LLM-driven, orchestrating `execute_python` calls for data scanning and profile generation; legacy `run()` is pure local processing, no longer on the active path)

**Input**: Data files in `data/` directory

**Supported Formats**:
| Format | Extension | Loader |
|--------|-----------|--------|
| CSV | `.csv` | pandas |
| Excel | `.xlsx`, `.xls` | openpyxl + pandas |
| SQLite | `.db`, `.sqlite`, `.sqlite3` | sqlite3 |
| DuckDB | `.duckdb` | duckdb |
| Parquet | `.parquet` | pyarrow |

**Process**:
1. Detect all supported files in `data/` (8 extensions in total)
2. Load all data files as DataFrames
3. Generate data profile:
   - Total file count
   - Shape (rows x columns) per table
   - Column names list and data types
   - Statistics summary for numeric columns (count, mean, std, min, max, etc.)
   - Null counts
   - File details (format, size)
4. Check coverage against the S2 data requirement list
5. Write `.anappt/s3_data_profile.md`

**Output**: `.anappt/s3_data_profile.md`

**is_ready Check**: `.anappt/s3_data_profile.md` exists and is non-empty

**Review Focus**:
- Data fully loaded
- Column names and data types correct
- Significant null values needing handling
- Data volume meets analysis needs

### S4: Data Analysis

**Model Role**: analysis

**Conversation Goal**: Perform iterative deep analysis on the data, produce `.anappt/s4_analysis_report.md`, supporting multiple rounds of user feedback

**Input**: `report.yaml` + `data/` files + `.anappt/s2_data_requirement.md` + `.anappt/s3_data_profile.md` (if generated)

**Process**:
1. Use `read_file` to read context: `report.yaml`, `data/` files and docs, S2 requirement list, S3 data profile
2. Perform preliminary analysis and form a first-draft conclusion
3. Iteratively call tools as needed (multiple rounds allowed):
   - `execute_python`: statistical computation, pivoting, correlation analysis, optionally generate charts to `output/images/`
   - `search_web`: supplement industry background, competitor data, market reports
   - `fetch_url`: read full text of related web pages/reports/policy documents (if `JINA_API_KEY` is not configured, fall back to `search_web` snippets)
4. Integrate conclusions, call `write_artifact(".anappt/s4_analysis_report.md", <content>)` to write the draft using a clear Markdown structure (Executive Summary, Methodology, Key Findings, Detailed Analysis, Recommendations, etc.)
5. Prompt the user to review the draft and provide feedback; receive feedback → deepen reasoning → update the report → submit for user confirmation again
6. Loop until the user inputs `/confirm` to proceed to S5

**Output**: `.anappt/s4_analysis_report.md` (the conversation path does not generate `.anappt/data_info.json`)

**Tool Subset**: `read_file`/`write_artifact`/`execute_python`/`search_web`/`fetch_url`/`read_memory`/`read_history`

**is_ready Check**: `.anappt/s4_analysis_report.md` exists and is non-empty

**Review Focus**:
- Analysis covers all objectives
- Statistical methods are reasonable
- Key findings are data-supported
- Recommendations are actionable

> **Sandbox Security**: `execute_python` runs in an isolated subprocess with network access fully blocked (socket module replaced) and file system access restricted to `data/`, temp directory, and current working directory.

### S5: Report Generation

**Model Role**: writing

**Conversation Goal**: Organize analysis conclusions into a complete, deliverable analysis report, producing `output/final_report.md`

**Input**: `report.yaml` + `.anappt/s4_analysis_report.md` + optional `output/images/`

**Process**:
1. Use `read_file` to read context: `report.yaml` (topic, audience, objectives, success criteria), `.anappt/s4_analysis_report.md` (confirmed analysis conclusions), `output/images/` chart file list (optional)
2. Generate a complete report with standard structure, including at least:
   - Executive Summary
   - Background & Objectives
   - Data Sources & Methodology
   - Core Findings (may be split into multiple sub-sections by theme)
   - Conclusions & Recommendations
   - Appendix / Data Notes
3. Call `write_artifact("output/final_report.md", <content>)` to write the report using clear Markdown formatting (headings, tables, lists, image references, etc.)
4. After writing, **explicitly remind the user to open `output/final_report.md` to review and edit**, informing the user that they can:
   - Open the file directly in an editor and edit it, then return to the conversation and input `/confirm`
   - Or propose revision feedback directly in the conversation; the LLM updates the report and asks for user confirmation again
5. Users may iterate multiple times; once satisfied, input `/confirm` to proceed to S6

**Output**: `output/final_report.md` (the conversation path does not generate `.anappt/s5_report.md`)

**Tool Subset**: `read_file`/`write_artifact`/`read_memory`/`read_history`

**is_ready Check**: `output/final_report.md` exists, is non-empty, and contains at least 2 level-1 headings (lines starting with `# `)

**Review Focus**:
- Report structure is clear
- Language is appropriate for target audience
- Conclusions are data-supported
- Recommendations are specific and actionable

> **Important**: After S5, the system prompts the user to open and review `output/final_report.md`. Users can:
> 1. Directly edit `output/final_report.md`
> 2. Describe revision feedback in the terminal; the LLM updates the report and waits for `/confirm` again
> 3. Confirm to proceed to S6 (PPT generation)

### Review Gate Mechanism

After each stage completes, status becomes `awaiting_review`. The system supports the following 6 meta-commands (all start with `/`, case-insensitive):

1. **`/confirm`**: Accept current output, advance to next stage
   - Calls the stage's `is_ready` check; if it fails, prints a notice and stays in the current stage
   - On success, triggers Git commit: `feat(S1): confirm Topic Definition`

2. **`/exit`**: Save progress and exit
   - Triggers Git commit: `chore: auto-save on exit`
   - Resume later with `anappt resume`

3. **`/status`**: Print the current pipeline status table (stage ID, name, status, iteration count)

4. **`/memory`**: Print project memory `.anappt/memory.md`

5. **`/help`**: Print the meta-command help

6. **`/ppt <requirement>`**: Skip the S1–S5 prep stages and generate a PPT directly (see [PPT Generation Workflow](ppt-workflow.en.md))

> **Meta-commands must start with `/`**: bare words (`confirm`/`exit`/`help`) and Chinese aliases (`退出`/`帮助`) have been removed. Input starting with `/` that is not a known meta-command (e.g. `/foo`) also enters the conversation as free text.
>
> **Revisions are free-text**: When the user input is not a meta-command, the entire text enters the current stage's LLM conversation as a message. The LLM updates the artifact based on the feedback and waits for the user's `/confirm` again. The system does **not** provide a standalone `revise`/`config`/`reset` system action.

### Artifact Files Summary

| Stage | Artifact | Description |
|-------|----------|-------------|
| S1 | `report.yaml` | Project root report specification |
| S1 | `.anappt/s1_topic.md` | Refined topic document |
| S2 | `.anappt/s2_data_requirement.md` | Data requirement document |
| S3 | `.anappt/s3_data_profile.md` | Data profile |
| S4 | `.anappt/s4_analysis_report.md` | Analysis report |
| S5 | `output/final_report.md` | Final analysis report |
