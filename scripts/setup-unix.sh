#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# AnaPPTAgent Unix Setup Script (Linux / macOS)
# Five-stage install: git -> uv -> Node.js -> clone -> uv tool install
# ============================================================

# --- Color constants ---
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

# --- Stage results accumulator (PASS / FAIL / SKIP) ---
STAGE_RESULTS=()

# --- Default parameter values ---
REPO_URL="https://github.com/SidneyLYZhang/AnaPPTAgent.git"
TARGET_DIR=""
SKIP_NODE=false
SKIP_CLONE=false

# ============================================================
# Helper functions
# ============================================================

usage() {
    cat <<'EOF'
Usage: setup-unix.sh [OPTIONS]

AnaPPTAgent Unix Setup Script (Linux/macOS)

Options:
    -r, --repo-url <url>      Git repository URL
                              (default: https://github.com/SidneyLYZhang/AnaPPTAgent.git)
    -t, --target-dir <dir>    Target parent directory for cloning
                              (default: current directory)
        --skip-node           Skip Stage 3 (Node.js installation)
        --skip-clone          Skip Stage 4 (assume already in repo root)
    -h, --help                Show this help message and exit

Stages:
    1. git              Check and install git
    2. uv               Check and install uv
    3. Node.js          Check and install Node.js (skippable with --skip-node)
    4. clone            Clone AnaPPTAgent repository (skippable with --skip-clone)
    5. uv tool install  Install anappt as a uv tool

Examples:
    bash setup-unix.sh
    bash setup-unix.sh --skip-node
    bash setup-unix.sh -r https://github.com/user/AnaPPTAgent.git -t /tmp
    bash setup-unix.sh --skip-clone
EOF
}

log_step() {
    local msg="$1"
    printf "\n${CYAN}==== %s ====${NC}\n" "$msg"
}

log_ok() {
    local msg="$1"
    printf "${GREEN}%s${NC}\n" "$msg"
}

log_warn() {
    local msg="$1"
    printf "${YELLOW}%s${NC}\n" "$msg"
}

log_err() {
    local msg="$1"
    printf "${RED}%s${NC}\n" "$msg" >&2
}

# test_stage <stage_name> <stage_num> <test_cmd> <fail_msg>
# Runs test_cmd via eval; on success appends PASS, on failure appends FAIL and exit 1.
# Uses `if eval ...` so set -e does not trigger on test failure.
test_stage() {
    local stage_name="$1"
    local stage_num="$2"
    local test_cmd="$3"
    local fail_msg="$4"

    if eval "$test_cmd"; then
        log_ok "[PASS] Stage $stage_num/5: $stage_name"
        STAGE_RESULTS+=("PASS")
    else
        log_err "[FAIL] Stage $stage_num/5: $stage_name"
        log_err "  $fail_msg"
        STAGE_RESULTS+=("FAIL")
        exit 1
    fi
}

# skip_stage <stage_name> <stage_num>
skip_stage() {
    local stage_name="$1"
    local stage_num="$2"
    printf "${YELLOW}[SKIP] Stage %d/5: %s${NC}\n" "$stage_num" "$stage_name"
    STAGE_RESULTS+=("SKIP")
}

# print_summary: print the installation summary table.
print_summary() {
    local -a STAGE_NAMES=("git" "uv" "Node.js" "clone" "uv tool install")
    printf "\n"
    printf "==================== Installation Summary ====================\n"
    for i in 0 1 2 3 4; do
        printf "Stage %d/5: %-25s [%s]\n" "$((i+1))" "${STAGE_NAMES[$i]}" "${STAGE_RESULTS[$i]}"
    done
    printf "==============================================================\n"
}

# detect_package_manager: echo the package manager command name.
# Order: apt-get -> dnf -> pacman -> apk -> brew. Exit 1 if none found.
detect_package_manager() {
    if command -v apt-get &> /dev/null; then
        echo "apt-get"
    elif command -v dnf &> /dev/null; then
        echo "dnf"
    elif command -v pacman &> /dev/null; then
        echo "pacman"
    elif command -v apk &> /dev/null; then
        echo "apk"
    elif command -v brew &> /dev/null; then
        echo "brew"
    else
        log_err "未识别的包管理器(支持 apt-get / dnf / pacman / apk / brew)"
        log_err "请手动安装所需依赖后重试"
        exit 1
    fi
}

# ============================================================
# Parameter parsing
# ============================================================

while [[ $# -gt 0 ]]; do
    case "$1" in
        -r|--repo-url)
            REPO_URL="$2"
            shift 2
            ;;
        -t|--target-dir)
            TARGET_DIR="$2"
            shift 2
            ;;
        --skip-node)
            SKIP_NODE=true
            shift
            ;;
        --skip-clone)
            SKIP_CLONE=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            log_err "未知参数: $1"
            usage
            exit 1
            ;;
    esac
done

if [[ -z "$TARGET_DIR" ]]; then
    TARGET_DIR="$(pwd)"
fi

# ============================================================
# Stage 1/5: git
# ============================================================
log_step "Stage 1/5: git"

if command -v git &> /dev/null; then
    log_ok "git 已安装,跳过安装步骤"
else
    if [[ "$(uname -s)" == "Darwin" ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            brew install git || { log_err "brew install git 失败"; exit 1; }
        else
            log_err "macOS 上未检测到 Homebrew"
            log_err "请运行 'xcode-select --install' 安装 Xcode Command Line Tools(包含 git)"
            log_err "或安装 Homebrew: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
            exit 1
        fi
    else
        # Linux
        PM="$(detect_package_manager)"
        case "$PM" in
            apt-get)
                sudo apt-get update && sudo apt-get install -y git || { log_err "apt-get 安装 git 失败"; exit 1; }
                ;;
            dnf)
                sudo dnf install -y git || { log_err "dnf 安装 git 失败"; exit 1; }
                ;;
            pacman)
                sudo pacman -S --noconfirm git || { log_err "pacman 安装 git 失败"; exit 1; }
                ;;
            apk)
                sudo apk add --no-cache git || { log_err "apk 安装 git 失败"; exit 1; }
                ;;
            brew)
                brew install git || { log_err "brew install git 失败"; exit 1; }
                ;;
        esac
    fi
fi

test_stage "git" 1 "git --version && git clone --help > /dev/null 2>&1" "git 不可用,请检查安装"

# ============================================================
# Stage 2/5: uv
# ============================================================
log_step "Stage 2/5: uv"

if command -v uv &> /dev/null; then
    log_ok "uv 已安装,跳过安装步骤"
else
    curl -LsSf https://astral.sh/uv/install.sh | sh || { log_err "uv 安装失败,请检查网络或手动安装"; exit 1; }
    export PATH="$HOME/.local/bin:$PATH"
    source "$HOME/.local/bin/env" 2>/dev/null || true
fi

test_stage "uv" 2 "uv --version && uv tool --help > /dev/null 2>&1" "uv 不可用,请检查安装"

# ============================================================
# Stage 3/5: Node.js
# ============================================================
log_step "Stage 3/5: Node.js"

if [[ "$SKIP_NODE" == "true" ]]; then
    skip_stage "Node.js" 3
else
    if command -v node &> /dev/null; then
        log_ok "Node.js 已安装,跳过安装步骤"
    else
        if [[ "$(uname -s)" == "Darwin" ]]; then
            # macOS
            if command -v brew &> /dev/null; then
                brew install node || { log_err "brew install node 失败"; exit 1; }
            else
                log_err "macOS 上未检测到 Homebrew,无法安装 Node.js"
                log_err "请安装 Homebrew 或从 https://nodejs.org/ 手动安装"
                exit 1
            fi
        else
            # Linux: prefer system package manager, fallback to NodeSource
            PM="$(detect_package_manager)"
            node_installed=false
            case "$PM" in
                apt-get)
                    if sudo apt-get install -y nodejs npm; then
                        node_installed=true
                    fi
                    ;;
                dnf)
                    if sudo dnf install -y nodejs npm; then
                        node_installed=true
                    fi
                    ;;
                pacman)
                    if sudo pacman -S --noconfirm nodejs npm; then
                        node_installed=true
                    fi
                    ;;
                apk)
                    if sudo apk add --no-cache nodejs npm; then
                        node_installed=true
                    fi
                    ;;
                brew)
                    if brew install node; then
                        node_installed=true
                    fi
                    ;;
            esac

            if [[ "$node_installed" != "true" ]]; then
                log_warn "系统包管理器安装 Node.js 失败,尝试 NodeSource 回退(Debian/Ubuntu)..."
                if [[ "$PM" == "apt-get" ]]; then
                    curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash - || { log_err "NodeSource 安装脚本执行失败"; exit 1; }
                    sudo apt-get install -y nodejs || { log_err "apt-get install nodejs 失败"; exit 1; }
                else
                    log_err "Node.js 安装失败且当前系统不支持 NodeSource 回退(仅 Debian/Ubuntu)"
                    log_err "请从 https://nodejs.org/ 手动安装"
                    exit 1
                fi
            fi
        fi
    fi

    test_stage "Node.js" 3 "node --version && npm --version > /dev/null 2>&1" "Node.js 不可用,请检查安装"
fi

# ============================================================
# Stage 4/5: clone
# ============================================================
log_step "Stage 4/5: clone"

if [[ "$SKIP_CLONE" == "true" ]]; then
    CLONE_PATH="$(pwd)"
    log_ok "已在仓库根目录,跳过 clone: $CLONE_PATH"
else
    CLONE_PATH="$TARGET_DIR/AnaPPTAgent"
    if [[ -e "$CLONE_PATH" ]]; then
        log_err "目录已存在: $CLONE_PATH"
        exit 1
    fi
    git clone "$REPO_URL" "$CLONE_PATH" || { log_err "git clone 失败,请检查 URL: $REPO_URL"; exit 1; }
    cd "$CLONE_PATH"
fi

test_stage "clone" 4 "[ -s \"$CLONE_PATH/pyproject.toml\" ] && [ -s \"$CLONE_PATH/src/anappt/__init__.py\" ]" "仓库结构不完整"

# ============================================================
# Stage 5/5: uv tool install
# ============================================================
log_step "Stage 5/5: uv tool install"

# Ensure we are in the repo root for `uv tool install .`
cd "$CLONE_PATH"
uv tool install --force . || { log_err "uv tool install 失败,请检查 pyproject.toml 或网络"; exit 1; }
export PATH="$HOME/.local/bin:$PATH"

# 三级回退测试:anappt -> uv tool run anappt -> uvx anappt
STAGE5_PASS=false
if anappt --help 2>&1 | grep -q 'anappt' 2>/dev/null; then
    STAGE5_PASS=true
elif uv tool run anappt --help 2>&1 | grep -q 'anappt' 2>/dev/null; then
    log_warn "anappt 不在 PATH 中,但可通过 'uv tool run anappt' 调用,请重启终端或检查 PATH"
    STAGE5_PASS=true
elif uvx anappt --help 2>&1 | grep -q 'anappt' 2>/dev/null; then
    log_warn "anappt 不在 PATH 中,但可通过 'uvx anappt' 调用,请重启终端或检查 PATH"
    STAGE5_PASS=true
fi

if [ "$STAGE5_PASS" = "true" ]; then
    log_ok "[PASS] Stage 5/5: uv tool install"
    STAGE_RESULTS+=("PASS")
else
    log_err "[FAIL] Stage 5/5: uv tool install"
    log_err "anappt 命令不可用,请检查 'uv tool list' 或重启终端"
    STAGE_RESULTS+=("FAIL")
    print_summary
    exit 1
fi

# ============================================================
# Installation Summary
# ============================================================
print_summary

log_ok "AnaPPTAgent 安装完成!运行 'anappt --help' 开始使用。"
