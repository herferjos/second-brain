"""Forward received uploads to configured processing APIs."""

from __future__ import annotations

import logging
from typing import Any

import requests

from .config import EndpointConfig

log = logging.getLogger("collector.forward")


def forward_upload(
    endpoint: EndpointConfig,
    file_content: bytes,
    filename: str,
    content_type: str,
) -> tuple[bool, int, str]:
    """Send file to one endpoint. Returns (ok, status_code, full_body)."""
    files = {"file": (filename, file_content, content_type)}
    data: dict[str, str] = {}
    headers = dict(endpoint.headers)

    try:
        if endpoint.method == "POST":
            r = requests.post(
                endpoint.url,
                files=files,
                data=data,
                headers=headers,
                timeout=endpoint.timeout,
            )
        else:
            r = requests.request(
                endpoint.method,
                endpoint.url,
                files=files,
                data=data,
                headers=headers,
                timeout=endpoint.timeout,
            )
        body = r.text or ""
        if r.status_code >= 300:
            log.warning(
                "Forward rejected | url=%s | status=%d | body=%s",
                endpoint.url,
                r.status_code,
                body[:500],
            )
            return False, r.status_code, body
        log.info("Forwarded | url=%s | status=%d", endpoint.url, r.status_code)
        return True, r.status_code, body
    except Exception as e:
        log.exception("Forward failed | url=%s", endpoint.url)
        return False, 0, str(e)
