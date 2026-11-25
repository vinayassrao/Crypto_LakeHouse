import json
import logging
import os
import time
from pathlib import Path

import websocket
from dotenv import load_dotenv
from kafka import KafkaProducer

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

PAIRS = ["BTC-USD", "ETH-USD", "SOL-USD"]
WS_URL = os.getenv("COINBASE_WS_URL", "wss://ws-feed.exchange.coinbase.com")
TOPIC = os.getenv("KAFKA_TOPIC_TRADES", "trades.raw")
BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")


def create_producer() -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )


def main() -> None:
    producer = create_producer()
    last_sequence: dict[str, int] = {}

    def on_open(ws):
        logger.info("WebSocket connected, subscribing to pairs: %s", PAIRS)
        ws.send(
            json.dumps(
                {
                    "type": "subscribe",
                    "product_ids": PAIRS,
                    "channels": ["matches"],
                }
            )
        )

    def on_message(ws, message):
        data = json.loads(message)
        if data.get("type") != "match":
            return

        product_id = data["product_id"]
        seq = data.get("sequence")
        if isinstance(seq, int):
            prev = last_sequence.get(product_id)
            if prev is not None and seq <= prev:
                logger.warning(
                    "Out-of-order/duplicate sequence for %s: got %s after %s",
                    product_id,
                    seq,
                    prev,
                )
            elif prev is not None and seq > prev + 1:
                logger.warning(
                    "Sequence gap for %s: expected %s, got %s (gap=%s)",
                    product_id,
                    prev + 1,
                    seq,
                    seq - prev - 1,
                )
            last_sequence[product_id] = max(prev or seq, seq)

        producer.send(TOPIC, data)
        logger.info("Published %s @ %s (size=%s)", product_id, data["price"], data["size"])

    def on_error(ws, error):
        logger.error("WebSocket error: %s", error)

    while True:
        ws = websocket.WebSocketApp(
            WS_URL,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
        )
        ws.run_forever(ping_interval=20, ping_timeout=10)
        logger.warning("WebSocket closed, reconnecting in 5s...")
        time.sleep(5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Producer stopped by user.")
