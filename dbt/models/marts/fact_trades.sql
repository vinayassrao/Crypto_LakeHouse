select
    t.trade_id,
    t.product_id,
    t.side,
    t.size,
    t.price,
    t.size * t.price as trade_value_usd,
    t.event_time,
    t.trade_date
from {{ ref('stg_trades') }} t
