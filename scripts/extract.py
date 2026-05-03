"""
Extract three financial fields from 10-K PDFs via Gemini and evaluate against
XBRL ground truth from edgar_single_source.json.

Fields: operating_income, stockholders_equity, capital_expenditures
Scope:  up to MAX_PDFS PDFs in data/pdfs/ that have all three ground-truth values
Output: data/db/extraction_results.db  (SQLite — each run appended with a unique run_id)
"""

import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import pdfplumber
from dotenv import load_dotenv
from google import genai
from google.genai import types

logging.getLogger("pdfminer").setLevel(logging.ERROR)

load_dotenv()

MODEL    = "gemini-3.1-flash-lite-preview"
_ROOT    = Path(__file__).parent.parent
PDF_DIR  = _ROOT / "data" / "pdfs"
GT_FILE  = _ROOT / "data" / "edgar_single_source.json"
DB_FILE  = _ROOT / "data" / "db" / "extraction_results.db"
MAX_PDFS = 30

gemini = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

METRICS = ("operating_income", "stockholders_equity", "capital_expenditures")


# ── Ground truth ──────────────────────────────────────────────────────────────

def load_ground_truth(path: Path) -> dict[tuple[str, int], dict]:
    """Returns {(company, year): {metric: value}} from edgar_single_source.json."""
    gt: dict[tuple[str, int], dict] = {}
    for row in json.loads(path.read_text()):
        if all(row.get(m) is not None for m in METRICS):
            gt[(row["company"], row["year"])] = {m: row[m] for m in METRICS}
    return gt


# ── Filename parsing ──────────────────────────────────────────────────────────

def parse_filename(name: str) -> tuple[str | None, int | None]:
    stem = name.removesuffix(".pdf")
    if not re.search(r'_10K$', stem, re.IGNORECASE):
        return None, None
    match = re.match(r'^([A-Z0-9][A-Z0-9_]*)_(\d{4})_10K$', stem)
    if not match:
        return None, None
    return match.group(1), int(match.group(2))


# ── Text extraction ───────────────────────────────────────────────────────────

_FS_KEYWORDS = [
    "cash flows", "statement of cash", "financing activities", "investing activities",
    "statement of operations", "statement of income", "statements of earnings",
    "statements of income", "income from operations", "operating income",
    "results of operations", "balance sheet", "stockholders", "shareholders",
]


def _financial_pages(pages: list[str]) -> list[str]:
    """Return only pages that look like financial statements (± 1 page buffer)."""
    keep = set()
    for i, p in enumerate(pages):
        lower = p.lower()
        if any(kw in lower for kw in _FS_KEYWORDS):
            keep.update([i - 1, i, i + 1])
    keep = sorted(k for k in keep if 0 <= k < len(pages))
    return [pages[i] for i in keep] if keep else pages


def extract_financial_text(pdf_path: Path) -> str:
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
        if pages and pages[0].count("(cid:") > 10:
            print("(cid font, retrying with pymupdf)", end="  ", flush=True)
            import fitz
            with fitz.open(pdf_path) as doc:
                pages = [doc[i].get_text() for i in range(len(doc))]
        return "\n\n".join(_financial_pages(pages))
    except Exception as e:
        return f"[PDF read error: {e}]"


# ── LLM call ─────────────────────────────────────────────────────────────────

PROMPT_TEMPLATE = """\
Extract three financial figures from this 10-K filing.
Company: {company}, fiscal year ending in {year}.

- operating_income: Consolidated operating income (or loss) for {year} — the subtotal BEFORE
  interest expense and income taxes. Valid labels: "operating income", "income from operations",
  "operating profit", "income before interest and taxes", "income before interest, taxes and other".
  If results are shown by segment, use the consolidated total across all segments.
  If no explicit line exists, derive it: start with total revenue, subtract cost of sales to get
  gross profit, then CONTINUE subtracting ALL remaining operating expenses (SG&A, selling expenses,
  R&D, D&A, restructuring, impairments, and any other items above the operating income subtotal).
  WARNING: revenue minus cost of sales alone gives GROSS PROFIT, not operating income.
  Do NOT substitute "income before taxes" or "pretax income".

- stockholders_equity: Total stockholders' equity (or deficit) attributable to the PARENT
  COMPANY ONLY as of the fiscal year-end balance sheet date for {year}. This corresponds to
  the XBRL concept us-gaap:StockholdersEquity — equity of the parent entity's shareholders only,
  explicitly EXCLUDING any noncontrolling (minority) interest portion.
  Prefer a line that contains the company's own name, e.g. "Total [Company] stockholders' equity".
  If the balance sheet has a subtotal for parent equity AND a separate line for "Noncontrolling
  interests", "Noncontrolling interest", "Redeemable noncontrolling interests", or "Minority
  interest", use the parent subtotal BEFORE those lines, not the grand total after them.
  Do NOT return "Total liabilities and stockholders' equity" or any total that includes NCI.
  Use the {year} column only — ignore prior-year comparative columns.

- capital_expenditures: Cash paid for purchases of property, plant and equipment for {year}
  from the investing activities section of the Cash Flow Statement.
  Use ONLY the continuing operations figure. Do NOT add discontinued operations CapEx.

Return the RAW number exactly as printed in the financial statements.
Find the unit in the nearest table header: "(in millions)", "(in thousands)", etc. If none, use "actual".
Return null for raw_value if the figure genuinely cannot be found or derived.

Excerpt:
{text}

JSON only, no extra text:
{{
  "operating_income":    {{"raw_value": <number or null>, "unit": "millions|thousands|actual"}},
  "stockholders_equity": {{"raw_value": <number or null>, "unit": "millions|thousands|actual"}},
  "capital_expenditures": {{"raw_value": <number or null>, "unit": "millions|thousands|actual"}},
  "note": "<one line: where each figure was found>"
}}"""

MULTIPLIERS = {"millions": 1_000_000, "thousands": 1_000, "actual": 1}


def call_llm(text: str, company: str, year: int) -> dict:
    prompt = PROMPT_TEMPLATE.format(company=company, year=year, text=text)
    for attempt in range(4):
        try:
            resp = gemini.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0,
                    max_output_tokens=512,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
        except Exception as e:
            if attempt < 3:
                wait = 15 * (attempt + 1)
                print(f"\n    API error (attempt {attempt+1}/4), retrying in {wait}s ...",
                      end="", flush=True)
                time.sleep(wait)
                continue
            return {m: None for m in METRICS} | {"note": str(e)[:120]}

        try:
            raw = resp.text.strip()
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            json_str = m.group() if m else raw
            json_str = re.sub(r'(\d),(\d)', r'\1\2', json_str)
            try:
                parsed = json.loads(json_str)
            except json.JSONDecodeError:
                parsed = json.loads(json_str.replace("'", '"'))

            result: dict = {"note": parsed.get("note", "")}
            for metric in METRICS:
                entry = parsed.get(metric, {})
                raw_val = entry.get("raw_value") if isinstance(entry, dict) else None
                unit    = (entry.get("unit", "actual") if isinstance(entry, dict) else "actual").lower()
                mult    = MULTIPLIERS.get(unit, 1)
                result[metric] = (
                    int(float(str(raw_val).replace(",", "")) * mult)
                    if raw_val is not None else None
                )
            return result

        except Exception as e:
            print(f"\n    parse error: {e} | raw: {repr(raw[:200])}", end="", flush=True)
            return {m: None for m in METRICS} | {"note": f"parse error: {str(e)[:80]}"}

    return {m: None for m in METRICS} | {"note": "failed after 4 attempts"}


# ── Database ──────────────────────────────────────────────────────────────────

def init_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS extraction_results (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id        TEXT    NOT NULL,
            file          TEXT    NOT NULL,
            company       TEXT    NOT NULL,
            year          INTEGER NOT NULL,
            metric        TEXT    NOT NULL,
            ground_truth  INTEGER,
            extracted     INTEGER,
            error_pct     REAL,
            correct       INTEGER,
            note          TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS run_summary (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id          TEXT    NOT NULL,
            metric          TEXT    NOT NULL,
            n_total         INTEGER NOT NULL,
            n_correct       INTEGER NOT NULL,
            n_wrong         INTEGER NOT NULL,
            n_null          INTEGER NOT NULL,
            accuracy_pct    REAL,
            mean_error_pct  REAL
        )
    """)
    conn.commit()
    return conn


def insert_rows(conn: sqlite3.Connection, run_id: str, rows: list[dict]) -> None:
    conn.executemany(
        """INSERT INTO extraction_results
               (run_id, file, company, year, metric,
                ground_truth, extracted, error_pct, correct, note)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (run_id, r["file"], r["company"], r["year"], r["metric"],
             r["ground_truth"], r["extracted"], r["error_pct"],
             1 if r["correct"] else 0, r["note"])
            for r in rows
        ],
    )
    conn.commit()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    gt   = load_ground_truth(GT_FILE)
    conn = init_db(DB_FILE)
    run_id = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # Build work list: PDFs with all three GT values, capped at MAX_PDFS
    work = []
    for p in sorted(PDF_DIR.glob("*.pdf")):
        company, year = parse_filename(p.name)
        if company is None or (company, year) not in gt:
            continue
        work.append((p, company, year, gt[(company, year)]))
        if len(work) == MAX_PDFS:
            break

    print(f"Run: {run_id}")
    print(f"Processing {len(work)} PDFs × {len(METRICS)} metrics = "
          f"{len(work) * len(METRICS)} comparisons\n")

    for i, (pdf_path, company, year, gt_vals) in enumerate(work, 1):
        print(f"[{i:2}/{len(work)}] {pdf_path.name}", end="  ", flush=True)

        text = extract_financial_text(pdf_path)
        llm  = call_llm(text, company, year)

        row_results = []
        for metric in METRICS:
            extracted = llm.get(metric)
            gt_val    = gt_vals[metric]
            if extracted is None or gt_val == 0:
                error_pct = None
                correct   = False
            else:
                error_pct = abs(extracted - gt_val) / abs(gt_val) * 100
                correct   = extracted is not None and extracted == gt_val
            row_results.append({
                "file":         pdf_path.name,
                "company":      company,
                "year":         year,
                "metric":       metric,
                "ground_truth": gt_val,
                "extracted":    extracted,
                "error_pct":    round(error_pct, 2) if error_pct is not None else None,
                "correct":      correct,
                "note":         llm.get("note", ""),
            })

        insert_rows(conn, run_id, row_results)

        # ── Per-PDF console output ────────────────────────────────────────────
        def fmt_val(v): return f"${v:>20,}" if v is not None else f"{'None':>21}"
        def status(r):
            if r["extracted"] is None: return "NULL  "
            return "OK    " if r["correct"] else f"ERR {r['error_pct']:>5.1f}%" if r["error_pct"] is not None else "ERR   "

        print(f"\n  {'Metric':<22} {'Extracted':>21}   {'Ground Truth':>21}   Status")
        print(f"  {'─'*22} {'─'*21}   {'─'*21}   {'─'*10}")
        for r in row_results:
            print(f"  {r['metric']:<22} {fmt_val(r['extracted'])}   {fmt_val(r['ground_truth'])}   {status(r)}")
        print(f"  note: {llm.get('note', '')[:80]}")

        time.sleep(3)

    # ── Summary (queried from DB, written to run_summary) ────────────────────
    print(f"\n{'='*65}  run={run_id}")
    print(f"{'Metric':<22} {'Correct':>8} {'Wrong':>8} {'Null':>8} {'Mean err':>10} {'Accuracy':>10}")
    print(f"{'='*65}")
    total = n_correct_total = 0
    summary_rows = []
    for metric in METRICS:
        rows = conn.execute(
            "SELECT correct, error_pct, extracted FROM extraction_results "
            "WHERE run_id=? AND metric=?", (run_id, metric)
        ).fetchall()
        n_total   = len(rows)
        n_correct = sum(r[0] for r in rows)
        n_null    = sum(1 for r in rows if r[2] is None)
        n_wrong   = n_total - n_correct - n_null
        errs      = [r[1] for r in rows if r[1] is not None]
        mean_err  = sum(errs) / len(errs) if errs else None
        accuracy  = n_correct / n_total * 100 if n_total else 0

        summary_rows.append((
            run_id, metric, n_total, n_correct, n_wrong, n_null,
            round(accuracy, 1), round(mean_err, 1) if mean_err is not None else None,
        ))

        mean_err_str = f"{mean_err:.1f}%" if mean_err is not None else "N/A"
        print(f"{metric:<22} {n_correct:>8} {n_wrong:>8} {n_null:>8} "
              f"{mean_err_str:>10} {accuracy:>9.1f}%")
        total += n_total
        n_correct_total += n_correct

    conn.executemany(
        """INSERT INTO run_summary
               (run_id, metric, n_total, n_correct, n_wrong, n_null,
                accuracy_pct, mean_error_pct)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        summary_rows,
    )
    conn.commit()

    print(f"{'='*65}")
    print(f"{'TOTAL':<22} {n_correct_total:>8} {total-n_correct_total:>8} "
          f"{'':>8}  {'':>10} {n_correct_total/total*100:>9.1f}%")
    print(f"\nAppended to → {DB_FILE}")


if __name__ == "__main__":
    main()
