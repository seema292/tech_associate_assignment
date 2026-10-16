from datetime import date

from scraper.fetcher import build_url


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
