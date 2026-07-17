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
    """Determine which search backend to use based on available API keys.

    Priority:
    1. If ANYSEARCH_API_KEY is set, use AnySearch
    2. If ZAI_API_KEY is set, use z.ai
    3. If both are set, check WEB_SEARCH_BACKEND env var
    4. Otherwise, fall back to DuckDuckGo

    Returns:
        SearchBackend enum value.
    """
    has_anysearch = bool(os.environ.get("ANYSEARCH_API_KEY"))
    has_zai = bool(os.environ.get("ZAI_API_KEY"))

    if has_anysearch and has_zai:
        # Both configured, check explicit preference
        preference = os.environ.get("WEB_SEARCH_BACKEND", "").lower()
        if preference == "zai":
            return SearchBackend.ZAI
        return SearchBackend.ANYSEARCH  # default to AnySearch
    elif has_anysearch:
        return SearchBackend.ANYSEARCH
    elif has_zai:
        return SearchBackend.ZAI
    else:
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
        api_key = os.environ.get("ANYSEARCH_API_KEY", "")
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
        api_key = os.environ.get("ZAI_API_KEY", "")
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
