"""The ONLY module that talks to the network. It loads a hotel page and returns its HTML.

No stealth plugins, no proxies, no header tricks, no login: it opens the public
page the way an ordinary browser would, using Playwright's own default settings.
"""

import logging
import subprocess
import sys
from datetime import date
from urllib.parse import urlencode

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from scraper.config import Config, checkout_for
from scraper.errors import BlockedError, FetchError
from scraper.parser import SEL_NO_AVAILABILITY, SEL_ROOM_TABLE

# HTTP statuses that mean "slow down / you are blocked". We stop on these.
BLOCK_STATUSES = (403, 429)

log = logging.getLogger(__name__)


def build_url(config: Config, checkin: date) -> str:
    """Hotel page URL for one stay date. Pure function, easy to test."""
    query = urlencode(
        {
            "checkin": checkin.isoformat(),
            "checkout": checkout_for(config, checkin).isoformat(),
            "group_adults": config.adults,
            "no_rooms": config.rooms,
            "group_children": 0,
            "selected_currency": config.currency,
            "lang": config.language,
        }
    )
    return f"{config.property_url}?{query}"


def install_browser() -> None:
    """Download Playwright's Chromium (one time per machine, about 150 MB)."""
    log.info("Browser not installed yet: running 'playwright install chromium' (one time)...")
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise FetchError("'playwright install chromium' failed: " + result.stderr.strip()[-300:])


class BookingFetcher:
    """Owns one browser for the whole run. Use it in a `with` block."""

    def __init__(self, config: Config):
        self._config = config
        self._playwright = None
        self._browser = None
        self._page = None

    def _launch(self):
        return self._playwright.chromium.launch(
            headless=self._config.headless,
            channel=self._config.browser_channel,  # None = Playwright's own Chromium
        )

    def __enter__(self) -> "BookingFetcher":
        self._playwright = sync_playwright().start()
        try:
            try:
                self._browser = self._launch()
            except PlaywrightError as exc:
                # First run on a new machine: the browser has not been downloaded yet.
                if "Executable doesn't exist" not in str(exc) or self._config.browser_channel:
                    raise
                install_browser()
                self._browser = self._launch()
        except (PlaywrightError, FetchError) as exc:
            self._playwright.stop()
            raise FetchError(f"could not start the browser: {exc}") from None
        context = self._browser.new_context(locale=self._config.language)
        self._page = context.new_page()
        self._page.set_default_timeout(self._config.page_timeout_seconds * 1000)
        return self

    def __exit__(self, *exc_info) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    def fetch_page(self, config: Config, checkin: date) -> str:
        """Load the hotel page for `checkin` and return the rendered HTML."""
        url = build_url(config, checkin)
        try:
            response = self._page.goto(url, wait_until="domcontentloaded")
        except PlaywrightTimeout:
            raise FetchError(f"timed out loading {checkin}") from None
        except PlaywrightError as exc:
            raise FetchError(f"browser error loading {checkin}: {exc}") from None

        if response is not None and response.status in BLOCK_STATUSES:
            raise BlockedError(f"HTTP {response.status} from Booking.com")

        if "/hotel/" not in self._page.url:
            # Booking.com sent us elsewhere (e.g. a search page): the hotel page is not there.
            raise FetchError(f"redirected away from the hotel page to {self._page.url.split('?')[0]}")

        try:
            # Wait for whichever of the two possible results appears.
            self._page.wait_for_selector(f"{SEL_ROOM_TABLE}, {SEL_NO_AVAILABILITY}", state="attached")
        except PlaywrightTimeout:
            pass  # not fatal: the parser will decide if this is a block page or an unknown page
        return self._page.content()
