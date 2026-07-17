"""Code execution sandbox for AnaPPTAgent.

Executes Python code in an isolated subprocess with:
- Timeout control
- Restricted file system access
- No network access (socket blocked)
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from pydantic import BaseModel


class ExecutionResult(BaseModel):
    """Result of a code execution."""

    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


# Wrapper script that blocks network access and restricts file system
_SANDBOX_WRAPPER = '''
import sys
import os
import socket
import tempfile

# Block network access
def _blocked_socket(*args, **kwargs):
    raise PermissionError("Network access is blocked in the sandbox")

socket.socket = _blocked_socket
socket.create_connection = _blocked_socket
socket.getaddrinfo = _blocked_socket

# Restrict file system access to allowed directories only
_original_open = open
if isinstance(__builtins__, dict):
    _original_import = __builtins__["__import__"]
else:
    _original_import = __builtins__.__import__

def _restricted_open(file, mode="r", *args, **kwargs):
    path = os.path.abspath(file) if not isinstance(file, int) else file
    if isinstance(path, str):
        allowed = os.environ.get("ANAPPT_ALLOWED_DIRS", "").split(os.pathsep)
        allowed = [os.path.abspath(d) for d in allowed if d]
        temp_dir = os.environ.get("ANAPPT_TEMP_DIR", tempfile.gettempdir())
        allowed.append(os.path.abspath(temp_dir))
        allowed.append(os.path.abspath(os.getcwd()))
        if not any(path.startswith(d) for d in allowed):
            raise PermissionError(f"Access to path is not allowed: {path}")
    return _original_open(file, mode, *args, **kwargs)

import builtins
builtins.open = _restricted_open

# Execute user code
exec(compile(sys.stdin.read(), "<sandbox>", "exec"))
'''


def execute_python(
    code: str,
    timeout: int = 60,
    allowed_dirs: list[str | Path] | None = None,
) -> ExecutionResult:
    """Execute Python code in an isolated subprocess sandbox.

    The code runs in a separate process with:
    - Network access blocked (socket module patched)
    - File system restricted to allowed_dirs + temp directory + cwd
    - Configurable timeout

    Args:
        code: Python source code to execute.
        timeout: Maximum execution time in seconds.
        allowed_dirs: Additional directories the code can access.

    Returns:
        ExecutionResult with stdout, stderr, and returncode.
    """
    # Build allowed directories list
    allowed_paths: list[str] = []
    if allowed_dirs:
        for d in allowed_dirs:
            allowed_paths.append(str(Path(d).resolve()))
    allowed_str = os.pathsep.join(allowed_paths)

    # Create a temp file for the wrapper script
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as wrapper_file:
        wrapper_file.write(_SANDBOX_WRAPPER)
        wrapper_path = wrapper_file.name

    try:
        env = os.environ.copy()
        env["ANAPPT_ALLOWED_DIRS"] = allowed_str
        env["ANAPPT_TEMP_DIR"] = tempfile.gettempdir()

        result = subprocess.run(
            [sys.executable, wrapper_path],
            input=code,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

        return ExecutionResult(
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
        )
    except subprocess.TimeoutExpired:
        return ExecutionResult(
            stdout="",
            stderr=f"Execution timed out after {timeout} seconds",
            returncode=-1,
        )
    finally:
        # Clean up wrapper file
        try:
            os.unlink(wrapper_path)
        except OSError:
            pass
