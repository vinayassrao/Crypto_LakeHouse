import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from kafka import KafkaConsumer

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db import get_conn

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

TOPIC = os.getenv("KAFKA_TOPIC_TRADES", "trades.raw")
BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

CREATE_RAW_TRADES_SQL = """
    CREATE TABLE IF NOT EXISTS raw_trades (
        trade_id    BIGINT,
        sequence    BIGINT,
        product_id  TEXT,
        side        TEXT,
        size        DOUBLE PRECISION,
        price       DOUBLE PRECISION,
        event_time  TIMESTAMPTZ,
        ingested_at TIMESTAMPTZ DEFAULT now()
    )
"""

INSERT_RAW_TRADE_SQL = """
    INSERT INTO raw_trades (
        trade_id, sequence, product_id, side, size, price, event_time
    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
"""


def ensure_raw_trades_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(CREATE_RAW_TRADES_SQL)
    conn.commit()


def main() -> None:
    conn = get_conn()
    ensure_raw_trades_table(conn)
    logger.info("Table raw_trades ready.")

    consumer = KafkaConsumer(
        TOPIC,
        bootstrap_servers=BOOTSTRAP_SERVERS,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        auto_offset_reset="earliest",
        group_id="trade-loader",
    )

    logger.info("Listening for trades on topic %s...", TOPIC)
    try:
        with conn.cursor() as cur:
            for msg in consumer:
                t = msg.value
                cur.execute(
                    INSERT_RAW_TRADE_SQL,
                    (
                        t["trade_id"],
                        t["sequence"],
                        t["product_id"],
                        t["side"],
                        float(t["size"]),
                        float(t["price"]),
                        t["time"],
                    ),
                )
                conn.commit()
                logger.info("Inserted trade: %s @ %s", t["product_id"], t["price"])
    except KeyboardInterrupt:
        logger.info("Consumer stopped by user.")
    finally:
        consumer.close()
        conn.close()


if __name__ == "__main__":
    main()
