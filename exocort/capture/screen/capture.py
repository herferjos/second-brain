from __future__ import annotations

import hashlib
import json
import logging
import time
from uuid import uuid4

import mss
import mss.tools
import requests

from .app import frontmost_app
from .models import CaptureRegion, CapturedScreen, ScreenSettings


def capture_screen(prompt_permission: bool = False) -> CapturedScreen:
    """Capture one frame. content_hash is SHA-1 of PNG bytes (pixel-level identity)."""
    with mss.mss() as sct:
        monitors = sct.monitors
        monitor = monitors[1] if len(monitors) > 1 else monitors[0]
        screenshot = sct.grab(monitor)
        png_bytes = mss.tools.to_png(screenshot.rgb, screenshot.size)

    capture_region = CaptureRegion(
        mode="display",
        source="primary",
        display_id=0,
        x=float(monitor["left"]),
        y=float(monitor["top"]),
        width=float(monitor["width"]),
        height=float(monitor["height"]),
    )
    app_name, bundle_id, pid = frontmost_app()
    return CapturedScreen(
        screen_id=uuid4().hex,
        png_bytes=png_bytes,
        width=screenshot.width,
        height=screenshot.height,
        content_hash=hashlib.sha1(png_bytes).hexdigest(),
        app={"name": app_name, "bundle_id": bundle_id, "pid": pid},
        window=None,
        capture=capture_region.to_dict(),
        permissions={"screen_recording": True, "accessibility": False},
    )


class ScreenCapture:
    """Dedup: consecutive same hash skipped; same hash within dedup_window_s also skipped (no upload)."""

    def __init__(self, cfg: ScreenSettings):
        self.cfg = cfg
        self.logger = logging.getLogger("screen_capture")
        self.last_screen_hash: str | None = None
        self._recent_sent: dict[str, float] = {}

    def _recent_sent_prune(self) -> None:
        now = time.monotonic()
        window = self.cfg.dedup_window_s
        expired = [h for h, t in self._recent_sent.items() if (now - t) > window]
        for h in expired:
            del self._recent_sent[h]

    def _already_sent_recently(self, content_hash: str) -> bool:
        self._recent_sent_prune()
        return content_hash in self._recent_sent

    def run(self) -> None:
        if not self.cfg.enabled:
            self.logger.info(
                "Screen capture disabled (set SCREEN_CAPTURE_ENABLED=1 to enable)."
            )
            return

        interval = 1.0 / self.cfg.fps

        self.logger.info(
            "Starting screen capture | fps=%.2f | dedup_window_s=%.0f",
            self.cfg.fps,
            self.cfg.dedup_window_s,
        )

        while True:
            started = time.time()
            try:
                screen = capture_screen(prompt_permission=self.cfg.prompt_permission)
            except Exception:
                self.logger.exception("Screen capture failed")
                self._sleep_remaining(interval, started)
                continue
            if screen.content_hash == self.last_screen_hash:
                self._sleep_remaining(interval, started)
                continue
            if self._already_sent_recently(screen.content_hash):
                self._sleep_remaining(interval, started)
                continue

            self.last_screen_hash = screen.content_hash

            self._upload_screen(screen)
            self._recent_sent[screen.content_hash] = time.monotonic()
            self._sleep_remaining(interval, started)

    def _upload_screen(self, screen: CapturedScreen) -> None:
        try:
            files = {"file": (f"{screen.screen_id}.png", screen.png_bytes, "image/png")}
            data = {
                "screen_id": screen.screen_id,
                "width": str(screen.width),
                "height": str(screen.height),
                "hash": screen.content_hash,
                "app": json.dumps(screen.app, ensure_ascii=False),
                "capture": json.dumps(screen.capture, ensure_ascii=False),
                "permissions": json.dumps(screen.permissions, ensure_ascii=False),
            }
            if screen.window is not None:
                data["window"] = json.dumps(screen.window, ensure_ascii=False)

            resp = requests.post(
                self.cfg.screen_url,
                files=files,
                data=data,
                timeout=self.cfg.request_timeout_s,
            )
            if resp.status_code >= 300:
                self.logger.warning(
                    "Screen upload rejected | status=%d | body=%s",
                    resp.status_code,
                    resp.text[:200],
                )
        except Exception:
            self.logger.exception("Screen upload failed")

    @staticmethod
    def _sleep_remaining(interval: float, started: float) -> None:
        sleep_for = interval - (time.time() - started)
        if sleep_for > 0:
            time.sleep(sleep_for)
