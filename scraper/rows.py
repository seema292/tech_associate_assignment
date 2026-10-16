"""Turn parser output (RawRoom) into CSV rows (RoomRow). Pure functions.

This is where rooms_available is decided. The rules, in priority order:
  1. not bookable          -> 0, source "sold_out_flag"
  2. "Only N left" message -> N, source "scarcity_message"
  3. dropdown maximum M    -> M, source "room_selector" (flagged if at the cap)
  4. bookable, no number   -> 1, source "bookable_min_1" (a lower bound)
"""

from datetime import date, datetime

from scraper.models import (
    RawRoom,
    RoomRow,
    STATUS_ERROR,
    STATUS_NO_ROOMS_LISTED,
    STATUS_OK,
    STATUS_SOLD_OUT,
)


def _estimate(raw: RawRoom, selector_cap: int | None) -> tuple[int, str, bool | None]:
    """Return (rooms_available, availability_source, is_capped) for a bookable room."""
    if raw.scarcity_count is not None:
        return raw.scarcity_count, "scarcity_message", False
    if raw.selector_max is not None:
        # If we do not know the dropdown's cap, "capped?" is unknown (None), not False.
        capped = None if selector_cap is None else raw.selector_max >= selector_cap
        return raw.selector_max, "room_selector", capped
    return 1, "bookable_min_1", True


def raw_to_row(
    raw: RawRoom,
    checkin: date,
    checkout: date,
    scraped_at: datetime,
    selector_cap: int | None,
) -> RoomRow:
    """Build the CSV row for one room category on one date."""
    common = dict(
        scrape_timestamp=scraped_at,
        checkin_date=checkin,
        checkout_date=checkout,
        room_category=raw.name,
        room_type_id=raw.room_type_id,
        scarcity_message=raw.scarcity_text,
        rate_plan_count=raw.rate_plan_count,
    )
    if not raw.is_bookable:
        return RoomRow(
            rooms_available=0,
            availability_source="sold_out_flag",
            min_price_inr=None,
            status=STATUS_SOLD_OUT,
            is_capped=False,
            **common,
        )
    rooms, source, capped = _estimate(raw, selector_cap)
    return RoomRow(
        rooms_available=rooms,
        availability_source=source,
        min_price_inr=min(raw.prices) if raw.prices else None,
        status=STATUS_OK,
        is_capped=capped,
        **common,
    )


def no_rooms_row(checkin: date, checkout: date, scraped_at: datetime) -> RoomRow:
    """One row for a date whose page loaded fine but lists no room categories."""
    return RoomRow(
        scrape_timestamp=scraped_at,
        checkin_date=checkin,
        checkout_date=checkout,
        room_category=None,
        rooms_available=None,
        availability_source=None,
        min_price_inr=None,
        status=STATUS_NO_ROOMS_LISTED,
    )


def error_row(checkin: date, checkout: date, scraped_at: datetime, detail: str) -> RoomRow:
    """One row for a date that failed on every attempt."""
    return RoomRow(
        scrape_timestamp=scraped_at,
        checkin_date=checkin,
        checkout_date=checkout,
        room_category=None,
        rooms_available=None,
        availability_source=None,
        min_price_inr=None,
        status=STATUS_ERROR,
        error_detail=detail,
    )
