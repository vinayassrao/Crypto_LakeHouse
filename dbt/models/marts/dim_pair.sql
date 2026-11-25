select distinct
    product_id,
    split_part(product_id, '-', 1) as base_currency,
    split_part(product_id, '-', 2) as quote_currency
from {{ ref('stg_trades') }}
