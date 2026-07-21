# 安装指南

本页详细介绍 AnaPPTAgent 的三种安装方式、验证方法、升级/卸载以及常见问题排查。

## 前置条件

| 依赖 | 版本要求 | 必需性 | 用途 |
|------|---------|--------|------|
| Python | >= 3.11（< 3.14） | 必需 | 运行 anappt |
| uv 包管理器 | 最新版 | 必需 | 安装与运行 anappt |
| git | 任意版本 | 必需（自动脚本安装时） | 克隆仓库 |
| Node.js + npm | >= 20 | 可选 | PPTX 导出（HTML 输出不需要） |
| Chrome / Chromium / Edge | 任意现代版本 | 可选 | PPTX 渲染（HTML 输出不需要） |

!!! note "关于 Node.js 与浏览器"
    未安装 Node.js 时，S6 阶段会自动回退为仅输出 HTML 格式，仍可在浏览器中打开并打印为 PDF。

!!! note "Node.js/npm 与 dashi-ppt-skill 的关系"
    安装脚本（方式一）与手动安装（方式二）只负责安装 Node.js + npm 等**前置依赖**；dashi-ppt-skill 本体由 `anappt setup` 或 `anappt new` 触发下载（详见下文[安装 dashi-ppt-skill](#安装-dashi-ppt-skill)小节）。

## 方式一：自动安装脚本（推荐）

AnaPPTAgent 提供跨平台的一键安装脚本，会自动安装依赖、克隆仓库并将 `anappt` 安装为全局可用的 uv 工具。

=== "Windows"

    **PowerShell**（一键下载并运行，无需先 clone）：

    ```powershell
    # 一键下载并运行（无需先 clone）
    Invoke-WebRequest -UseBasicParsing https://raw.githubusercontent.com/SidneyLYZhang/AnaPPTAgent/main/scripts/setup-windows.ps1 | Invoke-Expression
    ```

    或者先 clone 再运行：

    ```powershell
    git clone https://github.com/SidneyLYZhang/AnaPPTAgent.git AnaPPTAgent
    cd AnaPPTAgent
    .\scripts\setup-windows.ps1
    ```

=== "Linux / macOS"

    **Bash**（一键下载并运行）：

    ```bash
    # 一键下载并运行
    curl -fsSL https://raw.githubusercontent.com/SidneyLYZhang/AnaPPTAgent/main/scripts/setup-unix.sh | bash
    ```

    或者先 clone 再运行：

    ```bash
    git clone https://github.com/SidneyLYZhang/AnaPPTAgent.git AnaPPTAgent
    cd AnaPPTAgent
    bash scripts/setup-unix.sh
    ```

脚本会执行 5 个阶段（git / uv / Node.js / clone / uv tool install），每个阶段都有验证测试，最后输出汇总表。脚本只负责安装 Node.js + npm 等**前置依赖**；dashi-ppt-skill 本体由 `anappt setup` 或 `anappt new` 触发下载（详见[安装 dashi-ppt-skill](#安装-dashi-ppt-skill)小节）。

### 常用参数

两种脚本支持的参数对照如下：

| 参数 | Windows | Unix | 说明 |
|------|---------|------|------|
| `--skip-node` | `-SkipNode` | `--skip-node` | 跳过 Node.js 安装（适用于 CI 或已安装） |
| `--skip-clone` | `-SkipClone` | `--skip-clone` | 跳过 clone（适用于已在仓库根目录运行） |
| `-r <url>` | `-RepoUrl <url>` | `-r <url>` 或 `--repo-url <url>` | 指定仓库 URL（fork 时使用） |
| `-t <dir>` | `-TargetDir <dir>` | `-t <dir>` 或 `--target-dir <dir>` | 指定 clone 目标父目录 |
| 帮助 | 无（查看脚本头注释） | `-h` 或 `--help` | 显示帮助 |

**示例**：

```bash
# Unix：跳过 Node.js 与 clone，从当前目录直接安装
bash scripts/setup-unix.sh --skip-node --skip-clone

# Windows：使用 fork 仓库并指定目标目录
.\scripts\setup-windows.ps1 -RepoUrl "https://github.com/user/AnaPPTAgent.git" -TargetDir "D:\Projects"
```

## 方式二：手动安装

适用于已熟悉工具链或需要自定义流程的用户。

1. 安装 Python >= 3.11（< 3.14）：https://www.python.org/downloads/
2. 安装 uv：https://docs.astral.sh/uv/getting-started/installation/
3. 克隆仓库并安装为 uv 工具：

    ```bash
    git clone https://github.com/SidneyLYZhang/AnaPPTAgent.git AnaPPTAgent
    cd AnaPPTAgent
    uv tool install .
    ```

!!! tip "关于 `uv tool install .`"
    `uv tool install .` 会让 `anappt` 命令全局可用（无需 `uv run` 前缀）。安装后如果 `anappt` 命令找不到，请重启终端或检查 PATH 是否包含 uv 的 bin 目录（Linux/macOS 通常在 `~/.local/bin`，Windows 在 `%USERPROFILE%\.local\bin`）。

!!! note "Node.js 与 skill 安装"
    方式二仅安装 Python 工具链；Node.js + npm 需自行安装（见[前置条件](#前置条件)表），dashi-ppt-skill 本体由 `anappt setup` 或 `anappt new` 触发下载（详见[安装 dashi-ppt-skill](#安装-dashi-ppt-skill)小节）。

## 方式三：开发模式

适用于需要修改源码或运行测试套件（pytest、ruff）的贡献者。

```bash
git clone https://github.com/SidneyLYZhang/AnaPPTAgent.git AnaPPTAgent
cd AnaPPTAgent
uv sync --extra dev
```

说明：

- `uv sync --extra dev` 会安装 `pyproject.toml` 中的 `dev` 可选依赖（pytest、pytest-cov、pytest-asyncio、ruff）。
- 开发模式下可通过 `uv run anappt --help` 调用，无需全局安装。
- 运行测试：

    ```bash
    uv run pytest
    ```

- 运行 lint：

    ```bash
    uv run ruff check src tests
    ```

## 安装验证

提供三种验证方式：

```bash
# 方式 1：直接调用
anappt --help

# 方式 2：通过 uv tool run（PATH 未生效时的回退）
uv tool run anappt --help

# 方式 3：通过 uvx（最简形式）
uvx anappt --help
```

期望输出包含 `anappt` 字样与子命令列表（`new`、`run`、`resume`、`status`、`config`、`interactive`）。

另外可以查看已安装的 uv 工具列表：

```bash
uv tool list
```

应能看到 `anappt` 一项。

## 安装 dashi-ppt-skill

dashi-ppt-skill 是 S6 阶段 PPT 渲染的核心依赖，通过 `anappt setup` 命令安装。

`anappt setup` 会依次检查 Node.js ≥ 20、npm、Chrome（可选），然后调用 `npx dashi-ppt-skill@latest --dir <path>` 将 skill 安装到 `~/.anappt/skills/dashi-ppt/`。安装后 skill 父目录会持久化到 `~/.anappt/config.yaml`。

推荐两种触发方式：

- **方式 A**：运行 `anappt new <project>` 时自动尝试安装（除非加 `--no-skill` 跳过）。
- **方式 B**：手动运行 `anappt setup`：
    - `--dir <path>`：指定 skill 安装父目录（默认 `~/.anappt/skills`）。
    - `--registry <url>`：指定 npm 镜像地址（如 `https://registry.npmmirror.com`）。

```bash
# 手动安装或更新 skill
anappt setup

# 指定安装目录与 npm 镜像
anappt setup --dir /opt/anappt/skills --registry https://registry.npmmirror.com
```

未安装 skill 时 S6 阶段会失败并提示运行 `anappt setup`。

## 升级与卸载

### 升级

```bash
# 进入仓库目录拉取最新代码后重新安装
cd AnaPPTAgent
git pull
uv tool install --force .
```

### 卸载

```bash
uv tool uninstall anappt
```

## 常见问题

??? question "`anappt: command not found`"
    PATH 未刷新。重启终端；Linux/macOS 检查 `~/.local/bin` 是否在 PATH 中；Windows 检查 `%USERPROFILE%\.local\bin`。

??? question "`winget is not available`（Windows 脚本）"
    从 Microsoft Store 安装 "App Installer"，或手动安装 git/uv/Node.js 后改用 `--skip-clone` 模式。

??? question "`Node.js 安装失败`"
    改用 `--skip-node` 跳过（PPTX 导出将不可用，HTML 输出不受影响），或从 https://nodejs.org/ 手动安装。

??? question "`uv tool install` 失败"
    检查 Python 版本（需 >= 3.11, < 3.14）；检查网络代理；尝试 `uv tool install --force .`。

??? question "代理问题"
    设置环境变量：`HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY`（支持 socks5）。

    ```bash
    # 示例（Linux/macOS）
    export HTTP_PROXY=http://127.0.0.1:7890
    export HTTPS_PROXY=http://127.0.0.1:7890
    export ALL_PROXY=socks5://127.0.0.1:7890
    ```

    ```powershell
    # 示例（Windows PowerShell）
    $env:HTTP_PROXY = "http://127.0.0.1:7890"
    $env:HTTPS_PROXY = "http://127.0.0.1:7890"
    $env:ALL_PROXY = "socks5://127.0.0.1:7890"
    ```

??? question "PPTX 导出失败"
    运行 `anappt setup` 重新安装 dashi-ppt-skill。确认 Node.js >= 20 与 Chrome/Chromium/Edge 已安装。

## 下一步

安装完成后，继续阅读：

- [CLI 使用指南](cli-usage.md)
- [交互式 TUI 指南](tui-usage.md)
- [报告生成流程](report-workflow.md)
- [PPT 生成流程](ppt-workflow.md)
- [返回首页](index.md)
