from __future__ import annotations

import threading
import time
from pathlib import Path

from exocort.logs import get_logger

log = get_logger("processor", "retention")


def schedule_file_deletion(path: Path, *, expired_in: int | bool, reason: str) -> None:
    if expired_in is False:
        log.info("keeping %s forever (%s)", path, reason)
        return
    if isinstance(expired_in, bool):
        raise ValueError("expired_in must be a non-negative integer or False.")
    if expired_in < 0:
        raise ValueError("expired_in must be greater than or equal to 0, or False to keep files.")
    if expired_in == 0:
        delete_file(path, reason=reason)
        return

    thread = threading.Thread(
        target=_delete_after_delay,
        args=(path, expired_in, reason),
        daemon=True,
        name=f"delete-{path.name}",
    )
    thread.start()


def delete_file(path: Path, *, reason: str) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except IsADirectoryError:
        log.warning("skipped deleting directory %s (%s)", path, reason)
        return
    except Exception as exc:
        log.warning("failed deleting %s (%s): %s", path, reason, exc)
        return

    log.info("deleted %s (%s)", path, reason)


def _delete_after_delay(path: Path, expired_in: int, reason: str) -> None:
    time.sleep(expired_in)
    delete_file(path, reason=reason)
