from __future__ import annotations

import argparse
import multiprocessing
from pathlib import Path
import threading
from typing import Any

from dotenv import load_dotenv

from exocort.config import ExocortSettings, load_config
from exocort.logs import configure_logging, get_logger

DEFAULT_CONFIG_PATH = Path("config.yaml")
log = get_logger("runner")


def _run_service(target: Any, log_level: str, *args: Any) -> None:
    configure_logging(log_level)
    log.debug("starting service target=%s", getattr(target, "__name__", repr(target)))
    target(*args)


def run(config: ExocortSettings) -> None:
    services: list[multiprocessing.Process] = []
    threads: list[threading.Thread] = []
    capturer = config.capturer
    processor = config.processor

    if capturer.audio.enabled:
        from exocort.capturer.audio.capture import audio_loop

        services.append(
            multiprocessing.Process(
                target=_run_service,
                args=(audio_loop, config.log_level, capturer.audio),
                name="audio-capturer",
            )
        )

    if capturer.screen.enabled:
        from exocort.capturer.screen.capture import screenshot_loop

        threads.append(
            threading.Thread(
                target=screenshot_loop,
                args=(capturer.screen,),
                name="screen-capturer",
            )
        )

    if processor.ocr.enabled or processor.asr.enabled or processor.notes.enabled:
        from exocort.processor.service import processing_loop

        services.append(
            multiprocessing.Process(
                target=_run_service,
                args=(processing_loop, config.log_level, config),
                name="file-processor",
            )
        )

    if not services and not threads:
        log.info("no services enabled, nothing to run.")
        return

    for service in services:
        service.start()
        log.info("started %s pid=%s", service.name, service.pid)
    for thread in threads:
        thread.start()
        log.info("started %s thread", thread.name)

    log.info(
        "running %s service(s) with log_level=%s",
        len(services) + len(threads),
        config.log_level,
    )

    for service in services:
        service.join()
    for thread in threads:
        thread.join()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Exocort capturers from a YAML config.")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to YAML config file (default: {DEFAULT_CONFIG_PATH})",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    config = load_config(args.config)
    configure_logging(config.log_level)
    log.debug("loaded config from %s", args.config.expanduser().resolve())
    run(config)


if __name__ == "__main__":
    main()
