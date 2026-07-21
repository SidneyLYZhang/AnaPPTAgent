"""Tests for DashiPPTBridge subprocess bridge layer."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from anappt.bridge.dashi_ppt import DashiPPTBridge


class TestLoadSkillMd:
    """Tests for load_skill_md static method."""

    def test_returns_file_content(self, tmp_path: Path) -> None:
        skill_md = tmp_path / "SKILL.md"
        content = "# dashi-ppt-skill\n\nskill doc"
        skill_md.write_text(content, encoding="utf-8")
        result = DashiPPTBridge.load_skill_md(tmp_path)
        assert result == content

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            DashiPPTBridge.load_skill_md(tmp_path)

    def test_utf8_content(self, tmp_path: Path) -> None:
        skill_md = tmp_path / "SKILL.md"
        content = "# 中文标题\n\n这是一段中文内容"
        skill_md.write_text(content, encoding="utf-8")
        result = DashiPPTBridge.load_skill_md(tmp_path)
        assert result == content
        assert "中文标题" in result


class TestRenderDeck:
    """Tests for render_deck static method."""

    def test_returns_output_path_on_success(self, tmp_path: Path) -> None:
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "render_goal_deck.ps1").write_text("", encoding="utf-8")
        (scripts_dir / "render_goal_deck.sh").write_text("", encoding="utf-8")

        goal_json = tmp_path / "goal.json"
        goal_json.write_text("{}", encoding="utf-8")
        output_html = tmp_path / "output.html"

        with patch("anappt.bridge.dashi_ppt.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
            result = DashiPPTBridge.render_deck(goal_json, output_html, tmp_path)

        assert result == output_html
        assert isinstance(result, Path)

    def test_uses_powershell_on_windows(self, tmp_path: Path) -> None:
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "render_goal_deck.ps1").write_text("", encoding="utf-8")

        goal_json = tmp_path / "goal.json"
        output_html = tmp_path / "output.html"

        with patch("anappt.bridge.dashi_ppt.sys.platform", "win32"), \
             patch("anappt.bridge.dashi_ppt.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
            DashiPPTBridge.render_deck(goal_json, output_html, tmp_path)

        cmd = mock_run.call_args[0][0]
        cmd_str = " ".join(cmd)
        assert "powershell" in cmd_str
        assert "render_goal_deck.ps1" in cmd_str

    def test_uses_bash_on_unix(self, tmp_path: Path) -> None:
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "render_goal_deck.sh").write_text("", encoding="utf-8")

        goal_json = tmp_path / "goal.json"
        output_html = tmp_path / "output.html"

        with patch("anappt.bridge.dashi_ppt.sys.platform", "linux"), \
             patch("anappt.bridge.dashi_ppt.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
            DashiPPTBridge.render_deck(goal_json, output_html, tmp_path)

        cmd = mock_run.call_args[0][0]
        cmd_str = " ".join(cmd)
        assert "bash" in cmd_str
        assert "render_goal_deck.sh" in cmd_str

    def test_missing_script_raises_filenotfounderror(self, tmp_path: Path) -> None:
        goal_json = tmp_path / "goal.json"
        output_html = tmp_path / "output.html"

        with patch("anappt.bridge.dashi_ppt.sys.platform", "win32"), \
             patch("anappt.bridge.dashi_ppt.subprocess.run") as mock_run:
            with pytest.raises(FileNotFoundError):
                DashiPPTBridge.render_deck(goal_json, output_html, tmp_path)
            mock_run.assert_not_called()

    def test_subprocess_failure_raises_runtimeerror(self, tmp_path: Path) -> None:
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "render_goal_deck.ps1").write_text("", encoding="utf-8")

        goal_json = tmp_path / "goal.json"
        output_html = tmp_path / "output.html"

        with patch("anappt.bridge.dashi_ppt.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="error", stdout="")
            with pytest.raises(RuntimeError, match="returncode=1"):
                DashiPPTBridge.render_deck(goal_json, output_html, tmp_path)

    def test_creates_parent_dir(self, tmp_path: Path) -> None:
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "render_goal_deck.ps1").write_text("", encoding="utf-8")
        (scripts_dir / "render_goal_deck.sh").write_text("", encoding="utf-8")

        goal_json = tmp_path / "goal.json"
        output_html = tmp_path / "a" / "b" / "c" / "index.html"

        with patch("anappt.bridge.dashi_ppt.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
            DashiPPTBridge.render_deck(goal_json, output_html, tmp_path)

        assert output_html.parent.exists()
        assert output_html.parent == tmp_path / "a" / "b" / "c"


class TestExport:
    """Tests for export static method."""

    def test_returns_output_file_on_success_pptx(self, tmp_path: Path) -> None:
        deck_dir = tmp_path / "deck"
        deck_dir.mkdir()
        output_file = tmp_path / "out.pptx"

        with patch(
            "anappt.bridge.dashi_ppt.shutil.which", return_value="/fake/npm"
        ), patch("anappt.bridge.dashi_ppt.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
            result = DashiPPTBridge.export(deck_dir, "pptx", output_file, tmp_path)

        assert result == output_file

    def test_returns_output_file_on_success_pdf(self, tmp_path: Path) -> None:
        deck_dir = tmp_path / "deck"
        deck_dir.mkdir()
        output_file = tmp_path / "out.pdf"

        with patch(
            "anappt.bridge.dashi_ppt.shutil.which", return_value="/fake/npm"
        ), patch("anappt.bridge.dashi_ppt.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
            result = DashiPPTBridge.export(deck_dir, "pdf", output_file, tmp_path)

        assert result == output_file

    def test_invalid_format_raises_valueerror(self, tmp_path: Path) -> None:
        deck_dir = tmp_path / "deck"
        deck_dir.mkdir()
        output_file = tmp_path / "out.docx"

        with pytest.raises(ValueError):
            DashiPPTBridge.export(deck_dir, "docx", output_file, tmp_path)

    def test_command_contains_npm_prefix_and_export_format(
        self, tmp_path: Path
    ) -> None:
        deck_dir = tmp_path / "deck"
        deck_dir.mkdir()
        output_file = tmp_path / "out.pptx"

        with patch(
            "anappt.bridge.dashi_ppt.shutil.which", return_value="/fake/npm"
        ), patch("anappt.bridge.dashi_ppt.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
            DashiPPTBridge.export(deck_dir, "pptx", output_file, tmp_path)

        cmd = mock_run.call_args[0][0]
        cmd_str = " ".join(cmd)
        assert "/fake/npm" in cmd_str
        assert "--prefix" in cmd_str
        assert "project" in cmd_str
        assert "run" in cmd_str
        assert "export:pptx" in cmd_str
        assert str(deck_dir / "ppt") in cmd_str

    def test_subprocess_failure_raises_runtimeerror(self, tmp_path: Path) -> None:
        deck_dir = tmp_path / "deck"
        deck_dir.mkdir()
        output_file = tmp_path / "out.pptx"

        with patch(
            "anappt.bridge.dashi_ppt.shutil.which", return_value="/fake/npm"
        ), patch("anappt.bridge.dashi_ppt.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="error", stdout="")
            with pytest.raises(RuntimeError, match="returncode=1"):
                DashiPPTBridge.export(deck_dir, "pptx", output_file, tmp_path)

    def test_uses_shutil_which_to_resolve_npm(self, tmp_path: Path) -> None:
        """``export`` 应通过 ``shutil.which`` 解析 npm 完整路径,
        并将其作为 ``subprocess.run`` 命令列表的首个元素。

        这是为了兼容 Windows 上 npm 以 ``.cmd`` 脚本分发的情况:
        ``subprocess.run(["npm", ...])`` 在 ``shell=False`` 时无法找到
        ``npm.cmd``,会抛 ``FileNotFoundError``。
        """
        deck_dir = tmp_path / "deck"
        deck_dir.mkdir()
        output_file = tmp_path / "out.pptx"
        fake_npm = "/fake/path/to/npm.CMD"

        with patch(
            "anappt.bridge.dashi_ppt.shutil.which", return_value=fake_npm
        ) as mock_which, patch(
            "anappt.bridge.dashi_ppt.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
            DashiPPTBridge.export(deck_dir, "pptx", output_file, tmp_path)

        mock_which.assert_called_once_with("npm")
        args, _kwargs = mock_run.call_args
        assert args[0][0] == fake_npm

    def test_npm_not_in_path_raises_runtimeerror(self, tmp_path: Path) -> None:
        """``shutil.which('npm')`` 返回 None 时,``export`` 应抛
        ``RuntimeError``,不调用 ``subprocess.run``。"""
        deck_dir = tmp_path / "deck"
        deck_dir.mkdir()
        output_file = tmp_path / "out.pptx"

        with patch(
            "anappt.bridge.dashi_ppt.shutil.which", return_value=None
        ), patch(
            "anappt.bridge.dashi_ppt.subprocess.run"
        ) as mock_run:
            with pytest.raises(RuntimeError, match="npm"):
                DashiPPTBridge.export(deck_dir, "pptx", output_file, tmp_path)

        mock_run.assert_not_called()

    def test_export_passes_utf8_encoding_to_subprocess(self, tmp_path: Path) -> None:
        """``export`` 调用 ``subprocess.run`` 时必须显式传
        ``encoding="utf-8", errors="replace"``。

        ``npm run export:pptx/pdf`` 的输出含 UTF-8 字节(中文路径、进度
        日志),在中文 Windows 上若用默认 GBK 解码会导致 ``_readerthread``
        抛 ``UnicodeDecodeError``。
        """
        deck_dir = tmp_path / "deck"
        deck_dir.mkdir()
        output_file = tmp_path / "out.pptx"

        with patch(
            "anappt.bridge.dashi_ppt.shutil.which", return_value="/fake/npm"
        ), patch(
            "anappt.bridge.dashi_ppt.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
            DashiPPTBridge.export(deck_dir, "pptx", output_file, tmp_path)

        _args, kwargs = mock_run.call_args
        assert kwargs.get("encoding") == "utf-8"
        assert kwargs.get("errors") == "replace"


class TestConstructor:
    """Tests for __init__."""

    def test_sets_skill_root_and_output_dir(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "out"
        bridge = DashiPPTBridge(skill_root=tmp_path, output_dir=output_dir)
        assert bridge.skill_root == tmp_path
        assert bridge.output_dir == output_dir

    def test_accepts_string_paths(self, tmp_path: Path) -> None:
        bridge = DashiPPTBridge(
            skill_root=str(tmp_path), output_dir=str(tmp_path / "out")
        )
        assert isinstance(bridge.skill_root, Path)
        assert isinstance(bridge.output_dir, Path)
        assert bridge.skill_root == tmp_path
        assert bridge.output_dir == tmp_path / "out"
