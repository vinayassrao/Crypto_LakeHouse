-- Postgres has no first()/last() ordered aggregate; array_agg(...)[1]
-- picks the earliest and latest trade price within each hour bucket.
select
    product_id,
    date_trunc('hour', event_time)                 as hour,
    (array_agg(price order by event_time asc))[1]  as open,
    max(price)                                     as high,
    min(price)                                     as low,
    (array_agg(price order by event_time desc))[1] as close,
    sum(size)                                      as volume,
    count(*)                                       as trade_count
from {{ ref('stg_trades') }}
group by 1, 2
