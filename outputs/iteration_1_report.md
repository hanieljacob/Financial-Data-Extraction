# 10-K Data Extraction — Iteration 1 Report

## Approach

### Data Pipeline

The system is built as a single-source pipeline: both the PDFs and the ground-truth values are derived from the same SEC EDGAR filing accession number. This eliminates cross-source misalignment — every extracted value is compared against the XBRL fact from the exact document being read.

**Step 1 — Ground truth (`edgar_single_source.py`)**  
For each company, the SEC EDGAR submissions API is queried to find all 10-K filings. The XBRL company-concept API is then used to pull values for the three target metrics. The most recent fiscal year in which all three metrics are available is selected, giving one filing per company. The output is `edgar_single_source.json`.

**Step 2 — PDF download (`download_pdfs.py`)**  
PDFs are downloaded directly from the EDGAR archives URL embedded in each filing's metadata. If the primary document is HTML, the script checks the filing index for a PDF exhibit first; if none exists, Playwright renders the HTML to PDF locally (zero direct SEC requests from the browser to avoid rate-limiting).

**Step 3 — LLM extraction (`extract.py`)**  
The full PDF text is extracted using pdfplumber (with pymupdf as a fallback for CID-encoded fonts) and sent to Gemini (`gemini-3.1-flash-lite-preview`) with a structured prompt requesting the three values as JSON with raw value and unit. The unit is used to scale the raw number to actual dollars before comparing against ground truth. Results are appended to a SQLite database tagged with a run ID.

### Metrics

- **Correct**: extracted value equals the XBRL ground truth exactly (integer match after scaling).
- **Error %**: `|extracted − ground_truth| / |ground_truth| × 100` — stored for all non-null extractions regardless of correctness, for diagnostic use.

### Dataset

30 companies, one 10-K per company, sourced from well-known S&P 500 constituents across sectors. All 30 have verified XBRL ground truth for all three metrics.

| Company | Year | Company | Year |
|---------|------|---------|------|
| AAPL | 2025 | META | 2025 |
| ABBV | 2025 | MO | 2025 |
| AMD | 2025 | MSFT | 2025 |
| AMGN | 2025 | NVDA | 2026 |
| AMZN | 2025 | ORCL | 2025 |
| AVGO | 2025 | PEP | 2025 |
| BIIB | 2021 | PG | 2025 |
| BKNG | 2025 | PM | 2025 |
| BLK | 2025 | QCOM | 2025 |
| CMG | 2025 | SBUX | 2025 |
| COST | 2025 | TJX | 2019 |
| GILD | 2025 | WMT | 2026 |
| GOOGL | 2025 | HD | 2026 |
| JNJ | 2014 | KO | 2025 |
| LOW | 2026 | MCD | 2025 |

---

## Iteration 1 Results

**Run ID:** `2026-05-02T17:20:42`  
**Total comparisons:** 90 (30 PDFs × 3 metrics)

| Metric | Correct | Wrong | Null | Accuracy | Mean Error % |
|---|---|---|---|---|---|
| operating_income | 27 | 1 | 2 | **90.0%** | 0.5% |
| income_tax | 28 | 1 | 1 | **93.3%** | 0.0% |
| stockholders_equity | 20 | 9 | 1 | **66.7%** | 18.2% |
| **TOTAL** | **75** | **11** | **4** | **83.3%** | — |

---

## Error Analysis

### Null Extractions (4 total)

All 3 metrics null for **JNJ 2014** and `operating_income` null for **TJX 2019**.

| Company | Metric | Root Cause |
|---|---|---|
| JNJ 2014 | All 3 | Financial statements are in Exhibit 13, not the main 10-K body. The PDF body only contains a reference: *"financial statements in Exhibit 13"*. |
| TJX 2019 | operating_income | Income statement does not present operating income as an explicit line item. The LLM noted it could not identify a single unambiguous value. |

### Wrong Extractions (11 total)

#### operating_income (1 wrong)

| Company | Extracted | Ground Truth | Error % | Note |
|---|---|---|---|---|
| MCD 2025 | $10,747,000,000 | $12,393,000,000 | 13.3% | LLM likely picked "Income from franchised restaurants" or a segment subtotal rather than total operating income. |

#### income_tax (1 wrong)

| Company | Extracted | Ground Truth | Error % | Note |
|---|---|---|---|---|
| MCD 2025 | $2,356,000,000 | $2,334,000,000 | 0.9% | Off by $22M — very close. Likely a rounding difference between a rounded figure in a text summary and the precise table value. |

#### stockholders_equity (9 wrong)

The majority of errors are concentrated here, driven by two distinct failure modes:

**Failure mode 1 — Noncontrolling interest inclusion (3 cases)**  
The prompt instructs the LLM to return parent-only equity, but some companies present a prominent "Total equity" line that includes noncontrolling interests, which the LLM picks instead.

| Company | Extracted | Ground Truth | Error % |
|---|---|---|---|
| KO 2025 | $34,275,000,000 | $32,169,000,000 | 6.6% |
| WMT 2026 | $105,887,000,000 | $99,617,000,000 | 6.3% |
| PEP 2025 | $20,547,000,000 | $20,406,000,000 | 0.7% |

**Failure mode 2 — Off-by-small-amount (5 cases)**  
Values are very close but not exactly equal. Likely caused by the LLM reading from a rounded summary table rather than the precise consolidated balance sheet.

| Company | Extracted | Ground Truth | Error % |
|---|---|---|---|
| ABBV 2025 | −$3,228,000,000 | −$3,270,000,000 | 1.3% |
| GILD 2025 | $22,618,000,000 | $22,703,000,000 | 0.4% |
| MO 2025 | −$3,452,000,000 | −$3,502,000,000 | 1.4% |
| ORCL 2025 | $20,969,000,000 | $20,451,000,000 | 2.5% |
| PM 2025 | −$8,028,000,000 | −$9,994,000,000 | 19.7% |

**Failure mode 3 — Wrong equity line entirely (1 case)**

| Company | Extracted | Ground Truth | Error % |
|---|---|---|---|
| MCD 2025 | −$10,565,000,000 | −$1,791,000,000 | 489.9% |

McDonald's balance sheet has multiple equity-related lines (e.g. accumulated deficit, retained earnings components). The LLM picked the wrong one.

---

## Key Observations

1. **`operating_income` and `income_tax` perform well** — 90% and 93% respectively. These are usually presented as explicit, prominently labelled line items on the income statement.

2. **`stockholders_equity` is the hardest metric** at 67%. Three reasons:
   - The balance sheet has multiple equity lines and the correct one requires distinguishing parent equity from total equity including NCI.
   - Some companies present equity in a statement of changes in equity rather than the balance sheet itself, making it harder to locate.
   - Rounding: a few PDFs contain summary tables with rounded values that differ slightly from the precise consolidated balance sheet figures.

3. **JNJ 2014 is a structural failure** — the entire financial statement is in an exhibit, not the main document. This is an edge case in older EDGAR filings.

---

## Planned Improvements for Iteration 2

1. **Stockholders' equity prompt** — strengthen the instruction to always prefer the "Total [Company Name] shareholders' equity" line and explicitly reject "Total equity" if a separate parent-only line exists.
2. **Rounding** — instruct the LLM to always read from the main consolidated financial statements, not from selected financial data summaries or MD&A tables.
3. **JNJ / exhibit-only filings** — detect when the excerpt is empty or contains only exhibit references and skip rather than returning nulls.
