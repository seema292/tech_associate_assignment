"""Check rows before they are written. Pure functions: rows in, rows out."""

import logging
from dataclasses import replace
from datetime import timedelta

from scraper.models import RoomRow, STATUS_ERROR, STATUS_OK, STATUS_SOLD_OUT

log = logging.getLogger(__name__)


def _row_problems(row: RoomRow, nights: int) -> list[str]:
    """Return a list of rule violations for one row (empty list = row is fine)."""
    problems = []
    if row.rooms_available is not None and row.rooms_available < 0:
        problems.append("rooms_available is negative")
    if row.checkout_date != row.checkin_date + timedelta(days=nights):
        problems.append("checkout_date is not checkin_date + nights")
    if row.status == STATUS_SOLD_OUT and row.rooms_available != 0:
        problems.append("status sold_out but rooms_available is not 0")
    if row.status == STATUS_OK:
        if row.rooms_available is None or row.rooms_available < 1:
            problems.append("status ok but rooms_available is missing or < 1")
        if row.min_price_inr is None:
            problems.append("status ok but min_price_inr is missing")
    return problems


def validate_rows(rows: list[RoomRow], nights: int) -> list[RoomRow]:
    """Return the same rows in the same order; broken rows become status=error.

    A broken row is never dropped. Its status is changed to "error" and the
    reason is put in error_detail, so the problem is visible in the CSV.
    Duplicate (checkin_date, room_category) pairs: the first row is kept as
    is, every later one is flagged.
    """
    seen_pairs = set()
    checked = []
    for row in rows:
        problems = _row_problems(row, nights)
        # Rows with no category (no_rooms_listed / error) cannot be duplicates.
        if row.room_category is not None:
            pair = (row.checkin_date, row.room_category)
            if pair in seen_pairs:
                problems.append("duplicate checkin_date and room_category")
            seen_pairs.add(pair)
        if problems:
            detail = "; ".join(problems)
            log.warning(
                "Row failed validation (%s, %s): %s",
                row.checkin_date, row.room_category, detail,
            )
            row = replace(row, status=STATUS_ERROR, error_detail=detail)
        checked.append(row)
    return checked
