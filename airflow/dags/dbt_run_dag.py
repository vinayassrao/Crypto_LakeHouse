"""Optional dbt orchestration placeholder.

Per Section 5.8 of the build guide, dbt is executed manually from the host
(`cd dbt && dbt run --profiles-dir .`) because the stock `apache/airflow:2.9.0`
image does not ship with `dbt-postgres`.

Production upgrade path: build a custom Airflow image with `dbt-postgres`
installed and trigger `dbt run` / `dbt test` via `BashOperator` or
Astronomer Cosmos after `daily_candles` completes.
"""
