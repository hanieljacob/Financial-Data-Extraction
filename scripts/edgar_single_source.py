"""
Build a single-source 10-K dataset from SEC EDGAR.

One filing per company — the most recent 10-K that has all three target metrics
as XBRL ground truth. PDFs and ground-truth values are tied to the same
accession number, guaranteeing alignment.

Target metrics: operating_income, stockholders_equity, capital_expenditures

Output: edgar_single_source.json — one row per company (≤200 rows)
"""

import json
import time
from datetime import datetime
from pathlib import Path

import requests

HEADERS = {"User-Agent": "Haniel Thomson hanielthomson@gmail.com"}

TARGET_METRICS = ("operating_income", "stockholders_equity", "capital_expenditures")
TARGET_COUNT   = 30

TICKERS = [
    # Current set
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AVGO", "ORCL", "AMD", "QCOM",
    "BLK", "ABBV", "AMGN", "GILD", "BIIB", "AMZN", "HD", "LOW", "SBUX", "TJX",
    "BKNG", "CMG", "WMT", "PG", "KO", "PEP", "COST", "PM", "MO", "MDLZ", "KHC",
    "MRK", "LLY", "PFE", "UNH", "CVS", "XOM", "CVX", "COP", "SLB", "CAT", "DE",
    "GE", "HON", "MMM", "UPS", "FDX", "MCD", "DIS", "JPM", "BAC", "GS", "INTC", 
    "TXN", "CSCO", "CRM",
]

METRICS: dict[str, dict] = {
    "operating_income": {
        "instantaneous": False,
        "concepts": ["OperatingIncomeLoss"],
    },
    "stockholders_equity": {
        "instantaneous": True,
        "concepts": [
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ],
    },
    "capital_expenditures": {
        "instantaneous": False,
        "concepts": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    },
}

YEARS = list(range(2016, 2026))
EDGAR_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
OUT_FILE = Path(__file__).parent.parent / "data" / "edgar_single_source.json"


def get(url: str) -> requests.Response:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    time.sleep(0.12)
    return resp


# ── CIK lookup ────────────────────────────────────────────────────────────────

def fetch_cik_map() -> dict[str, str]:
    """Return {ticker: zero-padded-CIK} for all SEC-registered companies."""
    data = get("https://www.sec.gov/files/company_tickers.json").json()
    return {
        v["ticker"].upper(): str(v["cik_str"]).zfill(10)
        for v in data.values()
    }


# ── Filings metadata ──────────────────────────────────────────────────────────

def _parse_filings_block(block: dict) -> list[dict]:
    keys = ("accessionNumber", "reportDate", "filed", "form",
            "primaryDocument", "primaryDocDescription")
    arrays = {k: block.get(k, []) for k in keys}
    n = len(arrays["accessionNumber"])
    return [
        {
            "accn":         arrays["accessionNumber"][i],
            "period":       arrays["reportDate"][i]            if i < len(arrays["reportDate"])            else "",
            "filed":        arrays["filed"][i]                 if i < len(arrays["filed"])                 else "",
            "form":         arrays["form"][i]                  if i < len(arrays["form"])                  else "",
            "primary_doc":  arrays["primaryDocument"][i]       if i < len(arrays["primaryDocument"])       else "",
            "primary_desc": arrays["primaryDocDescription"][i] if i < len(arrays["primaryDocDescription"]) else "",
        }
        for i in range(n)
    ]


def fetch_10k_filings(cik: str) -> dict[str, dict]:
    data = get(f"https://data.sec.gov/submissions/CIK{cik}.json").json()
    filings_data = data.get("filings", {})
    rows = _parse_filings_block(filings_data.get("recent", {}))
    for extra in filings_data.get("files", []):
        try:
            page = get(f"https://data.sec.gov/submissions/{extra['name']}").json()
            rows.extend(_parse_filings_block(page))
        except Exception:
            pass
    return {
        r["accn"]: r
        for r in rows
        if r["form"] in ("10-K", "10-K405") and r["period"]
    }


def match_years(filings: dict[str, dict]) -> dict[int, dict]:
    """Return {year: earliest-filed-10K} for each year we have a filing."""
    result: dict[int, dict] = {}
    for info in filings.values():
        year = int(info["period"][:4])
        if year not in result or info["filed"] < result[year]["filed"]:
            result[year] = info
    return result


# ── XBRL lookup ───────────────────────────────────────────────────────────────

def build_xbrl_lookup(cik: str) -> dict[str, dict[str, dict[int, tuple[int, str]]]]:
    """
    {accn: {metric: {end_year: (value, concept)}}}

    Period facts (income statement) keyed by annual duration (340-400 days).
    Instantaneous facts (balance sheet) keyed by end date, no start date.
    First hit per (accn, end_year) wins — priority order in METRICS respected.
    """
    lookup: dict[str, dict[str, dict[int, tuple[int, str]]]] = {}

    for metric, cfg in METRICS.items():
        for concept in cfg["concepts"]:
            url = (
                f"https://data.sec.gov/api/xbrl/companyconcept/"
                f"CIK{cik}/us-gaap/{concept}.json"
            )
            resp = get(url)
            if resp.status_code != 200:
                continue
            for fact in resp.json().get("units", {}).get("USD", []):
                if fact.get("form") not in ("10-K", "10-K405"):
                    continue
                accn = fact.get("accn", "")
                if not accn:
                    continue
                if cfg["instantaneous"]:
                    if "start" not in fact:
                        end_year = int(fact["end"][:4])
                        yr_map = lookup.setdefault(accn, {}).setdefault(metric, {})
                        if end_year not in yr_map:
                            yr_map[end_year] = (fact["val"], concept)
                else:
                    start, end = fact.get("start", ""), fact.get("end", "")
                    if not (start and end):
                        continue
                    try:
                        days = (
                            datetime.strptime(end, "%Y-%m-%d")
                            - datetime.strptime(start, "%Y-%m-%d")
                        ).days
                    except ValueError:
                        continue
                    if 340 <= days <= 400:
                        end_year = int(end[:4])
                        yr_map = lookup.setdefault(accn, {}).setdefault(metric, {})
                        if end_year not in yr_map:
                            yr_map[end_year] = (fact["val"], concept)

    return lookup


# ── Document URL ──────────────────────────────────────────────────────────────

def doc_url(cik: str, accn: str, filename: str) -> str:
    return f"{EDGAR_ARCHIVES}/{int(cik)}/{accn.replace('-', '')}/{filename}"


def doc_type(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith((".htm", ".html")):
        return "html"
    return "other"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Fetching CIK map from SEC...")
    cik_map = fetch_cik_map()

    results = []
    n_tried = 0

    for ticker in TICKERS:
        if len(results) >= TARGET_COUNT:
            break

        cik = cik_map.get(ticker.upper())
        if not cik:
            print(f"  {ticker:<8} CIK not found — skipping")
            continue

        n_tried += 1
        print(f"  [{len(results):>3}/{TARGET_COUNT}] {ticker:<8}", end=" ", flush=True)

        try:
            filings  = fetch_10k_filings(cik)
            year_map = match_years(filings)
            xbrl     = build_xbrl_lookup(cik)
        except Exception as e:
            print(f"ERROR: {e}")
            continue

        # Find the most recent year with all three target metrics
        best_year = None
        for year in sorted(year_map.keys(), reverse=True):
            f    = year_map[year]
            accn = f["accn"]
            if all(
                xbrl.get(accn, {}).get(m, {}).get(year) is not None
                for m in TARGET_METRICS
            ):
                best_year = year
                break

        if best_year is None:
            print("no qualifying year")
            continue

        f     = year_map[best_year]
        accn  = f["accn"]
        fname = f["primary_doc"]

        row = {
            "company":    ticker,
            "year":       best_year,
            "cik":        cik,
            "accession":  accn,
            "period_end": f["period"],
            "filed":      f["filed"],
            "doc_url":    doc_url(cik, accn, fname) if fname else None,
            "doc_type":   doc_type(fname) if fname else None,
        }
        for m in TARGET_METRICS:
            entry = xbrl.get(accn, {}).get(m, {}).get(best_year, (None, None))
            row[m]              = entry[0]
            row[f"{m}_concept"] = entry[1]

        results.append(row)
        print(f"year={best_year}  oi={row['operating_income']:>15,}  "
              f"eq={row['stockholders_equity']:>15,}  capex={row['capital_expenditures']:>15,}")

    OUT_FILE.write_text(json.dumps(results, indent=2))

    print(f"\n{'='*60}")
    print(f"Companies tried : {n_tried}")
    print(f"Qualifying rows : {len(results)}")
    n_pdf  = sum(1 for r in results if r["doc_type"] == "pdf")
    n_html = sum(1 for r in results if r["doc_type"] == "html")
    print(f"PDF / HTML      : {n_pdf} / {n_html}")
    print(f"Saved → {OUT_FILE}")


if __name__ == "__main__":
    main()
