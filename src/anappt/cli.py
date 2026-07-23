"""CLI and interactive UI for AnaPPTAgent.

Provides the main entry point and command-line interface for the tool.
Supports: init, run, resume, status, config, and interactive mode.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from anappt.conversation import ConversationRunner
from anappt.i18n import t
from anappt.io.config import ReportConfig
from anappt.io.git_auto import GitAutoCommit
from anappt.io.memory import MemoryManager
from anappt.io.session import SessionLogger
from anappt.io.state import StateManager
from anappt.llm.provider import AnaPPTLLM, load_global_config, save_global_config
from anappt.orchestrator import Orchestrator
from anappt.project import create_project, is_anappt_project
from anappt.stage_base import StageBase
from anappt.stages.s1_topic import S1TopicStage
from anappt.stages.s2_data_req import S2DataRequirementStage
from anappt.stages.s3_data_load import S3DataLoadStage
from anappt.stages.s4_analysis import S4AnalysisStage
from anappt.stages.s5_report import S5ReportStage
from anappt.stages.s6_ppt import S6PPTStage
from anappt.types import InteractiveUIProtocol, PipelineContext


class InteractiveUI:
    """Interactive console UI implementing InteractiveUIProtocol.

    Uses rich for formatted output when available, falls back to
    plain print/input.
    """

    def __init__(self, use_rich: bool = True) -> None:
        """Initialize the UI.

        Args:
            use_rich: Whether to attempt using rich for formatting.
        """
        self._use_rich: bool = False
        if use_rich:
            try:
                from rich.console import Console
                from rich.table import Table

                self._console: Console = Console()
                self._Table: type[Table] = Table  # type: ignore[assignment]
                self._use_rich = True
            except ImportError:
                self._use_rich = False

    def print(self, message: str) -> None:
        """Print a message to the console.

        Args:
            message: Text to display.
        """
        if self._use_rich:
            self._console.print(message)
        else:
            print(message)

    def input(self, prompt: str) -> str:
        """Read a line of input from the user.

        Args:
            prompt: Prompt text to display.

        Returns:
            The user's input string.
        """
        return input(prompt)

    def confirm(self, prompt: str) -> bool:
        """Ask the user for a yes/no confirmation.

        Args:
            prompt: Confirmation prompt text.

        Returns:
            True if the user confirmed (y/yes).
        """
        response = self.input(f"{prompt} [y/N]: ")
        return response.strip().lower() in ("y", "yes")

    def table(self, headers: list[str], rows: list[list[str]]) -> None:
        """Display a table to the user.

        Args:
            headers: Column header strings.
            rows: List of row data, each row a list of cell strings.
        """
        if self._use_rich:
            tbl = self._Table()
            for header in headers:
                tbl.add_column(header)
            for row in rows:
                tbl.add_row(*row)
            self._console.print(tbl)
        else:
            # Simple text table
            col_widths = [len(h) for h in headers]
            for row in rows:
                for i, cell in enumerate(row):
                    if i < len(col_widths):
                        col_widths[i] = max(col_widths[i], len(cell))

            # Print headers
            header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
            print(header_line)
            print("-+-".join("-" * w for w in col_widths))
            for row in rows:
                line = " | ".join(
                    str(row[i]).ljust(col_widths[i]) if i < len(row) else ""
                    for i in range(len(headers))
                )
                print(line)

    def progress(self, message: str) -> None:
        """Show a progress/status message.

        Args:
            message: Progress message to display.
        """
        self.print(f"[{message}]")


def _build_stages() -> list[StageBase]:
    """Create and return all six pipeline stages in order.

    Returns:
        List of StageBase instances (S1 through S6).
    """
    return [
        S1TopicStage(),
        S2DataRequirementStage(),
        S3DataLoadStage(),
        S4AnalysisStage(),
        S5ReportStage(),
        S6PPTStage(),
    ]


def _load_pipeline_context(
    project_dir: str | Path,
    ui: InteractiveUIProtocol | None = None,
) -> PipelineContext:
    """Load the pipeline context for a project directory.

    ``report.yaml`` is optional at this stage: when missing or unparseable,
    an empty :class:`ReportConfig` is used as a placeholder. The S1
    conversation stage is responsible for generating ``report.yaml``; later
    stages will re-read it as needed.

    Args:
        project_dir: Path to the project directory.
        ui: Optional UI instance.

    Returns:
        PipelineContext ready for orchestration.
    """
    project_dir = Path(project_dir)
    report_yaml_path = project_dir / "report.yaml"

    # Load config — fall back to an empty ReportConfig when report.yaml is
    # missing or unparseable. S1 (conversation) generates it later.
    config = ReportConfig()
    if report_yaml_path.exists():
        try:
            config = ReportConfig.from_yaml(report_yaml_path)
        except Exception:
            config = ReportConfig()

    # Load models config (global only — project-level models.yaml is no longer read)
    models_config = load_global_config()

    # Warn if a stale project-level models.yaml exists (no longer read)
    project_models_path = project_dir / ".anappt" / "models.yaml"
    if project_models_path.exists():
        print(t("cli.config.project_models_ignored", path=str(project_models_path)))

    # Inject web tool config (env vars still take precedence inside the modules)
    try:
        from anappt.tools import web_fetch, web_search
        web_search.configure_from_models_config(models_config)
        web_fetch.configure_from_models_config(models_config)
    except Exception as e:
        print(f"⚠ web 工具配置初始化失败(将回退到环境变量): {e}")

    # Create LLM provider
    llm = AnaPPTLLM(models_config)

    # Create state manager
    state_file = project_dir / ".anappt" / "state.yaml"
    state = StateManager(state_file)

    # Create session logger
    session = SessionLogger(project_dir / ".anappt" / "session_history")

    # Create git auto-commit
    git = GitAutoCommit(project_dir)

    # Create project memory manager (``memory.md`` may not exist yet —
    # MemoryManager.read() tolerates absence and returns "").
    memory = MemoryManager(project_dir / ".anappt" / "memory.md")

    # Construct SkillManager (failure is non-fatal: skill_manager will be None)
    from anappt.io.skill_manager import SkillManager
    try:
        mgr = SkillManager()
    except Exception as e:
        print(f"⚠ SkillManager 构造失败,skill_manager 将为 None: {e}")
        mgr = None

    return PipelineContext(
        project_dir=project_dir,
        config=config,
        llm=llm,
        state=state,
        ui=ui,
        session=session,
        git=git,
        skill_manager=mgr,
        memory=memory,
    )


def cmd_init(args: list[str]) -> int:
    """Handle the 'init' command.

    Behavior:
      - ``anappt init`` (no name argument): initialize the current working
        directory in place. If the directory already contains
        ``.anappt/state.yaml``, exit with code 1.
      - ``anappt init <name>``: create a ``<name>/`` subdirectory under the
        current working directory and initialize it (legacy behavior).

    Args:
        args: Command arguments (optional project name).
            Optional flags:
              --no-skill          Skip dashi-ppt-skill download.
              --registry <url>    npm registry URL passed to install_or_update_skill.

    Returns:
        Exit code (0 for success).
    """
    project_name = None
    no_skill = False
    registry = None
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--no-skill":
            no_skill = True
        elif arg == "--registry":
            if i + 1 >= len(args):
                print(t("cli.usage"))
                return 1
            registry = args[i + 1]
            i += 1
        elif arg.startswith("--registry="):
            registry = arg[len("--registry="):]
        elif not arg.startswith("--") and project_name is None:
            project_name = arg
        else:
            print(t("cli.usage"))
            return 1
        i += 1

    if project_name is None:
        # In-place init: initialize the current working directory.
        project_dir = Path.cwd()
        if is_anappt_project(project_dir):
            print(t("cli.already_anappt_project", path=str(project_dir)))
            return 1
        # Best-effort project name from the current directory name.
        effective_name = project_dir.name
        try:
            result_path = create_project(
                project_dir,
                project_name=effective_name,
                init_git=True,
                in_place=True,
            )
            print(t("cli.in_place_initialized", path=str(result_path)))
            print(t("cli.edit_report", path=str(result_path / "report.yaml")))
            print(t("cli.put_data", path=str(result_path / "data")))
            print(t("cli.run_to_start"))
        except FileExistsError as e:
            print(str(e))
            return 1
    else:
        # Subdirectory init: create <name>/ under cwd.
        project_dir = Path.cwd() / project_name
        try:
            result_path = create_project(
                project_dir,
                project_name=project_name,
                init_git=True,
            )
            print(t("cli.new_project_created", path=str(result_path)))
            print(t("cli.edit_report", path=str(result_path / "report.yaml")))
            print(t("cli.put_data", path=str(result_path / "data")))
            print(t("cli.cd_to_start", name=project_name))
        except FileExistsError as e:
            print(str(e))
            return 1

    # Skill download sub-flow (anappt new 集成 skill 下载)
    # Does NOT block cmd_init: project is already created; skill failures
    # only print warnings so the user can run `anappt setup` later.
    if no_skill:
        print(t("cli.new_skill_skipped"))
    else:
        try:
            from anappt.io.skill_manager import SkillManager
            mgr = SkillManager()
            print(t("cli.new_skill_checking"))
            existing = mgr.locate_skill()
            if existing is not None:
                print(t("cli.new_skill_already_installed", path=existing))
            else:
                node_ok, node_ver = mgr.check_node()
                if not node_ok:
                    print(t("cli.new_skill_env_not_met", reason="Node.js ≥20 未安装"))
                else:
                    npm_ok, npm_ver = mgr.check_npm()
                    if not npm_ok:
                        print(t("cli.new_skill_env_not_met", reason="npm 未安装"))
                    else:
                        print(t("cli.new_skill_downloading"))
                        skill_parent_dir = Path.home() / ".anappt" / "skills"
                        try:
                            mgr.install_or_update_skill(skill_parent_dir, registry=registry)
                            mgr.save_skill_dir_config(skill_parent_dir)
                            skill_md_path = skill_parent_dir / "dashi-ppt" / "SKILL.md"
                            print(t("cli.new_skill_ready", path=skill_md_path))
                        except RuntimeError as e:
                            print(t("cli.new_skill_download_failed", error=str(e)))
        except Exception as e:
            print(t("cli.new_skill_download_failed", error=str(e)))

    return 0


def cmd_new(args: list[str]) -> int:
    """Handle the 'new' command (alias for init).

    Args:
        args: Command arguments.

    Returns:
        Exit code.
    """
    return cmd_init(args)


def _start_tui(
    project_dir: Path,
    mode: str,
    welcome: bool = False,
) -> int:
    """Load the pipeline context and launch the textual TUI.

    Shared by ``cmd_run`` / ``cmd_resume`` / ``cmd_interactive``: loads
    the project context (without an InteractiveUI — the textual adapter
    is wired in via ``runner_factory``), then constructs and runs a
    :class:`anappt.tui.ReportBuilderApp`. The adapter serves as both the
    ``ui`` and ``stream_sink`` for the :class:`ConversationRunner`.

    Args:
        project_dir: Path to the project directory.
        mode: ConversationRunner mode — ``"run"`` or ``"interactive"``.
        welcome: When True, write ``interactive.welcome`` to the chat
            area on mount (used by ``anappt interactive``).

    Returns:
        Exit code (0 for success, 1 on missing project or load error).
    """
    from anappt.tui import ReportBuilderApp

    print(t("cli.loading_config"))

    try:
        ctx = _load_pipeline_context(project_dir, ui=None)
    except FileNotFoundError as e:
        print(str(e))
        return 1

    print(t("cli.pipeline_started"))

    def runner_factory(adapter):
        ctx.ui = adapter
        return ConversationRunner(ctx, mode=mode, ui=adapter, stream_sink=adapter)

    welcome_message = t("interactive.welcome") if welcome else None
    app = ReportBuilderApp(runner_factory, welcome_message=welcome_message)
    app.run()
    return 0


def cmd_run(args: list[str]) -> int:
    """Handle the 'run' command — launch the textual TUI in ``run`` mode.

    Loads the project context (state + memory + LLM + git + skill manager)
    and enters the unified conversation loop via
    :class:`anappt.tui.ReportBuilderApp`. The runner drives stage entry,
    opening analysis, multi-turn dialog, ``/confirm`` gating, and
    exit-time finalize (session summary + memory update + git commit) —
    fully replacing the old Orchestrator.run/confirm/revise path.

    Args:
        args: Command arguments (unused).

    Returns:
        Exit code (0 for success, 1 on missing project or load error).
    """
    project_dir = Path.cwd()

    if not is_anappt_project(project_dir):
        print(t("cli.no_project_found"))
        return 1

    return _start_tui(project_dir, mode="run")


def cmd_resume(args: list[str]) -> int:
    """Handle the 'resume' command — launch the textual TUI in ``run`` mode.

    In the conversational TUI model, resume and run share the same path:
    ``ConversationRunner._enter_stage`` handles all three resume scenarios
    (pending → in_progress, already in_progress, awaiting_review) by
    reading the persisted stage state from ``state.yaml``. The user then
    re-enters the conversation at the current stage and continues from
    there. This function therefore mirrors ``cmd_run`` exactly.

    Args:
        args: Command arguments (unused).

    Returns:
        Exit code (0 for success, 1 on missing project or load error).
    """
    project_dir = Path.cwd()

    if not is_anappt_project(project_dir):
        print(t("cli.no_project_found"))
        return 1

    return _start_tui(project_dir, mode="run")


def cmd_status(args: list[str]) -> int:
    """Handle the 'status' command.

    Args:
        args: Command arguments.

    Returns:
        Exit code.
    """
    project_dir = Path.cwd()

    if not is_anappt_project(project_dir):
        print(t("cli.no_project_found"))
        return 1

    try:
        ctx = _load_pipeline_context(project_dir)
    except FileNotFoundError as e:
        print(str(e))
        return 1

    orch = Orchestrator()
    orch.register_stages(_build_stages())
    orch.set_context(ctx)

    status = orch.get_status()
    print(t("cli.status_header"))
    ui = InteractiveUI()
    rows = [[s["id"], s["name"], s["status"], str(s["iteration"])] for s in status]
    ui.table(["ID", "Name", "Status", "Iter"], rows)

    return 0


def _parse_thinking_raw(raw: str) -> str | int | None:
    """Parse the ``thinking`` value entered interactively by the user.

    - Empty input → ``None`` (use the model's maximum thinking effort).
    - ``FALSE`` / ``OFF`` (case-insensitive) → the string ``"FALSE"`` (the
      canonical disable sentinel stored in models.yaml).
    - Pure-digit input (e.g. ``8000``) → ``int`` (used as budget_tokens).
    - Anything else (e.g. ``low``/``medium``/``high``) → the lowercased
      string, kept as-is for provider-specific mapping.

    Args:
        raw: The raw user input string (already stripped of surrounding
            whitespace by the caller, but stripped again defensively).

    Returns:
        Parsed thinking value (``None``, ``"FALSE"``, an int, or a str).
    """
    raw = raw.strip()
    if not raw:
        return None
    upper = raw.upper()
    if upper in ("FALSE", "OFF"):
        return "FALSE"
    if raw.isdigit():
        return int(raw)
    return raw.lower()


def cmd_config(args: list[str]) -> int:
    """Handle the 'config' command.

    Args:
        args: Command arguments ('show' or 'set').

    Returns:
        Exit code.
    """
    if not args or args[0] == "show":
        config = load_global_config()
        # Inject web tool config so is_available() reflects effective config
        try:
            from anappt.tools import web_fetch, web_search
            web_search.configure_from_models_config(config)
            web_fetch.configure_from_models_config(config)
        except Exception as e:
            print(f"⚠ web 工具配置初始化失败(将回退到环境变量): {e}")
        print(t("cli.config_show"))
        print(config.to_effective_yaml())
        return 0

    if args[0] == "set":
        # Interactive config setup
        from anappt.io.config import (
            ModelRoleConfig,
            ModelsConfig,
            WebFetchConfig,
            WebSearchConfig,
        )

        print(t("cli.config_prompt"))
        roles = ["reasoning", "analysis", "writing"]
        new_config = ModelsConfig()

        for role in roles:
            print(f"\n--- {role} ---")
            provider = input(f"  Provider (e.g., openai, anthropic) [{role}]: ").strip()
            model = input(f"  Model name [{role}]: ").strip()
            api_base = input(f"  API base (optional) [{role}]: ").strip()
            api_key = input(f"  API key (use ${{VAR}} for env var) [{role}]: ").strip()
            thinking_raw = input(
                f"  Thinking (Enter=max, FALSE=off, low/medium/high or integer) [{role}]: "
            ).strip()
            thinking = _parse_thinking_raw(thinking_raw)

            role_config = ModelRoleConfig(
                provider=provider,
                model=model,
                api_base=api_base if api_base else None,
                api_key=api_key if api_key else None,
                thinking=thinking,
            )
            setattr(new_config, role, role_config)

        # web_search 配置(可选)
        print("\n--- web_search ---")
        ws_backend = input("  Backend (duckduckgo/anysearch/zai, Enter=auto): ").strip() or None
        ws_anysearch = input("  AnySearch API key (optional, use ${VAR} for env): ").strip() or None
        ws_zai = input("  z.ai API key (optional, use ${VAR} for env): ").strip() or None

        # web_fetch 配置(可选)
        print("\n--- web_fetch ---")
        wf_jina = (
            input("  Jina API key (optional, use ${VAR} for env, Enter=disable): ").strip()
            or None
        )

        new_config.web_search = WebSearchConfig(
            backend=ws_backend,
            anysearch_api_key=ws_anysearch,
            zai_api_key=ws_zai,
        )
        new_config.web_fetch = WebFetchConfig(jina_api_key=wf_jina)

        saved_path = save_global_config(new_config)
        # Inject web tool config so subsequent is_available() reflects new config
        try:
            from anappt.tools import web_fetch, web_search
            web_search.configure_from_models_config(new_config)
            web_fetch.configure_from_models_config(new_config)
        except Exception as e:
            print(f"⚠ web 工具配置初始化失败(将回退到环境变量): {e}")
        print(t("cli.config_saved", path=str(saved_path)))
        return 0

    print(t("cli.unknown_command", command=args[0]))
    return 1


def cmd_setup(args: list[str]) -> int:
    """处理 'setup' 命令: 检查运行环境并安装/更新 dashi-ppt-skill。

    支持的可选参数:
      --dir <path>      指定 skill 安装父目录(默认 ~/.anappt/skills)
      --registry <url>  指定 npm 镜像地址

    Args:
        args: 命令参数列表,支持 ``--dir <path>`` 与 ``--registry <url>`` 两个可选 flag。

    Returns:
        退出码(0 表示成功,1 表示失败)。
    """
    # 局部导入避免循环依赖
    from anappt.io.skill_manager import SkillManager

    # 解析参数(简单解析,不引入 argparse)
    user_dir: str | None = None
    registry: str | None = None
    i = 0
    while i < len(args):
        flag = args[i]
        if flag == "--dir":
            if i + 1 >= len(args):
                print(t("setup.usage_detail"))
                return 1
            user_dir = args[i + 1]
            i += 2
        elif flag == "--registry":
            if i + 1 >= len(args):
                print(t("setup.usage_detail"))
                return 1
            registry = args[i + 1]
            i += 2
        else:
            print(t("setup.usage_detail"))
            return 1

    # 1. 检查运行环境
    print(t("setup.checking_env"))
    mgr = SkillManager()

    # 3. 检查 Node.js
    node_ok, node_ver = mgr.check_node()
    if not node_ok and not node_ver:
        print(t("setup.node_missing"))
        return 1
    if not node_ok:
        print(t("setup.node_outdated", version=node_ver))
        return 1
    print(t("setup.node_ok", version=node_ver))

    # 4. 检查 npm
    npm_ok, npm_ver = mgr.check_npm()
    if not npm_ok:
        print(t("setup.npm_missing"))
        return 1
    print(t("setup.npm_ok", version=npm_ver))

    # 5. 检查 Chrome(仅警告,不阻塞)
    chrome_ok, chrome_path = mgr.check_chrome()
    if not chrome_ok:
        print(t("setup.chrome_missing_warning"))
    else:
        print(t("setup.chrome_ok", path=chrome_path))

    # 6. 确定 skill 父目录
    if user_dir is not None:
        skill_parent_dir = Path(user_dir)
    else:
        skill_parent_dir = Path.home() / ".anappt" / "skills"

    # 7. 检查 skill 是否已安装
    existing_skill = mgr.locate_skill()
    if existing_skill is not None:
        print(t("setup.updating_skill"))
    else:
        print(t("setup.installing_skill", path=str(skill_parent_dir)))

    # 8. 调用安装/更新
    try:
        skill_md_path = mgr.install_or_update_skill(skill_parent_dir, registry=registry)
    except RuntimeError as e:
        print(t("setup.skill_install_failed", error=str(e)))
        return 1

    # 9. 持久化 skill 父目录到 config.yaml
    mgr.save_skill_dir_config(skill_parent_dir)

    # 10. 完成
    print(t("setup.skill_installed", path=str(skill_md_path)))
    return 0


def cmd_interactive(args: list[str]) -> int:
    """Handle the 'interactive' command — launch the textual TUI.

    Loads the project context and enters the unified conversation loop in
    ``interactive`` mode via :class:`anappt.tui.ReportBuilderApp`. In this
    mode the runner's system prompt carries the full stage-state index,
    project memory, recent session-history index, and a current-artifacts
    listing, so the LLM self-identifies what the user most needs to do
    next and proactively prompts. The ``interactive.welcome`` line is
    written to the chat area on mount (before the LLM opening). The
    ``/status`` / ``/memory`` / ``/help`` / ``/confirm`` / ``/exit``
    meta-commands remain available inside ``ConversationRunner``.

    Args:
        args: Command arguments (unused).

    Returns:
        Exit code (0 for success, 1 on missing project or load error).
    """
    project_dir = Path.cwd()

    if not is_anappt_project(project_dir):
        print(t("cli.no_project_found"))
        return 1

    return _start_tui(project_dir, mode="interactive", welcome=True)


# Command registry
_COMMANDS: dict[str, Any] = {
    "init": cmd_init,
    "new": cmd_new,
    "run": cmd_run,
    "resume": cmd_resume,
    "status": cmd_status,
    "config": cmd_config,
    "interactive": cmd_interactive,
    "setup": cmd_setup,
}


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the CLI.

    Args:
        argv: Command-line arguments (defaults to sys.argv).

    Returns:
        Exit code (0 for success, 1 for error).
    """
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        print(t("cli.usage"))
        print(
            f"  anappt init [project_name] [--no-skill] [--registry <url>]    "
            f"{t('cli.command_init')}"
        )
        print(
            f"  anappt new [project_name] [--no-skill] [--registry <url>]     "
            f"{t('cli.command_init')}"
        )
        print(f"  anappt run                    {t('cli.command_run')}")
        print(f"  anappt resume                 {t('cli.command_resume')}")
        print(f"  anappt status                 {t('cli.command_status')}")
        print(f"  anappt config [show|set]      {t('cli.command_config')}")
        print(f"  anappt interactive            {t('cli.command_init')}")
        print(f"  anappt setup [--dir <path>] [--registry <url>]    {t('cli.command_setup')}")
        return 0

    command = argv[0]
    args = argv[1:]

    handler = _COMMANDS.get(command)
    if handler is None:
        print(t("cli.unknown_command", command=command))
        print(t("cli.usage"))
        return 1

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
