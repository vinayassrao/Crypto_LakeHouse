import os
import time
from datetime import datetime, timedelta

import psycopg2
import requests
from airflow.operators.python import PythonOperator

from airflow import DAG

PAIRS = ["BTC-USD", "ETH-USD", "SOL-USD"]

CREATE_RAW_CANDLES_SQL = """
    CREATE TABLE IF NOT EXISTS raw_candles (
        product_id  TEXT,
        candle_time TIMESTAMPTZ,
        low         DOUBLE PRECISION,
        high        DOUBLE PRECISION,
        open        DOUBLE PRECISION,
        close       DOUBLE PRECISION,
        volume      DOUBLE PRECISION,
        ingested_at TIMESTAMPTZ DEFAULT now()
    )
"""


def get_conn():
    """Connect to the warehouse Postgres (defaults to container host 'warehouse')."""
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "warehouse"),
        port=os.getenv("PG_PORT", "5432"),
        dbname=os.getenv("PG_DB", "warehouse"),
        user=os.getenv("PG_USER", "lake"),
        password=os.getenv("PG_PASSWORD", "lakepass"),
    )


def fetch_and_load(**context):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_RAW_CANDLES_SQL)
            conn.commit()

            for pair in PAIRS:
                url = (
                    f"https://api.exchange.coinbase.com/products/"
                    f"{pair}/candles?granularity=86400"
                )
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                rows = response.json()

                for ts, low, high, open_, close, volume in rows:
                    cur.execute(
                        "INSERT INTO raw_candles "
                        "(product_id, candle_time, low, high, open, close, volume) "
                        "VALUES (%s, to_timestamp(%s), %s, %s, %s, %s, %s)",
                        (pair, ts, low, high, open_, close, volume),
                    )
                conn.commit()
                print(f"Loaded {len(rows)} candles for {pair}")
                time.sleep(1)
    finally:
        conn.close()


with DAG(
    dag_id="daily_candles",
    start_date=datetime(2026, 1, 1),
    schedule="@daily",
    catchup=False,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["crypto-lakehouse", "batch"],
) as dag:
    PythonOperator(
        task_id="fetch_and_load_candles",
        python_callable=fetch_and_load,
    )
