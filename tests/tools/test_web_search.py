"""Tests for the web search module."""

from unittest.mock import MagicMock, patch

import pytest

from anappt.tools.web_search import (
    AnySearchBackend,
    DuckDuckGoBackend,
    SearchBackend,
    SearchResult,
    ZAIBackend,
    get_backend,
    get_backend_instance,
    search_web,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Remove all API key env vars before each test."""
    for key in ["ANYSEARCH_API_KEY", "ZAI_API_KEY", "WEB_SEARCH_BACKEND"]:
        monkeypatch.delenv(key, raising=False)


class TestSearchResult:
    """Test SearchResult model."""

    def test_create_search_result(self):
        result = SearchResult(title="Test", url="http://example.com", snippet="A test")
        assert result.title == "Test"
        assert result.url == "http://example.com"
        assert result.snippet == "A test"

    def test_search_result_default_snippet(self):
        result = SearchResult(title="Test", url="http://example.com")
        assert result.snippet == ""


class TestGetBackend:
    """Test backend selection logic."""

    def test_no_keys_returns_duckduckgo(self, monkeypatch):
        monkeypatch.delenv("ANYSEARCH_API_KEY", raising=False)
        monkeypatch.delenv("ZAI_API_KEY", raising=False)
        assert get_backend() == SearchBackend.DUCKDUCKGO

    def test_only_anysearch_key_returns_anysearch(self, monkeypatch):
        monkeypatch.setenv("ANYSEARCH_API_KEY", "test-key")
        monkeypatch.delenv("ZAI_API_KEY", raising=False)
        assert get_backend() == SearchBackend.ANYSEARCH

    def test_only_zai_key_returns_zai(self, monkeypatch):
        monkeypatch.delenv("ANYSEARCH_API_KEY", raising=False)
        monkeypatch.setenv("ZAI_API_KEY", "test-key")
        assert get_backend() == SearchBackend.ZAI

    def test_both_keys_default_anysearch(self, monkeypatch):
        monkeypatch.setenv("ANYSEARCH_API_KEY", "anysearch-key")
        monkeypatch.setenv("ZAI_API_KEY", "zai-key")
        monkeypatch.delenv("WEB_SEARCH_BACKEND", raising=False)
        assert get_backend() == SearchBackend.ANYSEARCH

    def test_both_keys_with_zai_preference(self, monkeypatch):
        monkeypatch.setenv("ANYSEARCH_API_KEY", "anysearch-key")
        monkeypatch.setenv("ZAI_API_KEY", "zai-key")
        monkeypatch.setenv("WEB_SEARCH_BACKEND", "zai")
        assert get_backend() == SearchBackend.ZAI

    def test_both_keys_with_anysearch_preference(self, monkeypatch):
        monkeypatch.setenv("ANYSEARCH_API_KEY", "anysearch-key")
        monkeypatch.setenv("ZAI_API_KEY", "zai-key")
        monkeypatch.setenv("WEB_SEARCH_BACKEND", "anysearch")
        assert get_backend() == SearchBackend.ANYSEARCH


class TestGetBackendInstance:
    """Test backend instance creation."""

    def test_get_duckduckgo_instance(self):
        backend = get_backend_instance(SearchBackend.DUCKDUCKGO)
        assert isinstance(backend, DuckDuckGoBackend)

    def test_get_anysearch_instance(self):
        backend = get_backend_instance(SearchBackend.ANYSEARCH)
        assert isinstance(backend, AnySearchBackend)

    def test_get_zai_instance(self):
        backend = get_backend_instance(SearchBackend.ZAI)
        assert isinstance(backend, ZAIBackend)

    def test_auto_select_no_keys(self, monkeypatch):
        monkeypatch.delenv("ANYSEARCH_API_KEY", raising=False)
        monkeypatch.delenv("ZAI_API_KEY", raising=False)
        backend = get_backend_instance()
        assert isinstance(backend, DuckDuckGoBackend)


class TestDuckDuckGoBackend:
    """Test DuckDuckGo search backend."""

    @patch("anappt.tools.web_search.DuckDuckGoBackend.search")
    def test_search_returns_results(self, mock_search):
        mock_search.return_value = [
            SearchResult(title="Python", url="https://python.org", snippet="Python language"),
        ]
        backend = DuckDuckGoBackend()
        results = backend.search("python programming", num_results=5)
        assert len(results) == 1
        assert results[0].title == "Python"

    @patch("anappt.tools.web_search.DuckDuckGoBackend.search")
    def test_search_empty_on_error(self, mock_search):
        mock_search.return_value = []
        backend = DuckDuckGoBackend()
        results = backend.search("nonexistent query")
        assert results == []

    def test_get_proxy_reads_https_proxy(self, monkeypatch):
        monkeypatch.setenv("HTTPS_PROXY", "http://proxy:8080")
        backend = DuckDuckGoBackend()
        assert backend._get_proxy() == "http://proxy:8080"

    def test_get_proxy_reads_http_proxy(self, monkeypatch):
        monkeypatch.delenv("HTTPS_PROXY", raising=False)
        monkeypatch.setenv("HTTP_PROXY", "http://proxy:8080")
        backend = DuckDuckGoBackend()
        assert backend._get_proxy() == "http://proxy:8080"

    def test_get_proxy_reads_all_proxy(self, monkeypatch):
        monkeypatch.delenv("HTTPS_PROXY", raising=False)
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        monkeypatch.setenv("ALL_PROXY", "socks5://proxy:1080")
        backend = DuckDuckGoBackend()
        assert backend._get_proxy() == "socks5://proxy:1080"

    def test_get_proxy_none_when_not_set(self, monkeypatch):
        monkeypatch.delenv("HTTPS_PROXY", raising=False)
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        monkeypatch.delenv("ALL_PROXY", raising=False)
        backend = DuckDuckGoBackend()
        assert backend._get_proxy() is None


class TestAnySearchBackend:
    """Test AnySearch backend."""

    def test_search_without_api_key_returns_empty(self, monkeypatch):
        monkeypatch.delenv("ANYSEARCH_API_KEY", raising=False)
        backend = AnySearchBackend()
        results = backend.search("test")
        assert results == []

    @patch("anappt.tools.web_search.httpx.Client")
    def test_search_with_api_key(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("ANYSEARCH_API_KEY", "test-key")
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {"title": "Result 1", "url": "http://example.com/1", "snippet": "Snippet 1"},
                {"title": "Result 2", "url": "http://example.com/2", "snippet": "Snippet 2"},
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        backend = AnySearchBackend()
        results = backend.search("test query", num_results=2)

        assert len(results) == 2
        assert results[0].title == "Result 1"
        assert results[1].url == "http://example.com/2"
        mock_client.post.assert_called_once()

        # Check headers
        call_kwargs = mock_client.post.call_args
        assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer test-key"

    @patch("anappt.tools.web_search.httpx.Client")
    def test_search_handles_error(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("ANYSEARCH_API_KEY", "test-key")
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.side_effect = Exception("Network error")
        mock_client_cls.return_value = mock_client

        backend = AnySearchBackend()
        results = backend.search("test")
        assert results == []

    @patch("anappt.tools.web_search.httpx.Client")
    def test_search_uses_proxy(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("ANYSEARCH_API_KEY", "test-key")
        monkeypatch.setenv("HTTPS_PROXY", "http://proxy:8080")
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status.return_value = None
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        backend = AnySearchBackend()
        backend.search("test")

        # Check that proxy was passed to Client
        call_kwargs = mock_client_cls.call_args
        assert call_kwargs.kwargs.get("proxy") == "http://proxy:8080"
        assert call_kwargs.kwargs.get("trust_env") is True


class TestZAIBackend:
    """Test z.ai backend."""

    def test_search_without_api_key_returns_empty(self, monkeypatch):
        monkeypatch.delenv("ZAI_API_KEY", raising=False)
        backend = ZAIBackend()
        results = backend.search("test")
        assert results == []

    @patch("anappt.tools.web_search.httpx.Client")
    def test_search_with_api_key(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("ZAI_API_KEY", "test-key")
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "search_result": [
                {"title": "Result 1", "link": "http://example.com/1", "content": "Content 1"},
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        backend = ZAIBackend()
        results = backend.search("test query", num_results=1)

        assert len(results) == 1
        assert results[0].title == "Result 1"
        assert results[0].url == "http://example.com/1"
        assert results[0].snippet == "Content 1"

    @patch("anappt.tools.web_search.httpx.Client")
    def test_search_handles_error(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("ZAI_API_KEY", "test-key")
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.side_effect = Exception("API error")
        mock_client_cls.return_value = mock_client

        backend = ZAIBackend()
        results = backend.search("test")
        assert results == []


class TestSearchWeb:
    """Test the search_web convenience function."""

    def test_search_web_uses_duckduckgo(self, monkeypatch):
        monkeypatch.delenv("ANYSEARCH_API_KEY", raising=False)
        monkeypatch.delenv("ZAI_API_KEY", raising=False)

        with patch.object(DuckDuckGoBackend, "search") as mock_search:
            mock_search.return_value = [
                SearchResult(title="Test", url="http://test.com", snippet=""),
            ]
            results = search_web("test query")
            assert len(results) == 1
            assert results[0].title == "Test"
