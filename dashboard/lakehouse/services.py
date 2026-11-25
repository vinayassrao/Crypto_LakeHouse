from __future__ import annotations

from typing import Any

from django.db import DatabaseError, connection

DEFAULT_PAIRS = ["BTC-USD", "ETH-USD", "SOL-USD"]


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


def get_hourly_ohlc(pair: str) -> list[dict[str, Any]]:
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
        return rows
    except DatabaseError:
        return []


def get_daily_volume(pair: str) -> list[dict[str, Any]]:
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


def get_recent_trades(pair: str, limit: int = 15) -> list[dict[str, Any]]:
    try:
        rows = _fetch_dicts(
            """
            SELECT trade_id, side, size, price, trade_value_usd, event_time
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
        return rows
    except DatabaseError:
        return []
