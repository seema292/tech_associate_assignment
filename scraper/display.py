"""Make the program runnable on a Linux machine that has no screen.

The scraper needs a normal (non-headless) browser window. On Windows and macOS a
screen always exists. On Linux without one we start Xvfb, a virtual screen, and
point DISPLAY at it. The browser is still an ordinary browser; nothing is disguised.
"""

import atexit
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

VIRTUAL_DISPLAY_NUMBER = 99


def needs_virtual_display(headless: bool, platform: str = sys.platform, env=os.environ) -> bool:
    """True if a visible browser is wanted but this Linux machine has no display."""
    if headless or not platform.startswith("linux"):
        return False
    return not env.get("DISPLAY") and not env.get("WAYLAND_DISPLAY")


def start_virtual_display(wait_seconds: float = 10.0) -> bool:
    """Start Xvfb on :99 and set DISPLAY. Returns False if Xvfb is not installed or fails."""
    xvfb = shutil.which("Xvfb")
    if xvfb is None:
        return False
    display = f":{VIRTUAL_DISPLAY_NUMBER}"
    process = subprocess.Popen(
        [xvfb, display, "-screen", "0", "1280x1024x24", "-nolisten", "tcp"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    atexit.register(process.terminate)  # stop the virtual screen when the program ends

    # Xvfb is ready when its socket file appears.
    socket_file = Path(f"/tmp/.X11-unix/X{VIRTUAL_DISPLAY_NUMBER}")
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:  # Xvfb exited (for example, display already in use)
            return False
        if socket_file.exists():
            os.environ["DISPLAY"] = display
            return True
        time.sleep(0.1)
    process.terminate()
    return False
