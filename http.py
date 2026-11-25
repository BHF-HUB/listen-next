"""Shared HTTP session: polite delays, retries, a normal browser-ish User-Agent."""
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 AudiobookQueue/1.0"
)

_session = None
_last_call = {}


def session():
    global _session
    if _session is None:
        s = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "POST"),
        )
        s.mount("https://", HTTPAdapter(max_retries=retry))
        s.headers.update({"User-Agent": USER_AGENT})
        _session = s
    return _session


def throttle(host, min_interval=0.4):
    """Wait so we never hit the same host faster than min_interval seconds."""
    now = time.monotonic()
    wait = _last_call.get(host, 0) + min_interval - now
    if wait > 0:
        time.sleep(wait)
    _last_call[host] = time.monotonic()


def get(url, host_key=None, min_interval=0.4, **kw):
    throttle(host_key or url.split("/")[2], min_interval)
    kw.setdefault("timeout", 30)
    return session().get(url, **kw)


def post(url, host_key=None, min_interval=0.4, **kw):
    throttle(host_key or url.split("/")[2], min_interval)
    kw.setdefault("timeout", 30)
    return session().post(url, **kw)
