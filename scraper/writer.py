"""Write rows to the per-run CSV and (optionally) append them to a master CSV."""

import csv
from datetime import datetime
from pathlib import Path

from scraper.models import CSV_COLUMNS, RoomRow

FILE_PREFIX = "shivvilas_inventory"  # file name required by the assignment


def _write_rows(handle, rows: list[RoomRow], write_header: bool) -> None:
    """Write rows to an open CSV file handle, in CSV_COLUMNS order."""
    writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
    if write_header:
        writer.writeheader()
    for row in rows:
        writer.writerow(row.to_csv_dict())


def write_run_csv(rows: list[RoomRow], output_dir: str | Path, run_started: datetime) -> Path:
    """Create shivvilas_inventory_<YYYYMMDD_HHMM>.csv and return its path."""
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{FILE_PREFIX}_{run_started:%Y%m%d_%H%M}.csv"
    # newline="" is what the csv module needs so it controls line endings.
    with path.open("w", encoding="utf-8", newline="") as handle:
        _write_rows(handle, rows, write_header=True)
    return path


def append_to_master(rows: list[RoomRow], master_path: str | Path) -> None:
    """Append rows to the master CSV, creating it with a header if needed.

    If the file already exists with different columns, stop instead of
    silently mixing two layouts.
    """
    path = Path(master_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists() or path.stat().st_size == 0
    if not is_new:
        with path.open(encoding="utf-8", newline="") as handle:
            existing_header = next(csv.reader(handle), [])
        if existing_header != CSV_COLUMNS:
            raise ValueError(f"Master CSV {path} has different columns than this program writes")
    with path.open("a", encoding="utf-8", newline="") as handle:
        _write_rows(handle, rows, write_header=is_new)
