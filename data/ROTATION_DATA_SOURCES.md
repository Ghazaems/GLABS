# Rotation data contract (personal research)

Verified on 2026-10-04 against the completed 2026-10-02 screening session.

## Free provider coverage observed
- Yahoo `^JKSE` (IHSG) and `^JKLQ45` (LQ45): 1,199 valid daily closes in a requested five-year chart window.
- Yahoo `IDX30.JK`, `IDX80.JK`, `KOMPAS100.JK`, `BISNIS-27.JK`, `MNC36.JK`, `IDXESGL.JK`, and the eleven `IDX*.JK` sector indices: only one valid latest close in the same request. Symbol discovery does not establish historical coverage.
- Stock history samples BBCA.JK and ASGR.JK returned more than 1,200 valid closes.
- Official IDX summary endpoints returned HTTP 403 during direct checks. No bypass, credentials, account creation, or paid feed is used.
These are observed responses, not an availability guarantee. Yahoo can change coverage or throttle requests.

## Publication and automation
The Sector Rotation workflow runs after the completed screening workflow and has an independent weekday recovery schedule. It uses dashboard.market_data_date and its SHA-256, never forces the wall-clock date. Holiday/weekend processing retains the last completed screening session.

Stock history bootstraps from five years, with bounded retries, incremental updates, and an Actions cache. Missing cache can be seeded from the last published history. A weekly full refresh and overlap checks prevent splicing inconsistent split/dividend adjustment bases. Indices accept zero trading volume when the close itself is valid. Neither IPO history nor missing sessions is forward-filled.

The small index archive accumulates actual future observations; one quote is not converted into a synthetic history. Benchmarks need at least 100 verified closes ending on the screening session to be enabled. An available benchmark does not imply every adjustment/range is supported: those are evaluated using actual aligned history. Chart retention is up to 600 sessions, not 600 fabricated observations.

Fresh IHSG and at least 50% fresh requested stock coverage are required before publication. Failures preserve the last valid committed dataset. CI validates dates, source hashes, schema, and regressions before publication; no manual local execution is required.

## Sector alternatives and interpretation
Official sector history is used only if it is fresh and at least 100 aligned sessions long. Otherwise the UI explicitly identifies a **Basket GLABS**: equal-weight average of observed adjusted daily stock returns within the current classification, requiring at least three return pairs per session. Membership can change with historical availability. It is not an official IDX sector index, point-in-time constituent reconstruction, backtest, or a proprietary JdK RRG calculation.

Foreign flow is unavailable without a verified feed. It is not inferred from prices or volume.

## Usage and sources
User confirmed personal use. yfinance is not affiliated with Yahoo and has no SLA. This does not grant redistribution rights for public JSON files; review provider rights before sharing beyond personal research.
- [yfinance documentation and usage disclaimer](https://ranaroussi.github.io/yfinance/)
- [Download API: inclusive start, exclusive end and price adjustment](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html)
- [IDX data services](https://www.idx.id/id/produk/layanan-data-bei/)
- [Twelve Data usage/access distinctions](https://support.twelvedata.com/en/articles/5332349-commercial-and-personal-usage)
- [GitHub workflow events and scheduled execution caveats](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
