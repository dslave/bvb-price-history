#!/usr/bin/env python3
"""Fetch daily BVB CSV data for shares, fund units, and bonds."""

from __future__ import annotations

import json
import os
import re
import sys
import time
import csv
import io
import argparse
from datetime import date as Date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Union

import requests


URL = os.environ.get(
    "BVB_HISTORY_URL",
    "https://www.bvb.ro/TradingAndStatistics/Trading/HistoricalTradingInfo.ashx",
)
EXCHSEGMENT = os.environ.get("BVB_EXCHSEGMENT", "BSE")
DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
SYMBOL_FILTER = {item.strip().upper() for item in os.environ.get("SYMBOL_FILTER", "").split(",") if item.strip()}
INSTRUMENT_TYPES = {"s": "share", "u": "fund_unit", "b": "bond"}
HISTORY_LIMIT = 30
try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Europe/Bucharest")
except ImportError:  # Python 3.8 and older
    LOCAL_TZ = timezone.utc

USER_AGENT = os.environ.get(
    "BVB_USER_AGENT",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/132.0.0.0 Safari/537.36",
)


def number(value: str, decimal_separator: str = ",") -> Optional[Union[float, int]]:
    value = value.strip().replace("\u00a0", "")
    if not value or value in {"-", "—"}:
        return None
    if decimal_separator == ".":
        value = value.replace(",", "")
    else:
        value = value.replace(".", "").replace(",", ".")
    try:
        result = float(value)
    except ValueError:
        return None
    return int(result) if result.is_integer() else result


def fetch_day(requested_day: Date) -> List[Dict[str, object]]:
    """Fetch one calendar day from BVB's date-addressable CSV export."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    result_rows: List[Dict[str, object]] = []
    for instrument_type, type_name in INSTRUMENT_TYPES.items():
        params = {
            "day": requested_day.strftime("%Y%m%d"),
            "exchsegment": EXCHSEGMENT,
            "type": instrument_type,
            "filetype": "csv",
            "lang": "en",
        }
        content = ""
        last_error = None
        for attempt in range(3):
            try:
                response = requests.get(URL, params=params, headers=headers, timeout=(15, 45))
                response.raise_for_status()
                content = response.content.decode("utf-8-sig", errors="replace")
                break
            except requests.RequestException as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(2 ** attempt)
        if last_error is not None and not content:
            print(f"WARNING: {requested_day} {type_name}: BVB request failed: {last_error}", file=sys.stderr)
            continue
        if not content.strip() or "<html" in content[:500].casefold() or "<!doctype" in content[:500].casefold():
            print(f"WARNING: {requested_day} {type_name}: no CSV data returned", file=sys.stderr)
            continue
        try:
            _, rows = parse_csv(content, requested_day.isoformat(), type_name)
        except RuntimeError as exc:
            print(f"WARNING: {requested_day} {type_name}: no usable data ({exc})", file=sys.stderr)
            continue
        if not rows:
            print(f"WARNING: {requested_day} {type_name}: no rows; nothing written", file=sys.stderr)
            continue
        result_rows.extend(rows)
    if not result_rows:
        print(f"WARNING: {requested_day}: no market rows; nothing written", file=sys.stderr)
    return result_rows


def parse_csv(content: str, date: str, instrument_type: str) -> Tuple[str, List[Dict[str, object]]]:
    sample = content[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    records = list(csv.reader(io.StringIO(content), dialect))
    if not records:
        return date, []
    header_idx = next((i for i, row in enumerate(records) if any("symbol" in cell.casefold() or "simbol" in cell.casefold() for cell in row)), None)
    if header_idx is None:
        raise RuntimeError("BVB CSV has no recognizable symbol header")
    raw_headers = [cell.strip() for cell in records[header_idx]]
    headers = [re.sub(r"[^a-z0-9%]+", "", cell.casefold()) for cell in raw_headers]
    if not any(header in {"symbol", "simbol"} for header in headers):
        raise RuntimeError("BVB CSV symbol column could not be mapped")
    names = []
    for original, header in zip(raw_headers, headers):
        if header in {"symbol", "simbol"}: name = "symbol"
        elif header in {"market", "piata"}: name = "market"
        elif header in {"nrtransactions", "nrtransaction", "transactions", "trades", "nrtranz", "nrtranzactii"}: name = "trades"
        elif header in {"volume", "volum"}: name = "volume"
        elif header in {"value", "valoare"}: name = "value"
        elif header in {"open", "opening", "desch"}: name = "open"
        elif header in {"low", "min"}: name = "min"
        elif header in {"high", "max"}: name = "max"
        elif header in {"average", "avg", "mediu"}: name = "average"
        elif header in {"close", "closing", "inchidere", "inch"}: name = "close"
        elif header in {"referenceprice", "refprice", "pretref"}: name = "reference_price"
        elif header in {"change%", "changepercent", "variation%", "var", "var%"}: name = "change_percent"
        else: name = re.sub(r"[^a-z0-9]+", "_", original.casefold()).strip("_") or "field"
        names.append(name)
    symbol_idx = names.index("symbol")
    rows = []
    for values in records[header_idx + 1:]:
        if len(values) <= symbol_idx:
            continue
        symbol = values[symbol_idx].strip().upper()
        if not re.fullmatch(r"[A-Z0-9.]+", symbol) or (SYMBOL_FILTER and symbol not in SYMBOL_FILTER):
            continue
        item = {"symbol": symbol, "instrument_type": instrument_type, "date": date}
        for key, raw in zip(names, values):
            raw = raw.strip()
            if key == "symbol":
                continue
            item[key] = raw if key == "market" or not raw else number(raw, decimal_separator=".")
        rows.append(item)
    return date, rows


def atomic_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def has_market_data_changed(path: Path, document: dict, ignored_fields: Tuple[str, ...] = ()) -> bool:
    """Ignore fetch timestamp changes so unchanged snapshots stay untouched."""
    if not path.exists():
        return True
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    existing.pop("fetchedAt", None)
    candidate = dict(document)
    candidate.pop("fetchedAt", None)
    for field in ignored_fields:
        existing.pop(field, None)
        candidate.pop(field, None)
    return existing != candidate


def write_rows(rows: List[Dict[str, object]]) -> Dict[str, List[Dict[str, object]]]:
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    history_updates: Dict[str, List[Dict[str, object]]] = {}
    for row in rows:
        ticker_dir = DATA_DIR / str(row["symbol"])
        record = dict(row)
        record["fetchedAt"] = fetched_at
        record["source"] = "BVB Historical Trading Info CSV export"
        history_updates.setdefault(str(row["symbol"]), []).append(record)
        daily_path = ticker_dir / f"{row['date']}.json"
        if has_market_data_changed(daily_path, record):
            atomic_json(daily_path, record)
        latest_path = ticker_dir / "latest.json"
        existing_date = ""
        if latest_path.exists():
            try:
                existing_date = str(json.loads(latest_path.read_text(encoding="utf-8")).get("date", ""))
            except (OSError, ValueError):
                pass
        # Backfills are fetched newest-to-oldest; never let an older row replace latest.
        if (not existing_date or str(row["date"]) >= existing_date) and has_market_data_changed(
            latest_path, record, ignored_fields=("values",)
        ):
            atomic_json(latest_path, record)
    return history_updates


def history_value(record: Dict[str, object]) -> Optional[Dict[str, object]]:
    """Map one daily snapshot to Wealthfolio's historical-series fields."""
    if record.get("date") is None or record.get("close") is None:
        return None
    item: Dict[str, object] = {"date": record["date"], "close": record["close"]}
    for field in ("open", "average", "trades", "volume", "value", "reference_price", "change_percent", "market"):
        if record.get(field) is not None:
            item[field] = record[field]
    if record.get("max") is not None:
        item["high"] = record["max"]
    if record.get("min") is not None:
        item["low"] = record["min"]
    return item


def write_historical_series(
    updates: Optional[Dict[str, List[Dict[str, object]]]] = None,
) -> int:
    """Write per-ticker historical.json arrays; full scan is for one-time generation."""
    updated = 0
    if updates is None:
        ticker_updates: Dict[str, List[Dict[str, object]]] = {}
        for ticker_dir in DATA_DIR.iterdir():
            if ticker_dir.is_dir():
                records = []
                for daily_path in ticker_dir.glob("????-??-??.json"):
                    try:
                        records.append(json.loads(daily_path.read_text(encoding="utf-8")))
                    except (OSError, ValueError):
                        continue
                if records:
                    ticker_updates[ticker_dir.name] = records
    else:
        ticker_updates = updates

    for symbol, records in ticker_updates.items():
        ticker_dir = DATA_DIR / symbol
        history_path = ticker_dir / "historical.json"
        by_date: Dict[str, Dict[str, object]] = {}
        if updates is not None and history_path.exists():
            try:
                existing = json.loads(history_path.read_text(encoding="utf-8"))
                for item in existing.get("values", []):
                    if item.get("date"):
                        by_date[str(item["date"])] = item
            except (OSError, ValueError, AttributeError):
                pass
        elif updates is not None:
            # New tickers may already have older daily snapshots in the checkout.
            records = []
            for daily_path in ticker_dir.glob("????-??-??.json"):
                try:
                    records.append(json.loads(daily_path.read_text(encoding="utf-8")))
                except (OSError, ValueError):
                    continue

        for record in records:
            item = history_value(record)
            if item:
                by_date[str(item["date"])] = item
        if not by_date:
            continue
        document = {
            "symbol": symbol,
            "instrument_type": next((r.get("instrument_type") for r in records if r.get("instrument_type")), None),
            "source": "BVB market history",
            "values": [by_date[day] for day in sorted(by_date)[-HISTORY_LIMIT:]],
        }
        if has_market_data_changed(history_path, document):
            atomic_json(history_path, document)
            updated += 1
    return updated


def run_backfill(days: int) -> Tuple[int, Dict[str, List[Dict[str, object]]]]:
    """Request each of the last X calendar days, including today."""
    if days < 1:
        raise ValueError("--backfill must be at least 1")
    today = datetime.now(LOCAL_TZ).date()
    total_rows = 0
    history_updates: Dict[str, List[Dict[str, object]]] = {}
    for offset in range(days):
        requested_day = today - timedelta(days=offset)
        rows = fetch_day(requested_day)
        if rows:
            updates = write_rows(rows)
            for symbol, records in updates.items():
                history_updates.setdefault(symbol, []).extend(records)
            total_rows += len(rows)
            print(f"{requested_day}: saved {len(rows)} rows")
        time.sleep(float(os.environ.get("BVB_REQUEST_DELAY", "0.2")))
    return total_rows, history_updates


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect BVB daily market data")
    parser.add_argument("--backfill", type=int, metavar="DAYS",
                        help="fetch the last DAYS calendar days, including today")
    args = parser.parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if args.backfill is not None:
        total_rows, history_updates = run_backfill(args.backfill)
    else:
        today = datetime.now(LOCAL_TZ).date()
        rows = fetch_day(today)
        history_updates = write_rows(rows)
        total_rows = len(rows)
    history_count = write_historical_series(history_updates)
    if history_count:
        print(f"Updated {history_count} historical.json series for Wealthfolio")
    if total_rows:
        print(f"Saved {total_rows} share/fund-unit/bond rows under {DATA_DIR}")
    elif args.backfill is not None:
        print(f"WARNING: no rows found in the last {args.backfill} days; no data files written.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"collector error: {exc}", file=sys.stderr)
        raise SystemExit(1)
