import os
import platform
import time
import psutil
from fastapi import APIRouter

router = APIRouter()

PROCESS_START = time.time()


@router.get("")
def health():
    p = psutil.Process(os.getpid())
    mem = p.memory_info()
    cpu_percent = p.cpu_percent(interval=0.0)
    return {
        "status": "ok",
        "pid": p.pid,
        "uptime_seconds": int(time.time() - PROCESS_START),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_percent": cpu_percent,
        "memory_rss": mem.rss,
    }

