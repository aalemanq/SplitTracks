#!/usr/bin/env python3
"""Split Tracks desktop launcher — starts server and opens browser."""

import os
import sys
import time
import webbrowser
import threading
from pathlib import Path

WEB_APP_DIR = Path(__file__).resolve().parent
os.chdir(str(WEB_APP_DIR))

ROOT = WEB_APP_DIR.parent
sys.path.insert(0, str(ROOT))

import uvicorn

WEB_HOST = os.environ.get("SPLITTRACKS_HOST", "127.0.0.1")
WEB_PORT = int(os.environ.get("SPLITTRACKS_PORT", "8745"))


def open_browser():
    time.sleep(1.5)
    webbrowser.open(f"http://{WEB_HOST}:{WEB_PORT}")


if __name__ == "__main__":
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run(
        "server:app",
        host=WEB_HOST,
        port=WEB_PORT,
        log_level="info",
        reload=False,
    )
