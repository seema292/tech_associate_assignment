"""Read a saved or freshly loaded Booking.com hotel page. PURE: no network, no files.

Everything here was written from pages observed on 2026-10-16 (see
tests/fixtures). If Booking.com changes its page, the CSS selectors in the
SELECTORS block below are the first place to look.
"""

import re
from decimal import Decimal

from bs4 import BeautifulSoup, Tag

from scraper.errors import BlockedError, ParseError
from scraper.models import RawRoom

# ---- every selector the parser relies on, in one place -------------------
SEL_HOTEL_NAME = "#hp_hotel_name"                  # present on every real hotel page
SEL_ROOM_TABLE = "#hprt-table"                     # the room table (absent when nothing is available)
SEL_NO_AVAILABILITY = ".rooms_table_noavailability"  # shown instead of the table
SEL_ALERT = ".bui-alert--error"                    # red notice boxes
SEL_ROOM_ROW = "tbody tr.js-rt-block-row"          # one row per rate plan
SEL_ROOM_NAME_CELL = "th.hprt-table-cell-roomtype"  # only on the first row of each room
SEL_ROOM_LINK = "a.hprt-roomtype-link"             # room name + data-room-id
SEL_DROPDOWN = "select.hprt-nos-select"            # the "select rooms" dropdown
SEL_SCARCITY = ".only_x_left"                      # text like "We have 5 left"
SEL_PRICE = ".bui-price-display__value"            # price before taxes and charges
NO_AVAILABILITY_PHRASE = "no availability"         # in "We have no availability here between ..."

# Text that means we are being challenged / blocked. Only checked when the
# normal hotel page is missing, so a stray word on a real page cannot trigger it.
BLOCK_MARKERS = (
    "captcha",
    "are you a robot",
    "verify you are human",
    "unusual traffic",
    "access denied",
)

_SCARCITY_NUMBER = re.compile(r"(\d+)\s+left", re.IGNORECASE)


def looks_blocked(page_text: str) -> bool:
    """True if the page text looks like a CAPTCHA / block page."""
    lowered = page_text.lower()
    return any(marker in lowered for marker in BLOCK_MARKERS)


def _clean(text: str) -> str:
    """Collapse all runs of whitespace (including non-breaking spaces) to one space."""
    return " ".join(text.split())


def _parse_price(text: str) -> Decimal | None:
    """'₹ 3,000' -> Decimal('3000'). Returns None if there are no digits."""
    digits = re.sub(r"[^\d.]", "", text)
    return Decimal(digits) if digits else None


def _dropdown_max(row: Tag) -> int | None:
    """Highest number in this row's 'select rooms' dropdown, or None if no dropdown."""
    select = row.select_one(SEL_DROPDOWN)
    if select is None:
        return None
    values = [int(o["value"]) for o in select.find_all("option") if o.get("value", "").isdecimal()]
    return max(values) if values else None


def _room_id_of(row: Tag) -> str:
    """Room ID of a table row: the part of data-block-id before the first '_'."""
    block_id = row.get("data-block-id", "")
    if not block_id:
        raise ParseError("room row without data-block-id")
    return block_id.split("_")[0]


def _read_room_names(table: Tag) -> dict[str, tuple[str, Tag]]:
    """Map room ID -> (room name, the name cell). Names appear once per room."""
    names = {}
    for cell in table.select(SEL_ROOM_NAME_CELL):
        link = cell.select_one(SEL_ROOM_LINK)
        if link is None or not link.get("data-room-id"):
            raise ParseError("room name cell without a room link / data-room-id")
        names[link["data-room-id"]] = (_clean(link.get_text()), cell)
    return names


def parse_page(page_text: str) -> list[RawRoom]:
    """Return one RawRoom per room category on the page.

    Returns [] when the page is a valid hotel page that says nothing is
    available. Raises BlockedError for a CAPTCHA/block page and ParseError for
    any page we do not recognise (so a broken selector is never mistaken for
    'no rooms').
    """
    soup = BeautifulSoup(page_text, "html.parser")

    if soup.select_one(SEL_HOTEL_NAME) is None:
        if looks_blocked(page_text):
            raise BlockedError("page looks like a CAPTCHA / block page")
        raise ParseError("hotel name element not found: not a hotel page")

    table = soup.select_one(SEL_ROOM_TABLE)
    if table is None:
        # Error-style notices anywhere on the page. The real "no availability" text
        # and the "Select dates ..." text (shown when the dates were not applied)
        # sit in the same kind of box, so the wording decides which one it is.
        alerts = " ".join(_clean(e.get_text()).lower() for e in soup.select(SEL_ALERT))
        if "select dates" in alerts:
            raise ParseError("page shows 'select dates': the stay dates were not applied")
        if soup.select_one(SEL_NO_AVAILABILITY) is not None and NO_AVAILABILITY_PHRASE in alerts:
            return []
        raise ParseError("neither the room table nor the no-availability notice was found")

    names = _read_room_names(table)
    rows_by_room: dict[str, list[Tag]] = {}
    for row in table.select(SEL_ROOM_ROW):
        rows_by_room.setdefault(_room_id_of(row), []).append(row)
    if not rows_by_room:
        raise ParseError("room table has no room rows")

    rooms = []
    for room_id, rows in rows_by_room.items():
        if room_id not in names:
            raise ParseError(f"no name found for room id {room_id}")
        name, name_cell = names[room_id]

        maxima = [m for m in (_dropdown_max(r) for r in rows) if m is not None]
        selector_max = max(maxima) if maxima else None

        scarcity_tag = name_cell.select_one(SEL_SCARCITY)
        scarcity_text = _clean(scarcity_tag.get_text()) if scarcity_tag else None
        match = _SCARCITY_NUMBER.search(scarcity_text) if scarcity_text else None

        prices = []
        for row in rows:
            price_tag = row.select_one(SEL_PRICE)
            price = _parse_price(price_tag.get_text()) if price_tag else None
            if price is not None:
                prices.append(price)

        rooms.append(
            RawRoom(
                name=name,
                # Bookable only if at least one rate plan lets you pick 1 or more rooms.
                is_bookable=selector_max is not None and selector_max >= 1,
                room_type_id=room_id,
                selector_max=selector_max,
                scarcity_count=int(match.group(1)) if match else None,
                scarcity_text=scarcity_text,
                prices=tuple(prices),
                rate_plan_count=len(rows),
            )
        )
    return rooms
