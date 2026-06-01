select
    ticker,
    cik,
    name,
    fiscal_year_end
from {{ source('raw', 'companies') }}
