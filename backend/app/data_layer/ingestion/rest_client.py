"""
Generic async REST client with bounded concurrency and basic rate-limit
(HTTP 429) backoff, shared by exchange source implementations.
"""
import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


class RestClient:
    """Thin wrapper around httpx.AsyncClient with a concurrency semaphore."""

    def __init__(self, base_url: str, max_concurrency: int = 10, timeout: float = 10.0):
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def get(self, path: str, params: dict | None = None, max_retries: int = 3) -> httpx.Response:
        async with self._semaphore:
            for attempt in range(max_retries):
                response = await self._client.get(path, params=params)
                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", "1"))
                    logger.warning(f"Rate limited on {path}, retrying after {retry_after}s")
                    await asyncio.sleep(retry_after)
                    continue
                response.raise_for_status()
                return response
            response.raise_for_status()
            return response

    async def close(self):
        await self._client.aclose()
