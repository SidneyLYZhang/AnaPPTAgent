<#
.SYNOPSIS
    AnaPPTAgent Windows Setup Script
.DESCRIPTION
    Installs prerequisites (git, uv, Node.js) via winget,
    clones the AnaPPTAgent repository, and installs the tool locally.
.PARAMETER RepoUrl
    Git remote URL to clone from. Defaults to a placeholder.
.PARAMETER TargetDir
    Target directory for cloning. Defaults to current directory.
.EXAMPLE
    .\setup-windows.ps1
    .\setup-windows.ps1 -RepoUrl "https://github.com/user/AnaPPTAgent.git"
    .\setup-windows.ps1 -RepoUrl "https://github.com/user/AnaPPTAgent.git" -TargetDir "C:\Projects"
#>

param(
    [string]$RepoUrl = "https://github.com/SidneyLYZhang/AnaPPTAgent.git",
    [string]$TargetDir = ""
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  $Message" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "  [OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "  [!] $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host "  [X] $Message" -ForegroundColor Red
}

function Test-Command {
    param([string]$Name)
    $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Install-ViaWinget {
    param(
        [string]$Id,
        [string]$DisplayName
    )

    if (-not (Test-Command "winget")) {
        Write-Err "winget is not available. Please install 'App Installer' from Microsoft Store."
        Write-Err "Manual install page: https://github.com/microsoft/winget-cli/releases"
        return $false
    }

    Write-Host "  Installing $DisplayName via winget..."
    $result = winget install --id $Id -e --source winget --accept-package-agreements --accept-source-agreements 2>&1

    if ($LASTEXITCODE -eq 0) {
        Write-Ok "$DisplayName installed successfully."
        return $true
    }
    else {
        # Check if it's already installed
        if ($result -match "already installed" -or $result -match "No applicable update") {
            Write-Ok "$DisplayName is already installed."
            return $true
        }
        Write-Err "Failed to install $DisplayName. Output: $result"
        return $false
    }
}

# ============================================================
# Step 0: Check winget availability
# ============================================================
Write-Step "AnaPPTAgent Windows Setup"

if (-not (Test-Command "winget")) {
    Write-Err "winget (App Installer) is not available on this system."
    Write-Err "Please install 'App Installer' from the Microsoft Store first:"
    Write-Err "  https://www.microsoft.com/store/apps/9NBLGGH4NNS1"
    Write-Host ""
    Write-Host "Alternatively, install prerequisites manually:"
    Write-Host "  git:     https://git-scm.com/download/win"
    Write-Host "  uv:      https://docs.astral.sh/uv/getting-started/installation/"
    Write-Host "  Node.js: https://nodejs.org/"
    exit 1
}

Write-Ok "winget is available."

# ============================================================
# Step 1: Install git
# ============================================================
Write-Step "Step 1/5: Checking git"

if (Test-Command "git") {
    $gitVersion = git --version
    Write-Ok "git is already installed: $gitVersion"
}
else {
    $success = Install-ViaWinget -Id "Git.Git" -DisplayName "git"
    if (-not $success) {
        Write-Err "Cannot continue without git. Please install it manually."
        exit 1
    }
    # Refresh PATH for current session
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
}

# ============================================================
# Step 2: Install uv
# ============================================================
Write-Step "Step 2/5: Checking uv"

if (Test-Command "uv") {
    $uvVersion = uv --version
    Write-Ok "uv is already installed: $uvVersion"
}
else {
    $success = Install-ViaWinget -Id "astral-sh.uv" -DisplayName "uv"
    if (-not $success) {
        Write-Warn "Failed to install uv via winget. Trying alternative method..."
        # Alternative: install via pip
        if (Test-Command "pip") {
            Write-Host "  Installing uv via pip..."
            pip install uv
            if ($?) {
                Write-Ok "uv installed via pip."
            }
            else {
                Write-Err "Failed to install uv. Please install manually:"
                Write-Err "  https://docs.astral.sh/uv/getting-started/installation/"
                exit 1
            }
        }
        else {
            Write-Err "Neither winget nor pip is available to install uv."
            Write-Err "Please install manually: https://docs.astral.sh/uv/getting-started/installation/"
            exit 1
        }
    }
    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
}

# ============================================================
# Step 3: Install Node.js (optional, for PPTX export)
# ============================================================
Write-Step "Step 3/5: Checking Node.js (optional, for PPTX export)"

if (Test-Command "node") {
    $nodeVersion = node --version
    Write-Ok "Node.js is already installed: $nodeVersion"
}
else {
    Write-Warn "Node.js is not installed. It is optional but recommended for PPTX export."
    $install = Read-Host "  Install Node.js now? (y/N)"
    if ($install -eq "y" -or $install -eq "Y") {
        $success = Install-ViaWinget -Id "OpenJS.NodeJS.LTS" -DisplayName "Node.js LTS"
        if ($success) {
            # Refresh PATH
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        }
        else {
            Write-Warn "Node.js installation failed. You can install it later from https://nodejs.org/"
        }
    }
    else {
        Write-Warn "Skipping Node.js. PPTX export will not be available (HTML output still works)."
    }
}

# ============================================================
# Step 4: Clone the repository
# ============================================================
Write-Step "Step 4/5: Clone AnaPPTAgent repository"

if ($TargetDir -eq "") {
    $TargetDir = Get-Location
}

$clonePath = Join-Path $TargetDir "AnaPPTAgent"

if (Test-Path $clonePath) {
    Write-Warn "Directory already exists: $clonePath"
    $overwrite = Read-Host "  Overwrite existing directory? (y/N)"
    if ($overwrite -eq "y" -or $overwrite -eq "Y") {
        Remove-Item -Recurse -Force $clonePath
    }
    else {
        Write-Err "Cannot clone to existing directory. Please choose a different target."
        exit 1
    }
}

Write-Host "  Cloning from: $RepoUrl"
Write-Host "  Target: $clonePath"

git clone $RepoUrl $clonePath
if (-not $?) {
    Write-Err "Failed to clone repository. Please check the URL: $RepoUrl"
    exit 1
}

Write-Ok "Repository cloned successfully."

# ============================================================
# Step 5: Install dependencies and tool
# ============================================================
Write-Step "Step 5/5: Install AnaPPTAgent and dependencies"

Set-Location $clonePath

Write-Host "  Running 'uv sync --extra dev'..."
uv sync --extra dev
if (-not $?) {
    Write-Err "Failed to sync dependencies with uv."
    Write-Err "Try running manually: cd $clonePath && uv sync --extra dev"
    exit 1
}

Write-Ok "Dependencies installed."

Write-Host "  Installing AnaPPTAgent as editable package..."
uv pip install -e .
if (-not $?) {
    Write-Warn "Failed to install as editable package. Trying 'uv pip install -e .' manually..."
    Write-Warn "The tool should still work via 'uv run anappt' from the project directory."
}
else {
    Write-Ok "AnaPPTAgent installed as editable package."
}

# ============================================================
# Verify installation
# ============================================================
Write-Step "Setup Complete!"

Write-Host ""
Write-Host "  AnaPPTAgent has been installed at: $clonePath" -ForegroundColor Green
Write-Host ""

if (Test-Command "anappt") {
    $anapptVersion = anappt 2>&1 | Select-Object -First 1
    Write-Ok "anappt CLI is available: $anapptVersion"
}
else {
    Write-Warn "anappt is not in PATH yet. You may need to:"
    Write-Warn "  1. Restart your terminal"
    Write-Warn "  2. Or use 'uv run anappt' from the project directory"
}

Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Cyan
Write-Host "    1. Configure your LLM models:"
Write-Host "       anappt config set"
Write-Host ""
Write-Host "    2. Create a new analysis project:"
Write-Host "       anappt new my_report"
Write-Host ""
Write-Host "    3. Navigate to project and run:"
Write-Host "       cd my_report"
Write-Host "       anappt run"
Write-Host ""
Write-Host "  Documentation:" -ForegroundColor Cyan
Write-Host "    - README_en.md (English)"
Write-Host "    - README_zh.md (Chinese)"
Write-Host "    - docs/cli-usage.md"
Write-Host "    - docs/tui-usage.md"
Write-Host "    - docs/report-workflow.md"
Write-Host "    - docs/ppt-workflow.md"
Write-Host ""
