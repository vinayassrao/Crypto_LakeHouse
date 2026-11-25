with source as (
    select * from {{ source('raw', 'raw_candles') }}
),
deduped as (
    select
        *,
        row_number() over (
            partition by product_id, cast(candle_time as date)
            order by ingested_at desc
        ) as rn
    from source
)
select
    product_id,
    cast(candle_time as date) as day,
    open,
    high,
    low,
    close,
    volume
from deduped
where rn = 1
  and volume >= 0
