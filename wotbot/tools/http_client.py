import json
import logging
from typing import Dict, Any, Optional
from urllib.parse import urlparse

import requests

from ..config import settings

log = logging.getLogger(__name__)


REDACT_HEADERS = {"authorization", "proxy-authorization", "x-api-key"}


def _redact_headers(headers: Optional[Dict[str, str]]) -> Dict[str, str]:
    if not headers:
        return {}
    out = {}
    for k, v in headers.items():
        if k.lower() in REDACT_HEADERS:
            out[k] = "<redacted>"
        else:
            out[k] = v
    return out


def _domain_allowed(url: str) -> bool:
    allow = settings.allow_http_domains
    if not allow:
        return False
    if allow == ("*",):
        return True
    netloc = urlparse(url).netloc.lower()
    return any(netloc.endswith(d.lower()) or netloc == d.lower() for d in allow)


def http_request(method: str, url: str, headers: Optional[Dict[str, str]] = None, params: Optional[Dict[str, str]] = None, body: Any = None) -> Dict[str, Any]:
    method = method.upper()
    if method not in {"GET", "POST", "PUT", "DELETE"}:
        return {"ok": False, "error": f"Unsupported method {method}"}
    if not _domain_allowed(url):
        return {"ok": False, "error": f"Domain not allowed for URL: {url}"}

    safe_headers = headers or {}
    log.info("HTTP tool %s %s headers=%s params=%s", method, url, _redact_headers(safe_headers), params)

    try:
        resp = requests.request(
            method,
            url,
            headers=safe_headers,
            params=params,
            json=body if isinstance(body, (dict, list)) else None,
            data=None if isinstance(body, (dict, list)) else (body if body is not None else None),
            timeout=settings.http_timeout_sec,
        )
    except requests.RequestException as e:
        return {"ok": False, "error": str(e)}

    content_type = resp.headers.get("content-type", "")
    data: Any
    if "application/json" in content_type:
        try:
            data = resp.json()
        except ValueError:
            data = resp.text[:4000]
    else:
        data = resp.text[:4000]

    return {
        "ok": True,
        "status": resp.status_code,
        "headers": _redact_headers(dict(resp.headers)),
        "data": data,
    }

