# Iteration 1 Report

**Date:** 2026-05-03
**Overall accuracy:** 84.4% (76/90 correct)

| Metric               | Accuracy |
|----------------------|----------|
| operating_income     | 90.0%    |
| stockholders_equity  | 70.0%    |
| capital_expenditures | 93.3%    |

---

## Changes from baseline

### 1. Swapped target metric: `income_tax` → `capital_expenditures`
The third metric was changed from income tax expense to capital expenditures (`PaymentsToAcquirePropertyPlantAndEquipment` in XBRL). This swap was made in `edgar_single_source.py`, `download_pdfs.py`, and `extract.py`.

### 2. Financial page filtering (`extract.py`)
Replaced whole-document text extraction with a keyword-based page filter (`_financial_pages`). Pages are only included if they contain terms like "cash flows", "statement of operations", "balance sheet", etc., plus a ±1 page buffer. This reduces noise sent to the LLM and keeps the context focused on the relevant financial statements.

### 3. Simplified and tightened the LLM prompt
Removed verbose per-metric definitions and rules from the prompt template. The new prompt gives concise one-line definitions for each metric and shorter instructions for units and nulls. `thinking_budget=0` was also set explicitly on the Gemini call to disable chain-of-thought, reducing latency and token use.

### 4. Bug fix: `correct` flag for null extractions
Fixed a logic bug where `correct` was evaluated outside the `else` branch, meaning a `null` extraction could incorrectly be marked correct. The fix ensures `correct = False` whenever the extracted value is `None`.

### 5. Ticker list refresh
The TICKERS list in `edgar_single_source.py` was updated to include more healthcare, financial, and industrial companies (e.g. MRK, LLY, JPM, BAC, GS, UPS, FDX) to ensure 30 eligible companies with all three target metrics could be found.
