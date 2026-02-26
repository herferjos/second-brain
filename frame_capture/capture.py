import time
from pathlib import Path

import mss
from PIL import Image


def capture_frame(output_dir: Path, idx: int, monitor_index: int = 1) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    with mss.mss() as sct:
        monitor = sct.monitors[monitor_index]
        frame = sct.grab(monitor)
        img = Image.frombytes("RGB", frame.size, frame.rgb)
        path = output_dir / f"frame_{idx:04d}.png"
        img.save(path)
        return path


def capture_loop(
    output_dir: Path,
    num_frames: int = 5,
    delay_s: float = 1.0,
    monitor_index: int = 1,
) -> list[Path]:
    captured: list[Path] = []
    for idx in range(num_frames):
        path = capture_frame(output_dir=output_dir, idx=idx, monitor_index=monitor_index)
        captured.append(path)
        print(f"Captured {path}")
        if idx < num_frames - 1:
            time.sleep(delay_s)
    return captured
