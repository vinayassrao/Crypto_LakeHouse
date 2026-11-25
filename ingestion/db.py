import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def get_conn():
    """Return a PostgreSQL connection to the warehouse database."""
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=os.getenv("PG_PORT", "5432"),
        dbname=os.getenv("PG_DB", "warehouse"),
        user=os.getenv("PG_USER", "lake"),
        password=os.getenv("PG_PASSWORD", "lakepass"),
    )
