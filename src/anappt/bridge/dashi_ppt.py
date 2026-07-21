"""Dashi-PPT subprocess bridge layer for AnaPPTAgent.

Bridges AnaPPTAgent to the dashi-ppt-skill by invoking subprocess
scripts (render_goal_deck.ps1/sh, npm run export:pptx/pdf) installed
under ~/.anappt/skills/dashi-ppt/. Does NOT generate HTML directly—
delegates all rendering to the skill's scripts.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


class DashiPPTBridge:
    """Subprocess bridge to the dashi-ppt-skill.

    Delegates HTML rendering and PPTX/PDF export to scripts installed
    under ``skill_root``. Does not perform any HTML generation itself.

    Attributes:
        skill_root: Root directory of the installed dashi-ppt-skill.
        output_dir: Default directory for generated artifacts.
    """

    def __init__(self, skill_root: Path, output_dir: Path) -> None:
        """Initialize the bridge.

        Args:
            skill_root: Root directory of the installed dashi-ppt-skill.
            output_dir: Default directory for generated artifacts.
        """
        self.skill_root: Path = Path(skill_root)
        self.output_dir: Path = Path(output_dir)

    @staticmethod
    def load_skill_md(skill_root: Path) -> str:
        """Read the skill's SKILL.md documentation.

        Args:
            skill_root: Root directory of the installed dashi-ppt-skill.

        Returns:
            Full text content of SKILL.md (UTF-8).

        Raises:
            FileNotFoundError: If SKILL.md is missing under ``skill_root``.
        """
        skill_md_path = Path(skill_root) / "SKILL.md"
        if not skill_md_path.is_file():
            raise FileNotFoundError(
                f"SKILL.md 不存在于 {skill_root / 'SKILL.md'},"
                f"请运行 'anappt setup' 安装 dashi-ppt-skill"
            )
        return skill_md_path.read_text(encoding="utf-8")

    @staticmethod
    def render_deck(
        goal_json_path: Path,
        output_html_path: Path,
        skill_root: Path,
    ) -> Path:
        """Render a goal deck to HTML via the skill's render script.

        Args:
            goal_json_path: Path to the goal.json input file.
            output_html_path: Path where the rendered HTML should be written.
            skill_root: Root directory of the installed dashi-ppt-skill.

        Returns:
            The ``output_html_path`` on success.

        Raises:
            FileNotFoundError: If the render script is missing.
            RuntimeError: If the render script exits with a non-zero code.
        """
        skill_root = Path(skill_root)
        if sys.platform == "win32":
            script_path = skill_root / "scripts" / "render_goal_deck.ps1"
            cmd = [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                str(goal_json_path),
                str(output_html_path),
            ]
        else:
            script_path = skill_root / "scripts" / "render_goal_deck.sh"
            cmd = [
                "bash",
                str(script_path),
                str(goal_json_path),
                str(output_html_path),
            ]

        if not script_path.is_file():
            raise FileNotFoundError(
                f"渲染脚本缺失: {script_path},请重新运行 'anappt setup'"
            )

        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"render_deck 失败 (returncode={result.returncode}): "
                f"{result.stderr}"
            )

        output_html_path = Path(output_html_path)
        output_html_path.parent.mkdir(parents=True, exist_ok=True)
        return output_html_path

    @staticmethod
    def export(
        deck_dir: Path,
        format: str,
        output_file: Path,
        skill_root: Path,
    ) -> Path:
        """Export a rendered deck to PPTX or PDF via npm script.

        Args:
            deck_dir: Directory containing the rendered deck (with ``ppt``
                subdirectory produced by the render step).
            format: Export format; must be ``"pptx"`` or ``"pdf"``.
            output_file: Path where the exported file should be written.
            skill_root: Root directory of the installed dashi-ppt-skill.

        Returns:
            The ``output_file`` on success.

        Raises:
            ValueError: If ``format`` is not ``"pptx"`` or ``"pdf"``.
            RuntimeError: If npm is not in PATH, or the npm export script
                exits with a non-zero code.
        """
        if format not in ("pptx", "pdf"):
            raise ValueError(
                f"Unsupported format: {format}. Must be 'pptx' or 'pdf'."
            )

        # 通过 shutil.which 解析 npm 完整路径:Windows 上 npm 以 .cmd 批处理
        # 脚本形式分发,subprocess.run(["npm", ...]) 在 shell=False 时调用
        # CreateProcessW,该 API 不会遵循 PATHEXT 解析 .cmd / .bat,导致即使
        # npm 已安装也会抛 FileNotFoundError。shutil.which 遵循 PATHEXT,
        # 能正确返回 npm.cmd 的完整路径。
        npm_path = shutil.which("npm")
        if npm_path is None:
            raise RuntimeError(
                "npm 未在 PATH 中找到,请确保 Node.js / npm 已正确安装"
            )

        cmd = [
            npm_path,
            "--prefix",
            str(Path(skill_root) / "project"),
            "run",
            f"export:{format}",
            "--",
            str(Path(deck_dir) / "ppt"),
            str(output_file),
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600, check=False
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(
                f"export:{format} 执行失败: {exc}"
            ) from exc
        if result.returncode != 0:
            raise RuntimeError(
                f"export:{format} 失败 (returncode={result.returncode}): "
                f"{result.stderr}"
            )

        return Path(output_file)
