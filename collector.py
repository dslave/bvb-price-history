#!/usr/bin/env python3
"""Fetch the BVB public daily trading summary and persist JSON snapshots."""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


URL = os.environ.get(
    "BVB_HISTORY_URL",
    "https://www.bvb.ro/TradingAndStatistics/Trading/HistoricalTradingInfo",
)
DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
SYMBOL_FILTER = {
    item.strip().upper()
    for item in os.environ.get("SYMBOL_FILTER", "R2804AE").split(",")
    if item.strip()
}
LOCAL_TZ = ZoneInfo("Europe/Bucharest")


def number(value: str) -> float | int | None:
    value = value.strip().replace("\u00a0", "")
    if not value or value in {"-", "—"}:
        return None
    value = value.replace(".", "").replace(",", ".")
    try:
        result = float(value)
    except ValueError:
        return None
    return int(result) if result.is_integer() else result


def fetch_rows() -> tuple[str, list[dict]]:
    response = requests.get(
        URL,
        headers={"User-Agent": "fidelis-data/1.0 (daily public BVB data archive)"},
        timeout=30,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    header_row = None
    for row in soup.select("tr"):
        labels = [cell.get_text(" ", strip=True).casefold() for cell in row.select("th, td")]
        if labels and "simbol" in labels and "inchidere" in labels:
            header_row = (row, labels)
            break
    if not header_row:
        raise RuntimeError("Could not find the expected BVB trading table headers")

    header, labels = header_row
    table = header.find_parent("table")
    if table is None:
        raise RuntimeError("BVB table structure changed")
    indexes = {label: idx for idx, label in enumerate(labels)}
    required = ["simbol", "piata", "nr. tranz.", "volum", "valoare", "desch.", "min.", "max.", "mediu", "inchidere", "pret ref.", "var. (%)"]
    missing = [label for label in required if label not in indexes]
    if missing:
        raise RuntimeError(f"BVB table is missing expected columns: {', '.join(missing)}")

    rows = []
    for row in table.select("tr"):
        cells = row.select("td")
        if len(cells) < len(labels):
            continue
        values = [cell.get_text(" ", strip=True) for cell in cells]
        symbol = values[indexes["simbol"]].strip().upper()
        if not re.fullmatch(r"[A-Z0-9.]+", symbol):
            continue
        if SYMBOL_FILTER and symbol not in SYMBOL_FILTER:
            continue
        rows.append({
            "symbol": symbol,
            "market": values[indexes["piata"]],
            "trades": number(values[indexes["nr. tranz."]]),
            "volume": number(values[indexes["volum"]]),
            "value": number(values[indexes["valoare"]]),
            "open": number(values[indexes["desch."]]),
            "low": number(values[indexes["min."]]),
            "high": number(values[indexes["max."]]),
            "avg": number(values[indexes["mediu"]]),
            "close": number(values[indexes["inchidere"]]),
            "refPrice": number(values[indexes["pret ref."]]),
            "changePercent": number(values[indexes["var. (%)"]]),
        })

    if not rows:
        raise RuntimeError(f"No matching bonds found for filter: {', '.join(sorted(SYMBOL_FILTER))}")
    date = datetime.now(LOCAL_TZ).date().isoformat()
    return date, rows


def atomic_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    date, rows = fetch_rows()
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    daily = {
        "date": date,
        "fetchedAt": fetched_at,
        "source": "BVB public Historical Trading Info",
        "symbolsRequested": sorted(SYMBOL_FILTER),
        "bondCount": len(rows),
        "bonds": rows,
    }

    daily_path = DATA_DIR / "trading" / f"{date}.json"
    atomic_json(daily_path, daily)

    index_path = DATA_DIR / "index.json"
    dates = set()
    if index_path.exists():
        existing = json.loads(index_path.read_text(encoding="utf-8"))
        dates.update(existing.get("tradingDates", {}).get("dates", []))
    dates.add(date)
    sorted_dates = sorted(dates)
    index = {
        "lastUpdated": fetched_at,
        "tradingDates": {
            "count": len(sorted_dates),
            "first": sorted_dates[0],
            "last": sorted_dates[-1],
            "dates": sorted_dates,
        },
        "symbols": sorted(SYMBOL_FILTER),
    }
    atomic_json(index_path, index)

    for row in rows:
        atomic_json(DATA_DIR / "bonds" / f"{row['symbol']}.json", {
            "symbol": row["symbol"],
            "lastUpdated": fetched_at,
            "source": "BVB public Historical Trading Info",
            "latestTradingDate": date,
            "latest": row,
        })

    print(f"Saved {len(rows)} matching bond row(s) for {date} under {DATA_DIR}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"collector error: {exc}", file=sys.stderr)
        raise SystemExit(1)
