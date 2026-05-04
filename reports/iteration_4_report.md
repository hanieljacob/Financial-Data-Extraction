# Iteration 4 Report

**Date:** 2026-05-03
**Overall accuracy:** 97.8% (88/90), up from 96.7% (87/90) in iteration 3

| Metric               | Iter 1 | Iter 2 | Iter 3 | Iter 4 |
|----------------------|--------|--------|--------|--------|
| operating_income     | 90.0%  | 93.3%  | 93.3%  | **96.7%** |
| stockholders_equity  | 70.0%  | 73.3%  | 100.0% | **100.0%** |
| capital_expenditures | 93.3%  | 96.7%  | 96.7%  | 96.7%  |
| **TOTAL**            | **84.4%** | **87.8%** | **96.7%** | **97.8%** |

---

## Changes from Iteration 3

### 1. Compact operating income rules (targets SLB and TJX)

Added two concise rules to the `operating_income` prompt definition:

- **Segment reconciliation rule**: In segment-profit reconciliation tables, the unlabeled total of all segment profits immediately before "General corporate expense" is operating income, even without an explicit label. *(targets TJX)*
- **Bottom-up fallback**: As a last resort, if no OI line or segment total exists, compute income before taxes plus net interest expense (interest expense minus interest income). *(targets SLB)*

A prior attempt (the failed intermediate run) used a 7-line verbose version of these same rules, which caused stockholders' equity to regress on PM and SBUX due to attention drift in the small model. The compact 3-line version fixed SLB without destabilizing SE.

---

## Remaining Failures (2/90)

| File | Metric | GT | Extracted | Error |
|------|--------|----|-----------|-------|
| TJX_2019_10K.pdf | capital_expenditures | $1,125,139,000 | $1,125,100,000 | 0.003% |
| TJX_2019_10K.pdf | operating_income | $4,763,227,000 | $4,182,073,000 | 12.2% |

- **TJX capex**: $39K rounding difference between PDF presentation and XBRL filing — irreducible.
- **TJX operating_income**: TJX's 2019 income statement presents segment profits that sum to $4,763,227K as an **unlabeled subtotal** in the PDF text. The segment reconciliation rule hasn't resolved this — the model still returns a value near pretax income. This is a structural limitation of the plain-text PDF extraction: the subtotal appears as a bare number with no label, making it unreliable for the model to identify.
