-- (ticker, fiscal_year) must be unique in the mart. Returns offending rows (build fails
-- if any exist).
select ticker, fiscal_year, count(*) as n
from {{ ref('fct_company_year') }}
group by ticker, fiscal_year
having count(*) > 1
