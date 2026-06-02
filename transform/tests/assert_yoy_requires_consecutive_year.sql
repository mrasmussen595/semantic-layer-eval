-- A YoY baseline is valid only when the immediately preceding mart row is the prior
-- fiscal year. Missing fiscal years must surface as unavailable rather than comparing
-- against an older period.
with years as (
    select
        ticker,
        fiscal_year,
        prev_total_revenue,
        lag(fiscal_year) over (
            partition by ticker order by fiscal_year
        ) as previous_fiscal_year
    from {{ ref('fct_company_year') }}
)

select *
from years
where prev_total_revenue is not null
  and previous_fiscal_year <> fiscal_year - 1
