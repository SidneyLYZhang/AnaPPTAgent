"""Web fetch module using Jina Reader API.

Reads web page content through the Jina Reader service (r.jina.ai).
Requires JINA_API_KEY environment variable.
"""

from __future__ import annotations

import os

import httpx


def is_available() -> bool:
    """Check if the Web Fetch tool is available.

    The tool requires JINA_API_KEY to be set.

    Returns:
        True if JINA_API_KEY is configured.
    """
    return bool(os.environ.get("JINA_API_KEY"))


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
    api_key = os.environ.get("JINA_API_KEY")
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
