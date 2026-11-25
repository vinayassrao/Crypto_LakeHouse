from django.http import JsonResponse
from django.shortcuts import render

from . import services


def _selected_pair(request, pairs: list[str]) -> str:
    pair = request.GET.get("pair")
    if pair and pair in pairs:
        return pair
    return pairs[0] if pairs else "BTC-USD"


def dashboard_view(request):
    status = services.get_pipeline_status()
    pairs = services.get_pairs() if status["db_connected"] else list(services.DEFAULT_PAIRS)
    pair = _selected_pair(request, pairs)

    if status["db_connected"]:
        ohlc = services.get_hourly_ohlc(pair)
        daily_volume = services.get_daily_volume(pair)
        reconciliation = services.get_reconciliation(pair)
        recent_trades = services.get_recent_trades(pair)
    else:
        ohlc, daily_volume, reconciliation, recent_trades = [], [], [], []

    latest_price = ohlc[-1]["close"] if ohlc else (recent_trades[0]["price"] if recent_trades else None)
    status_summary = {
        "ok": sum(1 for r in reconciliation if r["status"] == "OK"),
        "divergent": sum(1 for r in reconciliation if r["status"] == "DIVERGENT"),
        "no_stream": sum(1 for r in reconciliation if r["status"] == "NO_STREAM_DATA"),
    }

    context = {
        "status": status,
        "pairs": pairs,
        "selected_pair": pair,
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
    return JsonResponse({"pairs": services.get_pairs()})


def ohlc_api(request):
    pairs = services.get_pairs()
    pair = _selected_pair(request, pairs)
    return JsonResponse({"pair": pair, "ohlc": services.get_hourly_ohlc(pair)})


def reconciliation_api(request):
    pairs = services.get_pairs()
    pair = _selected_pair(request, pairs)
    return JsonResponse({"pair": pair, "reconciliation": services.get_reconciliation(pair)})


def daily_volume_api(request):
    pairs = services.get_pairs()
    pair = _selected_pair(request, pairs)
    return JsonResponse({"pair": pair, "daily_volume": services.get_daily_volume(pair)})
