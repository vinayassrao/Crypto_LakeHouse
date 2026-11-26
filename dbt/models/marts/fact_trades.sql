select
    t.trade_id,
    t.product_id,
    split_part(t.product_id, '-', 1) as base_currency,
    split_part(t.product_id, '-', 2) as quote_currency,
    t.side,
    t.size,
    t.price,
    t.size * t.price                 as notional_value,
    t.size * t.price                 as trade_value_usd,
    t.event_time,
    t.trade_date
from {{ ref('stg_trades') }} t
