"""HTTP request common functions — urllib.request 래퍼."""
from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from typing import Any, Dict, Optional, Union

log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 15


def request(
    url: str,
    *,
    data: Optional[Union[bytes, dict]] = None,
    headers: Optional[Dict[str, str]] = None,
    method: Optional[str] = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> bytes:
    """Perform an HTTP request and return the response body as bytes.

    If *data* is a dict it will be JSON-encoded automatically.
    """
    if isinstance(data, dict):
        data = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method or ("POST" if data else "GET"))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def request_json(
    url: str,
    *,
    data: Optional[Union[bytes, dict]] = None,
    headers: Optional[Dict[str, str]] = None,
    method: Optional[str] = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> Any:
    """Perform an HTTP request and return JSON-decoded response."""
    raw = request(url, data=data, headers=headers, method=method, timeout=timeout)
    return json.loads(raw)


def post_json(
    url: str,
    payload: dict,
    *,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> Any:
    """POST JSON data and return JSON-decoded response."""
    h = {"Content-Type": "application/json", **(headers or {})}
    return request_json(url, data=payload, headers=h, timeout=timeout)
