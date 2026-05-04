#!/usr/bin/env python3
"""
Serves the dashboard at http://localhost:8080
and exposes /api/results and /api/summary from the local SQLite database.

Usage:
    python3 server.py
"""

import json
import mimetypes
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

DB_PATH        = Path(__file__).parent / "data" / "db" / "extraction_results.db"
DASHBOARD_DIR  = Path(__file__).parent / "dashboard"
PORT           = 8080


def query_db(sql: str) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


API_ROUTES = {
    "/api/results": """
        SELECT run_id, company, year, metric,
               ground_truth, extracted, error_pct, correct
        FROM   extraction_results
        ORDER  BY run_id, company, metric
    """,
    "/api/summary": """
        SELECT run_id, metric, n_total, n_correct, n_wrong, n_null,
               accuracy_pct, mean_error_pct
        FROM   run_summary
        ORDER  BY run_id, metric
    """,
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")

    def send_json(self, data: list):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path):
        mime, _ = mimetypes.guess_type(str(path))
        body    = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]

        # API endpoints
        if path in API_ROUTES:
            try:
                self.send_json(query_db(API_ROUTES[path]))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
            return

        # Static files from dashboard/
        if path == "/":
            path = "/index.html"
        file_path = DASHBOARD_DIR / path.lstrip("/")
        if file_path.is_file():
            self.send_file(file_path)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")


if __name__ == "__main__":
    server = HTTPServer(("localhost", PORT), Handler)
    print(f"Dashboard running at http://localhost:{PORT}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
