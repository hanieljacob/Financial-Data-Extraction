# Iteration 2 Report

**Date:** 2026-05-03
**Approach:** Prompt optimization (no few-shot)

---

## Changes from Iteration 1

### 1. Stockholders' equity disambiguation (targets 9 failures)
Added explicit NCI (noncontrolling interest) disambiguation to the prompt: use the parent-company-only subtotal; if "Noncontrolling interests" appears as a separate line, use the line **above** it, not the grand total. Also blocked "Total liabilities and stockholders' equity" as a valid return value.

### 2. Operating income derivation fallback (targets 2 nulls + 1 wrong)
Added instruction to derive operating income when no explicit line exists: total revenue minus all operating expenses. Also anchored to the consolidated total (not a segment figure) and blocked "income before taxes" as a substitute.

### 3. Capital expenditures — continuing operations only (targets 1 wrong)
Added rule to use only continuing operations CapEx, explicitly excluding discontinued operations.

### 4. Page filter keyword expansion (supports operating income fixes)
Added `"income from operations"`, `"operating income"`, `"statements of income"`, and `"results of operations"` to `_FS_KEYWORDS` to improve recall for non-standard income statement page formats.

---

## Expected Outcome

| Metric               | Iter 1 | Iter 2 (expected) |
|----------------------|--------|-------------------|
| operating_income     | 90.0%  | ~93–97%           |
| stockholders_equity  | 70.0%  | ~93%              |
| capital_expenditures | 93.3%  | ~97%              |
| **TOTAL**            | **84.4%** | **~94–96%**    |

Estimated irreducible ceiling: ~87–88/90 due to sub-rounding PDF vs XBRL differences on TJX capex (0.003% error) and SBUX equity (0.09% error).
