"""Make the program runnable on a Linux machine that has no screen.

The scraper needs a normal (non-headless) browser window. On Windows and macOS a
screen always exists. On Linux without one we run the same command inside xvfb,
a virtual screen. The browser is still an ordinary browser; nothing is disguised.
"""

import os
import shutil
import sys


def needs_virtual_display(headless: bool, platform: str = sys.platform, env=os.environ) -> bool:
    """True if a visible browser is wanted but this Linux machine has no display."""
    if headless or not platform.startswith("linux"):
        return False
    return not env.get("DISPLAY") and not env.get("WAYLAND_DISPLAY")


def restart_under_xvfb() -> bool:
    """Re-run this same command inside xvfb. Only returns False if xvfb is missing.

    os.execvp replaces the current process, so on success this never returns.
    Inside xvfb the DISPLAY variable is set, so it cannot loop.
    """
    xvfb_run = shutil.which("xvfb-run")
    if xvfb_run is None:
        return False
    os.execvp(xvfb_run, [xvfb_run, "-a", sys.executable, *sys.argv])
    return True  # unreachable, keeps the type checker happy
