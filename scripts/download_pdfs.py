"""
Download 10-K filings as PDFs using URLs from edgar_single_source.json.

Strategy per filing:
  1. doc_type == "pdf"  → download directly from EDGAR
  2. doc_type == "html" → check the filing index for a PDF exhibit first;
                          if none, render the HTML to PDF via playwright
  3. No doc_url         → skip and log

Run edgar_single_source.py first to generate edgar_single_source.json.

For HTML→PDF conversion:
  pip install playwright
  playwright install chromium
"""

import json
import sys
import tempfile
import time
from pathlib import Path

import requests

HEADERS = {"User-Agent": "Haniel Thomson hanielthomson@gmail.com"}
SOURCE_FILE = Path(__file__).parent.parent / "data" / "edgar_single_source.json"
PDF_DIR = Path(__file__).parent.parent / "data" / "pdfs"
EDGAR_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
MIN_PDF_BYTES = 10_000  # anything smaller is almost certainly an error page


def get(url: str) -> requests.Response:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    time.sleep(0.12)
    return resp


def find_pdf_in_index(cik: str, accn: str) -> str | None:
    """Return URL of a PDF document in the filing index, or None."""
    cik_int = int(cik)
    accn_clean = accn.replace("-", "")
    url = f"{EDGAR_ARCHIVES}/{cik_int}/{accn_clean}/index.json"
    try:
        resp = get(url)
        if resp.status_code != 200:
            return None
        items = resp.json().get("directory", {}).get("item", [])
        pdfs = [it for it in items if it.get("name", "").lower().endswith(".pdf")]
        if not pdfs:
            return None
        # Prefer the primary 10-K document, fall back to any PDF
        for it in pdfs:
            if it.get("type", "") in ("10-K", "10-K405"):
                return f"{EDGAR_ARCHIVES}/{cik_int}/{accn_clean}/{it['name']}"
        return f"{EDGAR_ARCHIVES}/{cik_int}/{accn_clean}/{pdfs[0]['name']}"
    except Exception:
        return None


def download_pdf(url: str, dest: Path) -> int:
    """Stream-download a URL to dest and return file size in bytes."""
    resp = requests.get(url, headers=HEADERS, stream=True, timeout=90)
    resp.raise_for_status()
    with open(dest, "wb") as fh:
        for chunk in resp.iter_content(65_536):
            fh.write(chunk)
    size = dest.stat().st_size
    if size < MIN_PDF_BYTES or not dest.read_bytes().startswith(b"%PDF"):
        dest.unlink()
        raise ValueError(f"response does not look like a PDF ({size} bytes)")
    return size


def render_html_to_pdf(url: str, dest: Path) -> int:
    """
    Download the HTML once via requests (declared User-Agent, rate-limited),
    then render to PDF from a local temp file so playwright makes zero
    network requests to SEC.gov.
    """
    from playwright.sync_api import sync_playwright

    resp = get(url)
    resp.raise_for_status()

    with tempfile.NamedTemporaryFile(suffix=".html", mode="w",
                                     encoding="utf-8", delete=False) as f:
        f.write(resp.text)
        tmp = Path(f.name)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(f"file://{tmp}", wait_until="load", timeout=30_000)
            page.pdf(path=str(dest), format="A4", print_background=True)
            browser.close()
    finally:
        tmp.unlink(missing_ok=True)

    size = dest.stat().st_size
    if size < MIN_PDF_BYTES:
        dest.unlink()
        raise ValueError(f"rendered PDF is suspiciously small ({size} bytes)")
    return size


def check_playwright() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except ImportError:
        return False


def main():
    if not SOURCE_FILE.exists():
        sys.exit(f"ERROR: {SOURCE_FILE} not found — run edgar_single_source.py first.")

    data = json.loads(SOURCE_FILE.read_text())
    PDF_DIR.mkdir(exist_ok=True)

    playwright_ok = check_playwright()
    if not playwright_ok:
        print(
            "Note: playwright not installed — HTML filings will be skipped.\n"
            "      To enable: pip install playwright && playwright install chromium\n"
        )

    REQUIRED_METRICS = ("operating_income", "stockholders_equity", "capital_expenditures")

    eligible = [
        row for row in data
        if all(row.get(m) is not None for m in REQUIRED_METRICS)
    ]
    n_incomplete = len(data) - len(eligible)
    if n_incomplete:
        print(f"Skipping {n_incomplete} rows missing ≥1 ground-truth metric.\n")

    total = len(eligible)
    n_downloaded = 0
    n_skipped = 0
    n_html_rendered = 0
    failed: list[tuple[str, int, str]] = []

    for i, row in enumerate(eligible, 1):
        company  = row["company"]
        year     = row["year"]
        cik      = row["cik"]
        accn     = row["accession"]
        doc_type = row.get("doc_type")
        doc_url  = row.get("doc_url")

        dest = PDF_DIR / f"{company}_{year}_10K.pdf"

        if dest.exists():
            print(f"[{i:3}/{total}] {dest.name:<40} already exists")
            n_skipped += 1
            continue

        label = f"[{i:3}/{total}] {company} {year}"

        if not doc_url:
            print(f"{label}  — no document URL")
            failed.append((company, year, "no doc_url"))
            continue

        print(f"{label}  ({doc_type})", end="  ", flush=True)

        try:
            if doc_type == "pdf":
                size = download_pdf(doc_url, dest)
                print(f"{size // 1024} KB")
                n_downloaded += 1

            elif doc_type == "html":
                pdf_url = find_pdf_in_index(cik, accn)
                if pdf_url:
                    size = download_pdf(pdf_url, dest)
                    print(f"{size // 1024} KB  (PDF from index)")
                    n_downloaded += 1
                elif playwright_ok:
                    size = render_html_to_pdf(doc_url, dest)
                    print(f"{size // 1024} KB  (rendered from HTML)")
                    n_downloaded += 1
                    n_html_rendered += 1
                else:
                    print("skipped  (HTML, playwright not available)")
                    failed.append((company, year, "html/no-playwright"))

            else:
                print(f"skipped  (unsupported doc_type={doc_type!r})")
                failed.append((company, year, f"doc_type={doc_type}"))

        except Exception as e:
            print(f"FAILED  {e}")
            failed.append((company, year, str(e)[:100]))
            if dest.exists():
                dest.unlink()

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"""
{'='*60}
Saved to         : {PDF_DIR}/
{'='*60}
Downloaded       : {n_downloaded}
  HTML→PDF       : {n_html_rendered}
Already existed  : {n_skipped}
Failed / skipped : {len(failed)}
{'='*60}""")

    if failed:
        print("Failed entries:")
        for company, year, reason in failed:
            print(f"  {company:<25} {year}  {reason}")


if __name__ == "__main__":
    main()
