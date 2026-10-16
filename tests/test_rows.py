from datetime import date
from decimal import Decimal

from scraper.models import CSV_COLUMNS, RawRoom
from scraper.rows import error_row, no_rooms_row, raw_to_row

from conftest import SCRAPED_AT, make_row

CHECKIN = date(2026, 10, 20)
CHECKOUT = date(2026, 10, 21)


def test_csv_columns_match_the_pdf_order():
    assert CSV_COLUMNS == [
        "scrape_timestamp", "checkin_date", "checkout_date", "room_category",
        "rooms_available", "availability_source", "min_price_inr", "status",
        "room_type_id", "scarcity_message", "is_capped", "rate_plan_count", "error_detail",
    ]


def test_to_csv_dict_formats_values():
    data = make_row().to_csv_dict()
    assert data["scrape_timestamp"] == "2026-10-15T10:00:12+05:30"
    assert data["checkin_date"] == "2026-10-20"
    assert data["min_price_inr"] == "2450.00"
    assert list(data) == CSV_COLUMNS


def _convert(raw, cap=None):
    return raw_to_row(raw, CHECKIN, CHECKOUT, SCRAPED_AT, cap)


def test_not_bookable_is_sold_out_with_zero_rooms():
    row = _convert(RawRoom("Family Suite", is_bookable=False))
    assert (row.status, row.rooms_available, row.min_price_inr) == ("sold_out", 0, None)
    assert row.availability_source == "sold_out_flag"


def test_scarcity_message_wins_over_dropdown():
    raw = RawRoom("Cottage", True, selector_max=5, scarcity_count=2,
                  scarcity_text="Only 2 rooms left on our site", prices=(Decimal("1000"),))
    row = _convert(raw, cap=10)
    assert row.rooms_available == 2
    assert row.availability_source == "scarcity_message"
    assert row.is_capped is False
    assert row.scarcity_message == "Only 2 rooms left on our site"


def test_dropdown_below_cap_is_not_capped():
    row = _convert(RawRoom("Deluxe", True, selector_max=3, prices=(Decimal("1"),)), cap=10)
    assert (row.rooms_available, row.availability_source, row.is_capped) == (3, "room_selector", False)


def test_dropdown_at_cap_is_flagged_capped():
    row = _convert(RawRoom("Deluxe", True, selector_max=10, prices=(Decimal("1"),)), cap=10)
    assert row.is_capped is True


def test_dropdown_with_unknown_cap_leaves_capped_unknown():
    row = _convert(RawRoom("Deluxe", True, selector_max=4, prices=(Decimal("1"),)), cap=None)
    assert row.is_capped is None


def test_bookable_without_any_number_is_lower_bound_of_one():
    row = _convert(RawRoom("Deluxe", True, prices=(Decimal("1"),)))
    assert (row.rooms_available, row.availability_source, row.is_capped) == (1, "bookable_min_1", True)


def test_min_price_is_the_lowest_of_all_prices():
    raw = RawRoom("Deluxe", True, selector_max=2, prices=(Decimal("2500"), Decimal("2450"), Decimal("3000")))
    assert _convert(raw).min_price_inr == Decimal("2450")


def test_bonus_columns_are_copied_through():
    raw = RawRoom("Deluxe", True, room_type_id="123", selector_max=2,
                  prices=(Decimal("1"),), rate_plan_count=3)
    row = _convert(raw)
    assert (row.room_type_id, row.rate_plan_count) == ("123", 3)


def test_no_rooms_row():
    row = no_rooms_row(CHECKIN, CHECKOUT, SCRAPED_AT)
    assert row.status == "no_rooms_listed"
    assert row.room_category is None and row.rooms_available is None


def test_error_row_keeps_the_reason():
    row = error_row(CHECKIN, CHECKOUT, SCRAPED_AT, "TimeoutError: slow")
    assert row.status == "error"
    assert row.error_detail == "TimeoutError: slow"
