"""Plain data containers shared by every module, plus the CSV column order."""

from dataclasses import asdict, dataclass, fields
from datetime import date, datetime
from decimal import Decimal

# Allowed values for RoomRow.status
STATUS_OK = "ok"
STATUS_SOLD_OUT = "sold_out"
STATUS_NO_ROOMS_LISTED = "no_rooms_listed"
STATUS_ERROR = "error"


@dataclass(frozen=True)
class RawRoom:
    """What the parser pulls off the page for one room category.

    Nothing is estimated here. Fields the page did not show are None.
    """

    name: str                           # room name exactly as shown
    is_bookable: bool                   # False if listed but cannot be booked
    room_type_id: str | None = None     # Booking.com's room ID, if present
    selector_max: int | None = None     # highest number in the "select rooms" dropdown
    scarcity_count: int | None = None   # N from "Only N rooms left"
    scarcity_text: str | None = None    # the message text itself
    prices: tuple[Decimal, ...] = ()    # every price shown for this category (INR)
    rate_plan_count: int | None = None  # number of rate plans for this category


@dataclass(frozen=True)
class RoomRow:
    """One CSV row. The field ORDER here is the CSV column order.

    The first 8 fields are the required columns, the last 5 are the bonus
    columns, in the same order as the assignment PDF.
    """

    scrape_timestamp: datetime
    checkin_date: date
    checkout_date: date
    room_category: str | None
    rooms_available: int | None
    availability_source: str | None
    min_price_inr: Decimal | None
    status: str
    room_type_id: str | None = None
    scarcity_message: str | None = None
    is_capped: bool | None = None
    rate_plan_count: int | None = None
    error_detail: str | None = None

    def to_csv_dict(self) -> dict:
        """Return {column: value} with dates, timestamp and price text-formatted.

        None values stay None; the csv module writes them as empty cells.
        """
        data = asdict(self)
        data["scrape_timestamp"] = self.scrape_timestamp.isoformat(timespec="seconds")
        data["checkin_date"] = self.checkin_date.isoformat()
        data["checkout_date"] = self.checkout_date.isoformat()
        if self.min_price_inr is not None:
            data["min_price_inr"] = f"{self.min_price_inr:.2f}"
        return data


# Single source of truth for the column order: the field order of RoomRow.
CSV_COLUMNS: list[str] = [f.name for f in fields(RoomRow)]
