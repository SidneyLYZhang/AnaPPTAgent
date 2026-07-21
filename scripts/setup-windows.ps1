<#
.SYNOPSIS
    AnaPPTAgent Windows Setup Script (5-stage installation with stage tests)
.DESCRIPTION
    Installs prerequisites (git, uv, Node.js) via winget,
    clones the AnaPPTAgent repository, and installs the tool as a uv tool
    so the `anappt` command is globally available.
    Each stage ends with a functional test that verifies the stage's product.
.PARAMETER RepoUrl
    Git remote URL to clone from. Defaults to the official repository.
.PARAMETER TargetDir
    Target parent directory for cloning. Defaults to current directory.
.PARAMETER SkipNode
    Skip Node.js installation (Stage 3). Use in CI or when Node.js is already installed.
.PARAMETER SkipClone
    Skip repository clone (Stage 4). Use when the script is run from inside the repo root.
.EXAMPLE
    .\setup-windows.ps1
    .\setup-windows.ps1 -SkipNode -SkipClone
    .\setup-windows.ps1 -RepoUrl "https://github.com/user/AnaPPTAgent.git" -TargetDir "C:\Projects"
#>

param(
    [string]$RepoUrl = "https://github.com/SidneyLYZhang/AnaPPTAgent.git",
    [string]$TargetDir = "",
    [switch]$SkipNode,
    [switch]$SkipClone
)

$ErrorActionPreference = "Stop"

# ============================================================
# Global state: track each stage's status for the summary table
# ============================================================
$script:StageResults = @()

# ============================================================
# Helper functions
# ============================================================

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
    $result = winget install --id $Id -e --source winget --disable-interactivity --accept-package-agreements --accept-source-agreements 2>&1

    if ($LASTEXITCODE -eq 0) {
        Write-Ok "$DisplayName installed successfully."
        return $true
    }
    else {
        if ($result -match "already installed" -or $result -match "No applicable update") {
            Write-Ok "$DisplayName is already installed."
            return $true
        }
        Write-Err "Failed to install $DisplayName. Output: $result"
        return $false
    }
}

function Refresh-Path {
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
}

function Print-Summary {
    Write-Host ""
    Write-Host "==================== Installation Summary ====================" -ForegroundColor Cyan
    for ($i = 0; $i -lt $script:StageResults.Count; $i++) {
        $result = $script:StageResults[$i]
        $paddedName = $result.Name.PadRight(25)
        $statusText = "[$($result.Status)]"
        $color = if ($result.Status -eq "PASS") { "Green" } elseif ($result.Status -eq "FAIL") { "Red" } else { "Yellow" }
        Write-Host "Stage $($i+1)/5: $paddedName $statusText" -ForegroundColor $color
    }
    Write-Host "==============================================================" -ForegroundColor Cyan

    $failCount = ($script:StageResults | Where-Object { $_.Status -eq "FAIL" }).Count
    if ($failCount -eq 0) {
        Write-Host ""
        Write-Host "AnaPPTAgent 安装完成!运行 'anappt --help' 开始使用。" -ForegroundColor Green
    }
    else {
        Write-Host ""
        Write-Host "[X] 安装未完成,请根据上方 [FAIL] 行的提示修复后重试。" -ForegroundColor Red
    }
}

function Test-Stage {
    param(
        [string]$Name,
        [int]$StageNum,
        [scriptblock]$TestScript,
        [string]$FailureMessage
    )

    Write-Host ""
    Write-Host "  Running stage test for '$Name'..." -ForegroundColor Cyan
    $passed = & $TestScript
    if ($passed -eq $true) {
        Write-Host "[PASS] Stage $StageNum/5: $Name" -ForegroundColor Green
        $script:StageResults += [PSCustomObject]@{ Name = $Name; Status = "PASS" }
    }
    else {
        Write-Host "[FAIL] Stage $StageNum/5: $Name" -ForegroundColor Red
        Write-Err $FailureMessage
        $script:StageResults += [PSCustomObject]@{ Name = $Name; Status = "FAIL" }
        Print-Summary
        exit 1
    }
}

function Skip-Stage {
    param(
        [string]$Name,
        [int]$StageNum
    )
    Write-Host "[SKIP] Stage $StageNum/5: $Name" -ForegroundColor Yellow
    $script:StageResults += [PSCustomObject]@{ Name = $Name; Status = "SKIP" }
}

# ============================================================
# Stage 0: Check winget availability
# ============================================================
Write-Step "AnaPPTAgent Windows Setup (5 stages)"

if (-not (Test-Command "winget")) {
    Write-Err "winget (App Installer) is not available on this system."
    Write-Err "Please install 'App Installer' from the Microsoft Store first:"
    Write-Err "  https://www.microsoft.com/store/apps/9NBLGGH4NNS1"
    Write-Host ""
    Write-Host "Alternatively, install prerequisites manually:" -ForegroundColor Yellow
    Write-Host "  git:     https://git-scm.com/download/win"
    Write-Host "  uv:      https://docs.astral.sh/uv/getting-started/installation/"
    Write-Host "  Node.js: https://nodejs.org/"
    exit 1
}

Write-Ok "winget is available."

# ============================================================
# Stage 1: git
# ============================================================
Write-Step "Stage 1/5: git"

if (Test-Command "git") {
    $gitVersion = git --version 2>&1
    Write-Ok "git is already installed: $gitVersion"
}
else {
    $success = Install-ViaWinget -Id "Git.Git" -DisplayName "git"
    if (-not $success) {
        Write-Err "Cannot continue without git. Please install it manually: https://git-scm.com/download/win"
        $script:StageResults += [PSCustomObject]@{ Name = "git"; Status = "FAIL" }
        Print-Summary
        exit 1
    }
    Refresh-Path
}

Test-Stage -Name "git" -StageNum 1 -TestScript {
    git --version 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { return $false }
    git clone --help 2>&1 | Out-Null
    return ($LASTEXITCODE -eq 0)
} -FailureMessage "git installation verification failed. 'git --version' or 'git clone --help' did not return exit code 0. Please verify git is properly installed and on PATH."

# ============================================================
# Stage 2: uv
# ============================================================
Write-Step "Stage 2/5: uv"

if (Test-Command "uv") {
    $uvVersion = uv --version 2>&1
    Write-Ok "uv is already installed: $uvVersion"
}
else {
    $success = Install-ViaWinget -Id "astral-sh.uv" -DisplayName "uv"
    if (-not $success) {
        Write-Warn "Failed to install uv via winget. Trying alternative method (pip)..."
        if (Test-Command "pip") {
            Write-Host "  Installing uv via pip..."
            $pipOutput = pip install uv 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Err "Failed to install uv via pip. Output: $pipOutput"
                Write-Err "Please install manually: https://docs.astral.sh/uv/getting-started/installation/"
                $script:StageResults += [PSCustomObject]@{ Name = "uv"; Status = "FAIL" }
                Print-Summary
                exit 1
            }
            Write-Ok "uv installed via pip."
        }
        else {
            Write-Err "Neither winget nor pip is available to install uv."
            Write-Err "Please install manually: https://docs.astral.sh/uv/getting-started/installation/"
            $script:StageResults += [PSCustomObject]@{ Name = "uv"; Status = "FAIL" }
            Print-Summary
            exit 1
        }
    }
    Refresh-Path
}

Test-Stage -Name "uv" -StageNum 2 -TestScript {
    uv --version 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { return $false }
    uv tool --help 2>&1 | Out-Null
    return ($LASTEXITCODE -eq 0)
} -FailureMessage "uv installation verification failed. 'uv --version' or 'uv tool --help' did not return exit code 0. Please verify uv is properly installed and on PATH."

# ============================================================
# Stage 3: Node.js
# ============================================================
Write-Step "Stage 3/5: Node.js"

if ($SkipNode) {
    Write-Warn "Skipping Node.js installation (-SkipNode flag set). PPTX export will not be available."
    Skip-Stage -Name "Node.js" -StageNum 3
}
else {
    if (Test-Command "node") {
        $nodeVersion = node --version 2>&1
        Write-Ok "Node.js is already installed: $nodeVersion"
    }
    else {
        $success = Install-ViaWinget -Id "OpenJS.NodeJS.LTS" -DisplayName "Node.js LTS"
        if (-not $success) {
            Write-Err "Failed to install Node.js. Please install manually: https://nodejs.org/"
            $script:StageResults += [PSCustomObject]@{ Name = "Node.js"; Status = "FAIL" }
            Print-Summary
            exit 1
        }
        Refresh-Path
    }

    Test-Stage -Name "Node.js" -StageNum 3 -TestScript {
        node --version 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { return $false }
        npm --version 2>&1 | Out-Null
        return ($LASTEXITCODE -eq 0)
    } -FailureMessage "Node.js installation verification failed. 'node --version' or 'npm --version' did not return exit code 0. Please verify Node.js is properly installed and on PATH."
}

# ============================================================
# Stage 4: clone
# ============================================================
Write-Step "Stage 4/5: clone"

if ($SkipClone) {
    Write-Warn "Skipping clone (-SkipClone flag set). Assuming current directory is the repository root."
    $clonePath = (Get-Location).Path
    Skip-Stage -Name "clone" -StageNum 4
}
else {
    if ($TargetDir -eq "") {
        $TargetDir = (Get-Location).Path
    }

    $clonePath = Join-Path $TargetDir "AnaPPTAgent"

    if (Test-Path $clonePath) {
        Write-Err "Directory already exists: $clonePath"
        Write-Err "Please remove it or choose a different target directory."
        $script:StageResults += [PSCustomObject]@{ Name = "clone"; Status = "FAIL" }
        Print-Summary
        exit 1
    }

    Write-Host "  Cloning from: $RepoUrl"
    Write-Host "  Target: $clonePath"

    git clone $RepoUrl $clonePath 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to clone repository. Please check the URL: $RepoUrl"
        $script:StageResults += [PSCustomObject]@{ Name = "clone"; Status = "FAIL" }
        Print-Summary
        exit 1
    }

    Write-Ok "Repository cloned successfully."
    Set-Location $clonePath

    Test-Stage -Name "clone" -StageNum 4 -TestScript {
        $pyproject = Join-Path $clonePath "pyproject.toml"
        $initFile = Join-Path $clonePath "src\anappt\__init__.py"
        if (-not (Test-Path $pyproject)) { return $false }
        if ((Get-Item $pyproject).Length -eq 0) { return $false }
        if (-not (Test-Path $initFile)) { return $false }
        if ((Get-Item $initFile).Length -eq 0) { return $false }
        return $true
    } -FailureMessage "Clone verification failed. 'pyproject.toml' or 'src/anappt/__init__.py' is missing or empty. Please check the repository contents at: $clonePath"
}

# ============================================================
# Stage 5: uv tool install
# ============================================================
Write-Step "Stage 5/5: uv tool install"

Write-Host "  Running 'uv tool install --force .'..."
$installOutput = uv tool install --force . 2>&1
$installExitCode = $LASTEXITCODE
if ($installOutput) {
    $installOutput | ForEach-Object { Write-Host "  $_" }
}
if ($installExitCode -ne 0) {
    Write-Err "Failed to install AnaPPTAgent as uv tool."
    Write-Err "Try running manually: uv tool install --force ."
    $script:StageResults += [PSCustomObject]@{ Name = "uv tool install"; Status = "FAIL" }
    Print-Summary
    exit 1
}

Write-Ok "AnaPPTAgent installed as uv tool."

# Refresh PATH to pick up newly installed anappt binary
Refresh-Path

Test-Stage -Name "uv tool install" -StageNum 5 -TestScript {
    # Refresh PATH again in case the binary was just installed
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

    $output = ""
    $exitCode = 1

    try {
        if (Test-Command "anappt") {
            $output = anappt --help 2>&1 | Out-String
            $exitCode = $LASTEXITCODE
        }
    } catch {
        $exitCode = 1
    }

    if ($exitCode -ne 0) {
        try {
            if (Test-Command "uv") {
                $output = uv tool run anappt --help 2>&1 | Out-String
                $exitCode = $LASTEXITCODE
            }
        } catch {
            $exitCode = 1
        }
    }

    if ($exitCode -ne 0) {
        try {
            if (Test-Command "uvx") {
                $output = uvx anappt --help 2>&1 | Out-String
                $exitCode = $LASTEXITCODE
            }
        } catch {
            $exitCode = 1
        }
    }

    return ($exitCode -eq 0 -and $output -match "anappt")
} -FailureMessage "anappt command verification failed. 'anappt --help' did not return exit code 0 or output did not contain 'anappt'. Try: 1) restart your terminal to refresh PATH, 2) check 'uv tool list', 3) run 'uv tool install --force .' manually."

# ============================================================
# Installation Summary
# ============================================================
Print-Summary

# ============================================================
# Next steps
# ============================================================
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

exit 0