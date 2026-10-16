"""Load config.yaml into a validated, read-only Config object."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import yaml

# Ground rule from the assignment: at most one page load every 3 seconds.
MIN_ALLOWED_SECONDS_BETWEEN_LOADS = 3


class ConfigError(Exception):
    """Raised when the config file is missing, malformed or breaks a rule."""


@dataclass(frozen=True)
class Config:
    property_name: str
    property_url: str
    start_offset_days: int
    num_dates: int
    nights: int
    adults: int
    rooms: int
    currency: str
    language: str
    utc_offset_minutes: int
    min_seconds_between_loads: float
    max_attempts_per_date: int
    page_timeout_seconds: float
    selector_cap: int | None
    headless: bool
    start_minimized: bool
    browser_channel: str | None
    output_dir: str
    master_csv: str | None
    log_dir: str


def _require(data: dict, section: str, key: str, kind: type | tuple):
    """Return data[section][key], or raise a clear error if absent/wrong type."""
    block = data.get(section)
    if not isinstance(block, dict):
        raise ConfigError(f"Missing section '{section}' in config")
    if key not in block:
        raise ConfigError(f"Missing '{section}.{key}' in config")
    value = block[key]
    # bool is a subclass of int in Python, so a bool is only accepted when asked for.
    if (isinstance(value, bool) and kind is not bool) or not isinstance(value, kind):
        raise ConfigError(f"'{section}.{key}' has the wrong type: {value!r}")
    return value


def _optional(data: dict, section: str, key: str, kind: type | tuple):
    """Like _require, but the value may be null (None) or the key absent."""
    block = data.get(section)
    if not isinstance(block, dict) or block.get(key) is None:
        return None
    return _require(data, section, key, kind)


def _check_rules(config: Config) -> None:
    """Enforce the assignment's rules. Collect every problem, then raise once."""
    problems = []
    host = urlparse(config.property_url).hostname or ""
    if not host.endswith("booking.com"):
        problems.append("property.url must be a booking.com URL (fill it in after recon)")
    if config.min_seconds_between_loads < MIN_ALLOWED_SECONDS_BETWEEN_LOADS:
        problems.append(
            f"politeness.min_seconds_between_loads must be >= {MIN_ALLOWED_SECONDS_BETWEEN_LOADS}"
        )
    if config.currency != "INR":
        problems.append("search.currency must be INR")
    if config.num_dates < 1:
        problems.append("search.num_dates must be >= 1")
    if config.start_offset_days < 0:
        problems.append("search.start_offset_days must be >= 0")
    if config.nights < 1:
        problems.append("search.nights must be >= 1")
    if config.adults < 1 or config.rooms < 1:
        problems.append("search.adults and search.rooms must be >= 1")
    if config.max_attempts_per_date < 1:
        problems.append("politeness.max_attempts_per_date must be >= 1")
    if config.page_timeout_seconds <= 0:
        problems.append("politeness.page_timeout_seconds must be > 0")
    if config.selector_cap is not None and config.selector_cap < 1:
        problems.append("availability.selector_cap must be null or >= 1")
    if problems:
        raise ConfigError("Invalid config: " + "; ".join(problems))


def load_config(path: str | Path) -> Config:
    """Read the YAML file at `path` and return a validated Config."""
    path = Path(path)
    try:
        with path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {path}") from None
    except yaml.YAMLError as exc:
        raise ConfigError(f"Config file is not valid YAML: {exc}") from None
    if not isinstance(data, dict):
        raise ConfigError("Config file is empty or not a YAML mapping")

    number = (int, float)
    config = Config(
        property_name=_require(data, "property", "name", str),
        property_url=_require(data, "property", "url", str),
        start_offset_days=_require(data, "search", "start_offset_days", int),
        num_dates=_require(data, "search", "num_dates", int),
        nights=_require(data, "search", "nights", int),
        adults=_require(data, "search", "adults", int),
        rooms=_require(data, "search", "rooms", int),
        currency=_require(data, "search", "currency", str),
        language=_require(data, "search", "language", str),
        utc_offset_minutes=data.get("utc_offset_minutes"),
        min_seconds_between_loads=_require(data, "politeness", "min_seconds_between_loads", number),
        max_attempts_per_date=_require(data, "politeness", "max_attempts_per_date", int),
        page_timeout_seconds=_require(data, "politeness", "page_timeout_seconds", number),
        selector_cap=_optional(data, "availability", "selector_cap", int),
        headless=_require(data, "browser", "headless", bool),
        start_minimized=_require(data, "browser", "start_minimized", bool),
        browser_channel=_optional(data, "browser", "channel", str),
        output_dir=_require(data, "output", "dir", str),
        master_csv=_optional(data, "output", "master_csv", str),
        log_dir=_require(data, "output", "log_dir", str),
    )
    if isinstance(config.utc_offset_minutes, bool) or not isinstance(config.utc_offset_minutes, int):
        raise ConfigError("'utc_offset_minutes' must be an integer (IST = 330)")
    _check_rules(config)
    return config


def local_now(config: Config) -> datetime:
    """Current time in the configured timezone (IST), without microseconds."""
    tz = timezone(timedelta(minutes=config.utc_offset_minutes))
    return datetime.now(tz).replace(microsecond=0)


def stay_dates(config: Config, today: date) -> list[date]:
    """Check-in dates to search: `num_dates` days starting `start_offset_days` from today."""
    first = today + timedelta(days=config.start_offset_days)
    return [first + timedelta(days=i) for i in range(config.num_dates)]


def checkout_for(config: Config, checkin: date) -> date:
    """Check-out date for a given check-in date."""
    return checkin + timedelta(days=config.nights)
