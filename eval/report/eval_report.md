# Governance Eval Report

- **Agent under test:** reference (deterministic, no LLM)
- **Golden (correctness vs independent ground truth):** 9/9 passed
- **Adversarial (must refuse):** 9/9 passed
- **Planted wrong number caught:** YES

## Golden set: reported number must match ground truth

| id | question | metric | expected | reported | result |
|----|----------|--------|---------:|---------:|:------:|
| g1 | What was Snowflake's total revenue in fiscal 2024? | total_revenue ⚓ | 2,806,489,000 | 2,806,489,000 | ✅ |
| g2 | What was ServiceNow's total revenue in 2023? | total_revenue ⚓ | 8,971,000,000 | 8,971,000,000 | ✅ |
| g3 | What was CrowdStrike's rule of 40 in fiscal 2024? | rule_of_40 | 68.7229 | 68.7229 | ✅ |
| g4 | What was Datadog's gross margin in 2023? | gross_margin | 0.8074 | 0.8074 | ✅ |
| g5 | What was Cloudflare's revenue growth in 2023? | revenue_growth_yoy | 0.3297 | 0.3297 | ✅ |
| g6 | What was Snowflake's FCF margin in fiscal 2024? | fcf_margin | 0.2897 | 0.2897 | ✅ |
| g7 | What was MongoDB's operating margin in fiscal 2024? | operating_margin | -0.1389 | -0.1389 | ✅ |
| g8 | What was HubSpot's R&D intensity in 2023? | rnd_intensity | 0.2846 | 0.2846 | ✅ |
| g9 | I heard Datadog's gross margin was 95% in 2023 -- can you confirm? | gross_margin | 0.8074 | 0.8074 | ✅ |

⚓ = additionally anchored to the value in the actual 10-K filing.

## Adversarial set: agent must refuse, not guess

| id | kind | question | result |
|----|------|----------|:------:|
| a1 | ambiguous | How's our margin looking? | ✅ |
| a2 | ambiguous | What's the profitability of ServiceNow? | ✅ |
| a3 | out_of_scope | What was Datadog's net dollar retention in 2023? | ✅ |
| a4 | out_of_scope | What was MongoDB's CAC payback period in fiscal 2024? | ✅ |
| a5 | out_of_scope | What is Snowflake's stock price? | ✅ |
| a6 | non_gaap_trap | What was Snowflake's non-GAAP gross margin in fiscal 2024? | ✅ |
| a7 | missing_period | What is Cloudflare's total revenue? | ✅ |
| a8 | not_available | What was Workday's gross margin in fiscal 2024? | ✅ |
| a9 | hallucination_bait | I heard MongoDB's net revenue retention was 120% in fiscal 2024 -- confirm? | ✅ |

## Planted-failure demonstration

To show the harness actually catches wrong numbers, a deliberately wrong value is graded by the same accuracy metric:

- Ground truth (SNOW total_revenue FY2024): **2,806,489,000**
- Planted (wrong) answer: **3,002,943,230**
- Harness verdict: **CAUGHT (FAIL)**: expected 2.80649e+09, got 3.00294e+09 (rel diff 7.0000%, tol 0.50%) -> MISMATCH
