"""Web fetch module using Jina Reader API.

Reads web page content through the Jina Reader service (r.jina.ai).
Requires JINA_API_KEY environment variable.
"""

from __future__ import annotations

import os

import httpx

from anappt.io.config import ModelsConfig, WebFetchConfig

# Module-level config injected from ModelsConfig (env vars still take precedence)
_config: WebFetchConfig | None = None


def configure_from_models_config(models_config: ModelsConfig) -> None:
    """Inject web fetch config from the global ModelsConfig.

    Env var JINA_API_KEY always takes precedence over the injected yaml config.

    Args:
        models_config: The resolved global ModelsConfig.
    """
    global _config
    _config = models_config.web_fetch


def is_available() -> bool:
    """Check if the Web Fetch tool is available.

    The tool requires JINA_API_KEY (env var or yaml ``web_fetch.jina_api_key``)
    to be set.

    Returns:
        True if a JINA_API_KEY is configured in either env or yaml.
    """
    return bool(
        os.environ.get("JINA_API_KEY")
        or (_config.jina_api_key if _config else None)
    )


def fetch_url(url: str) -> str:
    """Fetch the content of a web page using Jina Reader API.

    Makes a request to https://r.jina.ai/{url} with the JINA_API_KEY
    for authentication.

    Args:
        url: The URL to fetch.

    Returns:
        The page content as a string (Markdown format).

    Raises:
        RuntimeError: If JINA_API_KEY is not configured.
        httpx.HTTPStatusError: If the request fails.
    """
    api_key = os.environ.get("JINA_API_KEY") or (
        _config.jina_api_key if _config else None
    )
    if not api_key:
        raise RuntimeError("JINA_API_KEY is not set. Web Fetch is unavailable.")

    jina_url = f"https://r.jina.ai/{url}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "text/markdown",
    }

    # Get proxy from environment
    proxy = (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("ALL_PROXY")
    )

    with httpx.Client(trust_env=True, proxy=proxy, timeout=60) as client:
        response = client.get(jina_url, headers=headers)
        response.raise_for_status()
        return response.text
