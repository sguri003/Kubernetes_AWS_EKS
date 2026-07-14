from django.http import JsonResponse
from django.shortcuts import render

import stocks


def dashboard(request):
    default_start, default_end = stocks.get_default_range()
    context = {
        "tickers": {t: stocks.TICKER_LABELS.get(t, t) for t in stocks.TICKERS},
        "default_start": default_start,
        "default_end": default_end,
    }
    return render(request, "main/dashboard.html", context)


def api_summary(request):
    return JsonResponse(stocks.get_summary(), safe=False)


def api_prices(request):
    return JsonResponse(stocks.get_full_price_series(), safe=False)
