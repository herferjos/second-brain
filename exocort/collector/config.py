"""Load collector routing from config.json."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EndpointConfig:
    url: str
    method: str = "POST"
    timeout: float = 30.0
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class CollectorConfig:
    audio: list[EndpointConfig] = field(default_factory=list)
    screen: list[EndpointConfig] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path | None = None) -> "CollectorConfig":
        if path is None:
            raw = os.getenv("COLLECTOR_CONFIG", "").strip() or "config.json"
            path = Path(raw)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            return cls()

        data = json.loads(path.read_text(encoding="utf-8"))

        def parse_endpoints(key: str) -> list[EndpointConfig]:
            block = data.get(key) or {}
            endpoints = block.get("endpoints") or []
            out = []
            for ep in endpoints:
                out.append(
                    EndpointConfig(
                        url=str(ep["url"]),
                        method=str(ep.get("method", "POST")).upper(),
                        timeout=float(ep.get("timeout", 30)),
                        headers=dict(ep.get("headers") or {}),
                    )
                )
            return out

        return cls(
            audio=parse_endpoints("audio"),
            screen=parse_endpoints("screen"),
        )
