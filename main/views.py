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
