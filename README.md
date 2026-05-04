# 10-K Data Extraction

Automated extraction and evaluation of three financial metrics from SEC 10-K filings using an LLM, benchmarked against XBRL ground truth.

## Target Metrics

| Field | Definition |
|---|---|
| `operating_income` | Consolidated operating income (loss) from the income statement |
| `stockholders_equity` | Parent-company-only stockholders' equity from the balance sheet |
| `capital_expenditures` | Cash paid for property, plant and equipment (investing activities) |

## Pipeline

**Step 1 — Ground truth (`scripts/edgar_single_source.py`)**  
Queries the SEC EDGAR submissions and XBRL company-concept APIs for each ticker. Selects the most recent fiscal year in which all three metrics are available as XBRL facts. Outputs `data/edgar_single_source.json` — one row per company with accession number, document URL, and XBRL values.

**Step 2 — PDF download (`scripts/download_pdfs.py`)**  
Downloads PDFs from the EDGAR archives URL embedded in each filing's metadata. If the primary document is HTML, the script checks the filing index for a PDF exhibit first; if none exists, Playwright renders the HTML to PDF locally (zero direct SEC requests from the browser to avoid rate-limiting).

**Step 3 — LLM extraction (`scripts/extract.py`)**  
Extracts full PDF text using pdfplumber (with pymupdf fallback for CID-encoded fonts), then sends it to Gemini with a structured prompt requesting the three values as JSON with raw value and unit. The unit scales the raw number to actual dollars before comparison against ground truth. Results are appended to a SQLite database (`data/db/extraction_results.db`) tagged with a run ID.

## Evaluation

- **Correct**: extracted value equals the XBRL ground truth exactly (integer match after unit scaling).
- **Error %**: `|extracted − ground_truth| / |ground_truth| × 100` — stored for all non-null extractions.

A single-source design (both the PDF and the XBRL facts come from the same EDGAR accession number) eliminates cross-source misalignment — every extracted value is compared against the fact from the exact document being read.

## Dataset

30 companies, one 10-K per company, sourced from S&P 500 constituents across sectors. All 30 have verified XBRL ground truth for all three metrics.

| Company | Year | Company | Year |
|---------|------|---------|------|
| AAPL | 2025 | KO | 2025 |
| ABBV | 2025 | LOW | 2026 |
| AMD | 2025 | MDLZ | 2025 |
| AMGN | 2025 | META | 2025 |
| AMZN | 2016 | MO | 2025 |
| AVGO | 2025 | MSFT | 2025 |
| BIIB | 2021 | NVDA | 2012 |
| BKNG | 2025 | ORCL | 2025 |
| BLK | 2025 | PG | 2025 |
| CMG | 2025 | PM | 2025 |
| COST | 2025 | SBUX | 2025 |
| CVS | 2025 | SLB | 2023 |
| GILD | 2025 | TJX | 2019 |
| GOOGL | 2025 | UNH | 2025 |
| KHC | 2025 | WMT | 2026 |

## Setup

```bash
pip install pdfplumber pymupdf google-genai python-dotenv requests
# Optional, for HTML→PDF conversion:
pip install playwright && playwright install chromium
```

Create a `.env` file with:
```
GEMINI_API_KEY=your_key_here
```

## Running

```bash
# 1. Build ground truth (only needed once, or to refresh)
python scripts/edgar_single_source.py

# 2. Download PDFs (only needed once)
python scripts/download_pdfs.py

# 3. Run extraction
python scripts/extract.py
```

Results are written to `data/db/extraction_results.db`. Iteration reports are in `reports/`.
