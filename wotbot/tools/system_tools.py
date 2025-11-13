import logging
import os
from typing import Dict, Any

import psutil

from ..config import settings

log = logging.getLogger(__name__)


def get_system_status() -> Dict[str, Any]:
    vm = psutil.virtual_memory()
    du = psutil.disk_usage("/")
    return {
        "ok": True,
        "cpu_percent": psutil.cpu_percent(interval=0.0),
        "memory": {
            "total": vm.total,
            "available": vm.available,
            "percent": vm.percent,
            "used": vm.used,
        },
        "disk": {
            "total": du.total,
            "used": du.used,
            "free": du.free,
            "percent": du.percent,
        },
        "uptime_seconds": psutil.boot_time(),
    }


def _safe_join(base: str, rel: str) -> str:
    base = os.path.abspath(base)
    candidate = os.path.abspath(os.path.join(base, rel))
    if not candidate.startswith(base + os.sep) and candidate != base:
        raise ValueError("Path outside allowed directory")
    return candidate


def read_log(path: str, lines: int = 200) -> Dict[str, Any]:
    try:
        full = _safe_join(settings.logs_dir, path or "app.log")
        if not os.path.exists(full):
            return {"ok": False, "error": f"Log not found: {path}"}
        out_lines = []
        with open(full, "r", encoding="utf-8", errors="ignore") as f:
            for line in f.readlines()[-lines:]:
                out_lines.append(line.rstrip("\n"))
        return {"ok": True, "path": path, "lines": out_lines}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def read_config(path: str) -> Dict[str, Any]:
    try:
        full = _safe_join(settings.config_dir, path)
        if not os.path.exists(full):
            return {"ok": False, "error": f"Config not found: {path}"}
        with open(full, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return {"ok": True, "path": path, "content": content[:8000]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def restart_self() -> Dict[str, Any]:
    # Safe restart signal: write a flag and exit after brief delay.
    try:
        flag_path = os.path.join(settings.logs_dir, "restart.flag")
        with open(flag_path, "w") as f:
            f.write("restart requested")
    except Exception:
        pass

    # Exit in a background thread to allow response to be sent first
    import threading, time, os

    def _exit_later():
        time.sleep(1.5)
        os._exit(3)

    threading.Thread(target=_exit_later, daemon=True).start()
    return {"ok": True, "message": "Restart scheduled"}

