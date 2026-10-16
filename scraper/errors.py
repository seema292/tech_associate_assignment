"""Exceptions shared by the fetcher, parser and main loop."""


class BlockedError(Exception):
    """Booking.com showed a CAPTCHA / block page. Never retried: the run stops."""


class ParseError(Exception):
    """The page loaded but did not look like the hotel page we expect."""


class FetchError(Exception):
    """The page could not be loaded (timeout, network failure)."""
