"""dashi-ppt-skill 环境与安装管理模块。

封装 dashi-ppt-skill 的环境检查、安装、定位逻辑。该 skill 通过
`npx dashi-ppt-skill@latest --dir <path>` 安装,安装后会生成
`<path>/dashi-ppt/SKILL.md` 入口文件。SkillManager 负责检查
Node.js / npm / Chrome 运行环境,执行 npx 安装/更新,定位已安装的
skill 根目录,并将 skill 安装路径持久化到 `~/.anappt/config.yaml`。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml


class SkillManager:
    """管理 dashi-ppt-skill 的环境检查、安装与定位。

    Attributes:
        config_dir: 配置目录(默认 `~/.anappt/`)。
        config_file: config.yaml 路径(`config_dir / "config.yaml"`)。
        config: 已加载的配置字典(文件不存在时为空字典)。
        default_skill_dir: 默认 skill 安装目录(`~/.anappt/skills/dashi-ppt/`)。
    """

    def __init__(self, config_dir: Path | None = None) -> None:
        """初始化 SkillManager。

        Args:
            config_dir: 配置目录路径;为 None 时使用 `~/.anappt/`。
        """
        if config_dir is not None:
            self.config_dir: Path = Path(config_dir)
        else:
            self.config_dir = Path.home() / ".anappt"
        self.config_file: Path = self.config_dir / "config.yaml"
        self.default_skill_dir: Path = Path.home() / ".anappt" / "skills" / "dashi-ppt"
        self.config: dict = self._load_config()

    def _load_config(self) -> dict:
        """加载 config.yaml;文件不存在或为空时返回空字典。

        Returns:
            已解析的配置字典;文件不存在时返回 `{}`。
        """
        if not self.config_file.exists():
            return {}
        try:
            with open(self.config_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except (OSError, yaml.YAMLError):
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _resolve_executable(name: str) -> str | None:
        """通过 ``shutil.which`` 解析可执行文件路径,兼容 Windows 上的 ``.cmd`` / ``.bat`` 脚本。

        Windows 上 ``npm`` / ``npx`` 以 ``.cmd`` 批处理脚本形式分发(如
        ``npm.CMD``、``npx.CMD``)。``subprocess.run([name, ...])`` 在
        ``shell=False`` 时底层调用 ``CreateProcessW``,该 API 不会遵循
        ``PATHEXT`` 解析 ``.cmd`` / ``.bat``,导致即使软件已安装也会抛
        ``FileNotFoundError``。``shutil.which`` 会遵循 ``PATHEXT``,能正确
        返回 ``npm.cmd`` / ``npx.cmd`` 的完整路径,从而绕过此限制。

        Args:
            name: 可执行文件名(如 ``"node"``、``"npm"``、``"npx"``)。

        Returns:
            完整路径字符串(找到时);``None`` 表示未在 ``PATH`` 中找到。
        """
        return shutil.which(name)

    def check_node(self) -> tuple[bool, str]:
        """检查 Node.js 是否安装且版本 ≥ 20。

        先通过 ``shutil.which`` 解析 ``node`` 的完整路径(兼容 Windows
        上的 ``.cmd`` / ``.bat`` 脚本分发),再调用 ``node --version`` 并
        解析 ``vMAJOR.MINOR.PATCH`` 格式。命令缺失、超时、返回码非零或
        主版本号 < 20 时返回失败。

        Returns:
            元组 `(ok, version)`:
              - 成功:`(True, "v20.x.x")` 形式的原始输出(已去除首尾空白)。
              - 命令失败:`(False, "")`。
              - 版本解析失败:`(False, raw_output)`。
              - 版本过低:`(False, raw_output)`。
        """
        node_path = self._resolve_executable("node")
        if node_path is None:
            return (False, "")

        try:
            result = subprocess.run(
                [node_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return (False, "")

        if result.returncode != 0:
            return (False, "")

        raw = (result.stdout or "").strip()
        # 解析 vMAJOR.MINOR.PATCH 格式
        match = re.match(r"^v?(\d+)\.", raw)
        if match is None:
            return (False, raw)
        major = int(match.group(1))
        if major < 20:
            return (False, raw)
        return (True, raw)

    def check_npm(self) -> tuple[bool, str]:
        """检查 npm 是否可用。

        先通过 ``shutil.which`` 解析 ``npm`` 的完整路径(兼容 Windows 上
        的 ``npm.cmd`` 脚本分发),再调用 ``npm --version`` 并去除首尾空白。

        Returns:
            元组 `(ok, version)`:
              - 成功:`(True, "10.x.x")` 形式的版本字符串。
              - 失败:`(False, "")`。
        """
        npm_path = self._resolve_executable("npm")
        if npm_path is None:
            return (False, "")

        try:
            result = subprocess.run(
                [npm_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return (False, "")

        if result.returncode != 0:
            return (False, "")

        version = (result.stdout or "").strip()
        if not version:
            return (False, "")
        return (True, version)

    def check_chrome(self) -> tuple[bool, str | None]:
        """检查 Chrome / Chromium / Edge 浏览器是否可用。

        查找顺序:
          1. `CHROME_PATH` 环境变量(若指向的文件存在则直接采用)。
          2. `shutil.which` 在 PATH 中查找 `chrome`、`chromium`、
             `chromium-browser`、`msedge`。
          3. Windows 上额外检查常见安装路径(Chrome、Edge)。

        Returns:
            元组 `(ok, path)`:
              - 找到:`(True, path)`。
              - 未找到:`(False, None)`。
        """
        # 1. 优先读 CHROME_PATH 环境变量
        env_path = os.environ.get("CHROME_PATH")
        if env_path:
            env_path_obj = Path(env_path)
            if env_path_obj.is_file():
                return (True, str(env_path_obj))

        # 2. 在 PATH 中查找
        for candidate in ("chrome", "chromium", "chromium-browser", "msedge"):
            found = shutil.which(candidate)
            if found:
                return (True, found)

        # 3. Windows 上额外检查常见安装路径
        if sys.platform == "win32":
            candidate_paths = [
                Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
                Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
                Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            ]
            local_app_data = os.environ.get("LOCALAPPDATA")
            if local_app_data:
                candidate_paths.append(
                    Path(local_app_data) / "Google" / "Chrome" / "Application" / "chrome.exe"
                )
            for candidate in candidate_paths:
                if candidate.is_file():
                    return (True, str(candidate))

        return (False, None)

    def install_or_update_skill(
        self,
        skill_dir: Path,
        registry: str | None = None,
    ) -> Path:
        """通过 `npx dashi-ppt-skill@latest --dir <skill_dir>` 安装或更新 skill。

        Args:
            skill_dir: skill 安装父目录;npx 会将 skill 安装到
                `<skill_dir>/dashi-ppt/` 子目录中。
            registry: 可选的 npm 镜像地址(如 `https://registry.npmmirror.com`)。

        Returns:
            安装后生成的 `SKILL.md` 完整路径
            (`<skill_dir>/dashi-ppt/SKILL.md`)。

        Raises:
            RuntimeError: npx 未在 PATH 中找到、npx 返回码非零,或安装后未
                找到 `SKILL.md`。
        """
        # 先通过 shutil.which 解析 npx 完整路径(Windows 上 npx 是 .cmd 脚本,
        # subprocess.run(["npx", ...]) 在 shell=False 时无法直接找到)。
        npx_path = self._resolve_executable("npx")
        if npx_path is None:
            raise RuntimeError(
                "npx 未在 PATH 中找到,请确保 Node.js / npm 已正确安装"
            )

        cmd: list[str] = [npx_path]
        if registry:
            cmd.append(f"--registry={registry}")
        cmd.extend(["dashi-ppt-skill@latest", "--dir", str(skill_dir)])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"npx 安装失败: {exc}") from exc

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise RuntimeError(
                f"npx 安装失败(returncode={result.returncode}): {stderr}"
            )

        expected_path = Path(skill_dir) / "dashi-ppt" / "SKILL.md"
        if not expected_path.exists():
            raise RuntimeError(f"安装后未找到 SKILL.md: {expected_path}")
        return expected_path

    def locate_skill(self) -> Path | None:
        """定位已安装的 dashi-ppt-skill 的 `SKILL.md` 路径。

        约定:config.yaml 中的 `skill_parent_dir` 字段存储的是 skill
        父目录(如 `~/.anappt/skills/`),实际 skill 根目录需追加
        `dashi-ppt/`。若该字段未配置,则回退到 `self.default_skill_dir`
        (本身已是 skill 根目录)。

        Returns:
            `SKILL.md` 完整路径(文件存在时);否则 None。
        """
        skill_parent_dir = self.config.get("skill_parent_dir")
        if skill_parent_dir:
            skill_root = Path(skill_parent_dir) / "dashi-ppt"
        else:
            skill_root = self.default_skill_dir

        skill_md = skill_root / "SKILL.md"
        if skill_md.exists():
            return skill_md
        return None

    def get_skill_root(self) -> Path:
        """获取已安装 skill 的根目录(SKILL.md 所在目录)。

        Returns:
            skill 根目录 Path 对象。

        Raises:
            FileNotFoundError: skill 未安装时抛出,提示先运行 `anappt setup`。
        """
        skill_md = self.locate_skill()
        if skill_md is None:
            raise FileNotFoundError(
                "dashi-ppt skill 未安装,请先运行 'anappt setup' 命令"
            )
        return skill_md.parent

    def save_skill_dir_config(self, skill_parent_dir: Path) -> None:
        """将 skill 父目录持久化到 `~/.anappt/config.yaml`。

        若 config.yaml 已存在,先读取再更新 `skill_parent_dir` 字段,
        避免覆盖其他字段。文件或父目录不存在时会自动创建。

        Args:
            skill_parent_dir: skill 父目录(如 `~/.anappt/skills/`),
                **不是** skill 根目录,以便 `locate_skill()` 还原。
        """
        # 重新加载最新的 config(避免内存中的 self.config 已过期)
        config: dict = {}
        if self.config_file.exists():
            try:
                with open(self.config_file, encoding="utf-8") as f:
                    loaded = yaml.safe_load(f)
                if isinstance(loaded, dict):
                    config = loaded
            except (OSError, yaml.YAMLError):
                config = {}

        config["skill_parent_dir"] = str(skill_parent_dir)

        # 确保父目录存在
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                config,
                f,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            )

        # 同步更新内存中的 config
        self.config = config
