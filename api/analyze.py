from __future__ import annotations

import html
import json
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from src.news_analyzer.service import analyze_latest_news


def _get_first(params: dict[str, list[str]], key: str, default: str = "") -> str:
    values = params.get(key)
    if not values:
        return default
    return (values[0] or "").strip()


def _as_int(value: str, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_float(value: str, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _as_bool(value: str) -> bool:
    lowered = (value or "").strip().lower()
    return lowered in {"1", "true", "yes", "on"}


def _html_page(title: str, body_html: str) -> bytes:
    doc = (
        "<!doctype html>"
        "<html lang='en'>"
        "<head>"
        "<meta charset='utf-8'/>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'/>"
        f"<title>{html.escape(title)}</title>"
        "</head>"
        "<body>"
        f"{body_html}"
        "</body>"
        "</html>"
    )
    return doc.encode("utf-8")


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query or "")

        asset_query = _get_first(params, "asset_query", "").strip()
        if not asset_query:
            body = _html_page(
                "Missing asset_query",
                "<h1>Error</h1><p><code>asset_query</code> is required.</p><p><a href='/'>Back</a></p>",
            )
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        asset_type = _get_first(params, "asset_type", "auto") or "auto"
        lookback_hours = _as_int(_get_first(params, "lookback_hours", "24"), 24)
        max_articles = _as_int(_get_first(params, "max_articles", "120"), 120)
        include_full_text = _as_bool(_get_first(params, "include_full_text", "0"))

        bullish_threshold = _as_float(_get_first(params, "bullish_threshold", "0.60"), 0.60)
        bearish_threshold = _as_float(_get_first(params, "bearish_threshold", "0.60"), 0.60)
        heavy_hitter_count = _as_int(_get_first(params, "heavy_hitter_count", "8"), 8)

        output_format = (_get_first(params, "format", "html") or "html").lower()

        payload = analyze_latest_news(
            asset_query=asset_query,
            asset_type=asset_type,
            market="india",
            lookback_hours=lookback_hours,
            max_articles=max_articles,
            include_full_text=include_full_text,
            site_profile="india_finance",
            bullish_threshold=bullish_threshold,
            bearish_threshold=bearish_threshold,
            heavy_hitter_count=heavy_hitter_count,
        )

        if output_format == "json":
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        summary = payload.get("sentiment_summary", {}) or {}
        stats = payload.get("fetch_stats", {}) or {}

        hitters = summary.get("heavy_hitters", []) or []
        hitters_items = []
        for item in hitters:
            headline = html.escape(str(item.get("headline", "")))
            source = html.escape(str(item.get("source", "")))
            direction = html.escape(str(item.get("direction", "")))
            impact = html.escape(str(item.get("impact_score", "")))
            bullish = html.escape(str(item.get("bullish", "")))
            bearish = html.escape(str(item.get("bearish", "")))
            url = str(item.get("publisher_url", "") or "")
            link = html.escape(url)
            if url:
                hitters_items.append(
                    f"<li><p><strong>{direction}</strong> impact={impact} bullish={bullish} bearish={bearish}</p>"
                    f"<p>{headline}</p><p>{source}</p><p><a href='{link}'>{link}</a></p></li>"
                )
            else:
                hitters_items.append(
                    f"<li><p><strong>{direction}</strong> impact={impact} bullish={bullish} bearish={bearish}</p>"
                    f"<p>{headline}</p><p>{source}</p></li>"
                )
        hitters_html = "<ol>" + "".join(hitters_items) + "</ol>" if hitters_items else "<p>(none)</p>"

        json_link = html.escape(self.path + ("&" if "?" in self.path else "?") + "format=json")

        body = _html_page(
            "Analysis Result",
            "<h1>Analysis Result</h1>"
            f"<p><a href='/'>New query</a> | <a href='{json_link}'>Raw JSON</a></p>"
            "<h2>Summary</h2>"
            "<dl>"
            f"<dt>dominant_label</dt><dd>{html.escape(str(summary.get('dominant_label')))}</dd>"
            f"<dt>sentiment_score</dt><dd>{html.escape(str(summary.get('sentiment_score')))}</dd>"
            f"<dt>bullish_count</dt><dd>{html.escape(str(summary.get('bullish_count')))}</dd>"
            f"<dt>bearish_count</dt><dd>{html.escape(str(summary.get('bearish_count')))}</dd>"
            f"<dt>neutral_count</dt><dd>{html.escape(str(summary.get('neutral_count')))}</dd>"
            f"<dt>bullish_probability_total</dt><dd>{html.escape(str(summary.get('bullish_probability_total')))}</dd>"
            f"<dt>bearish_probability_total</dt><dd>{html.escape(str(summary.get('bearish_probability_total')))}</dd>"
            f"<dt>net_bull_bear</dt><dd>{html.escape(str(summary.get('net_bull_bear')))}</dd>"
            "</dl>"
            "<h2>Heavy Hitters</h2>"
            f"{hitters_html}"
            "<h2>Fetch Stats</h2>"
            "<dl>"
            f"<dt>queries_run</dt><dd>{html.escape(str(stats.get('queries_run')))}</dd>"
            f"<dt>unique_candidates</dt><dd>{html.escape(str(stats.get('unique_candidates')))}</dd>"
            f"<dt>articles_selected</dt><dd>{html.escape(str(stats.get('articles_selected')))}</dd>"
            f"<dt>articles_with_body</dt><dd>{html.escape(str(stats.get('articles_with_body')))}</dd>"
            f"<dt>deduped_out</dt><dd>{html.escape(str(stats.get('deduped_out')))}</dd>"
            f"<dt>duration_seconds</dt><dd>{html.escape(str(stats.get('duration_seconds')))}</dd>"
            "</dl>"
            "<h2>Raw JSON Preview</h2>"
            f"<pre>{html.escape(json.dumps(payload, ensure_ascii=False, indent=2)[:20000])}</pre>",
        )

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

