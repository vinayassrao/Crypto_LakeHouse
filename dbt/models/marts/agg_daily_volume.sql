select
    product_id,
    trade_date,
    sum(size)         as total_volume,
    sum(size * price) as total_value_usd,
    count(*)          as trade_count
from {{ ref('stg_trades') }}
group by 1, 2
