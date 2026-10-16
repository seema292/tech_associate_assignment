from datetime import date
from decimal import Decimal

import pytest

import main as app
from scraper.errors import BlockedError, ParseError
from scraper.models import RawRoom
from scraper.ratelimit import RateLimiter


class NoWaitLimiter:
    """Stand-in limiter for tests that are not about timing."""

    def call(self, func, *args):
        return func(*args)


ROOM = RawRoom("Deluxe", True, selector_max=2, prices=())


# ---------- rate limiter ----------

def test_limiter_waits_the_remaining_time():
    now = [100.0]
    slept = []
    limiter = RateLimiter(3, clock=lambda: now[0], sleep=slept.append)
    limiter.call(lambda: None)          # first load: no wait
    now[0] = 101.0                      # 1 second later
    limiter.call(lambda: None)
    assert slept == [2.0]


def test_limiter_does_not_wait_when_enough_time_passed():
    now = [100.0]
    slept = []
    limiter = RateLimiter(3, clock=lambda: now[0], sleep=slept.append)
    limiter.call(lambda: None)
    now[0] = 110.0
    limiter.call(lambda: None)
    assert slept == []


def test_limiter_restarts_the_clock_even_when_the_load_fails():
    now = [100.0]
    slept = []
    limiter = RateLimiter(3, clock=lambda: now[0], sleep=slept.append)

    def boom():
        raise RuntimeError("timeout")

    with pytest.raises(RuntimeError):
        limiter.call(boom)
    limiter.call(lambda: None)
    assert slept == [3.0]


# ---------- one date ----------

def test_date_succeeds_on_first_attempt(config):
    rows = app.scrape_date(config, date(2026, 10, 20), lambda c, d: "page",
                           lambda text: [ROOM], NoWaitLimiter())
    assert [r.room_category for r in rows] == ["Deluxe"]
    assert rows[0].checkout_date == date(2026, 10, 21)


def test_date_retries_then_succeeds(config):
    attempts = []

    def flaky_fetch(c, d):
        attempts.append(1)
        if len(attempts) < 3:
            raise TimeoutError("slow")
        return "page"

    rows = app.scrape_date(config, date(2026, 10, 20), flaky_fetch, lambda t: [ROOM], NoWaitLimiter())
    assert len(attempts) == 3
    assert rows[0].status == "ok"


def test_date_gives_up_after_exactly_three_attempts(config):
    attempts = []

    def always_fails(c, d):
        attempts.append(1)
        raise TimeoutError("slow")

    rows = app.scrape_date(config, date(2026, 10, 20), always_fails, lambda t: [], NoWaitLimiter())
    assert len(attempts) == 3
    assert len(rows) == 1
    assert rows[0].status == "error"
    assert "TimeoutError" in rows[0].error_detail


def test_parse_error_is_retried_like_a_fetch_error(config):
    calls = []

    def bad_parse(text):
        calls.append(1)
        raise ParseError("anchor missing")

    rows = app.scrape_date(config, date(2026, 10, 20), lambda c, d: "p", bad_parse, NoWaitLimiter())
    assert len(calls) == 3 and rows[0].status == "error"


def test_empty_page_gives_one_no_rooms_row(config):
    rows = app.scrape_date(config, date(2026, 10, 20), lambda c, d: "p", lambda t: [], NoWaitLimiter())
    assert [r.status for r in rows] == ["no_rooms_listed"]


def test_block_is_not_retried(config):
    calls = []

    def blocked(text):
        calls.append(1)
        raise BlockedError("captcha")

    with pytest.raises(BlockedError):
        app.scrape_date(config, date(2026, 10, 20), lambda c, d: "p", blocked, NoWaitLimiter())
    assert len(calls) == 1


# ---------- whole run ----------

def test_one_failing_date_does_not_stop_the_others(config):
    def fetch(c, d):
        if d == date(2026, 10, 17):
            raise TimeoutError("slow")
        return "page"

    rows, stop = app.run_scrape(config, fetch, lambda t: [ROOM], NoWaitLimiter(), today=date(2026, 10, 15))
    assert stop is None
    assert len(rows) == 30                       # 29 good dates + 1 error row
    assert [r.status for r in rows].count("error") == 1


def test_block_stops_the_run_and_keeps_earlier_rows(config):
    def fetch(c, d):
        if d == date(2026, 10, 19):
            raise BlockedError("captcha")
        return "page"

    rows, stop = app.run_scrape(config, fetch, lambda t: [ROOM], NoWaitLimiter(), today=date(2026, 10, 15))
    assert stop == "blocked"
    assert [r.checkin_date for r in rows] == [date(2026, 10, 16), date(2026, 10, 17), date(2026, 10, 18)]


def test_ctrl_c_stops_the_run_and_keeps_earlier_rows(config):
    def fetch(c, d):
        if d == date(2026, 10, 18):
            raise KeyboardInterrupt
        return "page"

    rows, stop = app.run_scrape(config, fetch, lambda t: [ROOM], NoWaitLimiter(), today=date(2026, 10, 15))
    assert stop == "interrupted"
    assert len(rows) == 2


# ---------- main() end to end, with fakes ----------

def _config_for_main(write_config, tmp_path, num_dates="2"):
    path = write_config("num_dates: 30", f"num_dates: {num_dates}")
    text = open(path, encoding="utf-8").read()
    text = text.replace('dir: "outputs"', f'dir: "{tmp_path}/out"')
    text = text.replace('log_dir: "logs"', f'log_dir: "{tmp_path}/logs"')
    text = text.replace("master_csv: null", f'master_csv: "{tmp_path}/out/master.csv"')
    open(path, "w", encoding="utf-8").write(text)
    return path


def test_main_writes_csv_log_and_master(write_config, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "RateLimiter", lambda seconds: NoWaitLimiter())
    path = _config_for_main(write_config, tmp_path)
    priced = RawRoom("Deluxe", True, selector_max=2, prices=(Decimal("2450"),))

    code = app.main(["--config", path], lambda c, d: "page", lambda t: [priced])

    assert code == 0
    assert len(list((tmp_path / "out").glob("shivvilas_inventory_*.csv"))) == 1
    assert len(list((tmp_path / "logs").glob("run_*.log"))) == 1
    assert (tmp_path / "out" / "master.csv").exists()


def test_main_returns_1_when_some_rows_are_errors(write_config, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "RateLimiter", lambda seconds: NoWaitLimiter())
    path = _config_for_main(write_config, tmp_path)

    def fetch(c, d):
        raise TimeoutError("slow")

    assert app.main(["--config", path], fetch, lambda t: []) == 1


def test_main_returns_2_and_still_writes_csv_when_blocked(write_config, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "RateLimiter", lambda seconds: NoWaitLimiter())
    path = _config_for_main(write_config, tmp_path)

    def parse(text):
        raise BlockedError("captcha")

    assert app.main(["--config", path], lambda c, d: "p", parse) == 2
    assert len(list((tmp_path / "out").glob("shivvilas_inventory_*.csv"))) == 1


def test_main_returns_2_on_bad_config(tmp_path, capsys):
    assert app.main(["--config", str(tmp_path / "missing.yaml")]) == 2
    assert "Config error" in capsys.readouterr().err


def test_main_uses_the_real_fetcher_and_parser_when_none_are_injected(write_config, tmp_path, monkeypatch):
    """No network: BookingFetcher is replaced by a fake that serves a saved page."""
    from pathlib import Path

    page = (Path(__file__).parent / "fixtures" / "hotel_A_2026-10-17.html").read_text(encoding="utf-8")

    class FakeFetcher:
        def __init__(self, config):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def fetch_page(self, config, checkin):
            return page

    monkeypatch.setattr(app, "BookingFetcher", FakeFetcher)
    monkeypatch.setattr(app, "RateLimiter", lambda seconds: NoWaitLimiter())
    path = _config_for_main(write_config, tmp_path)

    assert app.main(["--config", path]) == 0
    csv_files = list((tmp_path / "out").glob("shivvilas_inventory_*.csv"))
    assert len(csv_files) == 1
    assert "Superior Double Room" in csv_files[0].read_text(encoding="utf-8")


def test_main_returns_2_when_the_browser_cannot_start(write_config, tmp_path, monkeypatch):
    class BrokenFetcher:
        def __init__(self, config):
            pass

        def __enter__(self):
            raise app.FetchError("no browser installed")

        def __exit__(self, *exc_info):
            return False

    monkeypatch.setattr(app, "BookingFetcher", BrokenFetcher)
    assert app.main(["--config", _config_for_main(write_config, tmp_path)]) == 2
