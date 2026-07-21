# Installation Guide

This page details the three installation methods for AnaPPTAgent, verification, upgrade/uninstall, and common troubleshooting.

## Prerequisites

| Dependency | Version | Required | Purpose |
|------------|---------|----------|---------|
| Python | >= 3.11 (< 3.14) | Required | Run anappt |
| uv package manager | Latest | Required | Install and run anappt |
| git | Any | Required (for automated script install) | Clone repository |
| Node.js + npm | >= 20 | Optional | PPTX export (HTML output does not require) |
| Chrome / Chromium / Edge | Any modern version | Optional | PPTX rendering (HTML output does not require) |

!!! note "About Node.js and browsers"
    When Node.js is not installed, stage S6 will automatically fall back to HTML-only output, which can still be opened in a browser and printed to PDF.

!!! note "Relationship between Node.js/npm and dashi-ppt-skill"
    The install scripts (Method 1) and manual install (Method 2) only install the **prerequisite** dependencies Node.js + npm; the dashi-ppt-skill itself is downloaded via `anappt setup` or `anappt new` (see the [Install dashi-ppt-skill](#install-dashi-ppt-skill) section below).

## Method 1: Automated install script (recommended)

AnaPPTAgent provides a cross-platform one-click install script that automatically installs dependencies, clones the repository, and installs `anappt` as a globally available uv tool.

=== "Windows"

    **PowerShell** (one-click download and run, no need to clone first):

    ```powershell
    # One-click download and run (no need to clone first)
    Invoke-WebRequest -UseBasicParsing https://raw.githubusercontent.com/SidneyLYZhang/AnaPPTAgent/main/scripts/setup-windows.ps1 | Invoke-Expression
    ```

    Or clone first, then run:

    ```powershell
    git clone https://github.com/SidneyLYZhang/AnaPPTAgent.git AnaPPTAgent
    cd AnaPPTAgent
    .\scripts\setup-windows.ps1
    ```

=== "Linux / macOS"

    **Bash** (one-click download and run):

    ```bash
    # One-click download and run
    curl -fsSL https://raw.githubusercontent.com/SidneyLYZhang/AnaPPTAgent/main/scripts/setup-unix.sh | bash
    ```

    Or clone first, then run:

    ```bash
    git clone https://github.com/SidneyLYZhang/AnaPPTAgent.git AnaPPTAgent
    cd AnaPPTAgent
    bash scripts/setup-unix.sh
    ```

The script runs 5 phases (git / uv / Node.js / clone / uv tool install), each with verification tests, and outputs a summary table at the end. The script only installs the **prerequisite** dependencies Node.js + npm; the dashi-ppt-skill itself is downloaded via `anappt setup` or `anappt new` (see the [Install dashi-ppt-skill](#install-dashi-ppt-skill) section).

### Common parameters

Both scripts support the following parameters:

| Parameter | Windows | Unix | Description |
|-----------|---------|------|-------------|
| `--skip-node` | `-SkipNode` | `--skip-node` | Skip Node.js install (for CI or already installed) |
| `--skip-clone` | `-SkipClone` | `--skip-clone` | Skip clone (for running from the repo root) |
| `-r <url>` | `-RepoUrl <url>` | `-r <url>` or `--repo-url <url>` | Specify repo URL (for forks) |
| `-t <dir>` | `-TargetDir <dir>` | `-t <dir>` or `--target-dir <dir>` | Specify clone target parent directory |
| Help | None (see script header comments) | `-h` or `--help` | Show help |

**Examples**:

```bash
# Unix: skip Node.js and clone, install directly from current directory
bash scripts/setup-unix.sh --skip-node --skip-clone

# Windows: use a fork repo and specify target directory
.\scripts\setup-windows.ps1 -RepoUrl "https://github.com/user/AnaPPTAgent.git" -TargetDir "D:\Projects"
```

## Method 2: Manual install

For users already familiar with the toolchain or who need a custom workflow.

1. Install Python >= 3.11 (< 3.14): https://www.python.org/downloads/
2. Install uv: https://docs.astral.sh/uv/getting-started/installation/
3. Clone the repository and install as a uv tool:

    ```bash
    git clone https://github.com/SidneyLYZhang/AnaPPTAgent.git AnaPPTAgent
    cd AnaPPTAgent
    uv tool install .
    ```

!!! tip "About `uv tool install .`"
    `uv tool install .` makes the `anappt` command globally available (no `uv run` prefix needed). If `anappt` is not found after install, restart your terminal or check that PATH includes uv's bin directory (Linux/macOS usually `~/.local/bin`, Windows `%USERPROFILE%\.local\bin`).

!!! note "Node.js and skill install"
    Method 2 only installs the Python toolchain; Node.js + npm must be installed separately (see the [Prerequisites](#prerequisites) table), and the dashi-ppt-skill itself is downloaded via `anappt setup` or `anappt new` (see the [Install dashi-ppt-skill](#install-dashi-ppt-skill) section).

## Method 3: Development mode

For contributors who need to modify source code or run the test suite (pytest, ruff).

```bash
git clone https://github.com/SidneyLYZhang/AnaPPTAgent.git AnaPPTAgent
cd AnaPPTAgent
uv sync --extra dev
```

Notes:

- `uv sync --extra dev` installs the `dev` optional dependencies from `pyproject.toml` (pytest, pytest-cov, pytest-asyncio, ruff).
- In development mode, you can invoke `uv run anappt --help` without global install.
- Run tests:

    ```bash
    uv run pytest
    ```

- Run lint:

    ```bash
    uv run ruff check src tests
    ```

## Install verification

Three ways to verify:

```bash
# Method 1: direct invocation
anappt --help

# Method 2: via uv tool run (fallback when PATH is not effective)
uv tool run anappt --help

# Method 3: via uvx (simplest form)
uvx anappt --help
```

Expected output includes the `anappt` string and the list of subcommands (`new`, `run`, `resume`, `status`, `config`, `interactive`).

You can also list installed uv tools:

```bash
uv tool list
```

You should see an `anappt` entry.

## Install dashi-ppt-skill

dashi-ppt-skill is the core dependency for PPT rendering in stage S6, installed via the `anappt setup` command.

`anappt setup` checks Node.js >= 20, npm, and Chrome (optional) in sequence, then invokes `npx dashi-ppt-skill@latest --dir <path>` to install the skill to `~/.anappt/skills/dashi-ppt/`. After installation, the skill parent directory is persisted to `~/.anappt/config.yaml`.

Two recommended ways to trigger the install:

- **Method A**: Run `anappt new <project>` to attempt automatic install (unless `--no-skill` is passed to skip).
- **Method B**: Manually run `anappt setup`:
    - `--dir <path>`: specify the skill install parent directory (default `~/.anappt/skills`).
    - `--registry <url>`: specify an npm mirror URL (e.g. `https://registry.npmmirror.com`).

```bash
# Manually install or update the skill
anappt setup

# Specify install directory and npm mirror
anappt setup --dir /opt/anappt/skills --registry https://registry.npmmirror.com
```

When the skill is not installed, stage S6 will fail and prompt you to run `anappt setup`.

## Upgrade and uninstall

### Upgrade

```bash
# Enter the repo directory, pull the latest code, then reinstall
cd AnaPPTAgent
git pull
uv tool install --force .
```

### Uninstall

```bash
uv tool uninstall anappt
```

## Common issues

??? question "`anappt: command not found`"
    PATH not refreshed. Restart the terminal; on Linux/macOS check that `~/.local/bin` is in PATH; on Windows check `%USERPROFILE%\.local\bin`.

??? question "`winget is not available` (Windows script)"
    Install "App Installer" from Microsoft Store, or manually install git/uv/Node.js and switch to `--skip-clone` mode.

??? question "`Node.js install failed`"
    Use `--skip-node` to skip (PPTX export will be unavailable, HTML output is unaffected), or manually install from https://nodejs.org/.

??? question "`uv tool install` failed"
    Check Python version (needs >= 3.11, < 3.14); check network proxy; try `uv tool install --force .`.

??? question "Proxy issues"
    Set environment variables: `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` (supports socks5).

    ```bash
    # Example (Linux/macOS)
    export HTTP_PROXY=http://127.0.0.1:7890
    export HTTPS_PROXY=http://127.0.0.1:7890
    export ALL_PROXY=socks5://127.0.0.1:7890
    ```

    ```powershell
    # Example (Windows PowerShell)
    $env:HTTP_PROXY = "http://127.0.0.1:7890"
    $env:HTTPS_PROXY = "http://127.0.0.1:7890"
    $env:ALL_PROXY = "socks5://127.0.0.1:7890"
    ```

??? question "PPTX export failed"
    Run `anappt setup` to reinstall dashi-ppt-skill. Confirm Node.js >= 20 and Chrome/Chromium/Edge are installed.

## Next steps

After installation, continue reading:

- [CLI usage guide](cli-usage.md)
- [Interactive TUI guide](tui-usage.md)
- [Report generation workflow](report-workflow.md)
- [PPT generation workflow](ppt-workflow.md)
- [Back to home](index.md)
