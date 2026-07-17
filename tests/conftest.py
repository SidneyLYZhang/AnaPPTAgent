"""Shared test fixtures for AnaPPTAgent test suite.

This conftest provides common fixtures used across multiple test modules.
Fixtures will be expanded as Phase 1-2 modules are completed.
"""

import os
from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture
def mock_llm():
    """Return a mock LLM object that returns canned responses.

    This fixture will be expanded once the LLM provider is implemented.
    """
    from unittest.mock import MagicMock

    mock = MagicMock()
    mock.chat.return_value = "Mock LLM response"
    return mock


@pytest.fixture
def mock_project_dir(tmp_path: Path) -> Path:
    """Create a temporary project directory structure mimicking a real project.

    Creates the standard directory layout: data/, output/, .anappt/
    """
    project = tmp_path / "test_project"
    project.mkdir()
    (project / "data").mkdir()
    (project / "output").mkdir()
    (project / "output" / "images").mkdir()
    (project / ".anappt").mkdir()
    (project / ".anappt" / "session_history").mkdir()
    return project


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    """Create a small sample CSV file for data loading tests."""
    import csv

    csv_path = tmp_path / "data" / "sample.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "value", "date"])
        writer.writerow(["A", "10", "2026-01-01"])
        writer.writerow(["B", "20", "2026-02-01"])
        writer.writerow(["C", "30", "2026-03-01"])
    return csv_path


@pytest.fixture
def clean_env() -> Generator[None, None, None]:
    """Temporarily remove API key environment variables for isolated testing."""
    api_keys = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "DEEPSEEK_API_KEY",
        "JINA_API_KEY",
        "ANYSEARCH_API_KEY",
        "ZAI_API_KEY",
        "WEB_SEARCH_BACKEND",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
    ]
    saved = {}
    for key in api_keys:
        if key in os.environ:
            saved[key] = os.environ.pop(key)
    yield
    for key, val in saved.items():
        os.environ[key] = val
