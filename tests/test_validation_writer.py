import csv
from datetime import date, datetime, timedelta, timezone

import pytest

from scraper.models import CSV_COLUMNS
from scraper.validation import validate_rows
from scraper.writer import append_to_master, write_run_csv

from conftest import make_row


# ---------- validation ----------

def test_good_rows_pass_through_unchanged():
    rows = [make_row(), make_row(room_category="Family Suite", rooms_available=0,
                                 min_price_inr=None, status="sold_out")]
    assert validate_rows(rows, nights=1) == rows


def test_negative_count_becomes_error():
    result = validate_rows([make_row(rooms_available=-1)], nights=1)
    assert result[0].status == "error"
    assert "negative" in result[0].error_detail


def test_duplicate_pair_flags_only_the_later_row():
    first, second = make_row(), make_row(rooms_available=2)
    result = validate_rows([first, second], nights=1)
    assert result[0].status == "ok"
    assert result[1].status == "error"
    assert "duplicate" in result[1].error_detail


def test_same_category_on_different_dates_is_not_a_duplicate():
    rows = [make_row(), make_row(checkin_date=date(2026, 10, 21), checkout_date=date(2026, 10, 22))]
    assert [r.status for r in validate_rows(rows, nights=1)] == ["ok", "ok"]


def test_rows_without_category_are_never_duplicates():
    rows = [make_row(room_category=None, rooms_available=None, status="error", error_detail="x"),
            make_row(room_category=None, rooms_available=None, status="error", error_detail="y")]
    assert [r.error_detail for r in validate_rows(rows, nights=1)] == ["x", "y"]


def test_wrong_checkout_is_flagged():
    result = validate_rows([make_row(checkout_date=date(2026, 10, 23))], nights=1)
    assert result[0].status == "error"


def test_sold_out_must_have_zero_rooms():
    result = validate_rows([make_row(status="sold_out", rooms_available=2)], nights=1)
    assert result[0].status == "error"


def test_ok_row_needs_a_price():
    result = validate_rows([make_row(min_price_inr=None)], nights=1)
    assert "min_price_inr" in result[0].error_detail


def test_order_and_length_are_preserved():
    rows = [make_row(room_category=f"Room {i}") for i in range(5)]
    assert [r.room_category for r in validate_rows(rows, nights=1)] == [f"Room {i}" for i in range(5)]


# ---------- writer ----------

def read_csv(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def test_run_csv_name_header_and_values(tmp_path):
    started = datetime(2026, 10, 15, 10, 0, 12, tzinfo=timezone(timedelta(minutes=330)))
    path = write_run_csv([make_row()], tmp_path / "out", started)
    assert path.name == "shivvilas_inventory_20261015_1000.csv"
    lines = read_csv(path)
    assert lines[0] == CSV_COLUMNS
    assert lines[1][:8] == ["2026-10-15T10:00:12+05:30", "2026-10-20", "2026-10-21",
                            "Deluxe Double Room", "3", "room_selector", "2450.00", "ok"]
    assert lines[1][8:] == [""] * 5   # unset bonus columns are empty cells


def test_room_names_with_commas_and_unicode_survive(tmp_path):
    started = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)
    name = "Deluxe Room, River View – Café"
    path = write_run_csv([make_row(room_category=name)], tmp_path, started)
    assert read_csv(path)[1][3] == name


def test_master_gets_one_header_and_appended_rows(tmp_path):
    master = tmp_path / "sub" / "master.csv"
    append_to_master([make_row()], master)
    append_to_master([make_row(), make_row(room_category="B")], master)
    lines = read_csv(master)
    assert lines[0] == CSV_COLUMNS
    assert len(lines) == 4


def test_master_with_different_columns_is_refused(tmp_path):
    master = tmp_path / "master.csv"
    master.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="different columns"):
        append_to_master([make_row()], master)
