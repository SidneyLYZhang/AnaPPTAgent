"""``anappt setup`` 命令与 ``SkillManager`` 的单元测试。

覆盖 tasks.md 中 Task 5 的全部 9 个 SubTask:
  - 5.1 ~ 5.6: 测试 ``cmd_setup`` 在各种环境与参数下的行为
  - 5.7 ~ 5.9: 测试 ``SkillManager`` 的 ``locate_skill`` /
    ``save_skill_dir_config`` / ``install_or_update_skill`` 方法
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from anappt.cli import cmd_setup
from anappt.io.skill_manager import SkillManager


@pytest.fixture(autouse=True)
def _force_zh_locale():
    """所有测试强制使用中文 locale,确保输出文本可预测。

    测试前后都重置 i18n 缓存,避免影响其他测试模块。
    """
    from anappt import i18n

    i18n._reset_cache()
    i18n.set_locale("zh")
    yield
    i18n._reset_cache()


def _install_mock_skill_manager(monkeypatch: pytest.MonkeyPatch, **returns) -> MagicMock:
    """用 ``MagicMock`` 替换 ``cmd_setup`` 内部使用的 ``SkillManager`` 类。

    通过 ``monkeypatch.setattr`` 把 ``anappt.io.skill_manager.SkillManager``
    替换为一个返回 ``MagicMock`` 实例的 lambda,使 ``cmd_setup`` 中的
    ``mgr = SkillManager()`` 拿到 mock 实例。``**returns`` 用于设置各方法
    的 ``return_value``。

    Returns:
        配置好的 ``MagicMock`` 实例,可继续断言调用参数。
    """
    mock_mgr = MagicMock()
    for method, value in returns.items():
        getattr(mock_mgr, method).return_value = value
    monkeypatch.setattr("anappt.io.skill_manager.SkillManager", lambda: mock_mgr)
    return mock_mgr


# ---------------------------------------------------------------------------
# SubTask 5.1: Node.js 缺失时返回 1
# ---------------------------------------------------------------------------


def test_cmd_setup_returns_1_when_node_missing(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    """SubTask 5.1 - Node.js 未安装时 ``cmd_setup`` 应返回 1 并打印缺失提示。

    让 ``check_node`` 返回 ``(False, "")``(命令未找到/无版本输出),
    验证退出码 1 且输出包含 "Node.js"。
    """
    monkeypatch.setattr(SkillManager, "check_node", lambda self: (False, ""))

    result = cmd_setup([])

    assert result == 1
    captured = capsys.readouterr()
    assert "Node.js" in captured.out


# ---------------------------------------------------------------------------
# SubTask 5.2: Node.js 版本过低时返回 1
# ---------------------------------------------------------------------------


def test_cmd_setup_returns_1_when_node_outdated(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    """SubTask 5.2 - Node.js 版本低于 20 时 ``cmd_setup`` 应返回 1。

    让 ``check_node`` 返回 ``(False, "v18.0.0")``,验证退出码 1,且输出
    同时包含版本号 "v18.0.0" 与"版本过低"字样。
    """
    monkeypatch.setattr(SkillManager, "check_node", lambda self: (False, "v18.0.0"))

    result = cmd_setup([])

    assert result == 1
    captured = capsys.readouterr()
    assert "v18.0.0" in captured.out
    assert "版本过低" in captured.out


# ---------------------------------------------------------------------------
# SubTask 5.3: npm 缺失时返回 1
# ---------------------------------------------------------------------------


def test_cmd_setup_returns_1_when_npm_missing(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    """SubTask 5.3 - npm 未安装时 ``cmd_setup`` 应返回 1。

    让 ``check_node`` 通过、``check_npm`` 返回 ``(False, "")``,
    验证退出码 1 且输出包含 "npm"。
    """
    monkeypatch.setattr(SkillManager, "check_node", lambda self: (True, "v20.0.0"))
    monkeypatch.setattr(SkillManager, "check_npm", lambda self: (False, ""))

    result = cmd_setup([])

    assert result == 1
    captured = capsys.readouterr()
    assert "npm" in captured.out


# ---------------------------------------------------------------------------
# SubTask 5.4: Chrome 缺失时不阻塞,返回 0
# ---------------------------------------------------------------------------


def test_cmd_setup_returns_0_when_chrome_missing(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    """SubTask 5.4 - Chrome 缺失时只打印警告,不阻塞 ``cmd_setup`` 成功路径。

    ``check_node`` / ``check_npm`` 通过,``check_chrome`` 返回 ``(False, None)``,
    ``locate_skill`` 返回 None,``install_or_update_skill`` 返回假路径。
    验证退出码 0 且输出包含 "Chrome" 警告字样。
    """
    _install_mock_skill_manager(
        monkeypatch,
        check_node=(True, "v20.0.0"),
        check_npm=(True, "10.5.0"),
        check_chrome=(False, None),
        locate_skill=None,
        install_or_update_skill=Path("/fake/dashi-ppt/SKILL.md"),
    )

    result = cmd_setup([])

    assert result == 0
    captured = capsys.readouterr()
    assert "Chrome" in captured.out


# ---------------------------------------------------------------------------
# SubTask 5.5: --dir <path> 参数解析
# ---------------------------------------------------------------------------


def test_cmd_setup_dir_arg_passed_to_install(monkeypatch: pytest.MonkeyPatch) -> None:
    """SubTask 5.5 - ``--dir <path>`` 指定的路径应原样传给 ``install_or_update_skill``。

    mock 整个 ``SkillManager``,执行 ``cmd_setup(["--dir", "/tmp/test-skills"])``,
    断言 ``install_or_update_skill`` 第一个位置参数等于 ``Path("/tmp/test-skills")``。
    """
    mock_mgr = _install_mock_skill_manager(
        monkeypatch,
        check_node=(True, "v20.0.0"),
        check_npm=(True, "10.5.0"),
        check_chrome=(True, "/fake/chrome"),
        locate_skill=None,
        install_or_update_skill=Path("/fake/dashi-ppt/SKILL.md"),
    )

    custom_dir = "/tmp/test-skills"
    result = cmd_setup(["--dir", custom_dir])

    assert result == 0
    mock_mgr.install_or_update_skill.assert_called_once()
    args, _kwargs = mock_mgr.install_or_update_skill.call_args
    assert args[0] == Path(custom_dir)


# ---------------------------------------------------------------------------
# SubTask 5.6: --registry <url> 参数解析
# ---------------------------------------------------------------------------


def test_cmd_setup_registry_arg_passed_to_install(monkeypatch: pytest.MonkeyPatch) -> None:
    """SubTask 5.6 - ``--registry <url>`` 应作为关键字参数传给 ``install_or_update_skill``。

    执行 ``cmd_setup(["--registry", "https://registry.npmmirror.com"])``,
    断言 ``install_or_update_skill`` 的 ``registry`` 关键字参数等于该 URL。
    """
    mock_mgr = _install_mock_skill_manager(
        monkeypatch,
        check_node=(True, "v20.0.0"),
        check_npm=(True, "10.5.0"),
        check_chrome=(True, "/fake/chrome"),
        locate_skill=None,
        install_or_update_skill=Path("/fake/dashi-ppt/SKILL.md"),
    )

    registry_url = "https://registry.npmmirror.com"
    result = cmd_setup(["--registry", registry_url])

    assert result == 0
    mock_mgr.install_or_update_skill.assert_called_once()
    _args, kwargs = mock_mgr.install_or_update_skill.call_args
    assert kwargs.get("registry") == registry_url


# ---------------------------------------------------------------------------
# SubTask 5.7: locate_skill() 在 skill 未安装/已安装时的行为
# ---------------------------------------------------------------------------
#
# 注意:SkillManager.default_skill_dir 始终为 Path.home() / ".anappt" / "skills"
# / "dashi-ppt",它并不随 ``config_dir`` 参数变化。为了让 locate_skill() 查找
# tmp_path 下的路径,这里通过写 config.yaml 设置 ``skill_parent_dir`` 字段,
# 使其指向 ``tmp_path / "skills"``。这样 ``locate_skill`` 会查找
# ``tmp_path / "skills" / "dashi-ppt" / "SKILL.md"``。


def test_locate_skill_returns_none_when_not_installed(tmp_path: Path) -> None:
    """SubTask 5.7 - skill 未安装(无 SKILL.md)时 ``locate_skill`` 返回 None。"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        f"skill_parent_dir: {tmp_path / 'skills'}\n", encoding="utf-8"
    )

    mgr = SkillManager(config_dir=tmp_path)

    assert mgr.locate_skill() is None


def test_locate_skill_returns_path_when_installed(tmp_path: Path) -> None:
    """SubTask 5.7 - skill 已安装(SKILL.md 存在)时返回该文件路径。"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        f"skill_parent_dir: {tmp_path / 'skills'}\n", encoding="utf-8"
    )

    skill_md = tmp_path / "skills" / "dashi-ppt" / "SKILL.md"
    skill_md.parent.mkdir(parents=True, exist_ok=True)
    skill_md.touch()

    mgr = SkillManager(config_dir=tmp_path)
    result = mgr.locate_skill()

    assert result is not None
    assert result == skill_md


# ---------------------------------------------------------------------------
# SubTask 5.8: save_skill_dir_config() 正确写入 config.yaml
# ---------------------------------------------------------------------------


def test_save_skill_dir_config_writes_and_preserves(tmp_path: Path) -> None:
    """SubTask 5.8 - ``save_skill_dir_config`` 写入 ``skill_parent_dir`` 且保留其他字段。

    预先写一个含 ``locale: zh`` 的 config.yaml,调用
    ``save_skill_dir_config(tmp_path / "custom-skills")``,验证:
      - config.yaml 文件存在
      - ``skill_parent_dir`` 字段等于 ``str(tmp_path / "custom-skills")``
      - 原有的 ``locale`` 字段仍保留
    """
    config_file = tmp_path / "config.yaml"
    config_file.write_text("locale: zh\n", encoding="utf-8")

    mgr = SkillManager(config_dir=tmp_path)
    custom_skills_dir = tmp_path / "custom-skills"
    mgr.save_skill_dir_config(custom_skills_dir)

    assert config_file.exists()

    with open(config_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert data["skill_parent_dir"] == str(custom_skills_dir)
    assert data["locale"] == "zh"


# ---------------------------------------------------------------------------
# SubTask 5.9: install_or_update_skill() 在 npx 失败时抛 RuntimeError
# ---------------------------------------------------------------------------


def test_install_or_update_skill_raises_on_npx_failure(tmp_path: Path) -> None:
    """SubTask 5.9 - ``subprocess.run`` 返回非零时 ``install_or_update_skill`` 抛 RuntimeError。

    mock ``shutil.which`` 返回假的 npm 路径,``subprocess.run`` 返回
    ``returncode=1, stderr="some error"``,验证抛出 ``RuntimeError``,
    异常消息包含 "some error" 或 "npm exec 安装失败"。
    """
    from unittest.mock import patch

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "some error"
    mock_result.stdout = ""

    # 用 patch 上下文管理器替换 skill_manager 模块内的 shutil.which 与
    # subprocess.run,使其分别返回假路径与 mock_result。
    with patch(
        "anappt.io.skill_manager.shutil.which", return_value="/fake/npm"
    ), patch(
        "anappt.io.skill_manager.subprocess.run", return_value=mock_result
    ):
        mgr = SkillManager(config_dir=tmp_path)

        with pytest.raises(RuntimeError) as exc_info:
            mgr.install_or_update_skill(tmp_path)

    message = str(exc_info.value)
    # 严格断言 "some error" 在消息中,以确认 mock 生效(而非真实 npm 调用失败)
    assert "some error" in message, f"Expected 'some error' in message, got: {message!r}"
    assert "npm exec 安装失败" in message


# ---------------------------------------------------------------------------
# SubTask 5.10: shutil.which 解析可执行文件(兼容 Windows .cmd / .bat)
# ---------------------------------------------------------------------------
#
# Windows 上 npm / npx 以 .cmd 批处理脚本形式分发,subprocess.run([name, ...])
# 在 shell=False 时无法找到 .cmd 文件。check_node / check_npm /
# install_or_update_skill 应先通过 shutil.which 解析完整路径再调用 subprocess。


def test_resolve_executable_uses_shutil_which() -> None:
    """SubTask 5.10 - ``_resolve_executable`` 直接委托给 ``shutil.which``。"""
    from unittest.mock import patch

    with patch(
        "anappt.io.skill_manager.shutil.which", return_value="/fake/path/npm"
    ) as mock_which:
        result = SkillManager._resolve_executable("npm")

    assert result == "/fake/path/npm"
    mock_which.assert_called_once_with("npm")


def test_check_node_uses_resolved_path(tmp_path: Path) -> None:
    """SubTask 5.10 - ``check_node`` 应通过 ``shutil.which`` 解析 node 路径,
    并把完整路径传给 ``subprocess.run``。"""
    from unittest.mock import patch

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "v20.10.0\n"
    mock_result.stderr = ""

    mgr = SkillManager(config_dir=tmp_path)
    with patch(
        "anappt.io.skill_manager.shutil.which", return_value="/fake/node"
    ) as mock_which, patch(
        "anappt.io.skill_manager.subprocess.run", return_value=mock_result
    ) as mock_run:
        ok, ver = mgr.check_node()

    assert ok is True
    assert ver == "v20.10.0"
    mock_which.assert_called_once_with("node")
    # 验证传给 subprocess.run 的是完整路径,而非裸 "node"
    args, _kwargs = mock_run.call_args
    assert args[0][0] == "/fake/node"


def test_check_node_returns_false_when_node_not_in_path(tmp_path: Path) -> None:
    """SubTask 5.10 - ``shutil.which('node')`` 返回 None 时,``check_node``
    应直接返回 ``(False, "")``,不调用 ``subprocess.run``。"""
    from unittest.mock import patch

    mgr = SkillManager(config_dir=tmp_path)
    with patch(
        "anappt.io.skill_manager.shutil.which", return_value=None
    ), patch(
        "anappt.io.skill_manager.subprocess.run"
    ) as mock_run:
        ok, ver = mgr.check_node()

    assert ok is False
    assert ver == ""
    mock_run.assert_not_called()


def test_check_npm_uses_resolved_path(tmp_path: Path) -> None:
    """SubTask 5.10 - ``check_npm`` 应通过 ``shutil.which`` 解析 npm 路径,
    并把完整路径传给 ``subprocess.run``(兼容 Windows 上的 npm.cmd)。"""
    from unittest.mock import patch

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "11.17.0\n"
    mock_result.stderr = ""

    mgr = SkillManager(config_dir=tmp_path)
    with patch(
        "anappt.io.skill_manager.shutil.which", return_value="/fake/npm.CMD"
    ) as mock_which, patch(
        "anappt.io.skill_manager.subprocess.run", return_value=mock_result
    ) as mock_run:
        ok, ver = mgr.check_npm()

    assert ok is True
    assert ver == "11.17.0"
    mock_which.assert_called_once_with("npm")
    # 验证传给 subprocess.run 的是完整路径,而非裸 "npm"
    args, _kwargs = mock_run.call_args
    assert args[0][0] == "/fake/npm.CMD"


def test_check_npm_returns_false_when_npm_not_in_path(tmp_path: Path) -> None:
    """SubTask 5.10 - ``shutil.which('npm')`` 返回 None 时,``check_npm``
    应直接返回 ``(False, "")``,不调用 ``subprocess.run``。"""
    from unittest.mock import patch

    mgr = SkillManager(config_dir=tmp_path)
    with patch(
        "anappt.io.skill_manager.shutil.which", return_value=None
    ), patch(
        "anappt.io.skill_manager.subprocess.run"
    ) as mock_run:
        ok, ver = mgr.check_npm()

    assert ok is False
    assert ver == ""
    mock_run.assert_not_called()


def test_install_or_update_skill_raises_when_npm_not_in_path(tmp_path: Path) -> None:
    """SubTask 5.10 - ``shutil.which('npm')`` 返回 None 时,
    ``install_or_update_skill`` 应直接抛 ``RuntimeError``,不调用
    ``subprocess.run``。"""
    from unittest.mock import patch

    mgr = SkillManager(config_dir=tmp_path)
    with patch(
        "anappt.io.skill_manager.shutil.which", return_value=None
    ), patch(
        "anappt.io.skill_manager.subprocess.run"
    ) as mock_run:
        with pytest.raises(RuntimeError) as exc_info:
            mgr.install_or_update_skill(tmp_path)

    assert "npm" in str(exc_info.value)
    mock_run.assert_not_called()


def test_install_or_update_skill_uses_npm_exec_with_yes_and_separator(
    tmp_path: Path,
) -> None:
    """SubTask 5.10 / 5.11 - ``install_or_update_skill`` 应:

    1. 通过 ``shutil.which`` 解析 npm 路径(兼容 Windows .cmd);
    2. 用 ``npm exec --yes -- <pkg> --dir <path>`` 而非 ``npx <pkg> --dir <path>``
       以避免 npx 捆绑的陈旧 npm(如 Scoop persist 目录里的 npm 5.x)与新 Node
       不兼容;
    3. ``--`` 分隔符确保 ``--dir`` 被传给 dashi-ppt-skill 而非被 npm exec 解析。
    """
    from unittest.mock import patch

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""
    mock_result.stdout = ""

    fake_npm = "/fake/npm.CMD"
    mgr = SkillManager(config_dir=tmp_path)
    with patch(
        "anappt.io.skill_manager.shutil.which", return_value=fake_npm
    ) as mock_which, patch(
        "anappt.io.skill_manager.subprocess.run", return_value=mock_result
    ) as mock_run:
        # 让安装后的 SKILL.md 真实存在,避免触发 "未找到 SKILL.md" RuntimeError
        skill_md = tmp_path / "dashi-ppt" / "SKILL.md"
        skill_md.parent.mkdir(parents=True, exist_ok=True)
        skill_md.touch()

        result = mgr.install_or_update_skill(tmp_path)

    assert result == skill_md
    mock_which.assert_called_once_with("npm")
    args, _kwargs = mock_run.call_args
    cmd = args[0]
    # 命令以解析后的 npm 完整路径开头,而非裸 "npx"
    assert cmd[0] == fake_npm
    # 必须包含 exec / --yes / -- 分隔符与 dashi-ppt-skill@latest / --dir
    assert cmd[1] == "exec"
    assert "--yes" in cmd
    assert "--" in cmd
    assert "dashi-ppt-skill@latest" in cmd
    assert "--dir" in cmd
    # --dir 的值应为 skill_dir 的字符串形式
    dir_idx = cmd.index("--dir")
    assert cmd[dir_idx + 1] == str(tmp_path)
    # -- 应在 dashi-ppt-skill@latest 之前,确保 --dir 不被 npm exec 解析
    sep_idx = cmd.index("--")
    pkg_idx = cmd.index("dashi-ppt-skill@latest")
    assert sep_idx < pkg_idx


def test_install_or_update_skill_passes_registry_to_npm_exec(tmp_path: Path) -> None:
    """``install_or_update_skill(registry=...)`` 应将 ``--registry=<url>`` 传给
    ``npm exec``,且位于 ``--`` 分隔符之前(作为 npm 自身的 flag)。"""
    from unittest.mock import patch

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""
    mock_result.stdout = ""

    mgr = SkillManager(config_dir=tmp_path)
    registry_url = "https://registry.npmmirror.com"
    with patch(
        "anappt.io.skill_manager.shutil.which", return_value="/fake/npm"
    ), patch(
        "anappt.io.skill_manager.subprocess.run", return_value=mock_result
    ) as mock_run:
        skill_md = tmp_path / "dashi-ppt" / "SKILL.md"
        skill_md.parent.mkdir(parents=True, exist_ok=True)
        skill_md.touch()

        mgr.install_or_update_skill(tmp_path, registry=registry_url)

    args, _kwargs = mock_run.call_args
    cmd = args[0]
    assert f"--registry={registry_url}" in cmd
    # --registry 应位于 -- 之前(npm 自身 flag)
    reg_idx = cmd.index(f"--registry={registry_url}")
    sep_idx = cmd.index("--")
    assert reg_idx < sep_idx


# ---------------------------------------------------------------------------
# 编码参数:subprocess.run 必须显式指定 UTF-8,避免中文 Windows 上 GBK
# 解码 UTF-8 输出导致 _readerthread 崩溃(UnicodeDecodeError)。
# ---------------------------------------------------------------------------


def test_check_node_passes_utf8_encoding_to_subprocess(tmp_path: Path) -> None:
    """``check_node`` 调用 ``subprocess.run`` 时必须显式传
    ``encoding="utf-8", errors="replace"``。

    中文 Windows 上 ``text=True`` 默认用 GBK 解码,而 Node.js 输出 UTF-8,
    会导致后台 ``_readerthread`` 抛 ``UnicodeDecodeError``。
    """
    from unittest.mock import patch

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "v20.10.0\n"
    mock_result.stderr = ""

    mgr = SkillManager(config_dir=tmp_path)
    with patch(
        "anappt.io.skill_manager.shutil.which", return_value="/fake/node"
    ), patch(
        "anappt.io.skill_manager.subprocess.run", return_value=mock_result
    ) as mock_run:
        mgr.check_node()

    _args, kwargs = mock_run.call_args
    assert kwargs.get("encoding") == "utf-8"
    assert kwargs.get("errors") == "replace"


def test_check_npm_passes_utf8_encoding_to_subprocess(tmp_path: Path) -> None:
    """``check_npm`` 调用 ``subprocess.run`` 时必须显式传
    ``encoding="utf-8", errors="replace"``。"""
    from unittest.mock import patch

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "11.17.0\n"
    mock_result.stderr = ""

    mgr = SkillManager(config_dir=tmp_path)
    with patch(
        "anappt.io.skill_manager.shutil.which", return_value="/fake/npm.CMD"
    ), patch(
        "anappt.io.skill_manager.subprocess.run", return_value=mock_result
    ) as mock_run:
        mgr.check_npm()

    _args, kwargs = mock_run.call_args
    assert kwargs.get("encoding") == "utf-8"
    assert kwargs.get("errors") == "replace"


def test_install_or_update_skill_passes_utf8_encoding_to_subprocess(
    tmp_path: Path,
) -> None:
    """``install_or_update_skill`` 调用 ``subprocess.run`` 时必须显式传
    ``encoding="utf-8", errors="replace"``。

    这是用户实际触发 ``UnicodeDecodeError`` 崩溃的调用点:npm exec 安装
    dashi-ppt-skill 时输出含 UTF-8 字节的日志,在中文 Windows 上被 GBK
    解码导致崩溃。
    """
    from unittest.mock import patch

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""
    mock_result.stdout = ""

    mgr = SkillManager(config_dir=tmp_path)
    with patch(
        "anappt.io.skill_manager.shutil.which", return_value="/fake/npm"
    ), patch(
        "anappt.io.skill_manager.subprocess.run", return_value=mock_result
    ) as mock_run:
        # 让安装后的 SKILL.md 真实存在,避免触发 "未找到 SKILL.md" RuntimeError
        skill_md = tmp_path / "dashi-ppt" / "SKILL.md"
        skill_md.parent.mkdir(parents=True, exist_ok=True)
        skill_md.touch()

        mgr.install_or_update_skill(tmp_path)

    _args, kwargs = mock_run.call_args
    assert kwargs.get("encoding") == "utf-8"
    assert kwargs.get("errors") == "replace"
