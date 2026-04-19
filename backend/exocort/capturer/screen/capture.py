from __future__ import annotations

from datetime import datetime
from pathlib import Path
import time

from PIL import ImageGrab

from exocort.config import ScreenSettings
from exocort.logs import get_logger

log = get_logger("screen")


def capture_screenshot() -> tuple[object, tuple[int, int]]:
    image = ImageGrab.grab()
    return image, image.size


def screenshot_loop(config: ScreenSettings) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    output_dir = config.output_dir
    log.info(
        "screen capture loop started interval=%ss output_dir=%s backend=%s",
        config.interval_seconds,
        output_dir,
        "pillow-imagegrab",
    )

    next_capture_at = time.monotonic()
    while True:
        loop_started_at = time.monotonic()
        lag_seconds = max(0.0, loop_started_at - next_capture_at)
        if lag_seconds:
            log.info("screen loop woke up %.2fs late", lag_seconds)

        grab_started_at = time.monotonic()
        image, size = capture_screenshot()
        grab_elapsed = time.monotonic() - grab_started_at

        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S%f")
        file_path = output_dir / f"{timestamp}.png"
        temp_path = output_dir / f".{timestamp}.png.tmp"

        write_started_at = time.monotonic()
        image.save(temp_path, format="PNG")
        temp_path.replace(file_path)
        write_elapsed = time.monotonic() - write_started_at
        file_size = file_path.stat().st_size

        loop_elapsed = time.monotonic() - loop_started_at
        next_capture_at = loop_started_at + config.interval_seconds
        sleep_seconds = max(0.0, next_capture_at - time.monotonic())
        log.info(
            "captured %s bytes -> %s size=%sx%s grab=%.2fs write=%.2fs loop=%.2fs next_sleep=%.2fs",
            file_size,
            file_path,
            size[0],
            size[1],
            grab_elapsed,
            write_elapsed,
            loop_elapsed,
            sleep_seconds,
        )
        if sleep_seconds:
            time.sleep(sleep_seconds)
