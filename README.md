# Booking.com room inventory scraper

Reads the public Booking.com page of a hotel for each of the next 30 stay dates (1 night,
2 adults, 1 room, INR) and writes each room category, an estimate of the rooms available
and the lowest price to a CSV file.

## Important: the hotel in the sample is a stand-in

I could not find **Hotel Shiv Vilas, Tapovan, Rishikesh** on Booking.com (checked 2026-10-16):

- The page that web search suggests, `/hotel/in/shiv-vilas-rishikesh.en-gb.html`, and two
  variants of it all redirect to a generic Rishikesh search page, while other hotel pages
  opened normally in the same browser.
- Searching "Tapovan, Rishikesh" and "Hotel Shiv Vilas Tapovan Rishikesh" did not list it.
  Searching "Shiv Vilas" offered only **Shiv Vilas Palace in Bharatpur, Rajasthan**.
- It is listed on Agoda, Hotels.com and Expedia.

The sample run therefore uses **Shiv Vilas Palace, Bharatpur**, a different hotel in a
different city that only shares part of the name. It is there to show the program working
on real data. To use the right hotel, change `property.url` in `config.yaml` and nothing else.

## Setup and run

Needs Python 3.10 or newer and Google Chrome installed (if Chrome is missing, the program
downloads Playwright's Chromium by itself on the first run). Pick your operating system.

### Windows (PowerShell)

```powershell
cd path\to\tech_associate_assignment
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py --config config.yaml
```

If PowerShell blocks the activate script, run this once, then activate again:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. Or use Command Prompt (cmd) with
`.venv\Scripts\activate`.

### macOS

```bash
cd path/to/tech_associate_assignment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py --config config.yaml
```

### Linux

```bash
cd path/to/tech_associate_assignment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py --config config.yaml
```

On a desktop Linux (with a screen) that is all. On a server with no screen, install the
virtual-screen tool first and, the first time, Chromium's system libraries:
`sudo apt install xvfb` and `playwright install-deps chromium`. The program then starts
its own virtual screen automatically.

- A browser window opens (minimised) and closes by itself. A run takes about 3 minutes.
- It uses the Google Chrome installed on the machine. If there is none, Playwright's
  Chromium is downloaded automatically on the first run.
- Linux without a screen: the program starts a virtual screen (Xvfb) if it is installed
  (`sudo apt install xvfb`). A new Linux machine may also need
  `playwright install-deps chromium` once (needs sudo).
- Docker alternative:
  ```bash
  docker build -t shivvilas-scraper .
  docker run --rm -v "$PWD/outputs:/app/outputs" -v "$PWD/logs:/app/logs" shivvilas-scraper
  ```
- Tests (no network needed): `python -m pytest -q`
- Offline demo (no network, for when Booking.com blocks the machine): rebuild the CSV from
  the saved pages committed in `samples/saved_pages/`:
  ```bash
  python main.py --config config.yaml --from-saved-pages samples/saved_pages
  ```

Output, per run:

- `outputs/shivvilas_inventory_<YYYYMMDD_HHMM>.csv` (IST)
- `outputs/master_inventory.csv`: every run appended, same columns
- `logs/run_<YYYYMMDD_HHMM>.log`

Exit code: `0` clean, `1` finished but some rows have `status=error`, `2` blocked,
interrupted or bad config.

`samples/` has a real run (2026-10-16): 30 dates, 142 rows, 140 `ok` and 2
`no_rooms_listed` (12 and 13 Nov). The 14 Nov rows were compared with the live page and matched.

## Config

All inputs are in `config.yaml`: hotel URL, number of dates, nights, adults, rooms,
currency, language, the 3-second gap, attempts per date, timeout, dropdown cap, browser
options and output folders. The loader refuses a gap below 3 seconds or a currency other
than INR.

## CSV columns

`scrape_timestamp, checkin_date, checkout_date, room_category, rooms_available,
availability_source, min_price_inr, status, room_type_id, scarcity_message, is_capped,
rate_plan_count, error_detail`

Status: `ok` (listed and bookable), `sold_out` (listed but cannot be booked),
`no_rooms_listed` (page loaded and says nothing is available; one row for that date),
`error` (all attempts failed, or the row failed validation).
`min_price_inr` is the lowest price shown for the room before taxes and charges.

## How it works

| File | Job |
|---|---|
| `main.py` | command line, loop over dates, retries, exit codes, logging |
| `scraper/config.py` | reads and checks `config.yaml`, computes the dates |
| `scraper/fetcher.py` | the only network code: loads a page in a browser, returns HTML |
| `scraper/parser.py` | pure function: HTML text in, room categories out (selectors at the top) |
| `scraper/rows.py` | turns parsed rooms into CSV rows; the `rooms_available` rules |
| `scraper/ratelimit.py` | enforces the 3-second gap for every page load, retries included |
| `scraper/validation.py` | no duplicates or negatives, sold-out means 0, check-out = check-in + 1 |
| `scraper/writer.py` | per-run CSV and master CSV |
| `scraper/display.py` | virtual screen on Linux machines without a display |
| `tests/` | unit tests; parser tests use pages saved from the live site |

Ground rules: public pages only, no login, no personal data; one page load at a time, at
least 3 seconds apart; no CAPTCHA or bot-protection bypass (a block page or HTTP 403/429
stops the run, is logged, and the rows collected so far are saved). `robots.txt` disallows
paths such as `/asapi/*` and `/fragment.json`; the program only opens the normal hotel page.

## Answers to the six questions

**1. How did you find the number of rooms available, and why?**
Each room has a "select rooms" dropdown and sometimes a message like "We have 5 left". If
the message exists I use its number (`scarcity_message`); otherwise I use the highest
number in the dropdown across the room's rate plans (`room_selector`). In every page I
saved, the two agreed whenever both were present. It reads only what a visitor sees, needs
no private endpoints, and records where each number came from.

**2. When could `rooms_available` be wrong, and how would someone spot it?**
The dropdown never went above 10, so a true count above 10 shows as 10 (those rows are
flagged `is_capped=True`). It is also only what Booking.com may sell, not the hotel's real
empty rooms. Spot it by filtering `is_capped=True` and comparing a row against the live page.

**3. What would break first if Booking.com changed its page?**
The CSS selectors in `scraper/parser.py`, which are all in one block at the top, with saved
pages and tests next to them. The parser raises an error on a page it does not recognise,
so the date becomes `status=error` instead of a wrong "no rooms". This happened for real:
a headless browser got a page that ignored the stay dates and was reported as an error.

**4. If you ran this daily for a month, how could the CSVs show a booking?**
Compare consecutive runs in `master_inventory.csv` for the same `checkin_date` and
`room_type_id`. A fall in `rooms_available` (say 3 to 2) probably means a booking, a rise a
cancellation. Trust it only when `is_capped=False`. It could also be the hotel closing a room.

**5. How would you cover 50 hotels?**
Make the hotels a list in the config and add a hotel ID column to the CSV. At 1,500 loads
(about 75 minutes), I would run it from a scheduler with a global rate limit, store rows in
a database instead of CSV files, and alert on error and block rates.

**6. Assumptions, and what would you do with one more day?**
Assumptions: 30 dates means tomorrow to tomorrow+29 (`num_dates: 31` gives the other
reading); "today" and timestamps are IST; "at most 3 retries" is implemented as 3 attempts
in total; the stand-in hotel above. With one more day: get the correct Shiv Vilas link from
the assignment contact, and look for a live example of a listed-but-unbookable room.

## Limitations

- **Not the requested hotel** (see top).
- **A visible browser is needed.** Headless browsers were served a page without the stay
  dates, so the program does not use them and does not disguise the browser.
- **One block seen.** On a Windows PC, Playwright's own Chromium got HTTP 403 on the first
  page; the program stopped and logged it. With installed Chrome the same PC completed a
  full run, and so did Docker. I do not know why the first run was blocked, and the site may
  block a machine or network again.
- **Tested on:** macOS (Python 3.15), Linux in Docker (3.12), Windows native and in Docker
  (3.12). Not tested on Python 3.10 or on Linux without Docker.
- **`sold_out` was never seen live.** In 86 hotel pages (8 hotels) no room was listed as
  unbookable: sold-out rooms simply disappear from the table, and a fully sold-out date
  shows "We have no availability" (`no_rooms_listed`). The `sold_out` status is tested
  only on a hand-made page.
- The selectors come from pages seen on 2026-10-16 and may change.

## Running it daily

Cron (macOS/Linux), every day at 06:00:

```cron
0 6 * * * cd /path/to/repo && .venv/bin/python main.py --config config.yaml >> logs/cron.log 2>&1
```

On Windows, use Task Scheduler to run `.venv\Scripts\python.exe main.py --config config.yaml`
in the project folder. Every run appends to `outputs/master_inventory.csv`.
