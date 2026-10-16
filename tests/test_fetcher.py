from datetime import date

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from scraper.errors import BlockedError, FetchError
from scraper.fetcher import BookingFetcher, build_url


def test_url_has_all_fixed_search_parameters(config):
    url = build_url(config, date(2026, 10, 20))
    base, query = url.split("?")
    assert base == config.property_url
    assert query.split("&") == [
        "checkin=2026-10-20",
        "checkout=2026-10-21",
        "group_adults=2",
        "no_rooms=1",
        "group_children=0",
        "selected_currency=INR",
        "lang=en-gb",
    ]


def test_checkout_follows_the_configured_nights(write_config):
    from scraper.config import load_config

    config = load_config(write_config("nights: 1", "nights: 2"))
    assert "checkout=2026-10-22" in build_url(config, date(2026, 10, 20))


# ---------- fetch_page behaviour, with a fake browser page (no network) ----------

class FakeResponse:
    def __init__(self, status):
        self.status = status


class FakePage:
    """Stands in for a Playwright page. Set the fields to script what the 'site' does."""

    def __init__(self, status=200, url="https://www.booking.com/hotel/in/x.en-gb.html",
                 goto_error=None, wait_error=None, html="<html>page</html>"):
        self.status, self.url, self.goto_error, self.wait_error, self.html = (
            status, url, goto_error, wait_error, html)
        self.visited = []

    def goto(self, url, wait_until):
        self.visited.append(url)
        if self.goto_error:
            raise self.goto_error
        return FakeResponse(self.status)

    def wait_for_selector(self, selector, state):
        if self.wait_error:
            raise self.wait_error

    def content(self):
        return self.html


def fetcher_with(config, page):
    fetcher = BookingFetcher(config)
    fetcher._page = page
    return fetcher


def test_good_page_returns_its_html(config):
    page = FakePage(html="<html>rooms</html>")
    assert fetcher_with(config, page).fetch_page(config, date(2026, 10, 20)) == "<html>rooms</html>"
    assert "checkin=2026-10-20" in page.visited[0]


@pytest.mark.parametrize("status", [403, 429])
def test_block_status_raises_blocked(config, status):
    with pytest.raises(BlockedError, match=str(status)):
        fetcher_with(config, FakePage(status=status)).fetch_page(config, date(2026, 10, 20))


def test_redirect_away_from_hotel_page_is_a_fetch_error(config):
    page = FakePage(url="https://www.booking.com/searchresults.en-gb.html?label=x")
    with pytest.raises(FetchError, match="redirected"):
        fetcher_with(config, page).fetch_page(config, date(2026, 10, 20))


def test_timeout_is_a_fetch_error(config):
    page = FakePage(goto_error=PlaywrightTimeout("slow"))
    with pytest.raises(FetchError, match="timed out"):
        fetcher_with(config, page).fetch_page(config, date(2026, 10, 20))


def test_other_browser_error_is_a_fetch_error(config):
    page = FakePage(goto_error=PlaywrightError("net::ERR_CONNECTION_RESET"))
    with pytest.raises(FetchError, match="browser error"):
        fetcher_with(config, page).fetch_page(config, date(2026, 10, 20))


def test_selector_timeout_is_not_fatal_the_parser_decides(config):
    page = FakePage(wait_error=PlaywrightTimeout("no table"), html="<html>odd page</html>")
    assert fetcher_with(config, page).fetch_page(config, date(2026, 10, 20)) == "<html>odd page</html>"
