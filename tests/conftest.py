"""Shared test helpers: a valid config file and a few ready-made objects."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from scraper.config import load_config
from scraper.models import RoomRow

IST = timezone(timedelta(minutes=330))
SCRAPED_AT = datetime(2026, 10, 15, 10, 0, 12, tzinfo=IST)

# A valid config. Tests change one line of it to check one rule.
VALID_YAML = """
property:
  name: "Test Hotel"
  url: "https://www.booking.com/hotel/in/example.html"
search:
  start_offset_days: 1
  num_dates: 30
  nights: 1
  adults: 2
  rooms: 1
  currency: "INR"
  language: "en-gb"
utc_offset_minutes: 330
politeness:
  min_seconds_between_loads: 3
  max_attempts_per_date: 3
  page_timeout_seconds: 45
availability:
  selector_cap: null
browser:
  headless: true
  channel: null
output:
  dir: "outputs"
  master_csv: null
  log_dir: "logs"
"""


@pytest.fixture
def write_config(tmp_path):
    """Return a function: write_config(old, new) -> path of a config with one replacement."""

    def _write(old: str = "", new: str = "") -> str:
        text = VALID_YAML.replace(old, new) if old else VALID_YAML
        path = tmp_path / "config.yaml"
        path.write_text(text, encoding="utf-8")
        return str(path)

    return _write


@pytest.fixture
def config(write_config):
    return load_config(write_config())


def make_row(**overrides) -> RoomRow:
    """A good 'ok' row; pass keyword arguments to change fields."""
    fields = dict(
        scrape_timestamp=SCRAPED_AT,
        checkin_date=date(2026, 10, 20),
        checkout_date=date(2026, 10, 21),
        room_category="Deluxe Double Room",
        rooms_available=3,
        availability_source="room_selector",
        min_price_inr=Decimal("2450"),
        status="ok",
    )
    fields.update(overrides)
    return RoomRow(**fields)
