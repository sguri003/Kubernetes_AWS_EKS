# Live Ticker Quotes — Design

## Problem

The dashboard's summary cards (`main/views.py` `api_summary` → `stocks.get_summary()`) only
reflect whatever is in SQLite, which only changes once per day after the 5PM ET refresh job
(`stocks.refresh_if_stale()`, gated by `REFRESH_HOUR_ET`). During market hours, the cards show
yesterday's closing price all day.

Additionally, the existing "Auto" refresh toggle/interval selector and manual "Refresh" button
(`templates/main/dashboard.html`, `refreshAll()`) don't actually re-fetch anything from the
server — they just re-render the same `SUMMARY`/`PRICES` arrays that were loaded once on initial
page load (`dashboard.html:628-631`). So today, "auto-refresh" is purely cosmetic.

## Goal

Summary cards show a live (intraday) current price and change during market hours, refreshed on
the existing auto-refresh cadence. The historical daily chart is out of scope and stays exactly
as-is — it reflects the daily-close pipeline already built (caching, incremental refresh with
lookback window).

## Design

### 1. Backend: `stocks.get_live_quotes()`

New function in `stocks.py`:

- Single batched intraday call: `yf.download(YF_TICKERS, period="1d", interval="1m",
  group_by="ticker", progress=False)` — one HTTP round trip for all 18 tickers, following the
  same column-normalization pattern as the existing `_yf_download_wide` (strip `=`/`^`, rename to
  our safe column names).
- For each ticker, take the last non-null `Close` value in the intraday series as the live price.
- Previous close for the change/change_pct calculation comes from the existing SQLite data (the
  same source `get_summary()` already reads) — no extra fetch.
- Returns the same row shape as `get_summary()`: `{"ticker", "name", "close", "change",
  "change_pct", "date"}`, so the frontend can reuse its existing rendering logic
  (`renderSummary()`) unchanged. `date` is today's date (`date.today().isoformat()`), not a full
  intraday timestamp — consistent with how `date` is displayed elsewhere on the cards.
- On any exception (network failure, yfinance error, empty response), log via `logger.warning`
  and return `[]` — a live-quote hiccup must not break the page or raise a 500.

### 2. Caching

Module-level cache with a short TTL (15 seconds), same globals pattern as the existing
`_sql_available()` 30-second cache (`_live_quotes_cache` / `_live_quotes_cache_time`). Protects
against multiple browser tabs or pods polling yfinance on overlapping cycles. Not day-scoped like
`get_full_price_series()`'s cache — this one expires quickly since the whole point is freshness.

### 3. New endpoint

`main/views.py`: `api_live(request)` → `JsonResponse(stocks.get_live_quotes(), safe=False)`,
following the exact pattern of `api_summary`/`api_prices`. Wired at `/api/live/` in `main/urls.py`.

### 4. Frontend wiring fix

`refreshAll()` (`templates/main/dashboard.html`) currently only calls `renderSummary()` and
`renderChart()` against already-loaded in-memory arrays. Change it to:

1. `fetch('/api/live/')`
2. Merge the returned rows into the existing `SUMMARY` array by `ticker` (update `close`,
   `change`, `change_pct`, `date`; leave everything else untouched)
3. Call `renderSummary()` (existing rendering code, unchanged)

`renderChart()` / `/api/prices/` are untouched — prices are still fetched once on initial page
load only, per the existing behavior.

### 5. Error handling

- Backend: `get_live_quotes()` never raises past its own boundary — any yfinance/network failure
  results in `[]`, and `api_live` returns `200` with an empty JSON array. The frontend's merge step
  is a no-op if the response is empty, so cards simply keep showing their last known values instead
  of erroring out.
- Frontend: if `fetch('/api/live/')` itself rejects (network error), swallow it in `refreshAll()`
  and leave existing cards untouched, matching how a live-data hiccup should feel to a user
  (stale-but-present beats broken).

### 6. Testing

TDD via `main/tests.py`, following the project's existing conventions:

- `stocks.get_live_quotes()`: mock the yfinance download call, assert the row shape and the
  change/change_pct calculation against a known previous close (reuse the `IncrementalRefreshTests`
  temp-sqlite-db pattern to control what "previous close" is available). Assert `[]` is returned
  and nothing raises when the mocked download fails/returns empty.
- `api_live` view: mock `main.views.stocks.get_live_quotes`, assert the endpoint returns its value
  as JSON, following the exact pattern of the existing `test_api_summary_returns_json_of_stocks_summary`
  test.
- No JS test harness exists in this project; the frontend wiring change will be verified manually
  by running the dev server and observing the summary cards update on the auto-refresh interval,
  rather than by an automated test.

## Out of scope

- Historical/intraday chart rendering (chart stays daily-close only).
- Persisting live quotes to SQLite (they are ephemeral, computed fresh per request/cache window).
- Any change to the daily refresh pipeline (`refresh_if_stale`, `refresh_all_to_sql`) — this is a
  fully separate, additive data path.
