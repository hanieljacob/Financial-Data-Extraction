# Iteration 3 Report

**Date:** 2026-05-03
**Overall accuracy:** 96.7% (87/90), up from 87.8% (79/90) in iteration 2

| Metric               | Iter 1 | Iter 2 | Iter 3 |
|----------------------|--------|--------|--------|
| operating_income     | 90.0%  | 93.3%  | 93.3%  |
| stockholders_equity  | 70.0%  | 73.3%  | **100.0%** |
| capital_expenditures | 93.3%  | 96.7%  | 96.7%  |
| **TOTAL**            | **84.4%** | **87.8%** | **96.7%** |

---

## Changes from Iteration 2

### 1. Stockholders' equity — full NCI overhaul (fixed all 8 remaining failures → 100%)
Three additions to the prompt definition:
- **XBRL concept anchor**: Explicitly referenced `us-gaap:StockholdersEquity` as the target concept — equity of the parent entity's shareholders only, excluding noncontrolling interests.
- **Company-name preference rule**: Instructed the model to prefer lines containing the company's own name (e.g. "Total CVS Health shareholders' equity") over generic "Total equity" or "Total stockholders' equity and noncontrolling interests".
- **Expanded NCI label variants**: Added "Noncontrolling interest" (singular), "Redeemable noncontrolling interests", and "Minority interest" to the list of NCI line labels the model must recognize and exclude.

### 2. Operating income — gross profit disambiguation (partial fix for TJX)
Added an explicit warning: `revenue minus cost of sales alone gives GROSS PROFIT, not operating income`. TJX improved from 133.9% error (iter 2) to 12.4% error (iter 3) — the model stopped returning gross profit and is now subtracting additional operating expenses, though it's still not capturing all of them.

Added valid label variants: `"income before interest and taxes"`, `"income before interest, taxes and other"` (targets SLB-style non-standard labeling — SLB remains a failure).

---

## Remaining Failures (3/90)

| File | Metric | GT | Extracted | Error |
|------|--------|----|-----------|-------|
| TJX_2019_10K.pdf | capital_expenditures | $1,125,139,000 | $1,125,100,000 | 0.003% |
| TJX_2019_10K.pdf | operating_income | $4,763,227,000 | $4,173,211,000 | 12.4% |
| SLB_2023_10K.pdf | operating_income | $6,523,000,000 | $5,282,000,000 | 19.0% |

- **TJX capex**: $39K rounding difference between PDF and XBRL filing — irreducible.
- **TJX operating_income**: Model now accounts for SG&A but is still missing ~$590M in operating expenses (likely miscellaneous operating items not captured by the derivation).
- **SLB operating_income**: SLB's 2023 income statement structure does not expose a standard operating income line. The model continues to fall back to income before taxes ($5,282M) rather than the correct pre-interest subtotal ($6,523M).
