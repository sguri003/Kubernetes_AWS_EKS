# Design: Match Kubernetes_AWS_EKS UI to Commodity_Web

## Goal

Make the Kubernetes_AWS_EKS Django app's UI visually and behaviorally match the
Commodity_Web ("GDS Solutions") dashboard — same layout, colors, chart, and
branding — while keeping the data source strictly the local `stock_data.csv`
file (no API endpoints, no database queries).

## Background

- **Commodity_Web** (`C:\Users\test\OneDrive\Documents\Commodity_Web\`) is a
  single-page dashboard: summary price cards, a ticker multi-select grid,
  a flatpickr date range, a Plotly candlestick chart, and a recent-prices
  table. Light/dark theme via CSS variables, glassmorphism styling,
  Bootstrap 5. Data is served live via `/api/summary/` and `/api/prices/`
  JSON endpoints backed by SQL Server / yfinance.
- **Kubernetes_AWS_EKS** currently has two bare, unstyled pages (`home.html`,
  `stocks.html`) with no chart, no JS, no CSS framework. Data comes from a
  static `stock_data.csv` read by `stocks.py` via plain CSV parsing — no DB,
  no network calls.
- The CSV already contains all 14 tickers Commodity_Web tracks
  (`NDX, GSPC, DJI, GC_F, SI_F, PL_F, PA_F, HG_F, CL_F, BZ_F, CVX, XEL, MP, B`),
  though `stocks.py` currently only uses 10 of them. Rows are sorted
  newest→oldest, ~1000 rows spanning 2022 through 2026-06-24, with occasional
  `NULL` fields.

## Non-goals

- No live data refresh — the CSV is static, so "Refresh" / "Auto" controls
  are kept for visual parity only and just re-render the same embedded data.
- No SQL Server, no yfinance, no JSON API endpoints of any kind.
- No change to the Docker/k8s deployment files.

## Design

### 1. Page structure

Replace the two existing pages with a single dashboard page:

- Delete `templates/main/home.html`, `templates/main/stocks.html`.
- Delete the `index` and `stocks_view` view functions in `main/views.py`.
- Add `templates/main/dashboard.html`, adapted from Commodity_Web's
  `stocks/templates/stocks/dashboard.html`: same CSS (theme variables, glass
  effect, navbar, price cards, ticker grid, flatpickr overrides, color
  palette), same "GDS Solutions" branding and dollar-sign logo/favicon, same
  Plotly candlestick chart section, same "Recent Prices" table, same
  light/dark theme toggle and auto-refresh controls.
- `main/urls.py`: single route, `path("", views.dashboard, name="dashboard")`.

### 2. Data: CSV-only, no API layer

`stocks.py` gains two new functions alongside the existing helpers:

- `get_full_price_series()` → `{ticker: {name, dates, opens, highs, lows,
  closes}}` for the entire CSV date range, dates converted from `M/D/YYYY` to
  ISO `YYYY-MM-DD` and sorted **ascending** (oldest→newest), matching
  Commodity_Web's `get_price_series` shape and Plotly's expected input order.
- `get_summary()` → list of `{ticker, name, close, change, change_pct, date}`
  using the two most recent non-null closes per ticker (change = latest close
  − previous close), matching Commodity_Web's summary semantics rather than
  the old open-based calculation in `get_latest_prices`.

`main/views.py`'s `dashboard` view:

- Computes `default_start`/`default_end` anchored to the **CSV's own latest
  date** (not `date.today()`), since the data stops 2026-06-24 and the real
  system date is later — anchoring to real "today" would show a chart with a
  trailing gap of empty days. `default_end = max date in CSV`,
  `default_start = default_end - 365 days`.
- Passes `tickers`, `default_start`, `default_end` as normal context, and the
  full price series + summary as JSON via Django's `json_script` template
  filter (two `<script type="application/json">` blocks, no fetch calls).

### 3. Dashboard JS (adapted from Commodity_Web)

- Reads the two `json_script` blocks into JS objects on page load instead of
  calling `/api/summary/` / `/api/prices/`.
- `loadChart()` becomes a pure client-side filter: given selected tickers
  (from the ticker-grid buttons) and the flatpickr start/end dates, slice the
  preloaded per-ticker arrays to the date range and build the same Plotly
  candlestick traces + layout (palette, grid, legend, dark/light colors,
  `xaxis`/`yaxis` styling, hover mode, margins) as Commodity_Web.
- The "Recent Prices" table is rebuilt from the same filtered arrays (last
  point vs. previous point in the filtered range), same column layout and
  positive/negative coloring as Commodity_Web.
- Summary cards render once from the embedded summary JSON on load.
- "Refresh" button and "Auto" toggle/interval select remain in the UI and
  still trigger a re-render (re-reading the same embedded data + updating the
  "Updated HH:MM:SS" timestamp) — kept for visual/behavioral parity, but they
  never touch the network or produce new numbers, since the source is a
  static file.
- Theme toggle (light/dark), localStorage persistence, and the CSS
  variable-driven Plotly re-color on toggle — copied verbatim.

### 4. Tickers and grouping

`stocks.py` `TICKERS` / `TICKER_LABELS` expand from 10 to all 14 columns
present in the CSV, with the same display names Commodity_Web uses:

| Symbol | Label |
|---|---|
| GC_F | Gold |
| SI_F | Silver |
| PL_F | Platinum |
| PA_F | Palladium |
| HG_F | Copper |
| CL_F | WTI Crude Oil |
| BZ_F | Brent Crude |
| NDX | NASDAQ 100 |
| DJI | Dow Jones |
| GSPC | S&P 500 |
| XEL | Xcel Energy |
| CVX | Chevron |
| MP | MP Materials |
| B | Barnes Group |

Dashboard JS quick-filter groups (same grouping as Commodity_Web, underscore
symbols instead of yfinance symbols):

```js
const METALS  = ['GC_F','SI_F','PL_F','PA_F','HG_F'];
const ENERGY  = ['CL_F','BZ_F'];
const INDICES = ['NDX','DJI','GSPC'];
```

### 5. Branding and static assets

- Copy `favicon.svg` and `dollar_logo.jpg` from
  `Commodity_Web\stocks\static\stocks\` and
  `Commodity_Web\stocks\static\` into `Kubernetes_AWS_EKS\main\static\main\`.
- Update `{% static %}` references in the new template to `main/favicon.svg`
  (Django's `AppDirectoriesFinder` picks these up automatically via
  `INSTALLED_APPS` — no `settings.py` changes needed).
- Keep the "GDS Solutions" navbar text and `<title>` exactly as in
  Commodity_Web.

## Files touched

**Added**
- `templates/main/dashboard.html`
- `main/static/main/favicon.svg`
- `main/static/main/dollar_logo.jpg`

**Modified**
- `stocks.py` — expanded tickers, new `get_full_price_series()` /
  `get_summary()`
- `main/views.py` — single `dashboard` view
- `main/urls.py` — single route

**Deleted**
- `templates/main/home.html`
- `templates/main/stocks.html`

## Testing

- `python manage.py runserver` and load `/` in a browser.
- Verify: summary cards populate for all 14 tickers, candlestick chart
  renders with the default 1-year range, ticker grid toggle updates the
  chart, date-range buttons (1M/3M/6M/1Y/5Y/10Y) and flatpickr both refilter
  correctly, quick-filter buttons (All/None/Metals/Energy/Indices) work,
  light/dark theme toggle re-colors the chart and persists via localStorage,
  Recent Prices table matches the chart's selected tickers/range.
- Confirm no network requests are made to any `/api/...` path (browser dev
  tools Network tab) — everything after initial page load is client-side.
