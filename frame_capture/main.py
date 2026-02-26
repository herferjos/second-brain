import os
from pathlib import Path

from dotenv import load_dotenv

from capture import capture_loop
from collector_client import send_frame_event
from formatter import save_markdown
from ocr import load_ocr_model, ocr_image_to_markdown


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def run() -> None:
    load_dotenv()

    output_dir = Path(os.getenv("FRAME_CAPTURE_OUTPUT_DIR", "outputs")).expanduser()
    num_frames = _env_int("FRAME_CAPTURE_NUM_FRAMES", 10)
    delay_s = _env_float("FRAME_CAPTURE_DELAY_S", 1.0)
    monitor_index = _env_int("FRAME_CAPTURE_MONITOR_INDEX", 1)
    collector_events_url = (
        os.getenv("FRAME_CAPTURE_COLLECTOR_EVENTS_URL", "http://127.0.0.1:8787/events")
    ).strip()
    collector_timeout_s = _env_float("FRAME_CAPTURE_COLLECTOR_TIMEOUT_S", 30.0)

    print(
        "Starting frame capture | output_dir=%s | frames=%d | delay_s=%.2f | monitor=%d | collector=%s"
        % (output_dir, num_frames, delay_s, monitor_index, collector_events_url or "none")
    )
    images = capture_loop(
        output_dir=output_dir,
        num_frames=num_frames,
        delay_s=delay_s,
        monitor_index=monitor_index,
    )

    model, processor, device, dtype = load_ocr_model()
    print("OCR model loaded | device=%s" % device)
    for idx, image_path in enumerate(images):
        markdown = ocr_image_to_markdown(
            model=model,
            processor=processor,
            device=device,
            dtype=dtype,
            image_path=image_path,
        )
        if collector_events_url:
            send_frame_event(
                collector_events_url=collector_events_url,
                frame_idx=idx,
                markdown_text=markdown,
                image_path=image_path,
                timeout_s=collector_timeout_s,
            )
        else:
            save_markdown(output_dir=output_dir, frame_idx=idx, markdown_text=markdown)

    print("Frame OCR pipeline finished.")


if __name__ == "__main__":
    run()

