from __future__ import annotations

import re
import concurrent.futures as cf
import threading
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import feedparser
import requests
from requests.adapters import HTTPAdapter

from .config import HEADERS, MAX_QUERY_WORKERS, MIN_QUERY_COUNT_BEFORE_EARLY_STOP
from .types import Candidate, ResolvedAsset

_TITLE_SUFFIX_RE = re.compile(r"\s+-\s+[A-Za-z0-9.& ]+$")
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


def google_rss_url(query: str) -> str:
    return (
        "https://news.google.com/rss/search?q="
        + quote(query)
        + "&hl=en-IN&gl=IN&ceid=IN:en"
    )


def parse_published(value: str) -> datetime | None:
    try:
        dt = parsedate_to_datetime(value)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def clean_headline(title: str) -> str:
    title = title.strip()
    return _TITLE_SUFFIX_RE.sub("", title).strip()


def _early_stop(unique_candidates: int, queries_run: int, max_articles: int) -> bool:
    return queries_run >= MIN_QUERY_COUNT_BEFORE_EARLY_STOP and unique_candidates >= max_articles * 4


def _parse_query_feed(query: str):
    try:
        response = _get_session().get(google_rss_url(query), headers=HEADERS, timeout=12)
        if response.status_code >= 400:
            return query, None
        return query, feedparser.parse(response.content)
    except Exception:
        return query, None


def fetch_candidates(
    queries: list[str],
    asset: ResolvedAsset,
    start_dt: datetime,
    end_dt: datetime,
    max_articles: int,
) -> tuple[list[Candidate], int]:
    del asset
    candidates_by_id: dict[str, Candidate] = {}
    queries_run = 0
    if not queries:
        return [], 0

    worker_count = min(MAX_QUERY_WORKERS, len(queries))
    executor = cf.ThreadPoolExecutor(max_workers=worker_count)
    inflight: dict[cf.Future, str] = {}
    query_iter = iter(queries)

    def submit_next() -> bool:
        try:
            query = next(query_iter)
        except StopIteration:
            return False
        inflight[executor.submit(_parse_query_feed, query)] = query
        return True

    for _ in range(worker_count):
        if not submit_next():
            break

    should_stop = False
    try:
        while inflight and not should_stop:
            done, _ = cf.wait(tuple(inflight), return_when=cf.FIRST_COMPLETED)
            for future in done:
                submitted_query = inflight.pop(future)
                try:
                    query, feed = future.result()
                except Exception:
                    query, feed = submitted_query, None
                queries_run += 1
                for entry in getattr(feed, "entries", []) if feed is not None else []:
                    google_id = entry.get("id") or entry.get("link") or ""
                    published = parse_published(entry.get("published", ""))
                    if not google_id or published is None:
                        continue
                    if published < start_dt or published > end_dt:
                        continue
                    candidate = Candidate(
                        google_id=google_id,
                        google_news_url=entry.get("link", "").strip(),
                        search_query=query,
                        headline=clean_headline(entry.get("title", "")),
                        source=entry.get("source", {}).get("title", "").strip() or "Unknown",
                        published_dt=published,
                    )
                    existing = candidates_by_id.get(google_id)
                    if existing is None or candidate.published_dt > existing.published_dt:
                        candidates_by_id[google_id] = candidate
                if _early_stop(len(candidates_by_id), queries_run, max_articles):
                    should_stop = True
                    break
                submit_next()
    finally:
        for future in inflight:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)

    ordered = sorted(
        candidates_by_id.values(),
        key=lambda item: (item.published_dt, item.source.lower(), item.headline.lower()),
        reverse=True,
    )
    return ordered, queries_run
