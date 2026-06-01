-- Anchor the normalized mart to values that are independently verifiable in the actual
-- 10-K filings. If tag-normalization ever drifts, these break the build. Tolerance 0.5%.
with expected(ticker, fiscal_year, revenue) as (
    values
        ('SNOW', 2024, 2806.0e6),   -- Snowflake FY2024 (period end 2024-01-31)
        ('CRM',  2024, 34857.0e6),  -- Salesforce FY2024
        ('DDOG', 2023, 2128.0e6),   -- Datadog FY2023
        ('NOW',  2023, 8971.0e6),   -- ServiceNow FY2023
        ('CRWD', 2024, 3056.0e6),   -- CrowdStrike FY2024 (IncludingAssessedTax tag)
        ('NET',  2023, 1297.0e6)    -- Cloudflare FY2023
)
select
    e.ticker,
    e.fiscal_year,
    e.revenue as expected_revenue,
    m.total_revenue as actual_revenue
from expected e
left join {{ ref('fct_company_year') }} m
    on e.ticker = m.ticker and e.fiscal_year = m.fiscal_year
where m.total_revenue is null
   or abs(m.total_revenue - e.revenue) / e.revenue > 0.005
