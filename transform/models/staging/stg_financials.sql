-- XBRL tag normalization: collapse the long-format facts into one row per
-- (company, fiscal year) with canonical financial line items.
--
-- This is where the real-world XBRL inconsistency is handled: companies tag the same
-- economic concept with different us-gaap names across filings and eras. We COALESCE a
-- prioritized list of candidate tags into one canonical column. Example seen in the data:
-- most companies tag revenue RevenueFromContractWithCustomerExcludingAssessedTax, but
-- CrowdStrike uses ...IncludingAssessedTax.
--
-- gross_profit falls back to (revenue - cost_of_revenue) when a company does not tag a
-- single GrossProfit line. Workday tags neither a consolidated GrossProfit nor a single
-- CostOfRevenue (it splits cost of revenue across service components), so gross_profit is
-- NULL for Workday by design -- the governed layer admits the gap rather than fabricating.
with f as (
    select * from {{ ref('stg_facts') }}
),

pivoted as (
    select
        ticker,
        fiscal_year,
        max(period_end) as fiscal_year_end_date,

        -- revenue candidates (priority order)
        max(value) filter (where concept = 'RevenueFromContractWithCustomerExcludingAssessedTax') as rev_excl,
        max(value) filter (where concept = 'RevenueFromContractWithCustomerIncludingAssessedTax') as rev_incl,
        max(value) filter (where concept = 'Revenues') as rev_revenues,
        max(value) filter (where concept = 'SalesRevenueNet') as rev_salesnet,

        -- cost of revenue candidates
        max(value) filter (where concept = 'CostOfRevenue') as cor,
        max(value) filter (where concept = 'CostOfGoodsAndServicesSold') as cogs,

        -- gross profit (when tagged directly)
        max(value) filter (where concept = 'GrossProfit') as gross_profit_tag,

        -- operating income / R&D
        max(value) filter (where concept = 'OperatingIncomeLoss') as operating_income,
        max(value) filter (where concept = 'ResearchAndDevelopmentExpense') as rnd_expense,

        -- operating cash flow candidates
        max(value) filter (where concept = 'NetCashProvidedByUsedInOperatingActivities') as ocf_main,
        max(value) filter (where concept = 'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations') as ocf_cont,

        -- capex candidates
        max(value) filter (where concept = 'PaymentsToAcquirePropertyPlantAndEquipment') as capex_ppe,
        max(value) filter (where concept = 'PaymentsToAcquireProductiveAssets') as capex_prod
    from f
    group by ticker, fiscal_year
)

select
    ticker,
    fiscal_year,
    fiscal_year_end_date,
    coalesce(rev_excl, rev_incl, rev_revenues, rev_salesnet) as total_revenue,
    coalesce(cor, cogs) as cost_of_revenue,
    coalesce(
        gross_profit_tag,
        coalesce(rev_excl, rev_incl, rev_revenues, rev_salesnet) - coalesce(cor, cogs)
    ) as gross_profit,
    operating_income,
    rnd_expense,
    coalesce(ocf_main, ocf_cont) as operating_cash_flow,
    coalesce(capex_ppe, capex_prod) as capex
from pivoted
