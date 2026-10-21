"""Shared HTTP layer: one session, per-host throttling, retry with backoff."""

from __future__ import annotations

import logging
import threading
import time
from urllib.parse import urlsplit

import requests

log = logging.getLogger("puckscrape")

# A realistic browser User-Agent. Sending the default "python-requests/x.x"
# is a common trigger for bot filtering -- Elite Prospects answers it with 403.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

# Minimum seconds between requests to a host. Be polite: these are free sites.
RATE_LIMITS: dict[str, float] = {
    "www.eliteprospects.com": 1.5,
    "moneypuck.com": 1.0,
    "peter-tanner.com": 1.0,
    "site.api.espn.com": 0.25,
    "site.web.api.espn.com": 0.25,
    # League and federation sites (puckscrape.leagues): HTML pages get 1 s, JSON APIs less.
    "www.collegehockeynews.com": 1.0,
    "www.eliteleague.co.uk": 1.0,
    "www.hokej.cz": 1.0,
    "www.penny-del.org": 1.0,
    "www.del-2.org": 1.0,
    "lscluster.hockeytech.com": 0.5,
    "www.shl.se": 0.5,
    "www.sdhl.se": 0.5,
    "liiga.fi": 0.5,
    "data.sihf.ch": 0.5,
    "tulospalvelu.leijonat.fi": 0.5,
    "hockeyallsvenskan.se": 0.5,
    "statistik.metalligaen.dk": 0.5,
}
DEFAULT_RATE_LIMIT = 0.1

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class PuckscrapeError(RuntimeError):
    """Base error for this package."""


class BlockedError(PuckscrapeError):
    """The site kept refusing us (403/429) after every retry."""


_session: requests.Session | None = None
_last_request: dict[str, float] = {}
_lock = threading.Lock()


def session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(HEADERS)
    return _session


def _throttle(host: str) -> None:
    interval = RATE_LIMITS.get(host, DEFAULT_RATE_LIMIT)
    with _lock:
        wait = _last_request.get(host, 0.0) + interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_request[host] = time.monotonic()


def get(
    url: str,
    *,
    params: dict | None = None,
    retries: int = 4,
    backoff: float = 2.0,
    retry_403: bool = False,
    timeout: float = 60,
) -> requests.Response:
    """GET with throttling and exponential backoff.

    ``retry_403`` treats 403 as a temporary block (Elite Prospects does this
    when it rate-limits you) instead of a hard failure.
    """
    return _request("GET", url, params=params, retries=retries, backoff=backoff,
                    retry_403=retry_403, timeout=timeout)


def post_json(url: str, body: dict, **kwargs) -> dict:
    """POST a JSON body (same throttling and retries as get) and decode the reply."""
    return _request("POST", url, json_body=body, **kwargs).json()


def _request(
    method: str,
    url: str,
    *,
    params: dict | None = None,
    json_body: dict | None = None,
    retries: int = 4,
    backoff: float = 2.0,
    retry_403: bool = False,
    timeout: float = 60,
) -> requests.Response:
    host = urlsplit(url).netloc
    statuses = RETRY_STATUSES | {403} if retry_403 else RETRY_STATUSES

    for attempt in range(retries + 1):
        _throttle(host)
        try:
            resp = session().request(method, url, params=params, json=json_body, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as e:
            if attempt == retries:
                raise
            wait = backoff * 2**attempt
            log.warning("%s on %s; retrying in %.0fs", type(e).__name__, url, wait)
            time.sleep(wait)
            continue

        if resp.status_code in statuses:
            if attempt == retries:
                if resp.status_code in (403, 429):
                    raise BlockedError(f"{resp.status_code} from {url} after {retries} retries")
                resp.raise_for_status()
            retry_after = resp.headers.get("Retry-After", "")
            wait = float(retry_after) if retry_after.isdigit() else backoff * 2**attempt
            log.warning("HTTP %s on %s; retrying in %.0fs", resp.status_code, url, wait)
            time.sleep(wait)
            continue

        resp.raise_for_status()
        return resp

    raise AssertionError("unreachable")


def get_json(url: str, **kwargs) -> dict:
    return get(url, **kwargs).json()
