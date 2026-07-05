# Match Commodity_Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Kubernetes_AWS_EKS's two bare pages with a single dashboard page that visually and behaviorally matches Commodity_Web ("GDS Solutions") — same charts, colors, branding — using only the local `stock_data.csv`, no APIs or database.

**Architecture:** `stocks.py` reads the whole CSV once per request and produces (a) a full ascending-date OHLC series per ticker and (b) a summary row per ticker. `main/views.py`'s single `dashboard` view embeds both as JSON (`json_script`) into `templates/main/dashboard.html`, a port of Commodity_Web's `dashboard.html`. The page's JS (adapted from Commodity_Web) filters the embedded data client-side by selected tickers/date-range instead of calling `/api/...` endpoints — no network calls after page load.

**Tech Stack:** Django 5.2 (already installed), Bootstrap 5.3 + Plotly 2.34 + Flatpickr (CDN, same versions as Commodity_Web), stdlib `csv`/`datetime`.

## Global Constraints

- Data source is `stock_data.csv` only — no SQL Server, no yfinance, no JSON API endpoints (per explicit user instruction).
- `/` (root URL) must serve the dashboard directly — it is the landing page.
- Branding, colors, chart styling, and layout must match Commodity_Web's `stocks/templates/stocks/dashboard.html` exactly (per approved spec `docs/superpowers/specs/2026-07-03-match-commodity-web-ui-design.md`).
- This project is not a git repository — no commit steps; each task ends with a manual verification instead.

---

### Task 1: Expand tickers and add CSV-derived data functions

**Files:**
- Modify: `stocks.py`
- Test: `main/tests.py`

**Interfaces:**
- Produces: `stocks.TICKERS` (list of 14 symbol strings), `stocks.TICKER_LABELS` (dict symbol→display name), `stocks.get_full_price_series() -> dict[str, dict]` where each value is `{"name": str, "dates": list[str] (ISO, ascending), "opens": list[float|None], "highs": list[float|None], "lows": list[float|None], "closes": list[float]}`, `stocks.get_summary() -> list[dict]` with keys `ticker, name, close, change, change_pct, date`, `stocks.get_default_range() -> tuple[str, str]` (`(start_iso, end_iso)`, anchored to the CSV's own max date, 365 days apart).
- Consumes: existing `stocks.CSV_PATH`, `stocks._safe_float`.

Replace the whole content of `stocks.py`:

```python
import csv
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "stock_data.csv"

TICKERS = ["GC_F", "SI_F", "PL_F", "PA_F", "HG_F", "CL_F", "BZ_F",
           "NDX", "DJI", "GSPC", "XEL", "CVX", "MP", "B"]

TICKER_LABELS = {
    "GC_F": "Gold",
    "SI_F": "Silver",
    "PL_F": "Platinum",
    "PA_F": "Palladium",
    "HG_F": "Copper",
    "CL_F": "WTI Crude Oil",
    "BZ_F": "Brent Crude",
    "NDX": "NASDAQ 100",
    "DJI": "Dow Jones",
    "GSPC": "S&P 500",
    "XEL": "Xcel Energy",
    "CVX": "Chevron",
    "MP": "MP Materials",
    "B": "Barnes Group",
}


def _safe_float(value):
    try:
        f = float(value)
        return f if f != 0 else None
    except (ValueError, TypeError):
        return None


def _all_rows():
    if not CSV_PATH.exists():
        return []
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _parsed_rows_ascending():
    parsed = []
    for row in _all_rows():
        raw_dt = row.get("Dt")
        if not raw_dt:
            continue
        try:
            d = datetime.strptime(raw_dt, "%m/%d/%Y").date()
        except ValueError:
            continue
        parsed.append((d, row))
    parsed.sort(key=lambda item: item[0])
    return parsed


def get_full_price_series():
    parsed = _parsed_rows_ascending()
    series = {}
    for ticker in TICKERS:
        dates, opens, highs, lows, closes = [], [], [], [], []
        for d, row in parsed:
            close = _safe_float(row.get(f"{ticker}_Close"))
            if close is None:
                continue
            dates.append(d.isoformat())
            opens.append(_safe_float(row.get(f"{ticker}_Open")))
            highs.append(_safe_float(row.get(f"{ticker}_High")))
            lows.append(_safe_float(row.get(f"{ticker}_Low")))
            closes.append(close)
        series[ticker] = {
            "name": TICKER_LABELS.get(ticker, ticker),
            "dates": dates,
            "opens": opens,
            "highs": highs,
            "lows": lows,
            "closes": closes,
        }
    return series


def get_summary():
    series = get_full_price_series()
    rows = []
    for ticker, info in series.items():
        closes = info["closes"]
        if not closes:
            continue
        close = closes[-1]
        if len(closes) >= 2:
            prev = closes[-2]
            change = round(close - prev, 2)
            change_pct = round((change / prev) * 100, 2) if prev else 0.0
        else:
            change = change_pct = 0.0
        rows.append({
            "ticker": ticker,
            "name": info["name"],
            "close": close,
            "change": change,
            "change_pct": change_pct,
            "date": info["dates"][-1],
        })
    rows.sort(key=lambda r: r["name"])
    return rows


def get_default_range():
    series = get_full_price_series()
    all_dates = sorted({d for info in series.values() for d in info["dates"]})
    if not all_dates:
        today = datetime.utcnow().date().isoformat()
        return today, today
    end = all_dates[-1]
    end_date = datetime.strptime(end, "%Y-%m-%d").date()
    start_date = end_date - timedelta(days=365)
    candidates = [d for d in all_dates if d >= start_date.isoformat()]
    start = candidates[0] if candidates else all_dates[0]
    return start, end
```

- [ ] **Step 1: Write the failing tests**

Append to `main/tests.py`:

```python
from django.test import TestCase

import stocks


class StocksDataTests(TestCase):
    def test_tickers_has_fourteen_symbols(self):
        self.assertEqual(len(stocks.TICKERS), 14)
        self.assertIn("PL_F", stocks.TICKERS)
        self.assertIn("MP", stocks.TICKERS)

    def test_full_price_series_covers_all_tickers_ascending(self):
        series = stocks.get_full_price_series()
        self.assertEqual(set(series.keys()), set(stocks.TICKERS))
        gspc = series["GSPC"]
        self.assertGreater(len(gspc["dates"]), 900)
        self.assertEqual(gspc["dates"], sorted(gspc["dates"]))
        self.assertEqual(len(gspc["dates"]), len(gspc["closes"]))

    def test_summary_has_change_vs_previous_close(self):
        summary = stocks.get_summary()
        by_ticker = {row["ticker"]: row for row in summary}
        gspc = by_ticker["GSPC"]
        series = stocks.get_full_price_series()["GSPC"]
        expected_change = round(series["closes"][-1] - series["closes"][-2], 2)
        self.assertEqual(gspc["close"], series["closes"][-1])
        self.assertEqual(gspc["change"], expected_change)
        self.assertEqual(gspc["date"], series["dates"][-1])

    def test_default_range_is_one_year_ending_at_max_data_date(self):
        start, end = stocks.get_default_range()
        series = stocks.get_full_price_series()
        max_date = max(d for info in series.values() for d in info["dates"])
        self.assertEqual(end, max_date)
        self.assertLess(start, end)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "C:\Users\test\OneDrive\Documents\AWS\Kubernetes_AWS_EKS" && venv\Scripts\python manage.py test main -v 2`
Expected: FAIL/ERROR — `get_full_price_series`, `get_summary`, `get_default_range` don't exist yet on the current `stocks.py`.

- [ ] **Step 3: Replace `stocks.py`** with the full content shown above.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "C:\Users\test\OneDrive\Documents\AWS\Kubernetes_AWS_EKS" && venv\Scripts\python manage.py test main -v 2`
Expected: PASS — 4 tests OK.

- [ ] **Step 5: Manual checkpoint** — no commit (no git repo); confirm test output shows `OK` before moving on.

---

### Task 2: Single dashboard view and URL

**Files:**
- Modify: `main/views.py`
- Modify: `main/urls.py`

**Interfaces:**
- Consumes: `stocks.TICKERS`, `stocks.TICKER_LABELS`, `stocks.get_summary()`, `stocks.get_full_price_series()`, `stocks.get_default_range()` (Task 1).
- Produces: `main.views.dashboard(request)` view, rendering `main/dashboard.html` with context keys `tickers` (dict symbol→label), `default_start`, `default_end` (ISO strings), `summary` (list, for `json_script`), `prices` (dict, for `json_script`).

- [ ] **Step 1: Replace `main/views.py`**

```python
from django.shortcuts import render

import stocks


def dashboard(request):
    default_start, default_end = stocks.get_default_range()
    context = {
        "tickers": {t: stocks.TICKER_LABELS.get(t, t) for t in stocks.TICKERS},
        "default_start": default_start,
        "default_end": default_end,
        "summary": stocks.get_summary(),
        "prices": stocks.get_full_price_series(),
    }
    return render(request, "main/dashboard.html", context)
```

- [ ] **Step 2: Replace `main/urls.py`**

```python
from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
]
```

- [ ] **Step 3: Manual checkpoint** — this task has no independent test (the view is only meaningfully testable once the template exists in Task 4); proceed to Task 3.

---

### Task 3: Static assets (favicon)

**Files:**
- Create: `main/static/main/favicon.svg`

**Interfaces:**
- Produces: static file served at `{% static 'main/favicon.svg' %}` (Django `AppDirectoriesFinder` picks up `main/static/` automatically since `main` is in `INSTALLED_APPS` — no `settings.py` change needed).

- [ ] **Step 1: Copy the favicon**

Run:
```bash
mkdir -p "/c/Users/test/OneDrive/Documents/AWS/Kubernetes_AWS_EKS/main/static/main"
cp "/c/Users/test/OneDrive/Documents/Commodity_Web/stocks/static/stocks/favicon.svg" \
   "/c/Users/test/OneDrive/Documents/AWS/Kubernetes_AWS_EKS/main/static/main/favicon.svg"
```

- [ ] **Step 2: Verify the file exists**

Run: `ls "/c/Users/test/OneDrive/Documents/AWS/Kubernetes_AWS_EKS/main/static/main/favicon.svg"`
Expected: file listed, non-zero size.

(Note: `dollar_logo.jpg` exists in Commodity_Web but is not referenced by `dashboard.html` or any active template — confirmed via grep, zero matches — so it is not copied, per YAGNI.)

---

### Task 4: Dashboard template (port of Commodity_Web UI)

**Files:**
- Create: `templates/main/dashboard.html`
- Delete: `templates/main/home.html`
- Delete: `templates/main/stocks.html`

**Interfaces:**
- Consumes: context from Task 2 (`tickers`, `default_start`, `default_end`, `summary`, `prices`), static asset from Task 3 (`main/favicon.svg`).

- [ ] **Step 1: Delete the old templates**

Run:
```bash
rm "/c/Users/test/OneDrive/Documents/AWS/Kubernetes_AWS_EKS/templates/main/home.html"
rm "/c/Users/test/OneDrive/Documents/AWS/Kubernetes_AWS_EKS/templates/main/stocks.html"
```

- [ ] **Step 2: Create `templates/main/dashboard.html`**

Port of Commodity_Web's `stocks/templates/stocks/dashboard.html`. Same `<head>` (Bootstrap 5.3.3, Flatpickr, Plotly 2.34.0 CDN links), same `<style>` block (theme variables, glass, navbar, cards, ticker grid, flatpickr overrides — copied verbatim from Commodity_Web), same body structure (navbar with "GDS Solutions" + favicon, summary cards row, control panel with ticker grid + date pickers + range buttons, chart card, recent-prices table). Differences from Commodity_Web are only in the `<script>` block: data comes from two `json_script` blocks instead of `fetch()`, tickers use underscore symbols, and date helpers anchor to the CSV's max date instead of the real calendar date.

```html
{% load static %}
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GDS Solutions</title>
  <link rel="icon" type="image/svg+xml" href="{% static 'main/favicon.svg' %}">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css" rel="stylesheet">
  <script src="https://cdn.plot.ly/plotly-2.34.0.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
  <style>
    :root {
      --bg-grad:   linear-gradient(135deg, #dde8ff 0%, #eef2ff 35%, #e8f4f0 70%, #fdf6e3 100%);
      --surface:   rgba(255, 255, 255, 0.65);
      --surface-solid: #ffffff;
      --border:    rgba(200, 210, 240, 0.6);
      --text:      #1a1d2e;
      --text-sub:  #2d3055;
      --text-muted:#6c7489;
      --input-bg:  rgba(255, 255, 255, 0.75);
      --hover:     rgba(90, 100, 220, 0.07);
      --accent:    #5059d8;
      --accent-h:  #3f47c4;
      --positive:  #1a8a65;
      --negative:  #cc3333;
      --shadow:    0 4px 24px rgba(80, 89, 216, 0.10);
      --shadow-sm: 0 2px 10px rgba(80, 89, 216, 0.07);
      --blur:      blur(18px);
    }
    [data-theme="dark"] {
      --bg-grad:   linear-gradient(135deg, #0a0c14 0%, #0f1117 50%, #0d1020 100%);
      --surface:   rgba(26, 29, 46, 0.80);
      --surface-solid: #1a1d2e;
      --border:    rgba(60, 70, 120, 0.55);
      --text:      #e0e0e0;
      --text-sub:  #c9cde8;
      --text-muted:#778;
      --input-bg:  rgba(15, 17, 23, 0.85);
      --hover:     rgba(124, 131, 253, 0.10);
      --accent:    #7c83fd;
      --accent-h:  #6870e8;
      --positive:  #26a17b;
      --negative:  #e05252;
      --shadow:    0 4px 24px rgba(0, 0, 0, 0.35);
      --shadow-sm: 0 2px 10px rgba(0, 0, 0, 0.25);
      --blur:      blur(18px);
    }
    *, *::before, *::after { transition: background-color .25s, border-color .25s, color .2s, box-shadow .25s; }
    html, body { min-height: 100%; }
    body {
      background: var(--bg-grad);
      background-attachment: fixed;
      color: var(--text);
      font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    }
    .glass {
      background: var(--surface);
      backdrop-filter: var(--blur);
      -webkit-backdrop-filter: var(--blur);
      border: 1px solid var(--border);
      box-shadow: var(--shadow);
      border-radius: 14px;
    }
    .navbar {
      background: var(--surface) !important;
      backdrop-filter: var(--blur) !important;
      -webkit-backdrop-filter: var(--blur) !important;
      border-bottom: 1px solid var(--border) !important;
      box-shadow: var(--shadow-sm) !important;
    }
    .navbar-brand { color: var(--accent) !important; font-weight: 700; letter-spacing: .5px; }
    .card {
      background: var(--surface);
      backdrop-filter: var(--blur);
      -webkit-backdrop-filter: var(--blur);
      border: 1px solid var(--border);
      border-radius: 14px;
      box-shadow: var(--shadow);
    }
    .price-card { transition: transform .18s, box-shadow .18s; }
    .price-card:hover { transform: translateY(-4px); box-shadow: 0 8px 32px rgba(80,89,216,0.15); }
    .price-card .ticker { font-size: .72rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1.2px; }
    .price-card .name   { font-size: .88rem; font-weight: 600; color: var(--text-sub); }
    .price-card .close  { font-size: 1.4rem; font-weight: 700; }
    .price-card .change { font-size: .84rem; font-weight: 500; }
    .positive { color: var(--positive); }
    .negative { color: var(--negative); }
    .neutral  { color: var(--text-muted); }
    .ctrl-panel {
      background: var(--surface);
      backdrop-filter: var(--blur);
      -webkit-backdrop-filter: var(--blur);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 1rem 1.25rem;
      box-shadow: var(--shadow-sm);
    }
    .form-control, .form-select {
      background: var(--input-bg);
      backdrop-filter: blur(8px);
      color: var(--text);
      border-color: var(--border);
      border-radius: 8px;
    }
    .form-control:focus, .form-select:focus {
      background: var(--input-bg); color: var(--text);
      border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 18%, transparent);
    }
    .input-group-text {
      background: var(--input-bg);
      backdrop-filter: blur(8px);
      border-color: var(--border);
      color: var(--accent);
    }
    .btn-primary { background: var(--accent); border-color: var(--accent); color: #fff; border-radius: 8px; }
    .btn-primary:hover { background: var(--accent-h); border-color: var(--accent-h); }
    .btn-outline-secondary {
      border-color: var(--border); color: var(--text-muted);
      background: var(--input-bg); border-radius: 8px;
    }
    .btn-outline-secondary:hover { background: var(--hover); color: var(--text); border-color: var(--accent); }
    .btn-refresh {
      background: var(--input-bg); border: 1px solid var(--border);
      color: var(--accent); transition: all .2s; border-radius: 8px;
      backdrop-filter: blur(8px);
    }
    .btn-refresh:hover { background: color-mix(in srgb, var(--accent) 12%, transparent); border-color: var(--accent); color: var(--accent); }
    .btn-refresh.refreshing svg { animation: spin .7s linear infinite; }
    .btn-theme {
      background: var(--input-bg); border: 1px solid var(--border);
      color: var(--text-muted); padding: 4px 10px; border-radius: 8px;
      transition: all .2s; cursor: pointer; backdrop-filter: blur(8px);
    }
    .btn-theme:hover { border-color: var(--accent); color: var(--accent); }
    .btn-theme .icon-sun  { display: none; }
    .btn-theme .icon-moon { display: inline; }
    [data-theme="light"] .btn-theme .icon-sun  { display: inline; }
    [data-theme="light"] .btn-theme .icon-moon { display: none; }
    #chart { height: 480px; }
    .table { color: var(--text-sub); }
    .table thead th {
      border-color: var(--border); color: var(--accent);
      font-size: .78rem; text-transform: uppercase; letter-spacing: .7px;
      background: transparent;
    }
    .table tbody tr { border-color: var(--border); }
    .table tbody tr:hover td { background: var(--hover); }
    .table-section-label { font-size: .78rem; letter-spacing: .9px; text-transform: uppercase; color: var(--text-muted); font-weight: 600; }
    .spinner-border { width: 1.2rem; height: 1.2rem; }
    #summary-cards .col { min-width: 160px; }
    .auto-badge {
      font-size: .7rem; padding: 2px 8px; border-radius: 20px;
      background: color-mix(in srgb, var(--positive) 15%, transparent);
      color: var(--positive); border: 1px solid color-mix(in srgb, var(--positive) 35%, transparent);
    }
    .flash { animation: flashIn .4s ease; }
    @keyframes flashIn { from { opacity: 0; transform: translateY(-6px); } to { opacity: 1; transform: translateY(0); } }
    @keyframes spin { to { transform: rotate(360deg); } }
    #start-date, #end-date { cursor: pointer; caret-color: transparent; }
    .ticker-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(108px, 1fr));
      gap: 5px;
    }
    .ticker-btn {
      background: var(--input-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 6px 9px;
      cursor: pointer;
      text-align: left;
      transition: background .15s, border-color .15s, color .15s;
      color: var(--text-muted);
      line-height: 1;
    }
    .ticker-btn .sym {
      display: block;
      font-size: .7rem;
      font-weight: 700;
      letter-spacing: .9px;
      text-transform: uppercase;
      color: var(--text-sub);
      margin-bottom: 2px;
    }
    .ticker-btn .nm {
      display: block;
      font-size: .68rem;
      line-height: 1.25;
      color: var(--text-muted);
    }
    .ticker-btn.active {
      background: color-mix(in srgb, var(--accent) 14%, transparent);
      border-color: var(--accent);
    }
    .ticker-btn.active .sym { color: var(--accent); }
    .ticker-btn.active .nm  { color: var(--text-sub); }
    .ticker-btn:hover:not(.active) {
      background: var(--hover);
      border-color: var(--accent);
    }
    .flatpickr-calendar {
      background: var(--surface-solid) !important;
      border: 1px solid var(--border) !important;
      box-shadow: 0 12px 40px rgba(80,89,216,0.15) !important;
      border-radius: 14px !important;
      color: var(--text) !important;
    }
    .flatpickr-months, .flatpickr-month { background: transparent !important; color: var(--text-sub) !important; fill: var(--text-sub) !important; }
    .flatpickr-current-month input.cur-year,
    .flatpickr-current-month .flatpickr-monthDropdown-months { color: var(--text-sub) !important; background: transparent !important; }
    .flatpickr-weekday { color: var(--accent) !important; background: transparent !important; font-weight: 600; }
    .flatpickr-day { color: var(--text) !important; border-color: transparent !important; border-radius: 8px !important; }
    .flatpickr-day:hover { background: var(--hover) !important; border-color: transparent !important; }
    .flatpickr-day.selected, .flatpickr-day.startRange, .flatpickr-day.endRange {
      background: var(--accent) !important; border-color: var(--accent) !important; color: #fff !important;
    }
    .flatpickr-day.inRange {
      background: color-mix(in srgb, var(--accent) 15%, transparent) !important;
      border-color: transparent !important;
      box-shadow: -5px 0 0 color-mix(in srgb, var(--accent) 15%, transparent),
                   5px 0 0 color-mix(in srgb, var(--accent) 15%, transparent) !important;
      color: var(--text) !important;
    }
    .flatpickr-day.today { border-color: #e8b84b !important; }
    .flatpickr-day.today:hover { background: rgba(232,184,75,.15) !important; }
    .flatpickr-day.flatpickr-disabled { color: var(--text-muted) !important; opacity: .35; }
    .flatpickr-prev-month svg, .flatpickr-next-month svg { fill: var(--accent) !important; }
  </style>
</head>
<body>

<nav class="navbar navbar-expand-lg mb-4">
  <div class="container-fluid px-4">
    <span class="navbar-brand fs-5 d-flex align-items-center gap-2">
      <img src="{% static 'main/favicon.svg' %}" width="30" height="30" alt="GDS logo">
      GDS Solutions
    </span>
    <div class="ms-auto d-flex align-items-center gap-3">
      <span class="text-muted small" id="last-updated"></span>
      <div class="d-flex align-items-center gap-2">
        <div class="form-check form-switch mb-0 d-flex align-items-center gap-2">
          <input class="form-check-input" type="checkbox" id="auto-refresh-toggle" style="cursor:pointer;">
          <label class="form-check-label small text-muted" for="auto-refresh-toggle" style="cursor:pointer;">Auto</label>
        </div>
        <select id="interval-select" class="form-select form-select-sm" style="width:auto;font-size:.8rem;">
          <option value="15">15s</option>
          <option value="30">30s</option>
          <option value="60" selected>60s</option>
          <option value="300">5m</option>
          <option value="600">10m</option>
          <option value="1800">30m</option>
        </select>
        <span id="auto-badge" class="auto-badge d-none">Auto</span>
      </div>
      <button id="refresh-btn" class="btn btn-refresh btn-sm px-3" onclick="refreshAll()">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="me-1">
          <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
          <path d="M3.51 9a9 9 0 0 1 14.36-3.36L23 10M1 14l5.13 4.36A9 9 0 0 0 20.49 15"/>
        </svg>Refresh
      </button>
      <button class="btn-theme" id="theme-toggle" title="Toggle light/dark mode">
        <svg class="icon-moon" xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
        </svg>
        <svg class="icon-sun" xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="5"/>
          <line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>
          <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
          <line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>
          <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
        </svg>
      </button>
    </div>
  </div>
</nav>

<div class="container-fluid px-4">

  <div class="row g-3 mb-4" id="summary-cards">
    <div class="col-12 text-center text-muted py-3">
      <span class="spinner-border me-2"></span> Loading prices&hellip;
    </div>
  </div>

  <div class="ctrl-panel mb-4">
    <div class="row g-3 align-items-end">
      <div class="col-md-5">
        <label class="form-label small text-muted mb-1">Tickers</label>
        <div class="ticker-grid" id="ticker-grid">
          {% for symbol, name in tickers.items %}
          <button class="ticker-btn active" data-ticker="{{ symbol }}" onclick="toggleTicker(this)">
            <span class="sym">{{ symbol }}</span>
            <span class="nm">{{ name }}</span>
          </button>
          {% endfor %}
        </div>
        <div class="d-flex gap-2 mt-2">
          <button class="btn btn-outline-secondary btn-sm py-0" onclick="selectAll()">All</button>
          <button class="btn btn-outline-secondary btn-sm py-0" onclick="selectNone()">None</button>
          <button class="btn btn-outline-secondary btn-sm py-0" onclick="selectMetals()">Metals</button>
          <button class="btn btn-outline-secondary btn-sm py-0" onclick="selectEnergy()">Energy</button>
          <button class="btn btn-outline-secondary btn-sm py-0" onclick="selectIndices()">Indices</button>
        </div>
      </div>
      <div class="col-md-1" style="min-width:130px">
        <label class="form-label small text-muted mb-1">Start Date</label>
        <div class="input-group input-group-sm">
          <span class="input-group-text">
            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" fill="currentColor" viewBox="0 0 16 16">
              <path d="M3.5 0a.5.5 0 0 1 .5.5V1h8V.5a.5.5 0 0 1 1 0V1h1a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V3a2 2 0 0 1 2-2h1V.5a.5.5 0 0 1 .5-.5zM1 4v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V4H1z"/>
            </svg>
          </span>
          <input type="text" id="start-date" class="form-control form-control-sm" placeholder="Start" readonly>
        </div>
      </div>
      <div class="col-md-1" style="min-width:130px">
        <label class="form-label small text-muted mb-1">End Date</label>
        <div class="input-group input-group-sm">
          <span class="input-group-text">
            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" fill="currentColor" viewBox="0 0 16 16">
              <path d="M3.5 0a.5.5 0 0 1 .5.5V1h8V.5a.5.5 0 0 1 1 0V1h1a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V3a2 2 0 0 1 2-2h1V.5a.5.5 0 0 1 .5-.5zM1 4v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V4H1z"/>
            </svg>
          </span>
          <input type="text" id="end-date" class="form-control form-control-sm" placeholder="End" readonly>
        </div>
      </div>
      <div class="col-md-2 d-flex gap-2 align-items-end">
        <button class="btn btn-primary btn-sm" onclick="renderChart()">
          <span id="chart-spinner" class="spinner-border d-none me-1"></span>Update Chart
        </button>
        <button class="btn btn-outline-secondary btn-sm" onclick="clearChart()" title="Reset to all tickers · 1 month">
          <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="me-1">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>Clear / Reset
        </button>
      </div>
      <div class="col-md-2 d-flex gap-1 flex-wrap">
        <button class="btn btn-outline-secondary btn-sm" onclick="setRange(30)">1M</button>
        <button class="btn btn-outline-secondary btn-sm" onclick="setRange(90)">3M</button>
        <button class="btn btn-outline-secondary btn-sm" onclick="setRange(180)">6M</button>
        <button class="btn btn-outline-secondary btn-sm" onclick="setRange(365)">1Y</button>
        <button class="btn btn-outline-secondary btn-sm" onclick="setRange(1825)">5Y</button>
        <button class="btn btn-outline-secondary btn-sm" onclick="setRange(3650)">10Y</button>
      </div>
    </div>
  </div>

  <div class="card mb-4 p-3">
    <div id="chart"></div>
  </div>

  <div class="card p-3 mb-5">
    <h6 class="table-section-label mb-3">Recent Prices</h6>
    <div class="table-responsive">
      <table class="table table-sm table-hover align-middle mb-0">
        <thead>
          <tr>
            <th>Ticker</th><th>Name</th><th>Date</th>
            <th class="text-end">Close</th><th class="text-end">Change</th><th class="text-end">Change %</th>
          </tr>
        </thead>
        <tbody id="table-body">
          <tr><td colspan="6" class="text-center text-muted">Loading&hellip;</td></tr>
        </tbody>
      </table>
    </div>
  </div>

</div>

{{ summary|json_script:"summary-data" }}
{{ prices|json_script:"prices-data" }}

<script>
const SUMMARY = JSON.parse(document.getElementById('summary-data').textContent);
const PRICES  = JSON.parse(document.getElementById('prices-data').textContent);
const DATA_END = '{{ default_end }}';

const METALS  = ['GC_F','SI_F','PL_F','PA_F','HG_F'];
const ENERGY  = ['CL_F','BZ_F'];
const INDICES = ['NDX','DJI','GSPC'];
const PALETTE = [
  '#7c83fd','#26a17b','#e8b84b','#e05252','#56c8d8',
  '#b48ef7','#f7a35c','#90ed7d','#f15c80','#8085e9',
  '#f7cb5c','#2b908f','#91e8e1'
];

function isDark() { return document.documentElement.dataset.theme !== 'light'; }

function plotlyLayout() {
  return isDark()
    ? { paper: '#1a1d2e', plot: '#0f1117', font: '#c9cde8', grid: 'rgba(60,70,120,0.4)' }
    : { paper: '#ffffff', plot: 'rgba(255,255,255,0.15)', font: '#1a1d2e', grid: 'rgba(120,150,220,0.45)' };
}

function applyTheme(dark) {
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  localStorage.setItem('gds-theme', dark ? 'dark' : 'light');
  const el = document.getElementById('chart');
  if (el && el.data && el.data.length) {
    const c = plotlyLayout();
    Plotly.relayout('chart', {
      paper_bgcolor: c.paper,
      plot_bgcolor:  c.plot,
      'font.color':  c.font,
      'xaxis.gridcolor': c.grid,
      'yaxis.gridcolor': c.grid,
      'legend.bordercolor': c.grid,
    });
  }
}

document.getElementById('theme-toggle').addEventListener('click', () => {
  applyTheme(!isDark());
});

const saved = localStorage.getItem('gds-theme');
if (saved) applyTheme(saved === 'dark');

function fmtNum(n, dec=2) {
  return n == null ? '—' : Number(n).toLocaleString('en-US', {minimumFractionDigits: dec, maximumFractionDigits: dec});
}
function today()    { return DATA_END; }
function daysAgo(n) { const d = new Date(DATA_END); d.setDate(d.getDate()-n); return d.toISOString().slice(0,10); }

function toggleTicker(btn) {
  btn.classList.toggle('active');
}
function clearChart() {
  selectAll();
  setRange(30);
}
function selectedTickers() {
  return [...document.querySelectorAll('.ticker-btn.active')].map(b => b.dataset.ticker);
}
function selectAll()    { document.querySelectorAll('.ticker-btn').forEach(b => b.classList.add('active')); }
function selectNone()   { document.querySelectorAll('.ticker-btn').forEach(b => b.classList.remove('active')); }
function selectMetals()  { selectNone(); document.querySelectorAll('.ticker-btn').forEach(b => { if(METALS.includes(b.dataset.ticker))  b.classList.add('active'); }); }
function selectEnergy()  { selectNone(); document.querySelectorAll('.ticker-btn').forEach(b => { if(ENERGY.includes(b.dataset.ticker))  b.classList.add('active'); }); }
function selectIndices() { selectNone(); document.querySelectorAll('.ticker-btn').forEach(b => { if(INDICES.includes(b.dataset.ticker)) b.classList.add('active'); }); }

const FP_OPTS = {
  dateFormat: 'Y-m-d',
  disableMobile: true,
};

const startPicker = flatpickr('#start-date', {
  ...FP_OPTS,
  defaultDate: '{{ default_start }}',
  maxDate: '{{ default_end }}',
  onChange([date]) {
    if (date) endPicker.set('minDate', date);
    if (date && endPicker.selectedDates[0]) renderChart();
  },
});

const endPicker = flatpickr('#end-date', {
  ...FP_OPTS,
  defaultDate: '{{ default_end }}',
  minDate: '{{ default_start }}',
  maxDate: today(),
  onChange([date]) {
    if (date) startPicker.set('maxDate', date);
    if (date && startPicker.selectedDates[0]) renderChart();
  },
});

function getPickerDates() {
  const s = startPicker.selectedDates[0];
  const e = endPicker.selectedDates[0];
  return {
    start: s ? startPicker.formatDate(s, 'Y-m-d') : daysAgo(365),
    end:   e ? endPicker.formatDate(e,   'Y-m-d') : today(),
  };
}

function setRange(days) {
  const s = daysAgo(days), e = today();
  startPicker.setDate(s);
  endPicker.setDate(e);
  startPicker.set('maxDate', e);
  endPicker.set('minDate', s);
  renderChart();
}

function renderSummary() {
  const cards = document.getElementById('summary-cards');
  cards.innerHTML = '';
  SUMMARY.forEach(row => {
    const sign  = row.change > 0 ? '+' : '';
    const cls   = row.change > 0 ? 'positive' : row.change < 0 ? 'negative' : 'neutral';
    const arrow = row.change > 0 ? '▲' : row.change < 0 ? '▼' : '—';
    cards.innerHTML += `
      <div class="col flash">
        <div class="card price-card p-3 h-100">
          <div class="ticker">${row.ticker}</div>
          <div class="name">${row.name}</div>
          <div class="close mt-1">${fmtNum(row.close)}</div>
          <div class="change ${cls}">${arrow} ${sign}${fmtNum(row.change)} (${sign}${fmtNum(row.change_pct)}%)</div>
          <div class="ticker mt-1">${row.date}</div>
        </div>
      </div>`;
  });
  document.getElementById('last-updated').textContent = 'Updated ' + new Date().toLocaleTimeString();
}

let autoTimer = null;

function refreshAll() {
  const btn = document.getElementById('refresh-btn');
  btn.classList.add('refreshing'); btn.disabled = true;
  try { renderSummary(); renderChart(); }
  finally { btn.classList.remove('refreshing'); btn.disabled = false; }
}

function intervalLabel(s) { return s >= 60 ? (s/60)+'m' : s+'s'; }

function startAutoRefresh() {
  clearInterval(autoTimer);
  const sec = parseInt(document.getElementById('interval-select').value, 10);
  document.getElementById('auto-badge').textContent = 'Auto ' + intervalLabel(sec);
  autoTimer = setInterval(refreshAll, sec * 1000);
}

document.getElementById('auto-refresh-toggle').addEventListener('change', function () {
  const badge = document.getElementById('auto-badge');
  if (this.checked) { badge.classList.remove('d-none'); startAutoRefresh(); }
  else              { badge.classList.add('d-none'); clearInterval(autoTimer); autoTimer = null; }
});
document.getElementById('interval-select').addEventListener('change', () => {
  if (document.getElementById('auto-refresh-toggle').checked) startAutoRefresh();
});

function filterSeries(sym, start, end) {
  const info = PRICES[sym];
  if (!info) return null;
  const dates = [], opens = [], highs = [], lows = [], closes = [];
  for (let i = 0; i < info.dates.length; i++) {
    const d = info.dates[i];
    if (d >= start && d <= end) {
      dates.push(d); opens.push(info.opens[i]); highs.push(info.highs[i]);
      lows.push(info.lows[i]); closes.push(info.closes[i]);
    }
  }
  return { name: info.name, dates, opens, highs, lows, closes };
}

function renderChart() {
  const tickers = selectedTickers();
  if (!tickers.length) return;
  const { start, end } = getPickerDates();
  const spinner = document.getElementById('chart-spinner');
  spinner.classList.remove('d-none');

  const data = {};
  tickers.forEach(sym => {
    const filtered = filterSeries(sym, start, end);
    if (filtered && filtered.dates.length) data[sym] = filtered;
  });
  spinner.classList.add('d-none');

  const traces = Object.entries(data).map(([sym, info], i) => {
    const col = PALETTE[i % PALETTE.length];
    return {
      x:     info.dates,
      open:  info.opens,
      high:  info.highs,
      low:   info.lows,
      close: info.closes,
      name:  info.name,
      type:  'candlestick',
      increasing: { line: { color: col }, fillcolor: col },
      decreasing: { line: { color: col }, fillcolor: 'rgba(0,0,0,0)' },
    };
  });

  const c = plotlyLayout();
  const layout = {
    paper_bgcolor: c.paper, plot_bgcolor: c.plot,
    font:   { color: c.font, size: 12 },
    xaxis:  { gridcolor: c.grid, showgrid: true, gridwidth: 1, griddash: 'dot', zeroline: false, linecolor: c.grid, showline: true, mirror: true, rangeslider: { visible: false } },
    yaxis:  { gridcolor: c.grid, showgrid: true, gridwidth: 1, griddash: 'dot', zeroline: false, linecolor: c.grid, showline: true, mirror: true, tickprefix: '$' },
    legend: {
      bgcolor: '#ffffff',
      bordercolor: 'rgba(120,150,220,0.5)',
      borderwidth: 1,
      font: { size: 11, color: '#1a1d2e' },
      orientation: 'v',
      x: 1.01, xanchor: 'left',
      y: 1,    yanchor: 'top',
      tracegroupgap: 4,
    },
    margin: { t: 20, r: 160, b: 50, l: 70 },
    hovermode: 'x unified',
  };
  Plotly.react('chart', traces, layout, { responsive: true, displayModeBar: false });

  const tbody = document.getElementById('table-body');
  tbody.innerHTML = '';
  Object.entries(data).forEach(([sym, info]) => {
    const last = info.dates.length - 1;
    if (last < 0) return;
    const close = info.closes[last];
    const prev  = last > 0 ? info.closes[last-1] : close;
    const change = +(close - prev).toFixed(2);
    const changePct = prev ? +((change/prev)*100).toFixed(2) : 0;
    const sign = change >= 0 ? '+' : '';
    const cls  = change > 0 ? 'positive' : change < 0 ? 'negative' : 'neutral';
    tbody.innerHTML += `
      <tr>
        <td><code class="text-info">${sym}</code></td>
        <td>${info.name}</td>
        <td class="text-muted">${info.dates[last]}</td>
        <td class="text-end">${fmtNum(close)}</td>
        <td class="text-end ${cls}">${sign}${fmtNum(change)}</td>
        <td class="text-end ${cls}">${sign}${fmtNum(changePct)}%</td>
      </tr>`;
  });
  document.getElementById('last-updated').textContent = 'Updated ' + new Date().toLocaleTimeString();
}

renderSummary();
renderChart();
</script>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
```

- [ ] **Step 3: Manual checkpoint** — proceed to Task 5 for end-to-end verification.

---

### Task 5: End-to-end verification

**Files:** none (manual browser check)

- [ ] **Step 1: Run the dev server**

Run: `cd "C:\Users\test\OneDrive\Documents\AWS\Kubernetes_AWS_EKS" && venv\Scripts\python manage.py runserver 8000`

- [ ] **Step 2: Load `http://127.0.0.1:8000/`** in a browser and verify:
  - Page loads directly to the dashboard (no separate home page) — confirms it's the landing page.
  - 14 summary cards render with ticker, name, close, change, date.
  - Candlestick chart renders for the default 1-year range ending at the CSV's last date (2026-06-24).
  - Toggling ticker buttons and clicking "Update Chart" changes the chart/table.
  - "Metals" / "Energy" / "Indices" / "All" / "None" quick-filters select the right tickers.
  - Date range buttons (1M/3M/6M/1Y/5Y/10Y) and the flatpickr pickers both refilter the chart.
  - Light/dark theme toggle switches the whole page and re-colors the chart; persists on reload (localStorage).
  - Browser dev tools Network tab shows no requests to any `/api/...` path after the initial page load — confirms CSV-only, no network calls.

- [ ] **Step 3: Stop the dev server** (Ctrl+C) once verified.

## Self-Review Notes

- **Spec coverage:** Page structure (Task 4), CSV-only data + no APIs (Tasks 1–2, verified in Task 5), ticker grouping (Task 1 + template JS), branding/static assets (Task 3, with `dollar_logo.jpg` correctly dropped since unused), landing page requirement (Task 2's `main/urls.py`, verified in Task 5) — all covered.
- **Placeholder scan:** No TBD/TODO; all steps contain complete code.
- **Type consistency:** `get_full_price_series()` return shape (`name/dates/opens/highs/lows/closes`) matches what the template JS reads from `PRICES[sym]`; `get_summary()` fields (`ticker/name/close/change/change_pct/date`) match what `renderSummary()` reads from `SUMMARY`; `get_default_range()` tuple order `(start, end)` matches how Task 2's view unpacks it.
