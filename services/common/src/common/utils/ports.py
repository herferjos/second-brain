from __future__ import annotations

import logging
import os
import signal
import subprocess

log = logging.getLogger("uvicorn.error")


def kill_processes_on_port(port: int) -> None:
    try:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        log.warning("lsof is not available; skipping port cleanup for %s", port)
        return

    pids = sorted({int(pid) for pid in result.stdout.split() if pid.isdigit()})
    if not pids:
        return

    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            continue
        except PermissionError:
            log.warning("Unable to kill process %s on port %s", pid, port)
