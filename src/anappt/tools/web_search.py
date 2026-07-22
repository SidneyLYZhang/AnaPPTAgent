"""Web search module for AnaPPTAgent.

Supports three backends with automatic selection based on API keys:
1. AnySearch (requires ANYSEARCH_API_KEY)
2. z.ai (requires ZAI_API_KEY)
3. DuckDuckGo (default, no key required)

All backends support system proxy via environment variables.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any

import httpx
from pydantic import BaseModel

from anappt.io.config import ModelsConfig, WebSearchConfig


class SearchResult(BaseModel):
    """A single web search result."""

    title: str
    url: str
    snippet: str = ""


class SearchBackend(StrEnum):
    """Available search backends."""

    DUCKDUCKGO = "duckduckgo"
    ANYSEARCH = "anysearch"
    ZAI = "zai"


# Module-level config injected from ModelsConfig (env vars still take precedence)
_config: WebSearchConfig | None = None


def configure_from_models_config(models_config: ModelsConfig) -> None:
    """Inject web search config from the global ModelsConfig.

    Env vars (ANYSEARCH_API_KEY, ZAI_API_KEY, WEB_SEARCH_BACKEND) always
    take precedence over the injected yaml config.

    Args:
        models_config: The resolved global ModelsConfig.
    """
    global _config
    _config = models_config.web_search


class SearchBackendBase(ABC):
    """Abstract base class for search backends."""

    @abstractmethod
    def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        """Execute a web search.

        Args:
            query: Search query string.
            num_results: Maximum number of results to return.

        Returns:
            List of SearchResult objects.
        """
        ...

    def _get_proxy(self) -> str | None:
        """Get proxy URL from environment variables.

        Returns:
            Proxy URL string or None.
        """
        return (
            os.environ.get("HTTPS_PROXY")
            or os.environ.get("HTTP_PROXY")
            or os.environ.get("ALL_PROXY")
        )


def get_backend() -> SearchBackend:
    """Determine which search backend to use.

    Priority for backend choice:
    1. WEB_SEARCH_BACKEND env var (if set to a valid value)
    2. web_search.backend from injected ModelsConfig (yaml)
    3. Auto-select based on available API keys (env > yaml)

    If an explicit backend's key is missing, fall back to DuckDuckGo with
    a warning.

    Returns:
        SearchBackend enum value.
    """
    # Resolve effective API keys (env > yaml)
    anysearch_key = os.environ.get("ANYSEARCH_API_KEY") or (
        _config.anysearch_api_key if _config else None
    )
    zai_key = os.environ.get("ZAI_API_KEY") or (
        _config.zai_api_key if _config else None
    )

    # Resolve explicit backend preference (env > yaml)
    preference = os.environ.get("WEB_SEARCH_BACKEND", "").lower().strip()
    if not preference and _config and _config.backend:
        preference = _config.backend.lower().strip()

    if preference:
        if preference == "duckduckgo":
            return SearchBackend.DUCKDUCKGO
        if preference == "anysearch":
            if anysearch_key:
                return SearchBackend.ANYSEARCH
            print(
                "⚠ web_search.backend=anysearch but no API key available; "
                "falling back to DuckDuckGo"
            )
            return SearchBackend.DUCKDUCKGO
        if preference == "zai":
            if zai_key:
                return SearchBackend.ZAI
            print(
                "⚠ web_search.backend=zai but no API key available; "
                "falling back to DuckDuckGo"
            )
            return SearchBackend.DUCKDUCKGO

    # No explicit preference: auto-select based on available keys
    if anysearch_key and zai_key:
        return SearchBackend.ANYSEARCH  # default to AnySearch when both available
    if anysearch_key:
        return SearchBackend.ANYSEARCH
    if zai_key:
        return SearchBackend.ZAI
    return SearchBackend.DUCKDUCKGO


class DuckDuckGoBackend(SearchBackendBase):
    """DuckDuckGo search backend using the ddgs library.

    No API key required. Free but rate-limited.
    """

    def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        """Search using DuckDuckGo.

        Args:
            query: Search query string.
            num_results: Maximum number of results.

        Returns:
            List of SearchResult objects.
        """
        try:
            from ddgs import DDGS
        except ImportError:
            return []

        proxy = self._get_proxy()
        kwargs: dict[str, Any] = {}
        if proxy:
            kwargs["proxy"] = proxy

        results: list[SearchResult] = []
        try:
            with DDGS(**kwargs) as ddgs:
                for item in ddgs.text(query, max_results=num_results):
                    results.append(
                        SearchResult(
                            title=item.get("title", ""),
                            url=item.get("href", item.get("url", "")),
                            snippet=item.get("body", item.get("snippet", "")),
                        )
                    )
        except Exception:
            pass
        return results


class AnySearchBackend(SearchBackendBase):
    """AnySearch API backend.

    Requires ANYSEARCH_API_KEY environment variable.
    """

    API_URL = "https://www.anysearch.com/api/search"

    def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        """Search using AnySearch API.

        Args:
            query: Search query string.
            num_results: Maximum number of results.

        Returns:
            List of SearchResult objects.
        """
        api_key = os.environ.get("ANYSEARCH_API_KEY") or (
            _config.anysearch_api_key if _config else None
        ) or ""
        if not api_key:
            return []

        proxy = self._get_proxy()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {"query": query, "num_results": num_results}

        try:
            with httpx.Client(trust_env=True, proxy=proxy, timeout=30) as client:
                response = client.post(self.API_URL, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except Exception:
            return []

        results: list[SearchResult] = []
        for item in data.get("results", []):
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", item.get("link", "")),
                    snippet=item.get("snippet", item.get("description", "")),
                )
            )
        return results


class ZAIBackend(SearchBackendBase):
    """z.ai (Zhipu) search backend.

    Requires ZAI_API_KEY environment variable.
    Uses the Zhipu API for web search.
    """

    API_URL = "https://open.bigmodel.cn/api/paas/v4/web_search"

    def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        """Search using z.ai API.

        Args:
            query: Search query string.
            num_results: Maximum number of results.

        Returns:
            List of SearchResult objects.
        """
        api_key = os.environ.get("ZAI_API_KEY") or (
            _config.zai_api_key if _config else None
        ) or ""
        if not api_key:
            return []

        proxy = self._get_proxy()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "search_engine": {"search_query": query, "count": num_results},
        }

        try:
            with httpx.Client(trust_env=True, proxy=proxy, timeout=30) as client:
                response = client.post(self.API_URL, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except Exception:
            return []

        results: list[SearchResult] = []
        for item in data.get("search_result", []):
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", item.get("url", "")),
                    snippet=item.get("content", item.get("snippet", "")),
                )
            )
        return results


# Backend registry
_BACKENDS: dict[SearchBackend, type[SearchBackendBase]] = {
    SearchBackend.DUCKDUCKGO: DuckDuckGoBackend,
    SearchBackend.ANYSEARCH: AnySearchBackend,
    SearchBackend.ZAI: ZAIBackend,
}


def get_backend_instance(backend: SearchBackend | None = None) -> SearchBackendBase:
    """Get an instance of the specified or auto-selected search backend.

    Args:
        backend: Specific backend to use. If None, auto-selects.

    Returns:
        SearchBackendBase instance.
    """
    if backend is None:
        backend = get_backend()
    backend_class = _BACKENDS[backend]
    return backend_class()


def search_web(query: str, num_results: int = 5) -> list[SearchResult]:
    """Execute a web search using the best available backend.

    Automatically selects the backend based on available API keys.

    Args:
        query: Search query string.
        num_results: Maximum number of results to return.

    Returns:
        List of SearchResult objects.
    """
    backend = get_backend_instance()
    return backend.search(query, num_results)
