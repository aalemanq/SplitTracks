#!/usr/bin/env python3
"""Split Tracks desktop launcher — starts server and opens browser."""

import os
import sys
import time
import webbrowser
import threading
from pathlib import Path

import uvicorn

FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(BASE_DIR))

sys.path.insert(0, str(Path(__file__).resolve().parent))
from server import app as server_app  # noqa: E402

WEB_HOST = os.environ.get("SPLITTRACKS_HOST", "127.0.0.1")
WEB_PORT = int(os.environ.get("SPLITTRACKS_PORT", "8745"))


def open_browser():
    time.sleep(1.5)
    webbrowser.open(f"http://{WEB_HOST}:{WEB_PORT}")


if __name__ == "__main__":
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run(
        server_app,
        host=WEB_HOST,
        port=WEB_PORT,
        log_level="info",
        reload=False,
    )
