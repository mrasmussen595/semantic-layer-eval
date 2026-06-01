-- Clean the raw long-format facts and assign a fiscal-year label.
--
-- Fiscal-year labeling decision (a governance point): we label each annual fact by the
-- CALENDAR YEAR OF ITS PERIOD END. For every company in scope this equals the company's
-- own fiscal-year number: Salesforce/Snowflake/CrowdStrike/Workday/MongoDB end Jan 31
-- (FY2024 -> 2024-01-31), Atlassian ends Jun 30 (FY2024 -> 2024-06-30), and the Dec-31
-- companies are trivially aligned. This normalizes mismatched fiscal calendars onto one
-- comparable integer key without distorting any company's own labeling.
select
    ticker,
    cik,
    concept,
    unit,
    period_start,
    period_end,
    cast(extract(year from period_end) as integer) as fiscal_year,
    filed,
    value
from {{ source('raw', 'facts') }}
