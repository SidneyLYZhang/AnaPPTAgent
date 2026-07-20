"""Tests for ``anappt init`` / ``anappt new`` skill download sub-flow.

覆盖 ``cmd_init`` 在 ``create_project`` 成功后的 skill 下载子流程:
  - 参数解析 (``--no-skill`` / ``--registry`` / 未知 flag / 缺失值)
  - skill 已安装 / 未安装 / 环境不满足 / 下载失败 / SkillManager 构造失败
  - ``cmd_new`` 作为 ``cmd_init`` 别名
  - 项目创建与 skill 下载的独立性 (skill 失败不阻塞 cmd_init)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anappt.cli import cmd_init, cmd_new


@pytest.fixture(autouse=True)
def _force_zh_locale():
    """强制中文 locale,确保输出文本可预测。

    测试前后都重置 i18n 缓存,避免影响其他测试模块。
    """
    from anappt import i18n

    i18n._reset_cache()
    i18n.set_locale("zh")
    yield
    i18n._reset_cache()


@pytest.fixture(autouse=True)
def _mock_create_project(monkeypatch: pytest.MonkeyPatch):
    """mock ``create_project`` 避免真实创建目录。

    需要不同行为 (例如抛异常、捕获调用参数) 的测试可在测试体内再次
    ``monkeypatch.setattr("anappt.cli.create_project", ...)`` 覆盖。
    """
    monkeypatch.setattr("anappt.cli.create_project", lambda *args, **kwargs: Path("/fake"))


def _install_mock_skill_manager(monkeypatch: pytest.MonkeyPatch, **returns) -> MagicMock:
    """用 ``MagicMock`` 替换 ``cmd_init`` 内部使用的 ``SkillManager`` 类。

    ``cmd_init`` 中是局部导入 ``from anappt.io.skill_manager import SkillManager``,
    所以需要 patch ``anappt.io.skill_manager.SkillManager``。``**returns`` 用于
    设置各方法的 ``return_value``。

    Returns:
        配置好的 ``MagicMock`` 实例,可继续断言调用参数。
    """
    mock_mgr = MagicMock()
    for method, value in returns.items():
        getattr(mock_mgr, method).return_value = value
    monkeypatch.setattr("anappt.io.skill_manager.SkillManager", lambda: mock_mgr)
    return mock_mgr


# ---------------------------------------------------------------------------
# 1. 参数解析测试
# ---------------------------------------------------------------------------


class TestInitArgParsing:
    """``cmd_init`` 参数解析测试。"""

    def test_no_skill_flag_skips_skill_subflow(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        """``--no-skill`` flag 应跳过整个 skill 下载子流程,SkillManager 不被实例化。"""
        mock_skill_cls = MagicMock()
        monkeypatch.setattr("anappt.io.skill_manager.SkillManager", mock_skill_cls)

        result = cmd_init(["myproj", "--no-skill"])

        assert result == 0
        captured = capsys.readouterr()
        assert "已跳过" in captured.out
        mock_skill_cls.assert_not_called()

    def test_registry_flag_passed_to_install(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        """``--registry <url>`` 应作为 ``registry`` 关键字参数传给 ``install_or_update_skill``。"""
        mock_mgr = _install_mock_skill_manager(
            monkeypatch,
            locate_skill=None,
            check_node=(True, "v20"),
            check_npm=(True, "10"),
            install_or_update_skill=Path("/fake/dashi-ppt/SKILL.md"),
        )

        result = cmd_init(["myproj", "--registry", "https://my.registry/"])

        assert result == 0
        mock_mgr.install_or_update_skill.assert_called_once()
        _args, kwargs = mock_mgr.install_or_update_skill.call_args
        assert kwargs.get("registry") == "https://my.registry/"

    def test_registry_equals_syntax(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        """``--registry=<url>`` 语法也应正确解析并传给 ``install_or_update_skill``。"""
        mock_mgr = _install_mock_skill_manager(
            monkeypatch,
            locate_skill=None,
            check_node=(True, "v20"),
            check_npm=(True, "10"),
            install_or_update_skill=Path("/fake/dashi-ppt/SKILL.md"),
        )

        result = cmd_init(["myproj", "--registry=https://my.registry/"])

        assert result == 0
        mock_mgr.install_or_update_skill.assert_called_once()
        _args, kwargs = mock_mgr.install_or_update_skill.call_args
        assert kwargs.get("registry") == "https://my.registry/"

    def test_missing_registry_value_returns_1(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        """``--registry`` 后无值时应返回 1,且 ``create_project`` 未被调用。"""
        mock_create = MagicMock(return_value=Path("/fake"))
        monkeypatch.setattr("anappt.cli.create_project", mock_create)

        result = cmd_init(["myproj", "--registry"])

        assert result == 1
        mock_create.assert_not_called()

    def test_unknown_flag_returns_1(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        """未知 flag 应返回 1,且 ``create_project`` 未被调用。"""
        mock_create = MagicMock(return_value=Path("/fake"))
        monkeypatch.setattr("anappt.cli.create_project", mock_create)

        result = cmd_init(["myproj", "--unknown"])

        assert result == 1
        mock_create.assert_not_called()

    def test_no_args_prompts_for_project_name(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        """无参数时应通过 ``input`` 提示输入 project_name 并传给 ``create_project``。"""
        monkeypatch.setattr("builtins.input", lambda *args: "interactive_proj")
        mock_create = MagicMock(return_value=Path("/fake"))
        monkeypatch.setattr("anappt.cli.create_project", mock_create)
        # locate_skill 返回已安装路径,跳过下载子流程
        _install_mock_skill_manager(monkeypatch, locate_skill="/fake/SKILL.md")

        result = cmd_init([])

        assert result == 0
        mock_create.assert_called_once()
        _args, kwargs = mock_create.call_args
        assert kwargs.get("project_name") == "interactive_proj"


# ---------------------------------------------------------------------------
# 2. skill 下载子流程测试
# ---------------------------------------------------------------------------


class TestInitSkillDownload:
    """``cmd_init`` skill 下载子流程测试。"""

    def test_skill_already_installed_skips_download(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        """``locate_skill`` 返回非 None 时应跳过下载,打印 '已检测到'。"""
        mock_mgr = _install_mock_skill_manager(
            monkeypatch,
            locate_skill="/path/to/SKILL.md",
        )

        result = cmd_init(["myproj"])

        assert result == 0
        captured = capsys.readouterr()
        assert "已检测到" in captured.out
        mock_mgr.install_or_update_skill.assert_not_called()

    def test_skill_not_installed_env_met_downloads_successfully(
        self, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        """skill 未安装且环境满足时应成功下载,打印 '已就绪'。"""
        mock_mgr = _install_mock_skill_manager(
            monkeypatch,
            locate_skill=None,
            check_node=(True, "v20"),
            check_npm=(True, "10"),
            install_or_update_skill=Path("/skills/dashi-ppt/SKILL.md"),
        )

        result = cmd_init(["myproj"])

        assert result == 0
        captured = capsys.readouterr()
        assert "已就绪" in captured.out
        mock_mgr.install_or_update_skill.assert_called_once()
        mock_mgr.save_skill_dir_config.assert_called_once()

    def test_node_missing_returns_0_no_block(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        """Node.js 缺失时不阻塞,返回 0,打印 '环境不满足'。"""
        mock_mgr = _install_mock_skill_manager(
            monkeypatch,
            locate_skill=None,
            check_node=(False, ""),
        )

        result = cmd_init(["myproj"])

        assert result == 0
        captured = capsys.readouterr()
        assert "环境不满足" in captured.out
        mock_mgr.install_or_update_skill.assert_not_called()

    def test_npm_missing_returns_0_no_block(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        """npm 缺失时不阻塞,返回 0,打印 '环境不满足'。"""
        mock_mgr = _install_mock_skill_manager(
            monkeypatch,
            locate_skill=None,
            check_node=(True, "v20"),
            check_npm=(False, ""),
        )

        result = cmd_init(["myproj"])

        assert result == 0
        captured = capsys.readouterr()
        assert "环境不满足" in captured.out
        mock_mgr.install_or_update_skill.assert_not_called()

    def test_install_failure_returns_0_no_block(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        """``install_or_update_skill`` 抛 RuntimeError 时不阻塞,返回 0,打印 '下载失败'。"""
        mock_mgr = _install_mock_skill_manager(
            monkeypatch,
            locate_skill=None,
            check_node=(True, "v20"),
            check_npm=(True, "10"),
        )
        mock_mgr.install_or_update_skill.side_effect = RuntimeError("network error")

        result = cmd_init(["myproj"])

        assert result == 0
        captured = capsys.readouterr()
        assert "下载失败" in captured.out

    def test_skill_manager_construction_failure_returns_0(
        self, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        """SkillManager 构造抛异常时不阻塞,返回 0,打印 '下载失败'。"""

        def raising_constructor() -> None:
            raise Exception("config corrupted")

        monkeypatch.setattr("anappt.io.skill_manager.SkillManager", raising_constructor)

        result = cmd_init(["myproj"])

        assert result == 0
        captured = capsys.readouterr()
        assert "下载失败" in captured.out


# ---------------------------------------------------------------------------
# 3. cmd_new 别名测试
# ---------------------------------------------------------------------------


class TestCmdNewAlias:
    """``cmd_new`` 别名测试。"""

    def test_cmd_new_is_alias_of_init(self, capsys) -> None:
        """``cmd_new`` 应与 ``cmd_init`` 行为一致(``--no-skill`` 时打印 '已跳过')。"""
        result = cmd_new(["myproj", "--no-skill"])

        assert result == 0
        captured = capsys.readouterr()
        assert "已跳过" in captured.out


# ---------------------------------------------------------------------------
# 4. 项目创建独立性测试
# ---------------------------------------------------------------------------


class TestProjectCreationIndependence:
    """项目创建与 skill 下载的独立性测试:skill 失败不阻塞项目创建。"""

    def test_project_created_before_skill_subflow(
        self, monkeypatch: pytest.MonkeyPatch, capsys, tmp_path: Path
    ) -> None:
        """``create_project`` 应在 skill 下载之前调用,即使 skill 下载失败 create_project 仍被调用。"""
        monkeypatch.chdir(tmp_path)
        mock_create = MagicMock(return_value=Path("/fake"))
        monkeypatch.setattr("anappt.cli.create_project", mock_create)

        def raising_constructor() -> None:
            raise Exception("config corrupted")

        monkeypatch.setattr("anappt.io.skill_manager.SkillManager", raising_constructor)

        result = cmd_init(["myproj"])

        assert result == 0
        mock_create.assert_called_once()
        captured = capsys.readouterr()
        assert "下载失败" in captured.out

    def test_create_project_failure_returns_1(
        self, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        """``create_project`` 抛 FileExistsError 时应返回 1,skill 下载未执行。"""

        def raising_create(*args, **kwargs) -> Path:
            raise FileExistsError("project already exists")

        monkeypatch.setattr("anappt.cli.create_project", raising_create)

        mock_skill_cls = MagicMock()
        monkeypatch.setattr("anappt.io.skill_manager.SkillManager", mock_skill_cls)

        result = cmd_init(["myproj"])

        assert result == 1
        mock_skill_cls.assert_not_called()
