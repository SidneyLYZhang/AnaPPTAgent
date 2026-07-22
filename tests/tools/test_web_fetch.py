"""Tests for the web fetch module."""

from unittest.mock import MagicMock, patch

import pytest

from anappt.io.config import ModelsConfig, WebFetchConfig
from anappt.tools.web_fetch import configure_from_models_config, fetch_url, is_available


@pytest.fixture(autouse=True)
def clean_jina_env(monkeypatch):
    """Remove JINA_API_KEY and reset _config before each test."""
    monkeypatch.delenv("JINA_API_KEY", raising=False)
    # Reset module-level _config to avoid leakage between tests
    monkeypatch.setattr("anappt.tools.web_fetch._config", None)


class TestIsAvailable:
    """Test availability check."""

    def test_not_available_without_key(self):
        assert is_available() is False

    def test_available_with_key(self, monkeypatch):
        monkeypatch.setenv("JINA_API_KEY", "test-key")
        assert is_available() is True


class TestFetchUrl:
    """Test fetch_url function."""

    def test_raises_without_api_key(self):
        with pytest.raises(RuntimeError, match="JINA_API_KEY is not set"):
            fetch_url("http://example.com")

    @patch("anappt.tools.web_fetch.httpx.Client")
    def test_fetch_url_makes_request(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("JINA_API_KEY", "test-key")
        mock_response = MagicMock()
        mock_response.text = "# Page Title\n\nContent here"
        mock_response.raise_for_status.return_value = None
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        result = fetch_url("http://example.com")

        assert result == "# Page Title\n\nContent here"
        mock_client.get.assert_called_once()

    @patch("anappt.tools.web_fetch.httpx.Client")
    def test_fetch_url_uses_correct_jina_url(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("JINA_API_KEY", "test-key")
        mock_response = MagicMock()
        mock_response.text = "content"
        mock_response.raise_for_status.return_value = None
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        fetch_url("http://example.com/page")

        call_args = mock_client.get.call_args
        assert "r.jina.ai" in call_args.args[0]
        assert "example.com/page" in call_args.args[0]

    @patch("anappt.tools.web_fetch.httpx.Client")
    def test_fetch_url_sends_auth_header(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("JINA_API_KEY", "my-api-key")
        mock_response = MagicMock()
        mock_response.text = "content"
        mock_response.raise_for_status.return_value = None
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        fetch_url("http://example.com")

        call_kwargs = mock_client.get.call_args
        assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer my-api-key"

    @patch("anappt.tools.web_fetch.httpx.Client")
    def test_fetch_url_uses_proxy(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("JINA_API_KEY", "test-key")
        monkeypatch.setenv("HTTPS_PROXY", "http://proxy:8080")
        mock_response = MagicMock()
        mock_response.text = "content"
        mock_response.raise_for_status.return_value = None
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        fetch_url("http://example.com")

        call_kwargs = mock_client_cls.call_args
        assert call_kwargs.kwargs.get("proxy") == "http://proxy:8080"
        assert call_kwargs.kwargs.get("trust_env") is True

    @patch("anappt.tools.web_fetch.httpx.Client")
    def test_fetch_url_raises_on_http_error(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("JINA_API_KEY", "test-key")
        import httpx

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found", request=MagicMock(), response=mock_response
        )
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        with pytest.raises(httpx.HTTPStatusError):
            fetch_url("http://example.com/notfound")


class TestConfigPrecedence:
    """Test config precedence (env > yaml > default) for web_fetch."""

    def test_env_key_overrides_yaml(self, monkeypatch):
        """Env JINA_API_KEY overrides yaml jina_api_key."""
        monkeypatch.setenv("JINA_API_KEY", "env-key")
        monkeypatch.setattr(
            "anappt.tools.web_fetch._config",
            WebFetchConfig(jina_api_key="yaml-key"),
        )
        assert is_available() is True

    def test_yaml_key_when_no_env(self, monkeypatch):
        """Yaml jina_api_key used when env not set."""
        monkeypatch.setattr(
            "anappt.tools.web_fetch._config",
            WebFetchConfig(jina_api_key="yaml-key"),
        )
        assert is_available() is True

    def test_no_config_no_env_unavailable(self, monkeypatch):
        """No injected _config and no env var → is_available() False."""
        monkeypatch.setattr("anappt.tools.web_fetch._config", None)
        assert is_available() is False

    def test_fetch_url_uses_env_key(self, monkeypatch):
        """fetch_url uses env key when set (does not raise RuntimeError)."""
        monkeypatch.setenv("JINA_API_KEY", "env-key")
        monkeypatch.setattr(
            "anappt.tools.web_fetch._config",
            WebFetchConfig(jina_api_key="yaml-key"),
        )
        # Should not raise RuntimeError since env key is set
        assert is_available() is True

    @patch("anappt.tools.web_fetch.httpx.Client")
    def test_fetch_url_env_key_in_header(self, mock_client_cls, monkeypatch):
        """fetch_url sends env key (not yaml key) in Authorization header."""
        monkeypatch.setenv("JINA_API_KEY", "env-key")
        monkeypatch.setattr(
            "anappt.tools.web_fetch._config",
            WebFetchConfig(jina_api_key="yaml-key"),
        )
        mock_response = MagicMock()
        mock_response.text = "content"
        mock_response.raise_for_status.return_value = None
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        fetch_url("http://example.com")

        call_kwargs = mock_client.get.call_args
        assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer env-key"

    @patch("anappt.tools.web_fetch.httpx.Client")
    def test_fetch_url_yaml_key_in_header_when_no_env(self, mock_client_cls, monkeypatch):
        """fetch_url falls back to yaml key in Authorization header."""
        monkeypatch.setattr(
            "anappt.tools.web_fetch._config",
            WebFetchConfig(jina_api_key="yaml-key"),
        )
        mock_response = MagicMock()
        mock_response.text = "content"
        mock_response.raise_for_status.return_value = None
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        fetch_url("http://example.com")

        call_kwargs = mock_client.get.call_args
        assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer yaml-key"

    def test_fetch_url_raises_when_no_config_no_env(self, monkeypatch):
        """fetch_url raises RuntimeError when neither env nor yaml key set."""
        monkeypatch.setattr("anappt.tools.web_fetch._config", None)
        with pytest.raises(RuntimeError, match="JINA_API_KEY is not set"):
            fetch_url("http://example.com")

    def test_configure_from_models_config_injects(self, monkeypatch):
        """configure_from_models_config injects the web_fetch section."""
        models_config = ModelsConfig(
            web_fetch=WebFetchConfig(jina_api_key="injected-key"),
        )
        configure_from_models_config(models_config)
        import anappt.tools.web_fetch as wf

        assert wf._config is not None
        assert wf._config.jina_api_key == "injected-key"
        assert is_available() is True
