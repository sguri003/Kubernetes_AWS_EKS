import json
from unittest.mock import patch

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


class StocksDataTests(TestCase):
    def test_tickers_has_eighteen_symbols_and_no_indices(self):
        self.assertEqual(len(stocks.TICKERS), 18)
        self.assertIn("PL_F", stocks.TICKERS)
        self.assertIn("MP", stocks.TICKERS)
        self.assertIn("NVDA", stocks.TICKERS)
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
