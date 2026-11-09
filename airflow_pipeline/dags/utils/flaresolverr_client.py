"""FlareSolverr Client with Rate Limiting and Exponential Backoff.

This module provides a robust HTTP client capable of bypassing Cloudflare
anti-bot protections using a dockerized FlareSolverr instance, with built-in
rate limiting and exponential backoff to handle HTTP 429 and connection issues.
"""

import json
import logging
import random
import time
import urllib.parse
from typing import Any, Dict, Optional
import requests

logger = logging.getLogger(__name__)


class FlareSolverrClient:
    """Client for routing requests through FlareSolverr to bypass Cloudflare,

    with fallback to direct HTTP requests and built-in rate-limiting.
    """

    def __init__(
        self,
        flaresolverr_url: str = "http://flaresolverr:8191/v1",
        timeout: int = 60,
        rate_limit_delay: float = 2.0,
        jitter_range: float = 1.0,
        max_retries: int = 5,
        base_backoff: float = 3.0,
    ):
        self.flaresolverr_url = flaresolverr_url
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        self.jitter_range = jitter_range
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.last_request_time = 0.0

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "application/json, text/plain, */*",
            }
        )

    def _apply_rate_limit(self) -> None:
        """Enforces minimum time between successive requests with random jitter."""
        now = time.time()
        elapsed = now - self.last_request_time
        jitter = random.uniform(0, self.jitter_range)
        target_delay = self.rate_limit_delay + jitter

        if elapsed < target_delay:
            sleep_time = target_delay - elapsed
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)

        self.last_request_time = time.time()

    def is_flaresolverr_available(self) -> bool:
        """Checks if the FlareSolverr service is reachable."""
        try:
            resp = self.session.get(self.flaresolverr_url.replace("/v1", ""), timeout=3)
            return resp.status_code in (200, 404, 405)
        except Exception:
            return False

    def request_via_flaresolverr(
        self,
        url: str,
        method: str = "GET",
        post_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Sends request through FlareSolverr proxy to solve Cloudflare challenge."""
        cmd = "request.post" if method.upper() == "POST" else "request.get"
        payload: Dict[str, Any] = {
            "cmd": cmd,
            "url": url,
            "maxTimeout": self.timeout * 1000,
        }
        if post_data and method.upper() == "POST":
            content_type = (headers or {}).get("Content-Type", "")
            if isinstance(post_data, dict):
                if "json" in content_type.lower():
                    payload["postData"] = json.dumps(post_data)
                else:
                    # Default for form submissions like Realtor.ca API
                    payload["postData"] = urllib.parse.urlencode(post_data)
            else:
                payload["postData"] = post_data
        if headers:
            payload["headers"] = headers

        resp = self.session.post(
            self.flaresolverr_url,
            json=payload,
            timeout=self.timeout + 15,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "ok":
            raise RuntimeError(f"FlareSolverr returned error status: {data.get('message')}")

        solution = data.get("solution", {})
        return {
            "status_code": solution.get("status", 200),
            "response": solution.get("response", ""),
            "cookies": solution.get("cookies", []),
            "headers": solution.get("headers", {}),
            "url": solution.get("url", url),
        }

    def direct_request(
        self,
        url: str,
        method: str = "GET",
        data: Optional[Any] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> requests.Response:
        """Sends direct HTTP request with user headers."""
        req_headers = self.session.headers.copy()
        if headers:
            req_headers.update(headers)

        if method.upper() == "POST":
            return self.session.post(
                url,
                data=data,
                json=json_data,
                headers=req_headers,
                timeout=self.timeout,
            )
        return self.session.get(
            url,
            params=data if isinstance(data, dict) else None,
            headers=req_headers,
            timeout=self.timeout,
        )

    def fetch(
        self,
        url: str,
        method: str = "GET",
        data: Optional[Any] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        prefer_flaresolverr: bool = False,
    ) -> Dict[str, Any]:
        """Fetches URL with rate limiting, FlareSolverr detection, and exponential backoff."""
        use_flaresolverr = prefer_flaresolverr and self.is_flaresolverr_available()

        for attempt in range(1, self.max_retries + 1):
            self._apply_rate_limit()

            try:
                if use_flaresolverr:
                    post_body = json_data or data
                    res = self.request_via_flaresolverr(url, method=method, post_data=post_body, headers=headers)
                    if res["status_code"] == 429:
                        raise requests.exceptions.HTTPError("429 Too Many Requests from FlareSolverr")
                    return res
                else:
                    resp = self.direct_request(url, method=method, data=data, json_data=json_data, headers=headers)

                    # Cloudflare challenge detected (403/503 with challenge keywords)
                    is_cloudflare = resp.status_code in (403, 503) and (
                        "cf-ray" in resp.headers or "cloudflare" in resp.text.lower()
                    )

                    if is_cloudflare:
                        logger.warning(f"Cloudflare detected at {url}. Attempting FlareSolverr bypass...")
                        if self.is_flaresolverr_available():
                            use_flaresolverr = True
                            continue

                    if resp.status_code == 429:
                        raise requests.exceptions.HTTPError(f"429 Too Many Requests: {resp.text[:100]}")

                    resp.raise_for_status()

                    return {
                        "status_code": resp.status_code,
                        "response": resp.text,
                        "cookies": [c.__dict__ for c in resp.cookies],
                        "headers": dict(resp.headers),
                        "url": resp.url,
                    }

            except (requests.exceptions.RequestException, RuntimeError) as err:
                logger.warning(
                    f"Attempt {attempt}/{self.max_retries} failed for {url}: {err}"
                )
                if attempt == self.max_retries:
                    logger.error(f"Exhausted all {self.max_retries} retries for {url}.")
                    raise

                # Exponential backoff with jitter: base * 2^(attempt-1) + jitter
                backoff_time = (self.base_backoff * (2 ** (attempt - 1))) + random.uniform(0.5, 2.0)
                logger.info(f"Backing off for {backoff_time:.2f}s before retry...")
                time.sleep(backoff_time)

        raise RuntimeError(f"Failed to fetch {url} after {self.max_retries} attempts")
