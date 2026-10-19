# BVB market data for Wealthfolio

Daily market data for Romanian securities listed on the Bucharest Stock Exchange (BVB), collected as simple JSON files and ready to use as a **latest-price source in Wealthfolio**.

The collector covers shares, fund units, and bonds. It stores the market fields BVB provides, including open, high, low, close, trade count, volume, and traded value when available.

> This is an unofficial community data feed. BVB is the data source; verify important values against BVB or your broker.

## Connect it to Wealthfolio

Wealthfolio supports custom market data providers. Once this repository is public and the JSON files have been committed, add a provider in **Settings → Market Data → Add Custom Provider**:

| Setting | Value |
| --- | --- |
| Name | BVB Daily Data |
| Format | JSON |
| Latest URL | `https://raw.githubusercontent.com/dslave/bvb-price-history/main/data/{SYMBOL}/latest.json` |
| Price Path | `$.close` |
| Date Path | `$.date` |

For historical prices, configure the **Historical** source in the same provider:

| Setting | Value |
| --- | --- |
| Format | JSON |
| URL | `https://raw.githubusercontent.com/dslave/bvb-price-history/main/data/{SYMBOL}/historical.json` |
| Price Path | `$.values[*].close` |
| Date Path | `$.values[*].date` |
| High Path | `$.values[*].high` |
| Low Path | `$.values[*].low` |
| Volume Path | `$.values[*].volume` |

Wealthfolio substitutes `{SYMBOL}` with the asset ticker, for example `R2804AE`. In the asset's market data settings, select **BVB Daily Data** as its preferred provider and enable automatic updates if desired. Make sure the asset's currency is set appropriately (typically RON for BVB listings).

`latest.json` remains a single current quote. `historical.json` contains only the latest 30 available daily quotes for Wealthfolio's Historical source. The per-day JSON snapshots remain available as the longer archive.

See Wealthfolio's [Custom Market Data Providers guide](https://wealthfolio.app/docs/guide/custom-providers/) for current provider options and field mapping.

## Data layout

Each ticker has a latest snapshot and date-addressed snapshots:

```text
data/{SYMBOL}/latest.json
data/{SYMBOL}/historical.json
data/{SYMBOL}/{YYYY-MM-DD}.json
```

For example:

```text
data/R2804AE/latest.json
data/R2804AE/2026-10-16.json
```

Records preserve BVB's available market columns as normalized JSON fields, plus metadata such as `symbol`, `instrument_type`, `date`, `fetchedAt`, and `source`. Price fields include `open`, `min`, `max`, `average`, and `close` when returned by BVB. Activity fields include `trades`, `volume`, and `value` when available. Some records or dates may omit fields that BVB does not provide.

## Run locally

Python 3.9 or newer is recommended. The first run creates a virtual environment and installs the dependencies:

```sh
./run.sh
```

Collect selected tickers:

```sh
SYMBOL_FILTER=R2804AE,TLV ./run.sh
```

By default, the collector fetches the latest available day. Backfill the most recent seven calendar days (including today):

```sh
./run.sh --backfill 7
```

Backfill just one ticker:

```sh
SYMBOL_FILTER=R2804AE ./run.sh --backfill 7
```

Leave `SYMBOL_FILTER` unset to collect all instruments in the configured BVB instrument classes.

## Automated updates with Coolify

Coolify is the scheduled collector and the only automatic publisher. The GitHub Actions workflow is manual-only and remains available for recovery from the repository's **Actions** tab.

Create a Coolify application from this repository and build it with the included `Dockerfile`. It does not expose a network port; the container stays running so Coolify can execute its Scheduled Task. Add a Coolify environment variable named `GITHUB_TOKEN` containing a fine-grained GitHub token restricted to this repository with **Contents: read and write** access. Keep it secret. `BACKFILL_DAYS` defaults to `7` and `BVB_EXCHSEGMENT` defaults to `BSE`.

In the application's **Scheduled Tasks**, add `BACKFILL_DAYS=7 /app/run-on-coolify.sh`, set the timeout to 3600 seconds, and schedule it for weekdays at 20:30. Set the Coolify server timezone to `Europe/Bucharest` so the task stays after the BVB session across daylight-saving changes. Run **Execute now** once and confirm that the execution succeeds and a data commit appears in this repository. Coolify runs scheduled commands inside the running application container and records their execution output.

Each run clones the latest `main`, collects the last seven calendar days, commits only changed files under `data/`, and pushes the commit. If there are no data changes, it exits without making a commit. Avoid running the manual GitHub workflow at the same time as Coolify; the push script retries once if another writer updates `main` during collection.

Because BVB's historical export appears to expose only about the most recent 30 calendar days, the rolling window helps recover recent missed runs; it is not a full historical backfill service. When a date or instrument has no matching BVB rows, the collector logs a warning and writes no empty snapshot.

## Raw JSON URLs

For a public repository, the files are available directly from GitHub:

```text
https://raw.githubusercontent.com/dslave/bvb-price-history/main/data/R2804AE/latest.json
https://raw.githubusercontent.com/dslave/bvb-price-history/main/data/R2804AE/historical.json
https://raw.githubusercontent.com/dslave/bvb-price-history/main/data/R2804AE/2026-10-16.json
```

## Source, scope, and license

The collector requests BVB's date-addressable historical trading export and currently uses the BSE segment. It requests shares, fund units, and bonds separately. The collected figures are market statistics from BVB, not a substitute for broker statements, portfolio transactions, or tax records.

The code is MIT-licensed. Market data is sourced from public BVB pages; BVB remains the data source.
