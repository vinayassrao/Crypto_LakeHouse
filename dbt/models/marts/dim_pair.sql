with all_pairs as (
    select distinct product_id from {{ ref('stg_trades') }}
    union
    select distinct product_id from {{ ref('stg_candles') }}
)
select
    product_id,
    split_part(product_id, '-', 1) as base_currency,
    split_part(product_id, '-', 2) as quote_currency
from all_pairs
