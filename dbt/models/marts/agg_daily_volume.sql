select
    product_id,
    split_part(product_id, '-', 2) as quote_currency,
    trade_date,
    sum(size)                      as total_volume,
    sum(size * price)              as total_notional_value,
    sum(size * price)              as total_value_usd,
    count(*)                       as trade_count
from {{ ref('stg_trades') }}
group by 1, 2, 3
