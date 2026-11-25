# Crypto Market Data Lakehouse

A hybrid streaming + batch data engineering pipeline built on free, local tooling with **PostgreSQL** and **Django**.

> **Data Engineering Portfolio Project:** This project ingests public cryptocurrency market data purely to practice data engineering (streaming ingestion, batch orchestration, ELT modelling, data quality gates, and serving). It produces no buy/sell signals, executes no trades, and gives no financial advice.

## Architecture

```text
STREAMING PATH
Coinbase WebSocket ──trades──▶ ingestion/producer.py ──▶ Kafka (trades.raw)
                                                               │
                                                     ingestion/consumer.py
                                                               ▼
BATCH PATH                                       PostgreSQL (warehouse db: public.raw_*)
Coinbase REST candles ◀─daily─ Airflow DAG ────────────────────┘
                                                               │
                                                   dbt (analytics schema)
                                                   staging (views) ─▶ marts (tables)
                                                               │
                                                        dbt tests (gates)
                                                               │
                                               Django + PostgreSQL (dashboard/)
                                               Web UI + JSON API + Read-Only Admin
```

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Language | Python | Ingestion, DAGs, Django web/API serving |
| Streaming | Apache Kafka (KRaft) | Industry-standard event log between producer & consumer |
| Orchestration | Apache Airflow 2.9 | Batch scheduler for daily Coinbase REST candles |
| Transformation | dbt (`dbt-postgres`) | Modular SQL ELT (`staging` views → `marts` tables) |
| Warehouse | PostgreSQL 16 | Concurrent client-server warehouse + Django backend |
| Data Quality | dbt tests | Automated assertions that fail on bad rows |
| Serving / UI | Django 6 + Chart.js | Web dashboard, JSON API endpoints, and read-only Admin |
| Containers | Docker + Compose | Reproducible local infrastructure |

## Repository Structure

```text
.
├── docker-compose.yml              # Kafka, warehouse Postgres, Airflow Postgres, Airflow
├── requirements.txt                # Pinned Python dependencies
├── .env.example                    # Environment variable template
├── ingestion/
│   ├── db.py                       # Shared psycopg2 warehouse helper
│   ├── producer.py                 # Coinbase WebSocket -> Kafka (with sequence-gap logging)
│   └── consumer.py                 # Kafka -> Postgres public.raw_trades
├── airflow/dags/
│   ├── daily_candles_dag.py        # Daily Coinbase REST candles -> public.raw_candles
│   └── dbt_run_dag.py              # Documented production dbt orchestration note
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml                # Targets warehouse.analytics
│   └── models/
│       ├── schema.yml              # dbt data quality tests
│       ├── staging/                # stg_trades, stg_candles (views)
│       └── marts/                  # dim_pair, fact_trades, agg_hourly_ohlc,
│                                   # agg_daily_volume, reconciliation (tables)
└── dashboard/
    ├── manage.py
    ├── config/                     # Django settings & URL routing (PostgreSQL backend)
    └── lakehouse/                  # Unmanaged warehouse models, SQL services, UI & API
```

## Setup & Runbook

1. **Prerequisites:** Python 3.12+, Docker Desktop, Git.
2. **Environment variables:**
   ```bash
   cp .env.example .env
   ```
3. **Python virtual environment:**
   ```bash
   python -m venv .venv
   # Windows (Git Bash): source .venv/Scripts/activate
   # Windows (PowerShell): .\.venv\Scripts\Activate.ps1
   # macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. **Start infrastructure (Docker Desktop must be running):**
   ```bash
   docker compose up -d
   docker compose ps
   ```
5. **Start streaming ingestion (two terminals):**
   ```bash
   python ingestion/producer.py
   python ingestion/consumer.py
   ```
6. **Trigger batch candles in Airflow:**
   - Open `http://localhost:8080` (login: `airflow` / `airflow`).
   - Unpause and trigger the `daily_candles` DAG.
7. **Run dbt models & data quality tests:**
   ```bash
   cd dbt
   dbt run --profiles-dir .
   dbt test --profiles-dir .
   cd ..
   ```
8. **Run Django migrations & launch the Django dashboard:**
   ```bash
   python dashboard/manage.py migrate
   python dashboard/manage.py runserver
   ```
   Open `http://127.0.0.1:8000/`.

### Django Endpoints

- `/` — Interactive dashboard (pair selector, hourly close chart, daily volume chart, reconciliation table, recent trades)
- `/api/health/` — PostgreSQL connectivity and row counts across raw & analytics tables
- `/api/pairs/` — Available trading pairs
- `/api/ohlc/?pair=BTC-USD` — Hourly OHLC series
- `/api/reconciliation/?pair=BTC-USD` — Stream vs official candle reconciliation
- `/api/daily-volume/?pair=BTC-USD` — Daily streamed volume
- `/admin/` — Django Admin (read-only views for `analytics.dim_pair` and `analytics.fact_trades`)

## Tradeoffs & Decisions

- **Why ELT, not ETL?** Raw trades and raw candles land append-only in `public.raw_*` without pre-cleaning. Deduplication and filtering happen in dbt (`stg_trades`, `stg_candles`), so transformation bugs can be fixed by re-running dbt without re-fetching source data.
- **Why PostgreSQL, not DuckDB?** PostgreSQL is client-server, allowing the Kafka consumer, Airflow DAG, dbt, and Django to read and write concurrently without single-writer file locks. At massive analytical scale, a columnar warehouse (Snowflake/BigQuery) would win; swapping `dbt-postgres` for `dbt-snowflake` is straightforward.
- **Why Kafka on a single machine?** Demonstrates the durable event-log streaming pattern cleanly; in production this would be managed Kafka (MSK / Confluent Cloud) with `confluent-kafka` and batched DB commits.
- **Why Django + PostgreSQL?** Replaces a lightweight prototyping UI with a structured web framework, parameterized PostgreSQL queries, JSON API endpoints, unmanaged mart models, and testable views.

## What I'd Do Next

- Swap local PostgreSQL for managed RDS / Cloud SQL (connection env vars only).
- Migrate warehouse analytics to Snowflake or BigQuery via dbt adapter swap.
- Build a custom Airflow image containing `dbt-postgres` to schedule dbt runs directly after `daily_candles`.
- Add indexes on `(product_id, event_time)` in `raw_trades` and `fact_trades` for larger datasets, plus Prometheus/Grafana observability.
