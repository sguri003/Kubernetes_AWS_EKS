import logging
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH  = BASE_DIR / "db.sqlite3"
TABLE    = "Commodity"

TICKER_LABELS = {
    "GC_F": "Gold",
    "SI_F": "Silver",
    "PL_F": "Platinum",
    "PA_F": "Palladium",
    "HG_F": "Copper",
    "CL_F": "WTI Crude Oil",
    "BZ_F": "Brent Crude",
    "XEL": "Xcel Energy",
    "CVX": "Chevron",
    "MP": "MP Materials",
    "B": "Barnes Group",
    "RTX": "RTX Corporation",
    "NVDA": "NVIDIA",
    "AAPL": "Apple",
    "NOC": "Northrop Grumman",
    "BA": "Boeing",
    "PSKY": "Paramount Skydance",
    "MSFT": "Microsoft",
}

TICKERS = list(TICKER_LABELS.keys())

# our safe column-name key -> actual yfinance symbol
COL_TO_TICKER = {
    "GC_F": "GC=F", "SI_F": "SI=F", "PL_F": "PL=F", "PA_F": "PA=F",
    "HG_F": "HG=F", "CL_F": "CL=F", "BZ_F": "BZ=F",
    "XEL": "XEL", "CVX": "CVX", "MP": "MP", "B": "B",
    "RTX": "RTX", "NVDA": "NVDA", "AAPL": "AAPL", "NOC": "NOC",
    "BA": "BA", "PSKY": "PSKY", "MSFT": "MSFT",
}
TICKER_TO_COL = {v: k for k, v in COL_TO_TICKER.items()}
YF_TICKERS = list(COL_TO_TICKER.values())

HISTORY_START      = "2010-01-01"
SUMMARY_LOOKBACK    = 10   # days
SQL_CHECK_INTERVAL  = 30   # seconds — reuse last availability result

_sql_last_check = None
_sql_up = False


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _sql_available() -> bool:
    """Check the sqlite file is reachable; result is cached for SQL_CHECK_INTERVAL seconds."""
    global _sql_last_check, _sql_up
    now = time.monotonic()
    if _sql_last_check is None or (now - _sql_last_check) > SQL_CHECK_INTERVAL:
        try:
            conn = _connect()
            try:
                conn.execute("SELECT 1")
            finally:
                conn.close()
            _sql_up = True
        except Exception:
            _sql_up = False
        _sql_last_check = now
    return _sql_up


# ── yfinance ──────────────────────────────────────────────────────────────────

def _yf_download_single(ticker: str, start: str, end: str) -> pd.DataFrame:
    raw = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index = pd.to_datetime(df.index).date
    return df.dropna(subset=["Close"])


def _yf_download_wide(start: str, end: str) -> pd.DataFrame:
    """Download all tickers in one call; return a wide DataFrame keyed by our safe column names."""
    raw = yf.download(YF_TICKERS, start=start, end=end,
                       group_by="ticker", auto_adjust=True, progress=False)
    if raw.empty:
        return pd.DataFrame()
    dt = raw.reset_index()
    dt.columns = ["_".join(str(c) for c in col).strip() if isinstance(col, tuple) else str(col)
                  for col in dt.columns]
    dt.columns = (dt.columns
                  .str.replace("=", "_", regex=False)
                  .str.replace("^", "",  regex=False)
                  .str.replace(" ", "_", regex=False)
                  .str.lstrip("_"))
    dt = dt[[c for c in dt.columns if "Adj" not in c]]
    dt = dt.rename(columns={c: "Dt" for c in dt.columns if "Date" in c or c == "Date_"})
    dt["Dt"] = pd.to_datetime(dt["Dt"]).dt.date.astype(str)
    return dt.round(4)


def _extract_ticker_from_wide(ticker: str, wide: pd.DataFrame) -> pd.DataFrame:
    """Parse one ticker's OHLCV from an already-downloaded wide DataFrame (no extra download)."""
    prefix = TICKER_TO_COL.get(ticker)
    if not prefix:
        return pd.DataFrame()
    col_map = {
        f"{prefix}_Open": "Open", f"{prefix}_High": "High",
        f"{prefix}_Low":  "Low",  f"{prefix}_Close": "Close",
        f"{prefix}_Volume": "Volume",
    }
    present = {k: v for k, v in col_map.items() if k in wide.columns}
    if "Close" not in present.values():
        return pd.DataFrame()
    df = wide[["Dt"] + list(present.keys())].copy()
    df = df.rename(columns=present).set_index("Dt")
    return df.dropna(subset=["Close"])


# ── sqlite3 write ──────────────────────────────────────────────────────────────

def _save_wide_to_sql(df: pd.DataFrame):
    """Upsert rows into the Commodity table; auto-add columns for new tickers.

    Uses INSERT ... ON CONFLICT DO UPDATE so a later, wider-range refresh can
    always correct or fill in prior values for any column on any date -- not
    just backfill columns that are brand new to the table.
    """
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(f'CREATE TABLE IF NOT EXISTS "{TABLE}" (Dt TEXT PRIMARY KEY)')

        cur.execute(f'PRAGMA table_info("{TABLE}")')
        db_cols = {row[1] for row in cur.fetchall()}

        cols = [c for c in df.columns if c != "Dt"]
        new_cols = [c for c in cols if c not in db_cols]
        for col in new_cols:
            cur.execute(f'ALTER TABLE "{TABLE}" ADD COLUMN "{col}" REAL')
            logger.info("Added column %s to %s", col, TABLE)

        col_list = ", ".join(f'"{c}"' for c in cols)
        placeholders = ", ".join(["?"] * (len(cols) + 1))
        update_clause = ", ".join(f'"{c}" = excluded."{c}"' for c in cols)
        upsert_sql = (
            f'INSERT INTO "{TABLE}" (Dt, {col_list}) VALUES ({placeholders}) '
            f'ON CONFLICT(Dt) DO UPDATE SET {update_clause}'
        )
        rows = [
            [row["Dt"]] + [float(row[c]) if pd.notna(row[c]) else None for c in cols]
            for _, row in df.iterrows()
        ]
        cur.executemany(upsert_sql, rows)
        conn.commit()
        logger.info("Upserted %d rows into %s", len(rows), TABLE)
    finally:
        conn.close()


# ── sqlite3 read ───────────────────────────────────────────────────────────────

def _read_tickers_from_sql(tickers: list, start: str, end: str) -> dict:
    """Fetch all requested tickers in a single query (SELECT *)."""
    prefixes = {t: TICKER_TO_COL[t] for t in tickers if t in TICKER_TO_COL}
    if not prefixes:
        return {}

    conn = _connect()
    try:
        cur = conn.execute(
            'SELECT name FROM sqlite_master WHERE type="table" AND name=?', (TABLE,)
        )
        if not cur.fetchone():
            return {}
        try:
            df = pd.read_sql(
                f'SELECT * FROM "{TABLE}" WHERE Dt >= ? AND Dt <= ? ORDER BY Dt',
                conn, params=(start, end),
            )
        except Exception as exc:
            logger.warning("sqlite read failed: %s", exc)
            return {}
    finally:
        conn.close()

    if df.empty:
        return {}

    result = {}
    for ticker, prefix in prefixes.items():
        col_map = {
            f"{prefix}_Open": "Open", f"{prefix}_High": "High",
            f"{prefix}_Low":  "Low",  f"{prefix}_Close": "Close",
            f"{prefix}_Volume": "Volume",
        }
        available = {k: v for k, v in col_map.items() if k in df.columns}
        if "Close" not in available.values():
            continue
        tdf = df[["Dt"] + list(available.keys())].rename(columns=available).set_index("Dt")
        tdf = tdf.dropna(subset=["Close"])
        if not tdf.empty:
            result[ticker] = tdf
    return result


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_prices(tickers: list, start: str, end: str) -> dict:
    """Return {ticker: DataFrame} — one sqlite query for all tickers, yfinance for any gaps."""
    use_sql = _sql_available()

    result = _read_tickers_from_sql(tickers, start, end) if use_sql else {}
    missing = [t for t in tickers if t not in result]

    if missing:
        logger.info("sqlite miss for %d ticker(s); fetching from yfinance", len(missing))
        wide = _yf_download_wide(start, end)
        if not wide.empty:
            if use_sql:
                try:
                    _save_wide_to_sql(wide)
                except Exception as exc:
                    logger.error("sqlite write failed: %s", exc)
            for ticker in missing:
                df = _extract_ticker_from_wide(ticker, wide)
                if df.empty:
                    df = _yf_download_single(COL_TO_TICKER.get(ticker, ticker), start, end)
                if not df.empty:
                    result[ticker] = df

    return result


def refresh_all_to_sql(start: str = HISTORY_START):
    """Download all tickers from yfinance and write new rows to the Commodity table."""
    end = date.today().strftime("%Y-%m-%d")
    wide = _yf_download_wide(start, end)
    if not wide.empty:
        _save_wide_to_sql(wide)
        logger.info("Refreshed %s with latest yfinance data", TABLE)


REFRESH_MARKER  = BASE_DIR / ".last_refresh"
EASTERN         = ZoneInfo("America/New_York")
REFRESH_HOUR_ET = 17  # 5:00 PM ET — after US equity close and most futures settlement


def _last_refresh_date():
    try:
        return date.fromisoformat(REFRESH_MARKER.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


def _mark_refreshed(d: date):
    REFRESH_MARKER.write_text(d.isoformat())


def refresh_if_stale():
    """Refresh all tickers from yfinance at most once per day, after that day's market close (5PM ET)."""
    now_et = datetime.now(EASTERN)
    if now_et.hour < REFRESH_HOUR_ET:
        return  # today's session hasn't settled yet
    today = now_et.date()
    if _last_refresh_date() == today:
        return
    refresh_all_to_sql()
    _mark_refreshed(today)


def get_full_price_series() -> dict:
    end = date.today().strftime("%Y-%m-%d")
    data = fetch_prices(TICKERS, HISTORY_START, end)
    series = {}
    for ticker in TICKERS:
        df = data.get(ticker)
        if df is None or df.empty:
            series[ticker] = {
                "name": TICKER_LABELS.get(ticker, ticker),
                "dates": [], "opens": [], "highs": [], "lows": [], "closes": [],
            }
            continue
        series[ticker] = {
            "name":   TICKER_LABELS.get(ticker, ticker),
            "dates":  [str(d) for d in df.index.tolist()],
            "opens":  [_safe_float(v) for v in df["Open"].tolist()],
            "highs":  [_safe_float(v) for v in df["High"].tolist()],
            "lows":   [_safe_float(v) for v in df["Low"].tolist()],
            "closes": [_safe_float(v) for v in df["Close"].tolist()],
        }
    return series


def _safe_float(value):
    try:
        f = float(value)
        return f if f == f else None  # filter NaN
    except (TypeError, ValueError):
        return None


def get_summary() -> list:
    end = date.today().strftime("%Y-%m-%d")
    start = (date.today() - timedelta(days=SUMMARY_LOOKBACK)).strftime("%Y-%m-%d")
    data = fetch_prices(TICKERS, start, end)
    rows = []
    for ticker, df in data.items():
        if df.empty:
            continue
        close = float(df["Close"].iloc[-1])
        if len(df) >= 2:
            prev = float(df["Close"].iloc[-2])
            change = round(close - prev, 2)
            change_pct = round((change / prev) * 100, 2) if prev else 0.0
        else:
            change = change_pct = 0.0
        rows.append({
            "ticker":     ticker,
            "name":       TICKER_LABELS.get(ticker, ticker),
            "close":      close,
            "change":     change,
            "change_pct": change_pct,
            "date":       str(df.index[-1]),
        })
    rows.sort(key=lambda r: r["name"])
    return rows


def get_default_range():
    series = get_full_price_series()
    all_dates = sorted({d for info in series.values() for d in info["dates"]})
    if not all_dates:
        today = date.today().isoformat()
        return today, today
    end = all_dates[-1]
    end_date = datetime.strptime(end, "%Y-%m-%d").date()
    start_date = end_date - timedelta(days=365)
    candidates = [d for d in all_dates if d >= start_date.isoformat()]
    start = candidates[0] if candidates else all_dates[0]
    return start, end
