# fidelis-data

Daily JSON snapshots of BVB trading summaries for selected Fidelis bonds. The collector is designed to run as a short-lived Docker Compose job on Coolify and keep its output in a persistent volume.

## Data and limitations

The collector reads BVB's public [Historical Trading Info](https://www.bvb.ro/TradingAndStatistics/Trading/HistoricalTradingInfo) page. It writes JSON with daily OHLC, average close, reference price, volume, value, trade count, market, and fetch timestamp. Output layout:

```text
data/
├── index.json
├── bonds/R2804AE.json
└── trading/YYYY-MM-DD.json
```

This is an unofficial consumer of the BVB public website, not an official API. BVB's web interface may limit historical downloads to recent dates and can change without notice. The collector archives each run going forward; it does not recreate older daily prices. A date with no matching trade row is treated as an error, so the job will not invent a close for a no-trade session.

## Run locally

```sh
mkdir -p data
docker compose run --rm collector
docker compose run --rm -e SYMBOL_FILTER=R2804AE,R2804A collector
```

The host directory `./data` persists output and is easy to commit or serve. In Coolify set `DATA_HOST_PATH` to a persistent writable path available to scheduled runs.

## Coolify deployment

1. Create a GitHub repository (suggested: `dslave/fidelis-data`) and push this project to `main`.
2. Import it in Coolify as a Docker Compose resource using `docker-compose.yml`.
3. Configure a persistent writable host path in Coolify as `DATA_HOST_PATH`; for example, a Coolify persistent storage mount mapped to `/app/data` inside the service.
4. Set `SYMBOL_FILTER` to a comma-separated list. Default: `R2804AE`.
5. Add a Coolify Scheduled Task / Scheduled Command to run `docker compose run --rm collector` on business days after BVB closes (for example, weekdays at 18:30 Europe/Bucharest). It must use the same `DATA_HOST_PATH` mount as the resource.

To publish JSON files on GitHub Raw, use a dedicated GitHub fine-grained token with Contents: Read and write only for the data repo, store it as a Coolify secret, and add a publishing step that commits the changed JSON. Keep that token out of this repository. The collection output is already ordinary files under `data/`, so it can be committed by a scheduled runner or served by a small read-only HTTP service.

## JSON endpoints after publishing

When `data/` is committed to a public repository, GitHub Raw paths look like:

```text
https://raw.githubusercontent.com/OWNER/REPO/main/data/index.json
https://raw.githubusercontent.com/OWNER/REPO/main/data/bonds/R2804AE.json
https://raw.githubusercontent.com/OWNER/REPO/main/data/trading/YYYY-MM-DD.json
```

## License and attribution

Code is MIT-licensed. Market data is sourced from BVB's public pages; BVB remains the source. Use for informational purposes and verify values against official broker or exchange records.
