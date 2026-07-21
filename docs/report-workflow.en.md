# Analysis Report Generation Workflow

### Overview

The analysis report is generated through five stages (S1-S5). Each stage uses a different LLM model role, produces specific artifacts, and includes a human review gate between stages.

### Flow Diagram

```
report.yaml
     │
     ▼
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│   S1    │────▶│   S2    │────▶│   S3    │────▶│   S4    │────▶│   S5    │
│  Topic  │     │  Data   │     │  Data   │     │  Data   │     │ Report  │
│reasoning│     │reasoning│     │  No LLM │     │analysis │     │ writing │
└─────────┘     └─────────┘     └─────────┘     └─────────┘     └─────────┘
     │               │               │               │               │
     ▼               ▼               ▼               ▼               ▼
 s1_topic.md  s2_data_req.md  s3_data_profile.md  s4_analysis.md  output/report.md
     │               │               │               │               │
     ▼               ▼               ▼               ▼               ▼
 [Review Gate]  [Review Gate]  [Review Gate]   [Review Gate]   [Review Gate]
 confirm/revise confirm/revise confirm/revise  confirm/revise  confirm/revise
```

### S1: Topic & Goal Definition

**Model Role**: reasoning

**Input**: Project configuration from `report.yaml`
- `project.name` — Project name
- `report.topic` — Analysis topic
- `report.motivation` — Analysis motivation
- `report.audience` — Target audience
- `report.objectives` — Analysis objectives
- `report.success_criteria` — Success criteria

**Process**:
1. Reads `report.yaml` configuration
2. Builds system prompt, instructing LLM to act as an expert analyst
3. LLM generates a structured topic document with:
   - Refined Topic
   - Analysis Objectives
   - Success Criteria
   - Suggested Approach

**Output**: `.anappt/s1_topic.md`

**Review Focus**:
- Topic direction accuracy
- Clarity and feasibility of analysis objectives
- Reasonableness of suggested approach

### S2: Data Requirement Analysis

**Model Role**: reasoning

**Input**: S1 output + existing data files list in `data/` directory

**Process**:
1. Reads S1 topic document
2. Scans `data/` directory for existing files
3. LLM generates data requirement document with:
   - Required Data Tables
   - Expected Schema (column name, type, description)
   - Data Quality Requirements
   - Suggested Data Sources

**Output**: `.anappt/s2_data_requirement.md`

**Review Focus**:
- Data requirements reasonably cover analysis objectives
- No missing key data
- Users can prepare and add data files to `data/` at this stage

> **Important**: This is the key moment for users to prepare data. After reviewing S2, users should place data files (CSV, Excel, SQLite, DuckDB, Parquet) into the `data/` directory, then confirm to proceed to S3.

### S3: Data Loading & Validation

**Model Role**: None (no LLM used)

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
1. Detects all supported files in `data/`
2. Loads all data files as DataFrames
3. Generates data profile:
   - Total file count
   - Shape (rows x columns) per table
   - Column names list
   - Data types
   - Statistics summary for numeric columns (count, mean, std, min, max, etc.)
   - Null counts
   - File details (format, size)

**Output**: `.anappt/s3_data_profile.md`

**Review Focus**:
- Data fully loaded
- Column names and data types correct
- Significant null values needing handling
- Data volume meets analysis needs

### S4: Data Analysis

**Model Role**: analysis

**Input**: S1 topic document + S2 data requirements + S3 data profile + data in `data/` directory

**Process**:
1. Reads S1, S2 outputs as context
2. Loads all data files from `data/` directory
3. Generates data info JSON (`.anappt/data_info.json`) with row count, column count, column names, and data types for each table
4. Builds toolset (3 tools):

| Tool | Function | Limitations |
|------|----------|-------------|
| `execute_python` | Execute Python code | Sandboxed: network blocked, FS restricted, 60s timeout |
| `search_web` | Web search | Auto-selects backend: DuckDuckGo / AnySearch / z.ai |
| `fetch_url` | Read web pages | Only available when `JINA_API_KEY` is set |

5. Creates AgentLoop (max 10 iterations)
6. LLM performs analysis via ReAct pattern:
   - Load and explore data
   - Perform statistical analysis
   - Create visualizations if needed
   - Identify key insights and patterns
7. Generates analysis report with:
   - Executive Summary
   - Methodology
   - Key Findings
   - Detailed Analysis
   - Recommendations

**Output**: `.anappt/s4_analysis_report.md`

**Review Focus**:
- Analysis covers all objectives
- Statistical methods are reasonable
- Key findings are data-supported
- Recommendations are actionable

> **Sandbox Security**: Code runs in an isolated subprocess with network access fully blocked (socket module replaced) and file system access restricted to `data/`, temp directory, and current working directory.

### S5: Report Generation

**Model Role**: writing

**Input**: S4 analysis report + S1 topic document + `report.yaml` configuration

**Process**:
1. Reads S4 analysis report
2. Reads S1 topic document for context
3. Reads audience and objectives from `report.yaml`
4. LLM transforms raw analysis into polished report:
   - Uses standard Markdown formatting (headings, tables, lists)
   - Includes: Executive Summary, Background, Methodology, Findings, Conclusions, Recommendations
   - Language consistent with project configuration

**Output**:
- `output/report.md` — Final report (user can view and edit)
- `.anappt/s5_report.md` — Report copy (internal archive)

**Review Focus**:
- Report structure is clear
- Language is appropriate for target audience
- Conclusions are data-supported
- Recommendations are specific and actionable

> **Important**: After S5, the system prompts the user to open and review the report. Users can:
> 1. Directly edit `output/report.md`
> 2. Describe revision feedback in the terminal for LLM to regenerate
> 3. Confirm to proceed to S6 (PPT generation)

### Review Gate Mechanism

After each stage completes, status becomes `awaiting_review`. Users can:

1. **Confirm**: Accept current output, advance to next stage
   - Triggers Git commit: `feat(S1): confirm Topic Definition`

2. **Revise**: Provide feedback to re-run the stage
   - Iteration count +1
   - Triggers Git commit: `feat(S1): complete Topic Definition - .anappt/s1_topic.md`
   - Feedback logged to session history

3. **Exit**: Save progress and exit
   - Triggers Git commit: `chore: auto-save on exit`
   - Resume later with `anappt resume`

### Artifact Files Summary

| Stage | Artifact | Description |
|-------|----------|-------------|
| S1 | `.anappt/s1_topic.md` | Topic & goal document |
| S2 | `.anappt/s2_data_requirement.md` | Data requirement document |
| S3 | `.anappt/s3_data_profile.md` | Data profile |
| S4 | `.anappt/s4_analysis_report.md` | Analysis report |
| S4 | `.anappt/data_info.json` | Data structure info (JSON) |
| S5 | `output/report.md` | Final analysis report |
| S5 | `.anappt/s5_report.md` | Report copy |
