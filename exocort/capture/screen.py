from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

import mss
import mss.tools
import requests

import settings

try:
    import pywinctl
except ImportError:
    pywinctl = None


@dataclass(frozen=True)
class ScreenSettings:
    enabled: bool
    fps: float
    save_png: bool
    out_dir: Path
    request_timeout_s: float
    frame_url: str
    prompt_permission: bool

    @classmethod
    def from_env(cls) -> "ScreenSettings":
        return cls(
            enabled=settings.screen_capture_enabled(),
            fps=settings.screen_capture_fps(),
            save_png=settings.screen_capture_save_png(),
            out_dir=settings.screen_capture_out_dir(),
            request_timeout_s=settings.screen_capture_request_timeout_s(),
            frame_url=settings.collector_frame_url(),
            prompt_permission=settings.screen_capture_prompt_permission(),
        )


@dataclass(frozen=True)
class RunningWindow:
    window_id: int
    owner_name: str
    owner_pid: int
    title: str
    x: float
    y: float
    width: float
    height: float

    def to_dict(self) -> dict[str, str | int | float]:
        return asdict(self)


@dataclass(frozen=True)
class CaptureRegion:
    mode: str
    source: str
    display_id: int | None
    x: float
    y: float
    width: float
    height: float

    def to_dict(self) -> dict[str, str | int | float | None]:
        return asdict(self)


@dataclass(frozen=True)
class DisplayBounds:
    display_id: int
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class CapturedFrame:
    frame_id: str
    png_bytes: bytes
    width: int
    height: int
    content_hash: str
    app: dict[str, object]
    window: dict[str, object] | None
    capture: dict[str, object]
    permissions: dict[str, object]


def capture_frame(prompt_permission: bool = False) -> CapturedFrame:
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
    app_name, bundle_id, pid = _frontmost_app()
    return CapturedFrame(
        frame_id=uuid4().hex,
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
    def __init__(self, cfg: ScreenSettings):
        self.cfg = cfg
        self.logger = logging.getLogger("screen_capture")
        self.last_frame_hash: str | None = None

    def run(self) -> None:
        if not self.cfg.enabled:
            self.logger.info(
                "Screen capture disabled (set SCREEN_CAPTURE_ENABLED=1 to enable)."
            )
            return

        interval = 1.0 / self.cfg.fps
        if self.cfg.save_png:
            self.cfg.out_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info(
            "Starting screen capture | fps=%.2f",
            self.cfg.fps,
        )

        while True:
            started = time.time()
            try:
                frame = capture_frame(prompt_permission=self.cfg.prompt_permission)
            except Exception:
                self.logger.exception("Screen capture failed")
                self._sleep_remaining(interval, started)
                continue
            if frame.content_hash == self.last_frame_hash:
                self._sleep_remaining(interval, started)
                continue

            self.last_frame_hash = frame.content_hash

            if self.cfg.save_png:
                out_path = self.cfg.out_dir / f"{frame.frame_id}.png"
                out_path.write_bytes(frame.png_bytes)

            self._upload_frame(frame)
            self._sleep_remaining(interval, started)

    def _upload_frame(self, frame: CapturedFrame) -> None:
        try:
            files = {"file": (f"{frame.frame_id}.png", frame.png_bytes, "image/png")}
            data = {
                "frame_id": frame.frame_id,
                "width": str(frame.width),
                "height": str(frame.height),
                "hash": frame.content_hash,
                "app": json.dumps(frame.app, ensure_ascii=False),
                "capture": json.dumps(frame.capture, ensure_ascii=False),
                "permissions": json.dumps(frame.permissions, ensure_ascii=False),
            }
            if frame.window is not None:
                data["window"] = json.dumps(frame.window, ensure_ascii=False)

            resp = requests.post(
                self.cfg.frame_url,
                files=files,
                data=data,
                timeout=self.cfg.request_timeout_s,
            )
            if resp.status_code >= 300:
                self.logger.warning(
                    "Frame upload rejected | status=%d | body=%s",
                    resp.status_code,
                    resp.text[:200],
                )
        except Exception:
            self.logger.exception("Frame upload failed")

    @staticmethod
    def _sleep_remaining(interval: float, started: float) -> None:
        sleep_for = interval - (time.time() - started)
        if sleep_for > 0:
            time.sleep(sleep_for)


def _frontmost_app() -> tuple[str, str, int]:
    """Cross-platform: app name, bundle_id (empty), pid for the active window."""
    if pywinctl is None:
        return "", "", 0
    try:
        win = pywinctl.getActiveWindow()
        if win is None:
            return "", "", 0
        name = win.getAppName() or win.title or ""
        pid = getattr(win, "getPID", lambda: None)()
        pid = int(pid) if pid is not None else 0
        return (name or "").strip(), "", pid
    except Exception:
        return "", "", 0


def main() -> None:
    logging.basicConfig(
        level=settings.screen_capture_log_level(),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    cfg = ScreenSettings.from_env()
    ScreenCapture(cfg).run()


if __name__ == "__main__":
    main()
