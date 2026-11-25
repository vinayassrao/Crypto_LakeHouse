with my_daily as (
    select
        product_id,
        trade_date as day,
        sum(size)  as my_volume,
        min(price) as my_low,
        max(price) as my_high
    from {{ ref('stg_trades') }}
    group by 1, 2
),
official as (
    select
        product_id,
        day,
        volume as official_volume,
        low    as official_low,
        high   as official_high
    from {{ ref('stg_candles') }}
)
select
    o.product_id,
    o.day,
    m.my_volume,
    o.official_volume,
    abs(m.my_volume - o.official_volume) as volume_gap,
    case
        when m.my_volume is null then 'NO_STREAM_DATA'
        when abs(m.my_volume - o.official_volume)
             / nullif(o.official_volume, 0) > 0.5 then 'DIVERGENT'
        else 'OK'
    end as status
from official o
left join my_daily m
    on o.product_id = m.product_id
   and o.day = m.day
