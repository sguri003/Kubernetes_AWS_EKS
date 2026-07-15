import json
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from django.test import TestCase

import stocks


class DashboardAPITests(TestCase):
    @patch("main.views.stocks.get_summary")
    def test_api_summary_returns_json_of_stocks_summary(self, mock_get_summary):
        mock_get_summary.return_value = [
            {"ticker": "GC_F", "close": 123.45, "change": 1.2, "date": "2026-07-10"}
        ]
        response = self.client.get("/api/summary/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(json.loads(response.content), mock_get_summary.return_value)

    @patch("main.views.stocks.get_full_price_series")
    def test_api_prices_returns_json_of_stocks_prices(self, mock_get_prices):
        mock_get_prices.return_value = {
            "GC_F": {"dates": ["2026-07-10"], "closes": [123.45]}
        }
        response = self.client.get("/api/prices/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(json.loads(response.content), mock_get_prices.return_value)

    @patch("main.views.stocks.get_live_quotes")
    def test_api_live_returns_json_of_live_quotes(self, mock_get_live):
        mock_get_live.return_value = [
            {"ticker": "GC_F", "close": 2415.3, "change": 9.6, "change_pct": 0.4, "date": "2026-07-14"}
        ]
        response = self.client.get("/api/live/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(json.loads(response.content), mock_get_live.return_value)

    @patch("main.views.stocks.get_summary")
    def test_dashboard_does_not_eagerly_fetch_summary(self, mock_summary):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        mock_summary.assert_not_called()

    def test_dashboard_page_does_not_embed_summary_or_price_json(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'id="summary-data"', response.content)
        self.assertNotIn(b'id="prices-data"', response.content)

    @patch.dict(os.environ, {"APP_VERSION": "v5"})
    def test_dashboard_shows_app_version_from_env(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"sguri003/gds-app:v5", response.content)

    @patch.dict(os.environ, {"APP_VERSION": "v5"})
    def test_dashboard_labels_app_version_as_current_release(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Current Release", response.content)

    def test_dashboard_defaults_app_version_to_dev_when_env_unset(self):
        with patch.dict(os.environ):
            os.environ.pop("APP_VERSION", None)
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"sguri003/gds-app:dev", response.content)


class CachingTests(TestCase):
    def setUp(self):
        stocks._series_cache = None
        stocks._series_cache_date = None

    def tearDown(self):
        stocks._series_cache = None
        stocks._series_cache_date = None

    @patch("stocks.fetch_prices")
    def test_full_price_series_is_cached_within_same_day(self, mock_fetch):
        mock_fetch.return_value = {}
        stocks.get_full_price_series()
        stocks.get_full_price_series()
        self.assertEqual(mock_fetch.call_count, 1)


class LiveQuoteTests(TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        self.db_path = Path(path)
        self.db_patcher = patch("stocks.DB_PATH", self.db_path)
        self.db_patcher.start()
        stocks._live_quotes_cache = None
        stocks._live_quotes_cache_time = None

    def tearDown(self):
        self.db_patcher.stop()
        self.db_path.unlink(missing_ok=True)
        stocks._live_quotes_cache = None
        stocks._live_quotes_cache_time = None

    @patch("stocks._yf_download_wide")
    @patch("stocks._yf_download_intraday_wide")
    def test_get_live_quotes_computes_change_vs_stored_previous_close(self, mock_intraday, mock_historical):
        mock_historical.return_value = pd.DataFrame()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        stocks._save_wide_to_sql(pd.DataFrame({"Dt": [yesterday], "GC_F_Close": [2400.0]}))
        mock_intraday.return_value = pd.DataFrame({
            "Dt": ["2026-07-14 09:30:00", "2026-07-14 09:31:00"],
            "GC_F_Close": [2410.0, 2415.3],
        })

        quotes = stocks.get_live_quotes()

        gold = next(q for q in quotes if q["ticker"] == "GC_F")
        self.assertEqual(gold["close"], 2415.3)
        self.assertEqual(gold["change"], round(2415.3 - 2400.0, 2))
        self.assertEqual(gold["date"], date.today().strftime("%Y-%m-%d"))

    @patch("stocks._yf_download_intraday_wide")
    def test_get_live_quotes_returns_empty_list_when_download_fails(self, mock_intraday):
        mock_intraday.side_effect = Exception("network down")

        quotes = stocks.get_live_quotes()

        self.assertEqual(quotes, [])

    @patch("stocks._yf_download_intraday_wide")
    def test_get_live_quotes_is_cached_briefly(self, mock_intraday):
        mock_intraday.return_value = pd.DataFrame()

        stocks.get_live_quotes()
        stocks.get_live_quotes()

        self.assertEqual(mock_intraday.call_count, 1)


class IncrementalRefreshTests(TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        self.db_path = Path(path)
        self.db_patcher = patch("stocks.DB_PATH", self.db_path)
        self.db_patcher.start()

    def tearDown(self):
        self.db_patcher.stop()
        self.db_path.unlink(missing_ok=True)

    @patch("stocks._yf_download_wide")
    def test_refresh_all_to_sql_requests_a_lookback_window_before_latest_stored_date(self, mock_download):
        mock_download.return_value = pd.DataFrame()
        stocks._save_wide_to_sql(pd.DataFrame({"Dt": ["2020-01-10"], "GC_F_Close": [123.4]}))

        stocks.refresh_all_to_sql()

        expected_start = (date(2020, 1, 10) - timedelta(days=stocks.REFRESH_LOOKBACK_DAYS)).isoformat()
        expected_end = date.today().strftime("%Y-%m-%d")
        mock_download.assert_called_once_with(expected_start, expected_end)

    @patch("stocks._yf_download_wide")
    def test_refresh_all_to_sql_backfills_full_history_when_table_empty(self, mock_download):
        mock_download.return_value = pd.DataFrame()

        stocks.refresh_all_to_sql()

        expected_end = date.today().strftime("%Y-%m-%d")
        mock_download.assert_called_once_with(stocks.HISTORY_START, expected_end)

    @patch("stocks._yf_download_wide")
    def test_refresh_all_to_sql_recovers_a_ticker_missing_from_an_earlier_run(self, mock_download):
        """Reproduces the real bug: futures post before equities close, so a same-day
        refresh can write a row with GC_F filled but AAPL_Close NULL. Since the max-date
        cursor is table-wide, a naive 'day after latest' incremental fetch would never
        revisit that date. The lookback window means a later run re-requests it and the
        upsert fills in the previously-missing column."""
        today_str = date.today().strftime("%Y-%m-%d")
        mock_download.side_effect = [
            pd.DataFrame({"Dt": [today_str], "GC_F_Close": [123.4]}),
            pd.DataFrame({"Dt": [today_str], "GC_F_Close": [123.5], "AAPL_Close": [199.9]}),
        ]

        stocks.refresh_all_to_sql()
        stocks.refresh_all_to_sql()

        conn = stocks._connect()
        row = conn.execute(f'SELECT AAPL_Close FROM "{stocks.TABLE}" WHERE Dt = ?', (today_str,)).fetchone()
        conn.close()
        self.assertEqual(row[0], 199.9)


class TickerPrefixBugfixTests(TestCase):
    """Regression tests: _read_tickers_from_sql/_extract_ticker_from_wide take our safe
    column-name tickers (e.g. "GC_F"), but were looking them up in TICKER_TO_COL, whose keys
    are yfinance symbols ("GC=F"). That only worked by coincidence for the 11 tickers where
    safe name == yfinance symbol (AAPL, MSFT, ...) and silently failed for the 7 futures."""

    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        self.db_path = Path(path)
        self.db_patcher = patch("stocks.DB_PATH", self.db_path)
        self.db_patcher.start()

    def tearDown(self):
        self.db_patcher.stop()
        self.db_path.unlink(missing_ok=True)

    def test_read_tickers_from_sql_finds_a_futures_ticker(self):
        stocks._save_wide_to_sql(pd.DataFrame({"Dt": ["2026-07-01"], "GC_F_Close": [2400.0]}))

        result = stocks._read_tickers_from_sql(["GC_F"], "2020-01-01", "2026-12-31")

        self.assertIn("GC_F", result)
        self.assertEqual(float(result["GC_F"]["Close"].iloc[-1]), 2400.0)

    def test_extract_ticker_from_wide_finds_a_futures_ticker(self):
        wide = pd.DataFrame({"Dt": ["2026-07-01"], "GC_F_Close": [2400.0]})

        df = stocks._extract_ticker_from_wide("GC_F", wide)

        self.assertFalse(df.empty)
        self.assertEqual(float(df["Close"].iloc[-1]), 2400.0)


class StocksDataTests(TestCase):
    def test_tickers_has_nineteen_symbols_and_no_indices(self):
        self.assertEqual(len(stocks.TICKERS), 19)
        self.assertIn("PL_F", stocks.TICKERS)
        self.assertIn("MP", stocks.TICKERS)
        self.assertIn("NVDA", stocks.TICKERS)
        self.assertIn("BAC", stocks.TICKERS)
        self.assertNotIn("NDX", stocks.TICKERS)
        self.assertNotIn("DJI", stocks.TICKERS)
        self.assertNotIn("GSPC", stocks.TICKERS)

    def test_full_price_series_covers_all_tickers_ascending(self):
        series = stocks.get_full_price_series()
        self.assertEqual(set(series.keys()), set(stocks.TICKERS))
        gold = series["GC_F"]
        self.assertGreater(len(gold["dates"]), 900)
        self.assertEqual(gold["dates"], sorted(gold["dates"]))
        self.assertEqual(len(gold["dates"]), len(gold["closes"]))

    def test_summary_has_change_vs_previous_close(self):
        summary = stocks.get_summary()
        by_ticker = {row["ticker"]: row for row in summary}
        gold = by_ticker["GC_F"]
        series = stocks.get_full_price_series()["GC_F"]
        expected_change = round(series["closes"][-1] - series["closes"][-2], 2)
        self.assertEqual(gold["close"], series["closes"][-1])
        self.assertEqual(gold["change"], expected_change)
        self.assertEqual(gold["date"], series["dates"][-1])

    def test_default_range_is_one_year_ending_at_max_data_date(self):
        start, end = stocks.get_default_range()
        series = stocks.get_full_price_series()
        max_date = max(d for info in series.values() for d in info["dates"])
        self.assertEqual(end, max_date)
        self.assertLess(start, end)
