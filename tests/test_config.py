from datetime import date

import pytest

from scraper.config import ConfigError, checkout_for, load_config, stay_dates


def test_valid_config_loads(config):
    assert config.num_dates == 30
    assert config.currency == "INR"
    assert config.selector_cap is None
    assert config.master_csv is None


def test_stay_dates_are_30_days_starting_tomorrow(config):
    dates = stay_dates(config, today=date(2026, 10, 15))
    assert len(dates) == 30
    assert dates[0] == date(2026, 10, 16)
    assert dates[-1] == date(2026, 11, 14)


def test_checkout_is_checkin_plus_nights(config):
    assert checkout_for(config, date(2026, 10, 31)) == date(2026, 11, 1)


@pytest.mark.parametrize(
    "old, new, message",
    [
        ("min_seconds_between_loads: 3", "min_seconds_between_loads: 1", "min_seconds_between_loads"),
        ('currency: "INR"', 'currency: "USD"', "currency"),
        ("https://www.booking.com/hotel/in/example.html", "https://example.com/x", "booking.com"),
        ("num_dates: 30", "num_dates: 0", "num_dates"),
        ("max_attempts_per_date: 3", "max_attempts_per_date: 0", "max_attempts_per_date"),
        ("selector_cap: null", "selector_cap: 0", "selector_cap"),
        ("num_dates: 30", "num_dates: true", "wrong type"),
        ("utc_offset_minutes: 330", "utc_offset_minutes: \"+05:30\"", "utc_offset_minutes"),
    ],
)
def test_rule_breaking_configs_are_refused(write_config, old, new, message):
    with pytest.raises(ConfigError, match=message):
        load_config(write_config(old, new))


def test_missing_key_is_reported(write_config):
    with pytest.raises(ConfigError, match="search.adults"):
        load_config(write_config("  adults: 2\n", ""))


def test_missing_file_is_reported(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


def test_shipped_config_loads_and_keeps_the_assignment_inputs():
    config = load_config("config.yaml")
    assert (config.num_dates, config.nights, config.adults, config.rooms) == (30, 1, 2, 1)
    assert config.currency == "INR"
    assert config.min_seconds_between_loads >= 3
    assert config.max_attempts_per_date == 3
