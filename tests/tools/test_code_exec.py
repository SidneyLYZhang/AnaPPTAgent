"""Tests for the code execution module."""


from unittest.mock import MagicMock, patch

from anappt.tools.code_exec import ExecutionResult, execute_python


class TestExecutionResult:
    """Test ExecutionResult model."""

    def test_default_values(self):
        result = ExecutionResult()
        assert result.stdout == ""
        assert result.stderr == ""
        assert result.returncode == 0

    def test_with_values(self):
        result = ExecutionResult(stdout="hello", stderr="warning", returncode=1)
        assert result.stdout == "hello"
        assert result.stderr == "warning"
        assert result.returncode == 1


class TestExecutePython:
    """Test execute_python function."""

    def test_normal_execution(self):
        code = "print('Hello, World!')"
        result = execute_python(code, timeout=10)
        assert result.returncode == 0
        assert "Hello, World!" in result.stdout

    def test_arithmetic(self):
        code = "x = 2 + 3\nprint(f'Result: {x}')"
        result = execute_python(code, timeout=10)
        assert result.returncode == 0
        assert "Result: 5" in result.stdout

    def test_import_allowed(self):
        code = "import math\nprint(math.pi)"
        result = execute_python(code, timeout=10)
        assert result.returncode == 0
        assert "3.14" in result.stdout

    def test_syntax_error(self):
        code = "print('unterminated string"
        result = execute_python(code, timeout=10)
        assert result.returncode != 0
        assert "SyntaxError" in result.stderr or "Error" in result.stderr

    def test_runtime_error(self):
        code = "raise ValueError('test error')"
        result = execute_python(code, timeout=10)
        assert result.returncode != 0
        assert "test error" in result.stderr

    def test_timeout(self):
        code = "import time\ntime.sleep(100)"
        result = execute_python(code, timeout=2)
        assert result.returncode == -1
        assert "timed out" in result.stderr.lower()

    def test_network_access_blocked(self):
        code = (
            "import socket\n"
            "s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
            "s.connect(('8.8.8.8', 53))\n"
        )
        result = execute_python(code, timeout=10)
        assert result.returncode != 0
        # The socket call should be blocked
        assert "blocked" in result.stderr.lower() or "PermissionError" in result.stderr

    def test_file_write_to_temp(self):
        """Writing to temp directory should be allowed."""

        code = (
            "import tempfile\n"
            "f = tempfile.NamedTemporaryFile(mode='w', delete=False)\n"
            "f.write('test')\n"
            "f.close()\n"
            "print(f.name)\n"
        )
        result = execute_python(code, timeout=10)
        assert result.returncode == 0
        assert result.stdout.strip() != ""

    def test_file_access_restricted(self):
        """Accessing files outside allowed dirs should be blocked."""
        code = "f = open('/etc/passwd', 'r')\nprint(f.read())"
        result = execute_python(code, timeout=10)
        # Should fail due to restricted access
        assert result.returncode != 0

    def test_allowed_dirs_parameter(self, tmp_path):
        """Test that allowed_dirs parameter grants access."""
        test_file = tmp_path / "test_data.txt"
        test_file.write_text("allowed content")

        code = f"f = open(r'{test_file}', 'r')\nprint(f.read())"
        result = execute_python(code, timeout=10, allowed_dirs=[str(tmp_path)])
        assert result.returncode == 0
        assert "allowed content" in result.stdout

    def test_stdout_capture(self):
        code = "for i in range(5):\n    print(f'Line {i}')"
        result = execute_python(code, timeout=10)
        assert result.returncode == 0
        for i in range(5):
            assert f"Line {i}" in result.stdout

    def test_multiline_code(self):
        code = (
            "data = [1, 2, 3, 4, 5]\n"
            "total = sum(data)\n"
            "avg = total / len(data)\n"
            "print(f'Sum: {total}, Avg: {avg}')\n"
        )
        result = execute_python(code, timeout=10)
        assert result.returncode == 0
        assert "Sum: 15" in result.stdout
        assert "Avg: 3.0" in result.stdout

    def test_no_output(self):
        code = "x = 1 + 1"
        result = execute_python(code, timeout=10)
        assert result.returncode == 0
        assert result.stdout == ""

    def test_empty_code(self):
        result = execute_python("", timeout=10)
        assert result.returncode == 0

    def test_chinese_stdout_capture(self):
        """子 Python 进程输出的中文应被正确捕获,不出现 mojibake。

        依赖两个修复:
        1. 父进程 ``subprocess.run`` 显式 ``encoding="utf-8"`` 解码子进程输出;
        2. 子进程 ``env["PYTHONUTF8"] = "1"`` 强制其 ``print()`` 用 UTF-8
           编码(否则中文 Windows 上子进程会用 GBK 编码,父进程按 UTF-8 解码
           会得到 mojibake)。
        """
        code = "print('你好,世界')"
        result = execute_python(code, timeout=10)
        assert result.returncode == 0
        assert "你好,世界" in result.stdout

    def test_pythonutf8_env_set(self):
        """``execute_python`` 必须在子进程 env 中设置 ``PYTHONUTF8=1``。

        PEP 540 的 ``PYTHONUTF8`` 环境变量强制 Python 子进程使用 UTF-8 作为
        stdin/stdout/stderr 编码,在中文 Windows 上覆盖默认的 GBK/CP936。
        不设置则子进程的 ``print("中文")`` 会用 GBK 编码输出,父进程按
        UTF-8 解码会得到 mojibake。
        """
        with patch(
            "anappt.tools.code_exec.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="", stderr=""
            )
            execute_python("print('hi')", timeout=10)

        _args, kwargs = mock_run.call_args
        env = kwargs.get("env", {})
        assert env.get("PYTHONUTF8") == "1"
        # 同时验证 encoding 参数
        assert kwargs.get("encoding") == "utf-8"
        assert kwargs.get("errors") == "replace"
