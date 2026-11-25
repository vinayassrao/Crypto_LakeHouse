# Crypto Lakehouse Guide — Corrections & Patches

Companion to `Crypto_Lakehouse_Step_By_Step_Guide.docx`. Keep this in the repo root as `CORRECTIONS.md`.

Reviewed the whole guide. The structure is sound and most code is correct. There are **two real bugs** that will likely bite on day one, **one root cause** (unpinned dependencies) behind most future breakage, and a few notes. Severity and confidence are tagged on each.

Equally important: a "verified correct — do not touch" list, so you don't waste time second-guessing the parts that are fine.

---

## 1. Pin your dependencies — [Certain] · root cause of most breakage

The guide's `requirements.txt` is fully unpinned. That's the real source of risk: an unpinned install can pull a major version that changed its API (this is exactly what causes issue #2 below). It also makes "works on my machine" non-reproducible — the opposite of the point.

**Replace `requirements.txt` with known-good ranges:**

```
kafka-python>=2.2.0          # 2.2.x supports Kafka 4.0 brokers; older versions DO NOT
websocket-client>=1.7,<2
psycopg2-binary>=2.9,<3
requests>=2.31,<3
dbt-postgres>=1.7,<1.9
sqlalchemy>=1.4,<2.0         # see #2 — <2.0 sidesteps the dashboard param bug
streamlit>=1.30,<2
pandas>=2.0,<3
```

**Then lock exact versions after your first successful build:**

```bash
pip freeze > requirements.txt
```

That single command is the most reliable pin — it records exactly what worked, so the next clone is identical.

---

## 2. Dashboard query will likely error under SQLAlchemy 2.x — [Likely] · Module 7

In `dashboard/app.py`, every `pd.read_sql` uses psycopg2-style named params:

```python
'... where product_id = %(p)s ...', engine, params={'p': pair}
```

Passed a SQLAlchemy **Engine**, pandas routes through SQLAlchemy. Under SQLAlchemy 2.0 a bare string with `%(p)s` commonly raises (param-style mismatch / "not an executable object"), because SQLAlchemy 2.0 expects `text()` with `:p` bind params.

**Two fixes — pick one:**

**(a) Simplest:** pin `sqlalchemy>=1.4,<2.0` (already in the requirements above). The `%(p)s` style works on 1.4. Done.

**(b) Robust (works on SQLAlchemy 2.x):** wrap each query in `text()` and switch `%(p)s` → `:p`:

```python
from sqlalchemy import create_engine, text

ohlc = pd.read_sql(
    text('select hour, close from analytics.agg_hourly_ohlc '
         'where product_id = :p order by hour'),
    engine, params={'p': pair},
)
```

Apply the same `text()` + `:p` change to the reconciliation and daily-volume queries. The pair-selector query has no params, so it's fine either way.

---

## 3. kafka-python / Kafka 4 — [Note, downgraded] · Modules 2–3

Earlier worry was overstated. Current `kafka-python` (2.2.x) is maintained again and tests against broker 4.0, so `apache/kafka:latest` works **as long as pip installs a recent version** — which #1's pin guarantees.

- Do **not** use `kafka-python-ng` — that fork was archived (read-only) in July 2025.
- If you still see `NoBrokersAvailable` (a version-probe quirk that predates 4.0), set the version explicitly:

```python
producer = KafkaProducer(
    bootstrap_servers='localhost:9092',
    api_version=(3, 8, 0),   # or your broker's version
    value_serializer=lambda v: json.dumps(v).encode('utf-8'),
)
```

Optional belt-and-suspenders: pin the broker image instead of `:latest`, e.g. `image: apache/kafka:3.8.0`, so the broker version never drifts under you.

---

## 4. Airflow startup command is redundant/fragile — [Low] · Module 4

The compose `command` chains:

```
airflow db init && airflow users create ... && airflow standalone
```

In Airflow 2.9: `airflow db init` is deprecated (prefer `airflow db migrate`), and `airflow standalone` **already** migrates the DB and creates an admin user on its own. The chain works but emits deprecation warnings and double-creates the admin.

**Cleaner:** let `standalone` do the work —

```yaml
command: bash -c 'airflow standalone'
```

`standalone` prints a generated admin password in its logs (`docker compose logs airflow | grep -i password`). If you want your fixed `airflow/airflow` login instead, keep the `users create` line but drop `db init`:

```yaml
command: >
  bash -c 'airflow db migrate &&
    airflow users create --username airflow --password airflow
      --firstname Admin --lastname User --role Admin --email admin@example.com &&
    airflow standalone'
```

Low priority — it's pinned to 2.9.0, so it won't suddenly break.

---

## Verified correct — do NOT change these

I checked these specifically because they're common failure points. They're right as written; don't "fix" them:

- **Coinbase candle unpacking** `ts, low, high, open_, close, volume = row` — Coinbase returns `[time, low, high, open, close, volume]`, **not** OHLC order. The guide gets this right. Reordering it to "open, high, low, close" would *introduce* a bug.
- **dbt schema layout** — `profiles.yml schema: analytics` with no `+schema:` override means staging views and mart tables all land in `analytics`. The dashboard's `analytics.fact_trades` etc. resolve correctly. No `analytics_analytics` doubling.
- **`array_agg(price order by ...)[1]`** for open/close — Postgres arrays are 1-indexed; the workaround for the missing `first()`/`last()` is correct.
- **Candle re-insert duplicates** — the DAG `INSERT`s (not upserts) every run, so candles duplicate. This is *intended*: `stg_candles` dedups with `row_number() ... order by ingested_at desc`. Working as designed.
- **`'matches'` channel** on `wss://ws-feed.exchange.coinbase.com` — legitimate; emits `match` messages. (If it ever goes quiet, the `full` channel also emits `match` events — but don't pre-change it.)

---

## Two things that are correct but worth knowing (talking points, not bugs)

- **Per-row `conn.commit()` in the consumer** is correct but slow — it's your throughput ceiling. Real optimization story if you batch commits later.
- **Kafka auto-commit + per-row DB write** is at-least-once: a crash between offset-commit and DB-write can duplicate or drop a trade. The dbt `row_number() partition by trade_id` dedup is what makes this safe downstream. This is genuinely good design — and a strong answer to "how did you handle exactly-once?"

---

## Priority order

1. Pin dependencies (#1) — do this before `pip install`, it prevents #2 and #3 from ever appearing.
2. Fix the dashboard query (#2) — or rely on the `sqlalchemy<2.0` pin.
3. Leave #3 alone unless `NoBrokersAvailable` shows up.
4. Tidy the Airflow command (#4) only if it annoys you.
