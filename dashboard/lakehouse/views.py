from django.http import JsonResponse
from django.shortcuts import render

from . import services


def _selected_pair(request, pairs: list[str]) -> str:
    pair = request.GET.get("pair")
    if pair and pair in pairs:
        return pair
    return pairs[0] if pairs else "BTC-USD"


def _selected_quote(request, quote_currencies: list[str]) -> str:
    quote = (request.GET.get("quote") or "ALL").upper()
    if quote == "ALL" or quote in quote_currencies:
        return quote
    return "ALL"


def _selected_display_currency(request) -> str:
    curr = (request.GET.get("currency") or "NATIVE").upper()
    if curr in services.DISPLAY_CURRENCIES:
        return curr
    return "NATIVE"


def _selected_compare_pairs(request, filtered_pairs: list[str], primary_pair: str) -> list[str]:
    requested = [p.upper() for p in request.GET.getlist("compare") if p in filtered_pairs]
    if requested:
        return requested[:5]
    defaults = [p for p in filtered_pairs[:3]]
    if primary_pair in filtered_pairs and primary_pair not in defaults:
        defaults = [primary_pair, *defaults[:2]]
    return defaults


def dashboard_view(request):
    status = services.get_pipeline_status()
    all_pairs = services.get_pairs() if status["db_connected"] else list(services.DEFAULT_PAIRS)
    quote_currencies = services.get_quote_currencies(all_pairs)
    selected_quote = _selected_quote(request, quote_currencies)
    filtered_pairs = services.filter_pairs_by_quote(all_pairs, selected_quote)
    pair = _selected_pair(request, filtered_pairs)
    display_currency = _selected_display_currency(request)
    compare_pairs = _selected_compare_pairs(request, filtered_pairs, pair)

    fx_rates, fx_live = (
        services.get_fx_rates() if display_currency != "NATIVE" else ({"USD": 1.0}, False)
    )
    pair_quote = services.pair_quote_currency(pair)
    effective_currency = (
        pair_quote
        if display_currency == "NATIVE"
        or (pair_quote not in fx_rates or display_currency not in fx_rates)
        else display_currency
    )
    curr_symbol = services.currency_symbol(effective_currency)

    if status["db_connected"]:
        ohlc = services.get_hourly_ohlc(pair, display_currency=display_currency, fx_rates=fx_rates)
        daily_volume = services.get_daily_volume(
            pair, display_currency=display_currency, fx_rates=fx_rates
        )
        reconciliation = services.get_reconciliation(pair)
        recent_trades = services.get_recent_trades(
            pair, display_currency=display_currency, fx_rates=fx_rates
        )
        overview = services.get_multi_pair_overview(
            filtered_pairs, display_currency=display_currency, fx_rates=fx_rates
        )
        compare_series = services.get_multi_pair_series(
            compare_pairs, display_currency=display_currency, fx_rates=fx_rates
        )
    else:
        ohlc, daily_volume, reconciliation, recent_trades = [], [], [], []
        overview = []
        compare_series = {}

    latest_price = (
        ohlc[-1]["close"] if ohlc else (recent_trades[0]["price"] if recent_trades else None)
    )
    status_summary = {
        "ok": sum(1 for r in reconciliation if r["status"] == "OK"),
        "divergent": sum(1 for r in reconciliation if r["status"] == "DIVERGENT"),
        "no_stream": sum(1 for r in reconciliation if r["status"] == "NO_STREAM_DATA"),
    }

    context = {
        "status": status,
        "all_pairs": all_pairs,
        "pairs": filtered_pairs,
        "selected_pair": pair,
        "quote_currencies": quote_currencies,
        "selected_quote": selected_quote,
        "display_currencies": services.DISPLAY_CURRENCIES,
        "selected_currency": display_currency,
        "effective_currency": effective_currency,
        "currency_symbol": curr_symbol,
        "fx_live": fx_live,
        "compare_pairs": compare_pairs,
        "compare_series": compare_series,
        "overview": overview,
        "ohlc": ohlc,
        "daily_volume": daily_volume,
        "reconciliation": reconciliation,
        "recent_trades": recent_trades,
        "latest_price": latest_price,
        "status_summary": status_summary,
    }
    return render(request, "lakehouse/index.html", context)


def health_api(request):
    status = services.get_pipeline_status()
    http_status = 200 if status["db_connected"] else 503
    return JsonResponse(status, status=http_status)


def pairs_api(request):
    all_pairs = services.get_pairs()
    quote_currencies = services.get_quote_currencies(all_pairs)
    quote = _selected_quote(request, quote_currencies)
    pairs = services.filter_pairs_by_quote(all_pairs, quote)
    return JsonResponse(
        {"pairs": pairs, "quote": quote, "quote_currencies": quote_currencies}
    )


def currencies_api(request):
    all_pairs = services.get_pairs()
    fx_rates, fx_live = services.get_fx_rates()
    return JsonResponse(
        {
            "display_currencies": services.DISPLAY_CURRENCIES,
            "quote_currencies": services.get_quote_currencies(all_pairs),
            "fx_base": "USD",
            "fx_live": fx_live,
            "fx_rates": fx_rates,
        }
    )


def overview_api(request):
    all_pairs = services.get_pairs()
    quote = _selected_quote(request, services.get_quote_currencies(all_pairs))
    pairs = services.filter_pairs_by_quote(all_pairs, quote)
    display_currency = _selected_display_currency(request)
    fx_rates, fx_live = (
        services.get_fx_rates() if display_currency != "NATIVE" else ({"USD": 1.0}, False)
    )
    return JsonResponse(
        {
            "quote": quote,
            "display_currency": display_currency,
            "fx_live": fx_live,
            "overview": services.get_multi_pair_overview(
                pairs, display_currency=display_currency, fx_rates=fx_rates
            ),
        }
    )


def ohlc_api(request):
    pairs = services.get_pairs()
    pair = _selected_pair(request, pairs)
    display_currency = _selected_display_currency(request)
    fx_rates, _ = (
        services.get_fx_rates() if display_currency != "NATIVE" else ({"USD": 1.0}, False)
    )
    return JsonResponse(
        {
            "pair": pair,
            "display_currency": display_currency,
            "ohlc": services.get_hourly_ohlc(
                pair, display_currency=display_currency, fx_rates=fx_rates
            ),
        }
    )


def reconciliation_api(request):
    pairs = services.get_pairs()
    pair = _selected_pair(request, pairs)
    return JsonResponse({"pair": pair, "reconciliation": services.get_reconciliation(pair)})


def daily_volume_api(request):
    pairs = services.get_pairs()
    pair = _selected_pair(request, pairs)
    display_currency = _selected_display_currency(request)
    fx_rates, _ = (
        services.get_fx_rates() if display_currency != "NATIVE" else ({"USD": 1.0}, False)
    )
    return JsonResponse(
        {
            "pair": pair,
            "display_currency": display_currency,
            "daily_volume": services.get_daily_volume(
                pair, display_currency=display_currency, fx_rates=fx_rates
            ),
        }
    )
