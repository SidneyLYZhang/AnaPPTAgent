"""Tests for the config module."""


import pytest

from anappt.io.config import (
    ModelRoleConfig,
    ModelsConfig,
    ReportConfig,
    _expand_env_vars,
)


class TestExpandEnvVars:
    """Test environment variable expansion."""

    def test_expand_simple_var(self, monkeypatch):
        monkeypatch.setenv("MY_API_KEY", "secret123")
        result = _expand_env_vars("${MY_API_KEY}")
        assert result == "secret123"

    def test_expand_in_dict(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "abc")
        result = _expand_env_vars({"api_key": "${API_KEY}"})
        assert result["api_key"] == "abc"

    def test_expand_in_list(self, monkeypatch):
        monkeypatch.setenv("VAL", "xyz")
        result = _expand_env_vars(["${VAL}", "normal"])
        assert result == ["xyz", "normal"]

    def test_expand_missing_var_keeps_original(self, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_VAR", raising=False)
        result = _expand_env_vars("${NONEXISTENT_VAR}")
        assert result == "${NONEXISTENT_VAR}"

    def test_expand_non_string_unchanged(self):
        assert _expand_env_vars(123) == 123
        assert _expand_env_vars(None) is None
        assert _expand_env_vars(True) is True

    def test_expand_multiple_vars_in_string(self, monkeypatch):
        monkeypatch.setenv("VAR1", "hello")
        monkeypatch.setenv("VAR2", "world")
        result = _expand_env_vars("${VAR1} ${VAR2}")
        assert result == "hello world"


class TestReportConfig:
    """Test ReportConfig serialization and deserialization."""

    def test_default_values(self):
        config = ReportConfig()
        assert config.project.name == ""
        assert config.project.type == "one_time"
        assert config.report.topic == ""
        assert config.delivery.ppt_pages == "15-20"
        assert config.delivery.formats == ["pptx", "html"]

    def test_from_yaml(self, tmp_path):
        yaml_content = """
project:
  name: "Test Report"
  type: "monthly"
  created: "2026-07-17"

report:
  topic: "Sales Analysis"
  motivation: "Need to understand trends"
  audience:
    - "Management"
  objectives:
    - "Identify trends"
  success_criteria:
    - "Data-backed conclusions"

delivery:
  ppt_pages: "10-15"
  formats: ["pptx"]
  theme_preference: null
"""
        yaml_path = tmp_path / "report.yaml"
        yaml_path.write_text(yaml_content, encoding="utf-8")

        config = ReportConfig.from_yaml(yaml_path)
        assert config.project.name == "Test Report"
        assert config.project.type == "monthly"
        assert config.report.topic == "Sales Analysis"
        assert config.report.audience == ["Management"]
        assert config.delivery.formats == ["pptx"]

    def test_to_yaml_roundtrip(self, tmp_path):
        config = ReportConfig()
        config.project.name = "Roundtrip Test"
        config.report.topic = "Test Topic"
        config.delivery.ppt_pages = "20-25"

        yaml_str = config.to_yaml()
        # Write and re-read
        yaml_path = tmp_path / "roundtrip.yaml"
        yaml_path.write_text(yaml_str, encoding="utf-8")
        loaded = ReportConfig.from_yaml(yaml_path)

        assert loaded.project.name == "Roundtrip Test"
        assert loaded.report.topic == "Test Topic"
        assert loaded.delivery.ppt_pages == "20-25"

    def test_from_yaml_with_env_vars(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REPORT_NAME", "Env Var Report")
        yaml_content = """
project:
  name: "${REPORT_NAME}"
  type: "one_time"
"""
        yaml_path = tmp_path / "env_report.yaml"
        yaml_path.write_text(yaml_content, encoding="utf-8")

        config = ReportConfig.from_yaml(yaml_path)
        assert config.project.name == "Env Var Report"

    def test_from_yaml_empty_file(self, tmp_path):
        yaml_path = tmp_path / "empty.yaml"
        yaml_path.write_text("", encoding="utf-8")
        config = ReportConfig.from_yaml(yaml_path)
        assert config.project.name == ""
        assert config.report.topic == ""


class TestModelsConfig:
    """Test ModelsConfig serialization and deserialization."""

    def test_default_values(self):
        config = ModelsConfig()
        assert config.reasoning.model == ""
        assert config.analysis.model == ""
        assert config.writing.model == ""

    def test_from_yaml(self, tmp_path):
        yaml_content = """
reasoning:
  provider: "deepseek"
  model: "deepseek-reasoner"
  api_base: "https://api.deepseek.com/v1"
  api_key: "${DEEPSEEK_API_KEY}"

analysis:
  provider: "openai"
  model: "gpt-4o"
  api_key: "${OPENAI_API_KEY}"

writing:
  provider: "anthropic"
  model: "claude-sonnet-4-20250514"
  api_key: "${ANTHROPIC_API_KEY}"
"""
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-key-123")
        monkeypatch.setenv("OPENAI_API_KEY", "oai-key-456")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-key-789")

        yaml_path = tmp_path / "models.yaml"
        yaml_path.write_text(yaml_content, encoding="utf-8")

        config = ModelsConfig.from_yaml(yaml_path)
        assert config.reasoning.model == "deepseek-reasoner"
        assert config.reasoning.api_key == "ds-key-123"
        assert config.analysis.model == "gpt-4o"
        assert config.analysis.api_key == "oai-key-456"
        assert config.writing.model == "claude-sonnet-4-20250514"
        assert config.writing.api_key == "ant-key-789"

        monkeypatch.undo()

    def test_to_yaml_roundtrip(self, tmp_path):
        config = ModelsConfig()
        config.reasoning = ModelRoleConfig(provider="deepseek", model="test-model", api_key="key")
        config.analysis = ModelRoleConfig(provider="openai", model="gpt-4o")

        yaml_str = config.to_yaml()
        yaml_path = tmp_path / "models_roundtrip.yaml"
        yaml_path.write_text(yaml_str, encoding="utf-8")
        loaded = ModelsConfig.from_yaml(yaml_path)

        assert loaded.reasoning.model == "test-model"
        assert loaded.reasoning.api_key == "key"
        assert loaded.analysis.model == "gpt-4o"

    def test_model_role_config_from_dict_with_env(self, monkeypatch):
        monkeypatch.setenv("TEST_KEY", "expanded-value")
        role_config = ModelRoleConfig.from_dict({"model": "test", "api_key": "${TEST_KEY}"})
        assert role_config.api_key == "expanded-value"

    def test_model_role_config_to_dict(self):
        role_config = ModelRoleConfig(provider="openai", model="gpt-4o", api_key="key")
        d = role_config.to_dict()
        assert d["model"] == "gpt-4o"
        assert d["api_key"] == "key"
        assert d["provider"] == "openai"
        # api_base is None and should be excluded
        assert "api_base" not in d
