from django.test import TestCase

import stocks


class StocksDataTests(TestCase):
    def test_tickers_has_twentyone_symbols(self):
        self.assertEqual(len(stocks.TICKERS), 21)
        self.assertIn("PL_F", stocks.TICKERS)
        self.assertIn("MP", stocks.TICKERS)
        self.assertIn("NVDA", stocks.TICKERS)

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
