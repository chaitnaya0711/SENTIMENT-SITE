from __future__ import annotations

import json
import re
import threading
from typing import Iterable

import requests
from requests.adapters import HTTPAdapter

from .config import BLOCK_PAGE_MARKERS, HEADERS, LOW_VALUE_LINES, MIN_BODY_CHARS

try:
    import trafilatura
except Exception:  # pragma: no cover - optional dependency fallback
    trafilatura = None

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - optional dependency fallback
    BeautifulSoup = None

try:
    from readability import Document
except Exception:  # pragma: no cover - optional dependency fallback
    Document = None

_WHITESPACE_RE = re.compile(r"\s+")
_HTTP_POOL_SIZE = 32
_THREAD_LOCAL = threading.local()


def _get_session() -> requests.Session:
    session = getattr(_THREAD_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=_HTTP_POOL_SIZE, pool_maxsize=_HTTP_POOL_SIZE, max_retries=0)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        _THREAD_LOCAL.session = session
    return session


def clean_line(text: str) -> str:
    text = text.replace("\xa0", " ")
    return _WHITESPACE_RE.sub(" ", text).strip()


def collapse_lines(lines: Iterable[str]) -> str:
    seen: set[str] = set()
    kept: list[str] = []
    for line in lines:
        cleaned = clean_line(line)
        lowered = cleaned.lower()
        if len(cleaned) < 40:
            continue
        if any(marker in lowered for marker in LOW_VALUE_LINES):
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        kept.append(cleaned)
    return "\n".join(kept).strip()


def flatten_jsonld(value: object) -> Iterable[dict]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from flatten_jsonld(child)
    elif isinstance(value, list):
        for item in value:
            yield from flatten_jsonld(item)


def extract_jsonld_text_from_soup(soup) -> str:
    if soup is None:
        return ""
    chunks: list[str] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text(" ", strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        for node in flatten_jsonld(payload):
            article_body = node.get("articleBody")
            if isinstance(article_body, str):
                chunks.append(article_body)
    return collapse_lines(chunks)


def extract_jsonld_text(html: str) -> str:
    if not BeautifulSoup:
        return ""
    soup = BeautifulSoup(html, "lxml")
    return extract_jsonld_text_from_soup(soup)


def extract_readability_text(html: str) -> str:
    if not Document or not BeautifulSoup:
        return ""
    try:
        summary = Document(html).summary(html_partial=True)
    except Exception:
        return ""
    soup = BeautifulSoup(summary, "lxml")
    lines = [tag.get_text(" ", strip=True) for tag in soup.find_all(["p", "h2", "li"])]
    return collapse_lines(lines)


def extract_bs4_text_from_soup(soup) -> str:
    if soup is None:
        return ""
    selectors = [
        "article p",
        "main p",
        "div.article-body p",
        "div.article_content p",
        "div.story-content p",
        "div.storyPage p",
        "div.story-page p",
        "div[itemprop='articleBody'] p",
        "div.post-content p",
        "section p",
        "p",
    ]
    for selector in selectors:
        selected = soup.select(selector)
        if not selected:
            continue
        lines = [tag.get_text(" ", strip=True) for tag in selected]
        cleaned = collapse_lines(lines)
        if len(cleaned) >= MIN_BODY_CHARS:
            return cleaned
    return ""


def extract_bs4_text(html: str) -> str:
    if not BeautifulSoup:
        return ""
    soup = BeautifulSoup(html, "lxml")
    return extract_bs4_text_from_soup(soup)


def extract_article_text(url: str) -> str:
    try:
        response = _get_session().get(url, headers=HEADERS, timeout=20)
    except Exception:
        return ""
    if response.status_code >= 400:
        return ""
    content_type = response.headers.get("Content-Type", "").lower()
    if content_type and "html" not in content_type and "xml" not in content_type:
        return ""
    html = response.text or ""
    lowered = html.lower()
    if any(marker.lower() in lowered for marker in BLOCK_PAGE_MARKERS):
        return ""

    candidates: list[str] = []
    soup = BeautifulSoup(html, "lxml") if BeautifulSoup else None
    if trafilatura:
        try:
            extracted = trafilatura.extract(
                html,
                url=url,
                include_comments=False,
                include_tables=False,
                favor_recall=True,
                deduplicate=True,
            )
        except Exception:
            extracted = None
        if extracted:
            candidates.append(collapse_lines(extracted.splitlines()))

    for value in (
        extract_jsonld_text_from_soup(soup),
        extract_readability_text(html),
        extract_bs4_text_from_soup(soup),
    ):
        if value:
            candidates.append(value)

    if not candidates:
        return ""
    return max(candidates, key=len).strip()
