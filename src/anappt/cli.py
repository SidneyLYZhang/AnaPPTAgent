"""CLI and interactive UI for AnaPPTAgent.

Provides the main entry point and command-line interface for the tool.
Supports: init, run, resume, status, config, and interactive mode.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from anappt.i18n import t
from anappt.io.config import ReportConfig
from anappt.io.git_auto import GitAutoCommit
from anappt.io.session import SessionLogger
from anappt.io.state import StateManager
from anappt.llm.provider import AnaPPTLLM, load_global_config, merge_config, save_global_config
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

    Args:
        project_dir: Path to the project directory.
        ui: Optional UI instance.

    Returns:
        PipelineContext ready for orchestration.

    Raises:
        FileNotFoundError: If report.yaml is not found.
    """
    project_dir = Path(project_dir)
    report_yaml_path = project_dir / "report.yaml"
    if not report_yaml_path.exists():
        raise FileNotFoundError(f"report.yaml not found in {project_dir}")

    # Load config
    config = ReportConfig.from_yaml(report_yaml_path)

    # Load models config
    global_config = load_global_config()
    project_models_path = project_dir / ".anappt" / "models.yaml"
    if project_models_path.exists():
        from anappt.io.config import ModelsConfig

        project_config = ModelsConfig.from_yaml(project_models_path)
        models_config = merge_config(global_config, project_config)
    else:
        models_config = global_config

    # Create LLM provider
    llm = AnaPPTLLM(models_config)

    # Create state manager
    state_file = project_dir / ".anappt" / "state.yaml"
    state = StateManager(state_file)

    # Create session logger
    session = SessionLogger(project_dir / ".anappt" / "session_history")

    # Create git auto-commit
    git = GitAutoCommit(project_dir)

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
    )


def cmd_init(args: list[str]) -> int:
    """Handle the 'init' command.

    Args:
        args: Command arguments (project name or path).
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
        project_name = input(t("cli.project_name_prompt")).strip()

    project_dir = Path.cwd() / project_name

    try:
        result_path = create_project(project_dir, project_name=project_name, init_git=True)
        print(t("cli.new_project_created", path=str(result_path)))
        print(t("cli.edit_report", path=str(result_path / "report.yaml")))
        print(t("cli.put_data", path=str(result_path / "data")))
        print(t("cli.run_to_start"))
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


def cmd_run(args: list[str]) -> int:
    """Handle the 'run' command.

    Args:
        args: Command arguments.

    Returns:
        Exit code.
    """
    project_dir = Path.cwd()

    if not is_anappt_project(project_dir):
        print(t("cli.no_project_found"))
        return 1

    ui = InteractiveUI()
    print(t("cli.loading_config"))

    try:
        ctx = _load_pipeline_context(project_dir, ui=ui)
    except FileNotFoundError as e:
        print(str(e))
        return 1

    # Create orchestrator
    orch = Orchestrator()
    orch.register_stages(_build_stages())
    orch.set_context(ctx)

    # Run the pipeline
    print(t("cli.pipeline_started"))
    result = orch.run()

    if result["completed"]:
        print(t("cli.all_done"))
        return 0

    # Interactive confirm/revise loop
    return _interactive_confirm_loop(orch, ui, result)


def cmd_resume(args: list[str]) -> int:
    """Handle the 'resume' command.

    Args:
        args: Command arguments.

    Returns:
        Exit code.
    """
    project_dir = Path.cwd()

    if not is_anappt_project(project_dir):
        print(t("cli.no_project_found"))
        return 1

    ui = InteractiveUI()
    try:
        ctx = _load_pipeline_context(project_dir, ui=ui)
    except FileNotFoundError as e:
        print(str(e))
        return 1

    orch = Orchestrator()
    orch.register_stages(_build_stages())
    orch.set_context(ctx)

    result = orch.resume()

    if result["completed"]:
        print(t("cli.all_done"))
        return 0

    return _interactive_confirm_loop(orch, ui, result)


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


def cmd_config(args: list[str]) -> int:
    """Handle the 'config' command.

    Args:
        args: Command arguments ('show' or 'set').

    Returns:
        Exit code.
    """
    if not args or args[0] == "show":
        config = load_global_config()
        print(t("cli.config_show"))
        print(config.to_yaml())
        return 0

    if args[0] == "set":
        # Interactive config setup
        from anappt.io.config import ModelRoleConfig, ModelsConfig

        print(t("cli.config_prompt"))
        roles = ["reasoning", "analysis", "writing"]
        new_config = ModelsConfig()

        for role in roles:
            print(f"\n--- {role} ---")
            provider = input(f"  Provider (e.g., openai, anthropic) [{role}]: ").strip()
            model = input(f"  Model name [{role}]: ").strip()
            api_base = input(f"  API base (optional) [{role}]: ").strip()
            api_key = input(f"  API key (use ${{VAR}} for env var) [{role}]: ").strip()

            role_config = ModelRoleConfig(
                provider=provider,
                model=model,
                api_base=api_base if api_base else None,
                api_key=api_key if api_key else None,
            )
            setattr(new_config, role, role_config)

        saved_path = save_global_config(new_config)
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


def _interactive_confirm_loop(
    orch: Orchestrator,
    ui: InteractiveUI,
    result: dict[str, Any],
) -> int:
    """Run the interactive confirm/revise loop.

    Args:
        orch: The orchestrator instance.
        ui: The UI instance.
        result: Initial run result.

    Returns:
        Exit code (0 for success).
    """
    while not result.get("completed", False):
        print(t("gate.confirm_prompt"))
        user_input = ui.input("> ").strip()

        if user_input.lower() == t("interactive.confirm_short"):
            result = orch.confirm()
        elif user_input.lower() == t("interactive.exit_cmd"):
            break
        else:
            # Revision feedback
            result = orch.revise(user_input)

    if result.get("completed"):
        print(t("cli.all_done"))
        return 0

    return 0


def cmd_interactive(args: list[str]) -> int:
    """Handle the 'interactive' command — start interactive mode.

    Args:
        args: Command arguments.

    Returns:
        Exit code.
    """
    project_dir = Path.cwd()

    if not is_anappt_project(project_dir):
        print(t("cli.no_project_found"))
        return 1

    ui = InteractiveUI()
    ui.print(t("interactive.welcome"))

    try:
        ctx = _load_pipeline_context(project_dir, ui=ui)
    except FileNotFoundError as e:
        ui.print(str(e))
        return 1

    orch = Orchestrator()
    orch.register_stages(_build_stages())
    orch.set_context(ctx)

    while True:
        ui.print(t("interactive.exit_prompt"))
        user_input = ui.input("> ").strip().lower()

        if user_input == t("interactive.exit_cmd"):
            ui.print(t("interactive.exiting"))
            # Final git commit on exit
            if ctx.git is not None:
                ctx.git.commit_on_exit()
            break
        elif user_input == t("interactive.status_cmd"):
            status = orch.get_status()
            headers = ["ID", "Name", "Status", "Iter"]
            rows = [[s["id"], s["name"], s["status"], str(s["iteration"])] for s in status]
            ui.table(headers, rows)
        elif user_input == t("interactive.config_cmd"):
            cmd_config(["show"])
        elif user_input == t("interactive.reset_cmd"):
            orch.reset()
            ui.print(t("orchestrator.resetting"))
        elif user_input == t("interactive.help_cmd"):
            ui.print(t("interactive.help_text"))
        elif user_input == t("interactive.confirm_short"):
            orch.confirm()
        else:
            # Try running the pipeline
            result = orch.run()
            if result.get("completed"):
                ui.print(t("cli.all_done"))
                break
            _interactive_confirm_loop(orch, ui, result)

    return 0


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
        print(f"  anappt init <project_name> [--no-skill] [--registry <url>]    {t('cli.command_init')}")
        print(f"  anappt new <project_name> [--no-skill] [--registry <url>]     {t('cli.command_init')}")
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
