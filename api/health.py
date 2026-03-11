from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler

from src.news_analyzer.service import build_healthcheck


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        payload = build_healthcheck()
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

