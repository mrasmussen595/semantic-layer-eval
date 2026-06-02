-- One row per (company, fiscal year): the canonical financial base the semantic layer
-- points at. Carries prior-year revenue so revenue_growth_yoy (and rule_of_40) compile
-- to simple per-row expressions over a single table.
with fin as (
    select * from {{ ref('stg_financials') }}
),

co as (
    select * from {{ ref('stg_companies') }}
),

joined as (
    select
        fin.ticker,
        co.name,
        fin.fiscal_year,
        fin.fiscal_year_end_date,
        fin.total_revenue,
        fin.cost_of_revenue,
        fin.gross_profit,
        fin.operating_income,
        fin.rnd_expense,
        fin.operating_cash_flow,
        fin.capex
    from fin
    inner join co on fin.ticker = co.ticker
)

select
    *,
    case
        when lag(fiscal_year) over (
            partition by ticker order by fiscal_year
        ) = fiscal_year - 1
        then lag(total_revenue) over (
            partition by ticker order by fiscal_year
        )
    end as prev_total_revenue
from joined
