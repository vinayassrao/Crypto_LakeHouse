with source as (
    select * from {{ source('raw', 'raw_trades') }}
),
deduped as (
    select
        *,
        row_number() over (
            partition by trade_id order by ingested_at
        ) as rn
    from source
)
select
    trade_id,
    product_id,
    side,
    size,
    price,
    event_time,
    cast(event_time as date) as trade_date
from deduped
where rn = 1
  and price > 0
  and size > 0
