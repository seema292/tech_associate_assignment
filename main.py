"""Entry point:  python main.py --config config.yaml"""

import argparse
import logging
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from scraper.config import Config, ConfigError, checkout_for, load_config, local_now, stay_dates
from scraper.display import needs_virtual_display, start_virtual_display
from scraper.errors import BlockedError, FetchError
from scraper.fetcher import BookingFetcher, SavedPagesFetcher
from scraper.models import RoomRow, STATUS_ERROR
from scraper.parser import parse_page as default_parse_page
from scraper.ratelimit import RateLimiter
from scraper.rows import error_row, no_rooms_row, raw_to_row
from scraper.validation import validate_rows
from scraper.writer import append_to_master, write_run_csv

log = logging.getLogger("main")

EXIT_OK = 0
EXIT_ERROR_ROWS = 1   # run finished, but some rows have status=error
EXIT_STOPPED = 2      # blocked, interrupted, or bad config: run did not finish


def setup_logging(log_dir: str, run_started) -> Path:
    """Log to the console and to logs/run_<YYYYMMDD_HHMM>.log."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_path = Path(log_dir) / f"run_{run_started:%Y%m%d_%H%M}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_path, encoding="utf-8")],
        force=True,  # replace any handlers already installed (so each run gets its own file)
    )
    return log_path


def scrape_date(config: Config, checkin: date, fetch_page, parse_page, limiter) -> list[RoomRow]:
    """Get all room rows for one check-in date, with up to N total attempts.

    fetch_page(config, checkin) -> page text      (network, slow)
    parse_page(page_text)       -> list[RawRoom]  (pure; raises ParseError/BlockedError)
    BlockedError is never retried; it goes straight up and stops the run.
    """
    checkout = checkout_for(config, checkin)
    last_error = "unknown error"
    for attempt in range(1, config.max_attempts_per_date + 1):
        try:
            page_text = limiter.call(fetch_page, config, checkin)
            raw_rooms = parse_page(page_text)
        except BlockedError:
            raise
        except Exception as exc:  # any other failure: log it and try again
            last_error = f"{type(exc).__name__}: {exc}"[:200].replace("\n", " ")
            log.warning("%s attempt %d/%d failed: %s",
                        checkin, attempt, config.max_attempts_per_date, last_error)
            continue
        scraped_at = local_now(config)
        if not raw_rooms:
            log.info("%s: page loaded, no room categories listed", checkin)
            return [no_rooms_row(checkin, checkout, scraped_at)]
        rows = [raw_to_row(r, checkin, checkout, scraped_at, config.selector_cap) for r in raw_rooms]
        log.info("%s: %d categories found", checkin, len(rows))
        return rows

    log.error("%s: giving up after %d attempts", checkin, config.max_attempts_per_date)
    return [error_row(checkin, checkout, local_now(config), last_error)]


def run_scrape(config: Config, fetch_page, parse_page, limiter, today: date):
    """Loop over every stay date. Returns (rows, stop_reason or None)."""
    rows: list[RoomRow] = []
    for checkin in stay_dates(config, today):
        try:
            rows.extend(scrape_date(config, checkin, fetch_page, parse_page, limiter))
        except BlockedError as exc:
            log.error("BLOCKED on %s: %s. Stopping the run; not retrying.", checkin, exc)
            return rows, "blocked"
        except KeyboardInterrupt:
            log.error("Interrupted by user on %s. Saving what was collected.", checkin)
            return rows, "interrupted"
    return rows, None


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Booking.com room inventory scraper")
    parser.add_argument("--config", required=True, help="path to config.yaml")
    parser.add_argument("--from-saved-pages", metavar="DIR",
                        help="read pages from DIR/<checkin>.html instead of the live site (offline)")
    return parser.parse_args(argv)


def execute(config: Config, run_started, fetch_page, parse_page, min_gap_seconds=None) -> int:
    """Scrape every date, validate, write the CSV files, and return the exit code.

    min_gap_seconds overrides the between-load wait (0 for offline runs, which hit no site).
    """
    gap = config.min_seconds_between_loads if min_gap_seconds is None else min_gap_seconds
    limiter = RateLimiter(gap)
    rows, stop_reason = run_scrape(config, fetch_page, parse_page, limiter, run_started.date())
    rows = validate_rows(rows, config.nights)

    csv_path = write_run_csv(rows, config.output_dir, run_started)
    if config.master_csv:
        append_to_master(rows, config.master_csv)

    counts = Counter(row.status for row in rows)
    log.info("Finished. %d rows written to %s. Status counts: %s", len(rows), csv_path, dict(counts))
    if stop_reason:
        log.error("Run stopped early: %s", stop_reason)
        return EXIT_STOPPED
    return EXIT_ERROR_ROWS if counts[STATUS_ERROR] else EXIT_OK


def main(argv=None, fetch_page=None, parse_page=None) -> int:
    """Run the whole job. fetch_page / parse_page can be passed in (used by tests);
    when omitted, the real browser fetcher and the real parser are used.
    """
    args = parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return EXIT_STOPPED

    if fetch_page is None and needs_virtual_display(config.headless):
        print("No display found: starting a virtual screen (Xvfb).", file=sys.stderr)
        if not start_virtual_display():
            print("No display and Xvfb could not be started. On Debian/Ubuntu: "
                  "sudo apt install xvfb   (or run on a machine with a screen).", file=sys.stderr)
            return EXIT_STOPPED

    run_started = local_now(config)
    log_path = setup_logging(config.log_dir, run_started)
    log.info("Run started %s, log file %s", run_started.isoformat(), log_path)
    log.info("Property: %s | %s", config.property_name, config.property_url)

    if fetch_page is not None:
        return execute(config, run_started, fetch_page, parse_page or default_parse_page)

    # Offline mode: read saved pages instead of the live site.
    if args.from_saved_pages:
        log.info("Offline mode: reading saved pages from %s", args.from_saved_pages)
        try:
            with SavedPagesFetcher(args.from_saved_pages) as fetcher:
                return execute(config, run_started, fetcher.fetch_page, default_parse_page, min_gap_seconds=0)
        except FetchError as exc:
            log.error("Could not start: %s", exc)
            return EXIT_STOPPED

    try:
        with BookingFetcher(config) as fetcher:
            return execute(config, run_started, fetcher.fetch_page, parse_page or default_parse_page)
    except FetchError as exc:
        log.error("Could not start: %s", exc)
        return EXIT_STOPPED


if __name__ == "__main__":
    # Windows consoles often use a legacy encoding; never crash on a non-ASCII character.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
