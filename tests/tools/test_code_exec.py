"""Tests for the code execution module."""


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
