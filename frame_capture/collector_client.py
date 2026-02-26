"""Send frame capture events to the collector. Content is stored under data/frame/."""
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import requests


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def send_frame_event(
    collector_events_url: str,
    frame_idx: int,
    markdown_text: str,
    image_path: Path | None = None,
    timeout_s: float = 30.0,
) -> dict | None:
    """POST a frame.capture event to the collector. Returns response json or None on failure."""
    event_id = uuid4().hex
    ts = _utc_now_iso()
    event = {
        "id": event_id,
        "ts": ts,
        "source": "frame_capture",
        "type": "frame.capture",
        "meta": {
            "text": markdown_text,
            "frame_idx": frame_idx,
        },
    }
    if image_path is not None:
        event["meta"]["image_path"] = str(image_path)
    try:
        r = requests.post(
            collector_events_url,
            json=event,
            timeout=timeout_s,
            headers={"Content-Type": "application/json"},
        )
        r.raise_for_status()
        out = r.json()
        print(f"Sent frame {frame_idx} to collector | event_id={event_id}")
        return out
    except Exception as e:
        print(f"Failed to send frame {frame_idx} to collector: {e}")
        return None
