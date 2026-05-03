"""Async NSE HTTP client.

NSE blocks bare requests — needs browser headers AND cookies seeded by hitting
the homepage first. Cookies (`nsit`, `nseappid`, `bm_*`) expire, so we re-seed
on a TTL or after a 401/403.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from .cache import JsonFileCache

NSE_HOME = "https://www.nseindia.com/"
NSE_API_BASE = "https://www.nseindia.com/api"
NSE_WARMUP_PATHS = ("/", "/get-quotes/equity?symbol=TCS")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

_CLIENT_HINTS = {
    "Sec-Ch-Ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}

NAV_HEADERS = {
    "User-Agent": _UA,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    **_CLIENT_HINTS,
}

API_HEADERS = {
    "User-Agent": _UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "X-Requested-With": "XMLHttpRequest",
    **_CLIENT_HINTS,
}


class NSEError(RuntimeError):
    """Raised when NSE returns something we can't recover from."""


class NSEClient:
    def __init__(
        self,
        *,
        timeout: float = 15.0,
        cookie_ttl: float = 600.0,
        cache: Optional[JsonFileCache] = None,
        cache_ttl: float = 60.0,
    ) -> None:
        self._client = httpx.AsyncClient(
            headers=API_HEADERS,
            timeout=timeout,
            follow_redirects=True,
        )
        self._cookie_ttl = cookie_ttl
        self._cookie_at: float = 0.0
        self._lock = asyncio.Lock()
        self._cache = cache
        self._cache_ttl = cache_ttl

    async def __aenter__(self) -> "NSEClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _ensure_session(self) -> None:
        async with self._lock:
            fresh = (time.time() - self._cookie_at) < self._cookie_ttl
            if fresh and self._client.cookies:
                return
            # Warm-up: hit homepage with navigation headers, then a deeper page
            # so the API treats us as same-origin XHR with a real referer chain.
            for path in NSE_WARMUP_PATHS:
                url = NSE_HOME.rstrip("/") + path
                r = await self._client.get(url, headers=NAV_HEADERS)
                if r.status_code != 200:
                    raise NSEError(
                        f"NSE session warm-up GET {url} returned {r.status_code} "
                        f"(likely anti-bot block — try from an Indian IP, or install "
                        f"`curl_cffi` for browser-grade TLS fingerprinting)."
                    )
            if not self._client.cookies:
                raise NSEError("NSE warm-up returned no cookies — being blocked?")
            self._cookie_at = time.time()

    async def get_json(
        self, path: str, *, retries: int = 2, cache_ttl: Optional[float] = None
    ) -> Any:
        cache_key = f"GET {path}"
        if self._cache is not None:
            cached = self._cache.get(cache_key, ttl=cache_ttl or self._cache_ttl)
            if cached is not None:
                return cached

        await self._ensure_session()
        url = f"{NSE_API_BASE}/{path.lstrip('/')}"
        last_err: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                r = await self._client.get(url)
                if r.status_code in (401, 403):
                    self._cookie_at = 0.0
                    self._client.cookies.clear()
                    await self._ensure_session()
                    continue
                if r.status_code == 429:
                    await asyncio.sleep(2.0 * (attempt + 1))
                    continue
                r.raise_for_status()
                payload = r.json()
                if self._cache is not None:
                    self._cache.set(cache_key, payload)
                return payload
            except (httpx.HTTPError, ValueError) as e:
                last_err = e
                await asyncio.sleep(0.5 * (attempt + 1))
        raise NSEError(f"GET {url} failed after {retries + 1} attempts: {last_err}")


def default_cache() -> JsonFileCache:
    return JsonFileCache(Path(".cache") / "nse")
