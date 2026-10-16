# Booking.com room inventory scraper

Reads the public Booking.com page of one hotel for each of the next 30 stay dates
(1 night, 2 adults, 1 room, INR) and writes the room categories it finds, with an
estimated number of rooms available, to a CSV file.

## Please read first: the property is a stand-in

**Hotel Shiv Vilas, Tapovan, Rishikesh could not be found on Booking.com**, so the
sample run in this repository is for a different property. What I checked on
2026-10-16:

- Three URL variants of the slug that web search suggests
  (`/hotel/in/shiv-vilas-rishikesh.en-gb.html`, the same without `.en-gb`, and with stay
  dates) all redirected to a generic Rishikesh search page. Live hotel pages such as
  `zostel-rishikesh-tapovan` and `tripli-hotels-sukritham` opened normally in the same
  browser, so this looks like a page that no longer exists, but I cannot prove that.
- Searching "Tapovan, Rishikesh" (26 results) and "Hotel Shiv Vilas Tapovan Rishikesh"
  (25 results) did not list it. Searching "Shiv Vilas" in the site's search box offered
  only **Shiv Vilas Palace in Bharatpur, Rajasthan** (a different hotel, see below).
- The hotel does appear on Agoda, Hotels.com and Expedia, but not (any more) on Booking.com
  as far as I could find.

I therefore used **Shiv Vilas Palace in Bharatpur, Rajasthan** (Booking.com slug
`rubystone-shiv-vilas-palace`) as a stand-in. It is a **different hotel in a different
city** (about 280 km from Rishikesh) that only shares part of the name; it is used purely
so the whole pipeline is shown working on real data. The parser was also checked against
two Rishikesh-area hotels (Zostel Rishikesh, Tapovan and Tripli Hotels Sukritham), whose
saved pages are the test fixtures. To point the program at the right hotel, change only
`property.url` in `config.yaml`. The output
file name keeps the required `shivvilas_inventory_` prefix.

## Setup and run (Windows, macOS, Linux)

Python 3.10 or newer. Same commands everywhere; only the activate line differs.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows (cmd): .venv\Scripts\activate
pip install -r requirements.txt
python main.py --config config.yaml
```

(On macOS/Linux the first command may be `python3`; on Windows `py` also works.)

The first run downloads Playwright's Chromium automatically (about 150 MB, one time) and
says so in the log. Runs take about 2.5 minutes: 30 page loads, at least 3 seconds apart.

- **Windows / macOS:** your installed Google Chrome opens (minimised) and closes by itself;
  if Chrome is not installed, Playwright's own Chromium is downloaded and used.
- **Linux with a screen:** same.
- **Linux without a screen (server):** the program notices there is no display and starts
  its own virtual screen (Xvfb) if it is installed (`sudo apt install xvfb`). A fresh Linux machine may also need Chromium's system
  libraries once: `playwright install-deps chromium` (needs sudo).

Developed on macOS with Python 3.15; a full run also worked on Linux (Python 3.12) inside
the Docker image below. The syntax is 3.10-compatible. A native Windows run
also worked (see Limitations).

Outputs:

- `outputs/shivvilas_inventory_<YYYYMMDD_HHMM>.csv` - this run (IST)
- `outputs/master_inventory.csv` - every run appended, same columns
- `logs/run_<YYYYMMDD_HHMM>.log` - run log

Exit code: `0` clean, `1` finished but some rows have `status=error`, `2` blocked,
interrupted or bad config.

A sample real run is in `samples/` (stand-in property in Bharatpur, 2026-10-16 13:30 IST):
30 dates, 142 rows: 140 `ok` and 2 `no_rooms_listed` (12 and 13 Nov had no availability).
Of the `ok` rows, 112 use `room_selector` and 28 use `scarcity_message`; 84 are flagged
`is_capped=True` (dropdown at its apparent limit of 10). The 14 Nov rows were compared
with the live page and matched (five categories; dropdown maxima 10, 10, 10, 2, 8; "We have
2 left" on the Suite).

Tests (no network needed):

```bash
python -m pytest -q
```

## Inputs (config.yaml)

Property URL, number of dates, nights, adults, rooms, currency, language, the 3-second
gap, attempts per date, timeout, the dropdown cap, browser options and output paths all
live in `config.yaml`. The loader refuses a gap below 3 seconds or a currency other
than INR.

## CSV columns (in this exact order)

`scrape_timestamp, checkin_date, checkout_date, room_category, rooms_available,
availability_source, min_price_inr, status` then the bonus columns `room_type_id,
scarcity_message, is_capped, rate_plan_count, error_detail`.

Status values: `ok` (listed and bookable), `sold_out` (listed but cannot be booked),
`no_rooms_listed` (the page loaded and says there is no availability; one row for that
date), `error` (all attempts failed, or the row failed validation).

## How it is organised

| File | Job |
|---|---|
| `main.py` | command line, loop over dates, retries, exit codes, logging |
| `scraper/config.py` | read and check `config.yaml`, compute the dates |
| `scraper/fetcher.py` | **only** network code: loads one page in a browser, returns HTML |
| `scraper/parser.py` | **pure**: HTML text in, room categories out; all CSS selectors in one block |
| `scraper/rows.py` | turns parsed rooms into rows; the `rooms_available` rules live here |
| `scraper/ratelimit.py` | enforces the 3-second gap for every page load, retries included |
| `scraper/validation.py` | no duplicates, no negatives, sold-out means 0, check-out = check-in + 1 |
| `scraper/writer.py` | per-run CSV and master CSV |
| `tests/` | unit tests; parser tests use pages saved from the live site |

## Ground rules followed

- Public hotel pages only: no login, no guest or personal data. Saved fixtures contain
  only the room table (no reviews, cookies or session IDs).
- One page load at a time, at least 3 seconds apart (the limiter also covers retries).
- No CAPTCHA or bot-protection bypass, no stealth plugins, no proxies, no spoofed
  headers. A CAPTCHA/block page or HTTP 403/429 stops the run, is logged, and the rows
  gathered so far are still saved.
- `robots.txt` (checked 2026-10-16) disallows `/asapi/*`, `/fragment.json`,
  `/monthly_minrates*` and similar for all crawlers. The program never calls those; it
  only opens the normal hotel page.
- `outputs/`, `logs/` and `recon/` are git-ignored.

## Answers to the six questions

**1. How did you find the number of rooms available, and why this method?**
The hotel page has a "select rooms" dropdown per rate plan, and sometimes a message
"We have N left" per room type. If the message exists I use N (`scarcity_message`); if
not, I use the highest number in the dropdown, taking the maximum across a room's rate
plans because they share the same rooms (`room_selector`). In every page I saved, the
message and the dropdown maximum were equal whenever both were present. I chose this
because it reads only what a visitor sees, needs no private endpoints, and records which
source each number came from.

**2. When could `rooms_available` be wrong, and how would someone spot it?**
(a) The dropdown seems to stop at 10: across 9 hotels many room types showed exactly 10 and nothing
went higher, so a true count above 10 would be hidden. That is inferred from what I saw,
not documented. Those rows have `is_capped=True`. (b) The number is what Booking.com
is allowed to sell for 2 adults, not the hotel's real empty rooms. (c) A bookable room
with no number would be reported as 1 (`bookable_min_1`, flagged capped); I did not see
this live. (d) If the hotel changes the rate plans shown, the number can move without any
booking. Spot-check by comparing a row with the live page, filtering `is_capped=True`,
and looking at big jumps between runs.

**3. What would break first if Booking.com changed its page?**
The CSS selectors in `scraper/parser.py`. All of them sit in one block at the top, with
saved pages and tests beside them, so a fix means re-saving a page and adjusting that
block. The parser also refuses to guess: an unrecognised page raises an error and the
date is written as `status=error`, instead of being recorded as "no rooms". I hit this
for real: a headless browser was served a page that ignored the stay dates, and the
parser reported "dates were not applied" rather than writing wrong data.

**4. If you ran it daily for a month, how could the CSVs show a booking?**
Compare consecutive runs for the same `checkin_date` and `room_type_id` in
`master_inventory.csv`. If `rooms_available` falls (say 3 to 2) between two daily runs,
that is likely a booking, and a rise is a cancellation or new inventory. Only trust it
when `is_capped=False`; a value stuck at 10 cannot show small changes. A drop may also
be a hotel closing the room, so it is evidence, not proof.

**5. How would you cover 50 hotels instead of one?**
Make `properties` a list in the config, each with its own URL, and run the same fetch,
parse and write steps for each, adding a hotel ID column to the CSV. At 3 seconds per
load, 50 hotels x 30 dates is 1,500 loads, about 75 minutes, so I would run it from a
scheduler with a global rate limit, store rows in a database instead of CSV files,
alert on error and block rates, and check with Booking.com whether an official partner
feed is a better way to get this data.

**6. What assumptions did you make, and what would you do with one more day?**
Assumptions: 30 dates means tomorrow to tomorrow+29 (`num_dates: 31` gives the other
reading); "today" and timestamps are in IST; price is the lowest price shown before taxes
and charges; "3 attempts" means 3 tries in total per date; the stand-in property
described above. With one more day: confirm the dropdown cap with a larger hotel, see
check a busier hotel for a listed-but-unbookable room (I only have a hand-made test page
for that branch), try the real Shiv Vilas page again or ask the assignment contact for
the link, and test on Windows and Linux.

## Limitations (honest list)

- **Not the requested hotel** (see top).
- **Headless mode does not work.** In my test both headless modes (old and new) were
  served a page that dropped the stay dates; a normal visible browser worked. The program
  detects this and reports `error`, and I did not try to disguise the browser. So the
  default is `headless: false`, which needs a screen; on Linux servers the program starts
  its own Xvfb virtual screen.
- **One 403 on Windows, then success.** A first run on a Windows PC using Playwright's own
  Chromium got HTTP 403 on the first page, although the same URL opened normally in the
  user's Chrome. The program did what the ground rules ask: it stopped, logged
  `BLOCKED ... HTTP 403`, wrote the (empty) CSV and did not retry. I did not try to get
  around it. After the default became the installed Chrome (`browser.channel: "chrome"`),
  the same PC completed a full native run (14:18 IST: 142 rows, 140 `ok`, 2
  `no_rooms_listed`), and Docker on it did too. I do not know whether the browser or the
  timing caused the 403, and Booking.com may block a machine or network again; I cannot
  promise it works everywhere.
- **Completed full runs:** macOS (Chrome), Linux in Docker, Windows in Docker and native
  Windows (Chrome), all with the same 142 rows for the stand-in hotel. Native Linux
  without Docker is untested. The code uses `pathlib`, UTF-8 files and no OS-specific
  calls.
- **"Listed but cannot be booked" was never seen live.** I scanned 86 hotel pages with a room
  table (8 hotels, 2026-10-16) for room rows without a usable dropdown, "sold
  out"/"unavailable" wording or sold-out CSS classes inside the room table: none. On the
  live site a room type that is sold out simply disappears from the table (for example 2
  of 7 types remained on 18 Oct), and a date with nothing left shows a "We have no
  availability" notice and no table (`no_rooms_listed`, seen live on 17 Oct at another hotel, and on 12 and 13 Nov in the sample). The
  `sold_out` status is still implemented for the PDF's definition, but it is covered only
  by a hand-written test page. Expect `sold_out` rows to be rare or absent.
- **The 10-room dropdown cap is inferred, not documented.** It is supported by a second
  scan (2026-10-16, 6 more Rishikesh hotels, 5 dates each: 126 room-type observations):
  the highest dropdown value was 10, it was reached 19 times, and nothing went above 10.
  Together with the stand-in hotel and the first two hotels, that is 9 hotels in total
  with no value above 10. A true count above 10 would still look like 10.
- Selectors come from pages seen on 2026-10-16 and may change.
- Tested on Python 3.12 (Windows, Linux) and 3.15 (macOS); not on 3.10, the minimum.
- During development one of my own unit tests accidentally opened the live site for a
  few page loads (a nonexistent hotel page, at the normal 3-second spacing). That test
  was replaced by one using a fake fetcher.

## Docker (optional)

```bash
docker build -t shivvilas-scraper .
docker run --rm -v "$PWD/outputs:/app/outputs" -v "$PWD/logs:/app/logs" shivvilas-scraper
```

The image is `python:3.12-slim` plus `xvfb`, the Python packages and Playwright's Chromium
with its system libraries. Chrome is not installed there, so the program logs a warning and
uses Playwright's Chromium. I ran this on 2026-10-16 on Linux: 142 rows, and every column
except the timestamp was identical to the macOS run made 23 minutes earlier. (The
timestamps in the log lines inside the container are UTC; the CSV timestamps are IST.)
The same image was also run by the author on a Windows PC with Docker Desktop
(2026-10-16 14:06 IST) and gave the same result: 142 rows, 140 `ok` and 2 `no_rooms_listed`
(12 and 13 Nov). The first image build takes a few minutes and downloads about 1 GB.

## Running it daily

With cron (macOS/Linux), every day at 06:00 IST:

```cron
0 6 * * * cd /path/to/shivvilas-scraper && .venv/bin/python main.py --config config.yaml >> logs/cron.log 2>&1
```

On Windows, create a Task Scheduler task that runs `.venv\Scripts\python.exe main.py
--config config.yaml` in the project folder. Each run appends to
`outputs/master_inventory.csv`.
