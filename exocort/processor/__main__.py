"""Module entrypoint for the processor package.

The processor runs in watch mode by default so the main loop can stay alive
continuously, matching the original design goal. A small compatibility parser
is kept here so existing flags still work without needing a separate module.
"""

from __future__ import annotations



import logging
import multiprocessing
import signal
import sys

from exocort import settings
from .config import load_app_config
from .engine import ProcessorConfig, _l1_worker, _l2_worker, _l3_worker, _l4_worker

def main() -> None:
    logging.basicConfig(
        level=settings.log_level(),
        format="%(asctime)s | %(levelname)s | %(processName)s | %(name)s | %(message)s",
    )

    app_config = load_app_config()

    processor_config = ProcessorConfig(
        vault_dir=settings.processor_vault_dir(),
        out_dir=settings.processor_out_dir(),
        state_dir=settings.processor_state_dir(),
        poll_interval_seconds=settings.processor_poll_interval_seconds(),
        l1_trigger_threshold=settings.processor_l1_trigger_threshold(),
        l2_trigger_threshold=settings.processor_l2_trigger_threshold(),
        l3_trigger_threshold=settings.processor_l3_trigger_threshold(),
        l4_enabled=settings.processor_l4_enabled(),
        l4_interval_hours=settings.processor_l4_interval_hours(),
        dry_run=False, # Or add a setting for this
    )

    semaphore = multiprocessing.Semaphore(settings.processor_max_concurrent_tasks())

    workers = [_l1_worker, _l2_worker, _l3_worker, _l4_worker]
    processes = []

    for worker_func in workers:
        process = multiprocessing.Process(
            target=worker_func,
            args=(processor_config, app_config, semaphore)
        )
        processes.append(process)
        process.start()
        logging.info(f"Started worker: {worker_func.__name__}")

    def shutdown(signum, frame):
        logging.info("Shutting down workers...")
        for p in processes:
            p.terminate()
        for p in processes:
            p.join()
        logging.info("Shutdown complete.")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    for p in processes:
        p.join()


if __name__ == "__main__":
    main()
