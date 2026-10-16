"""Guarantees the gap between page loads. One object, used for every load."""

import time


class RateLimiter:
    """Make sure at least `min_seconds` pass between the END of one page load
    and the START of the next. Retries go through the same object, so they
    obey the same rule.
    """

    def __init__(self, min_seconds: float, clock=time.monotonic, sleep=time.sleep):
        self._min_seconds = min_seconds
        self._clock = clock    # injectable so tests need not really wait
        self._sleep = sleep
        self._last_finished = None

    def call(self, func, *args):
        """Wait if needed, run func(*args), then note when it finished."""
        if self._last_finished is not None:
            remaining = self._min_seconds - (self._clock() - self._last_finished)
            if remaining > 0:
                self._sleep(remaining)
        try:
            return func(*args)
        finally:
            # finally: the clock restarts even if the load failed or timed out
            self._last_finished = self._clock()
