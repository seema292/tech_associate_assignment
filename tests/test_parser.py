"""Parser tests against pages saved from the live site on 2026-10-16.

Expected values below were read off the live pages with the browser's
developer tools at the time of saving, not produced by the parser.
Hotel A = Tripli Hotels Sukritham, hotel B = Zostel Rishikesh, Tapovan.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from scraper.errors import BlockedError, ParseError
from scraper.parser import looks_blocked, parse_page

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def by_name(rooms):
    return {room.name: room for room in rooms}


# ---------- hotel A, 17 Oct: every room shows a "We have N left" message ----------

def test_hotel_a_oct17_categories_and_ids():
    rooms = parse_page(load("hotel_A_2026-10-17.html"))
    assert [(r.name, r.room_type_id) for r in rooms] == [
        ("Superior Double Room", "1610471801"),
        ("King Room with Balcony", "1610471802"),
        ("Family Suite with Balcony", "1610471804"),
    ]


def test_hotel_a_oct17_dropdown_and_scarcity_agree():
    rooms = by_name(parse_page(load("hotel_A_2026-10-17.html")))
    assert (rooms["Superior Double Room"].selector_max, rooms["Superior Double Room"].scarcity_count) == (5, 5)
    assert (rooms["King Room with Balcony"].selector_max, rooms["King Room with Balcony"].scarcity_count) == (6, 6)
    assert (rooms["Family Suite with Balcony"].selector_max, rooms["Family Suite with Balcony"].scarcity_count) == (1, 1)
    assert rooms["Superior Double Room"].scarcity_text == "We have 5 left"


def test_hotel_a_oct17_prices_and_rate_plans():
    rooms = by_name(parse_page(load("hotel_A_2026-10-17.html")))
    superior = rooms["Superior Double Room"]
    assert superior.rate_plan_count == 3
    assert superior.prices == (Decimal("3000"), Decimal("3500"), Decimal("4500"))
    assert min(rooms["King Room with Balcony"].prices) == Decimal("3500")
    assert min(rooms["Family Suite with Balcony"].prices) == Decimal("5000")


# ---------- hotel A, 8 Nov: one room has a dropdown but no message ----------

def test_hotel_a_nov08_room_without_scarcity_message():
    rooms = by_name(parse_page(load("hotel_A_2026-11-08.html")))
    assert list(rooms) == ["Superior Double Room", "King Room with Balcony",
                           "King Suite with Balcony", "Family Suite with Balcony"]
    king = rooms["King Room with Balcony"]
    assert (king.selector_max, king.scarcity_count, king.scarcity_text) == (9, None, None)
    assert [rooms[n].selector_max for n in rooms] == [5, 9, 3, 3]
    assert [rooms[n].scarcity_count for n in rooms] == [5, None, 3, 3]


# ---------- hotel B, 14 Nov: no messages, two dropdowns stop at exactly 10 ----------

def test_hotel_b_nov14_seven_categories_with_dropdown_maxima():
    rooms = parse_page(load("hotel_B_2026-11-14.html"))
    assert len(rooms) == 7
    assert [r.selector_max for r in rooms] == [4, 1, 2, 10, 8, 10, 6]
    assert all(r.scarcity_count is None for r in rooms)
    assert all(r.is_bookable for r in rooms)


def test_hotel_b_nov14_lowest_prices():
    rooms = parse_page(load("hotel_B_2026-11-14.html"))
    assert [min(r.prices) for r in rooms] == [Decimal(p) for p in (3849, 3849, 6049, 934, 824, 824, 824)]
    assert rooms[3].name == "Bed in 4-Bed Mixed Dormitory Room"


# ---------- dates with nothing to sell ----------

def test_no_availability_page_gives_an_empty_list_not_an_error():
    assert parse_page(load("hotel_B_2026-10-17_noavail.html")) == []


def test_page_that_says_select_dates_is_an_error_not_no_rooms():
    """Seen live in a fresh headless browser: the dates in the URL were dropped."""
    with pytest.raises(ParseError, match="dates were not applied"):
        parse_page(load("hotel_B_no_dates_selected.html"))


# ---------- unrecognised or blocked pages must NOT look like "no rooms" ----------

def test_page_without_hotel_name_is_a_parse_error():
    with pytest.raises(ParseError):
        parse_page("<html><body><h1>Rishikesh: 444 properties found</h1></body></html>")


def test_captcha_page_raises_blocked():
    with pytest.raises(BlockedError):
        parse_page("<html><body>Please complete the CAPTCHA to continue</body></html>")


def test_hotel_page_with_neither_table_nor_notice_is_a_parse_error():
    with pytest.raises(ParseError, match="neither"):
        parse_page('<html><body><span id="hp_hotel_name">X</span></body></html>')


def test_the_word_captcha_on_a_real_hotel_page_is_not_a_block():
    html = load("hotel_A_2026-10-17.html").replace("</body>", "<p>captcha</p></body>")
    assert len(parse_page(html)) == 3


def test_looks_blocked_markers():
    assert looks_blocked("Are you a robot?")
    assert not looks_blocked("Superior Double Room, We have 5 left")


# ---------- SYNTHETIC page (not from the live site): a room that cannot be booked ----------
# We never saw this on the live site. The page below is hand-written to pin down
# the rule "no dropdown value of 1 or more means not bookable".

SYNTHETIC_UNBOOKABLE = """
<html><body>
<span id="hp_hotel_name">Synthetic Hotel</span>
<table id="hprt-table"><tbody>
  <tr class="js-rt-block-row" data-block-id="900_1_2_0_0">
    <th class="hprt-table-cell-roomtype"><a class="hprt-roomtype-link" data-room-id="900">Sold Out Suite</a></th>
    <td><select class="hprt-nos-select" data-room-id="900"><option value="0">0</option></select></td>
  </tr>
</tbody></table>
</body></html>
"""


def test_synthetic_room_with_only_zero_in_dropdown_is_not_bookable():
    (room,) = parse_page(SYNTHETIC_UNBOOKABLE)
    assert room.name == "Sold Out Suite"
    assert room.is_bookable is False
    assert room.prices == ()


def test_synthetic_room_row_without_a_name_is_a_parse_error():
    html = SYNTHETIC_UNBOOKABLE.replace('data-room-id="900">Sold', 'data-room-id="901">Sold')
    with pytest.raises(ParseError, match="no name"):
        parse_page(html)
