"""
Extract three financial fields from 10-K PDFs via Gemini and evaluate against
XBRL ground truth from edgar_single_source.json.

Fields: operating_income, income_tax, stockholders_equity
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

METRICS = ("operating_income", "income_tax", "stockholders_equity")


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

def _is_garbled(text: str) -> bool:
    """True if the text contains enough CID codes to be unreadable."""
    return text.count("(cid:") > 30


def _extract_with_pdfplumber(pdf_path: Path) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        pages = [p.extract_text() or "" for p in pdf.pages]
    return "\n\n".join(pages)


def _extract_with_pymupdf(pdf_path: Path) -> str:
    import fitz
    with fitz.open(pdf_path) as doc:
        pages = [doc[i].get_text() for i in range(len(doc))]
    return "\n\n".join(pages)


def extract_financial_text(pdf_path: Path) -> str:
    """
    Extract text from income statement and balance sheet pages.
    Falls back to pymupdf if pdfplumber produces CID-encoded garbled text.
    """
    try:
        text = _extract_with_pdfplumber(pdf_path)
        if _is_garbled(text):
            print("(cid font, retrying with pymupdf)", end="  ", flush=True)
            text = _extract_with_pymupdf(pdf_path)
        return text
    except Exception as e:
        return f"[PDF read error: {e}]"


# ── LLM call ─────────────────────────────────────────────────────────────────

PROMPT_TEMPLATE = """\
Extract three financial figures from this 10-K excerpt.
Company: {company}, fiscal year ending in {year}.

Definitions:
- operating_income:      operating income (or loss) for {year}. Also labelled "income from \
operations" or "operating profit". Can be negative. Do NOT return income before taxes or net income.
- income_tax:            income tax expense (or benefit) for {year}. Also labelled "provision for \
income taxes". Return as POSITIVE for expense — even if the PDF shows it in parentheses as a \
deduction from income. Return NEGATIVE only if the line is literally labelled "benefit for income \
taxes" and represents a net tax credit that increases income.
- stockholders_equity:   total stockholders' equity (or shareholders' equity) as of the \
fiscal year-end in {year}. Can be negative (deficit). Do NOT return total equity including \
noncontrolling interests unless no parent-only figure exists.

Rules:
- Return the RAW number exactly as printed in the table — do not scale it yourself.
- Find the unit in each table header: "(in millions)", "(in thousands)", etc. If none, use "actual".
- Return null for raw_value if the figure is not present in the excerpt.

Excerpt:
{text}

JSON only, no extra text:
{{
  "operating_income":    {{"raw_value": <number or null>, "unit": "millions|thousands|actual"}},
  "income_tax":          {{"raw_value": <number or null>, "unit": "millions|thousands|actual"}},
  "stockholders_equity": {{"raw_value": <number or null>, "unit": "millions|thousands|actual"}},
  "note": "<one line>"
}}"""

MULTIPLIERS = {"millions": 1_000_000, "thousands": 1_000, "actual": 1}


def call_llm(text: str, company: str, year: int) -> dict:
    prompt = PROMPT_TEMPLATE.format(company=company, year=year, text=text)
    for attempt in range(4):
        try:
            resp = gemini.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0, max_output_tokens=512),
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
