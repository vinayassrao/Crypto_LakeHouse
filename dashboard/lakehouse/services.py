from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from typing import Any

import requests
from django.db import DatabaseError, connection

_DEFAULT_PAIRS_STR = (
    "BTC-USD,ETH-USD,SOL-USD,"
    "BTC-EUR,ETH-EUR,BTC-GBP,"
    "XRP-USD,ADA-USD,DOGE-USD"
)
DEFAULT_PAIRS = [
    p.strip().upper()
    for p in os.getenv("CRYPTO_PAIRS", _DEFAULT_PAIRS_STR).split(",")
    if p.strip()
]

DISPLAY_CURRENCIES = ["NATIVE", "USD", "EUR", "GBP", "INR", "JPY"]

CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "INR": "₹",
    "JPY": "¥",
    "BTC": "₿",
    "ETH": "Ξ",
}

_FX_CACHE: dict[str, Any] = {"timestamp": 0.0, "rates": {"USD": 1.0}, "live": False}
_FX_TTL_SECONDS = 300


def pair_base_currency(pair: str) -> str:
    return pair.split("-", 1)[0] if "-" in pair else pair


def pair_quote_currency(pair: str) -> str:
    return pair.split("-", 1)[1] if "-" in pair else "USD"


def currency_symbol(code: str) -> str:
    return CURRENCY_SYMBOLS.get(code, f"{code} ")


def get_fx_rates(force_refresh: bool = False) -> tuple[dict[str, float], bool]:
    """Fetch USD-based exchange rates from Coinbase public API with a 5-minute cache."""
    now = time.monotonic()
    if not force_refresh and _FX_CACHE["live"] and (now - _FX_CACHE["timestamp"] < _FX_TTL_SECONDS):
        return dict(_FX_CACHE["rates"]), True

    try:
        resp = requests.get(
            "https://api.coinbase.com/v2/exchange-rates?currency=USD",
            timeout=3,
        )
        resp.raise_for_status()
        raw_rates = resp.json()["data"]["rates"]
        parsed: dict[str, float] = {"USD": 1.0}
        for code in ("EUR", "GBP", "INR", "JPY", "USD", "USDC", "USDT"):
            if code in raw_rates:
                parsed[code] = float(raw_rates[code])
        _FX_CACHE["rates"] = parsed
        _FX_CACHE["timestamp"] = now
        _FX_CACHE["live"] = True
        return dict(parsed), True
    except (requests.RequestException, KeyError, ValueError, TypeError):
        return dict(_FX_CACHE["rates"]), bool(_FX_CACHE["live"])


def convert_amount(
    amount: float | None,
    from_currency: str,
    to_currency: str,
    fx_rates: dict[str, float],
) -> float | None:
    """Convert an amount between currencies via USD pivot; returns None if rate is missing."""
    if amount is None:
        return None
    if to_currency == "NATIVE" or from_currency == to_currency:
        return float(amount)
    from_rate = fx_rates.get(from_currency)
    to_rate = fx_rates.get(to_currency)
    if not from_rate or not to_rate or from_rate <= 0 or to_rate <= 0:
        return None
    return (float(amount) / from_rate) * to_rate


def _fetch_dicts(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """Execute a parameterized query and return rows as dictionaries."""
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _safe_count(qualified_table: str) -> int | None:
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {qualified_table}")
            row = cursor.fetchone()
            return int(row[0]) if row else 0
    except DatabaseError:
        return None


def get_pipeline_status() -> dict[str, Any]:
    """Return PostgreSQL connectivity and row counts across raw and analytics tables."""
    try:
        connection.ensure_connection()
    except DatabaseError as exc:
        return {
            "db_connected": False,
            "error": str(exc),
            "counts": {
                "raw_trades": None,
                "raw_candles": None,
                "fact_trades": None,
                "reconciliation": None,
            },
        }

    return {
        "db_connected": True,
        "error": None,
        "counts": {
            "raw_trades": _safe_count("public.raw_trades"),
            "raw_candles": _safe_count("public.raw_candles"),
            "fact_trades": _safe_count("analytics.fact_trades"),
            "reconciliation": _safe_count("analytics.reconciliation"),
        },
    }


def get_pairs() -> list[str]:
    """Return available trading pairs from analytics marts, or default pairs."""
    for table in ("analytics.dim_pair", "analytics.fact_trades", "analytics.reconciliation"):
        try:
            rows = _fetch_dicts(f"SELECT DISTINCT product_id FROM {table} ORDER BY product_id")
            pairs = [r["product_id"] for r in rows if r.get("product_id")]
            if pairs:
                return pairs
        except DatabaseError:
            continue
    return list(DEFAULT_PAIRS)


def get_quote_currencies(pairs: list[str]) -> list[str]:
    """Return sorted unique quote currencies across available pairs."""
    seen: list[str] = []
    for pair in pairs:
        quote = pair_quote_currency(pair)
        if quote not in seen:
            seen.append(quote)
    return seen


def filter_pairs_by_quote(pairs: list[str], quote: str) -> list[str]:
    """Filter pairs by quote currency unless quote is ALL/empty."""
    if not quote or quote.upper() == "ALL":
        return list(pairs)
    target = quote.upper()
    filtered = [p for p in pairs if pair_quote_currency(p) == target]
    return filtered if filtered else list(pairs)


def get_hourly_ohlc(
    pair: str,
    display_currency: str = "NATIVE",
    fx_rates: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    from_curr = pair_quote_currency(pair)
    rates = fx_rates or {"USD": 1.0}
    try:
        rows = _fetch_dicts(
            """
            SELECT hour, open, high, low, close, volume, trade_count
            FROM analytics.agg_hourly_ohlc
            WHERE product_id = %s
            ORDER BY hour ASC
            """,
            (pair,),
        )
        for row in rows:
            if row.get("hour") is not None:
                row["hour"] = row["hour"].isoformat()
            for field in ("open", "high", "low", "close"):
                converted = convert_amount(row.get(field), from_curr, display_currency, rates)
                if converted is not None:
                    row[field] = converted
        return rows
    except DatabaseError:
        return []


def get_daily_volume(
    pair: str,
    display_currency: str = "NATIVE",
    fx_rates: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    from_curr = pair_quote_currency(pair)
    rates = fx_rates or {"USD": 1.0}
    try:
        rows = _fetch_dicts(
            """
            SELECT trade_date, total_volume, total_value_usd, trade_count
            FROM analytics.agg_daily_volume
            WHERE product_id = %s
            ORDER BY trade_date ASC
            """,
            (pair,),
        )
        for row in rows:
            if row.get("trade_date") is not None:
                row["trade_date"] = row["trade_date"].isoformat()
            converted = convert_amount(
                row.get("total_value_usd"), from_curr, display_currency, rates
            )
            row["display_notional"] = (
                converted if converted is not None else row.get("total_value_usd")
            )
        return rows
    except DatabaseError:
        return []


def get_reconciliation(pair: str, limit: int = 30) -> list[dict[str, Any]]:
    try:
        rows = _fetch_dicts(
            """
            SELECT day, my_volume, official_volume, volume_gap, status
            FROM analytics.reconciliation
            WHERE product_id = %s
            ORDER BY day DESC
            LIMIT %s
            """,
            (pair, limit),
        )
        for row in rows:
            if row.get("day") is not None:
                row["day"] = row["day"].isoformat()
        return rows
    except DatabaseError:
        return []


def get_recent_trades(
    pair: str,
    limit: int = 15,
    display_currency: str = "NATIVE",
    fx_rates: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    from_curr = pair_quote_currency(pair)
    rates = fx_rates or {"USD": 1.0}
    try:
        rows = _fetch_dicts(
            """
            SELECT trade_id, side, size, price, (size * price) AS notional_value, event_time
            FROM analytics.fact_trades
            WHERE product_id = %s
            ORDER BY event_time DESC
            LIMIT %s
            """,
            (pair, limit),
        )
        for row in rows:
            if row.get("event_time") is not None:
                row["event_time"] = row["event_time"].isoformat()
            price_conv = convert_amount(row.get("price"), from_curr, display_currency, rates)
            notional_conv = convert_amount(
                row.get("notional_value"), from_curr, display_currency, rates
            )
            if price_conv is not None:
                row["price"] = price_conv
            if notional_conv is not None:
                row["notional_value"] = notional_conv
        return rows
    except DatabaseError:
        return []


def get_multi_pair_overview(
    pairs: list[str],
    display_currency: str = "NATIVE",
    fx_rates: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Return latest price, volume, and reconciliation status across all pairs."""
    rates = fx_rates or {"USD": 1.0}
    latest_prices: dict[str, float] = {}
    trade_counts: dict[str, int] = {}
    stream_volumes: dict[str, float] = {}
    recon_statuses: dict[str, str] = {}

    try:
        for r in _fetch_dicts(
            """
            SELECT DISTINCT ON (product_id) product_id, close
            FROM analytics.agg_hourly_ohlc
            ORDER BY product_id, hour DESC
            """
        ):
            latest_prices[r["product_id"]] = float(r["close"])
    except DatabaseError:
        pass

    try:
        for r in _fetch_dicts(
            """
            SELECT product_id, SUM(total_volume) AS vol, SUM(trade_count) AS trades
            FROM analytics.agg_daily_volume
            GROUP BY product_id
            """
        ):
            stream_volumes[r["product_id"]] = float(r["vol"])
            trade_counts[r["product_id"]] = int(r["trades"])
    except DatabaseError:
        pass

    try:
        for r in _fetch_dicts(
            """
            SELECT DISTINCT ON (product_id) product_id, status
            FROM analytics.reconciliation
            ORDER BY product_id, day DESC
            """
        ):
            recon_statuses[r["product_id"]] = r["status"]
    except DatabaseError:
        pass

    overview = []
    for pair in pairs:
        native_quote = pair_quote_currency(pair)
        raw_price = latest_prices.get(pair)
        converted = convert_amount(raw_price, native_quote, display_currency, rates)
        target_currency = (
            native_quote
            if display_currency == "NATIVE" or converted is None
            else display_currency
        )
        overview.append(
            {
                "product_id": pair,
                "base_currency": pair_base_currency(pair),
                "quote_currency": native_quote,
                "display_currency": target_currency,
                "currency_symbol": currency_symbol(target_currency),
                "display_price": converted if converted is not None else raw_price,
                "stream_volume": stream_volumes.get(pair),
                "trade_count": trade_counts.get(pair, 0),
                "recon_status": recon_statuses.get(pair, "PENDING"),
            }
        )
    return overview


def get_multi_pair_series(
    selected_pairs: list[str],
    display_currency: str = "NATIVE",
    fx_rates: dict[str, float] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return hourly close series keyed by pair for multi-currency comparison."""
    series: dict[str, list[dict[str, Any]]] = {}
    for pair in selected_pairs:
        series[pair] = get_hourly_ohlc(
            pair, display_currency=display_currency, fx_rates=fx_rates
        )
    return series


def get_live_coinbase_ticker(pair: str) -> dict[str, Any] | None:
    """Fetch the current spot ticker for a pair from Coinbase Exchange."""
    try:
        resp = requests.get(
            f"https://api.exchange.coinbase.com/products/{pair}/ticker",
            timeout=3,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "trade_id": int(data["trade_id"]) if data.get("trade_id") is not None else None,
            "price": float(data["price"]),
            "size": float(data["size"]) if data.get("size") is not None else None,
            "bid": float(data["bid"]) if data.get("bid") is not None else None,
            "ask": float(data["ask"]) if data.get("ask") is not None else None,
            "volume_24h": float(data["volume"]) if data.get("volume") is not None else None,
            "event_time": data.get("time") or datetime.now(UTC).isoformat(),
            "side": "ticker",
        }
    except (requests.RequestException, KeyError, ValueError, TypeError):
        return None


def _get_raw_trade_points(pair: str, limit: int = 60) -> list[dict[str, Any]]:
    """Fetch most recent raw trades for a pair from public.raw_trades chronologically."""
    try:
        rows = _fetch_dicts(
            """
            SELECT trade_id, side, size, price, (size * price) AS notional_value, event_time
            FROM public.raw_trades
            WHERE product_id = %s
              AND price > 0
              AND size > 0
            ORDER BY event_time DESC
            LIMIT %s
            """,
            (pair, limit),
        )
        rows.reverse()
        return rows
    except DatabaseError:
        return []


def _is_recent_timestamp(ts: Any, max_age_seconds: int = 120) -> bool:
    if ts is None:
        return False
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)
        except ValueError:
            return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return (datetime.now(UTC) - ts).total_seconds() <= max_age_seconds


def get_live_stream_snapshot(
    pair: str,
    display_currency: str = "NATIVE",
    fx_rates: dict[str, float] | None = None,
    source_mode: str = "auto",
    limit: int = 60,
) -> dict[str, Any]:
    """Return live price tick and rolling stream series from Postgres and/or Coinbase."""
    from_curr = pair_quote_currency(pair)
    rates = fx_rates or {"USD": 1.0}
    target_currency = (
        from_curr
        if display_currency == "NATIVE"
        or from_curr not in rates
        or display_currency not in rates
        else display_currency
    )
    symbol = currency_symbol(target_currency)

    raw_points = [] if source_mode == "coinbase" else _get_raw_trade_points(pair, limit=limit)
    latest_raw_dt = raw_points[-1]["event_time"] if raw_points else None
    raw_is_fresh = _is_recent_timestamp(latest_raw_dt, max_age_seconds=120)

    converted_points: list[dict[str, Any]] = []
    for row in raw_points:
        ev = row.get("event_time")
        ev_iso = ev.isoformat() if hasattr(ev, "isoformat") else str(ev)
        price_val = convert_amount(row.get("price"), from_curr, target_currency, rates)
        notional_val = convert_amount(
            row.get("notional_value"), from_curr, target_currency, rates
        )
        converted_points.append(
            {
                "trade_id": row.get("trade_id"),
                "side": row.get("side"),
                "size": float(row["size"]) if row.get("size") is not None else None,
                "price": price_val if price_val is not None else float(row["price"]),
                "notional_value": notional_val,
                "event_time": ev_iso,
            }
        )

    ticker = None
    if source_mode == "coinbase" or (source_mode == "auto" and not raw_is_fresh):
        ticker = get_live_coinbase_ticker(pair)

    if ticker is not None:
        ticker_price = convert_amount(ticker["price"], from_curr, target_currency, rates)
        bid_val = convert_amount(ticker.get("bid"), from_curr, target_currency, rates)
        ask_val = convert_amount(ticker.get("ask"), from_curr, target_currency, rates)
        latest = {
            "trade_id": ticker.get("trade_id"),
            "side": "ticker",
            "size": ticker.get("size"),
            "price": ticker_price if ticker_price is not None else ticker["price"],
            "bid": bid_val if bid_val is not None else ticker.get("bid"),
            "ask": ask_val if ask_val is not None else ticker.get("ask"),
            "volume_24h": ticker.get("volume_24h"),
            "event_time": ticker["event_time"],
        }
        source = "coinbase_ticker"
    elif converted_points:
        last_pt = converted_points[-1]
        latest = {
            "trade_id": last_pt["trade_id"],
            "side": last_pt["side"],
            "size": last_pt["size"],
            "price": last_pt["price"],
            "bid": None,
            "ask": None,
            "volume_24h": None,
            "event_time": last_pt["event_time"],
        }
        source = "postgres_stream" if raw_is_fresh else "postgres_cached"
    else:
        latest = None
        source = "unavailable"

    return {
        "pair": pair,
        "source": source,
        "effective_currency": target_currency,
        "currency_symbol": symbol,
        "raw_trades_total": _safe_count("public.raw_trades"),
        "latest": latest,
        "points": converted_points,
        "server_time": datetime.now(UTC).isoformat(),
    }
