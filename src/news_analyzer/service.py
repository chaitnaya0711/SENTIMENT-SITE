from __future__ import annotations

import concurrent.futures as cf
import csv
import tempfile
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from .aggregate import summarize_sentiment
from .article_extractor import extract_article_text
from .assets import AssetResolver, resolved_asset_to_dict, supported_assets as built_in_supported_assets
from .config import (
    APP_VERSION,
    CACHE_TTL_SECONDS,
    DEFAULT_LOOKBACK_HOURS,
    DEFAULT_MARKET,
    DEFAULT_MAX_ARTICLES,
    MAX_ARTICLE_WORKERS,
    MAX_ARTICLES,
    MAX_LOOKBACK_HOURS,
    MIN_BODY_CHARS,
    SOURCE_DIVERSITY_BOOST,
)
from .finbert import clip_text_for_model, get_finbert_analyzer
from .google_news import fetch_candidates
from .query_builder import build_queries
from .relevance import score_article_text, score_candidate, title_is_bad
from .types import AnalysisResponse, ArticleRecord, AssetRequest, FetchStats, FinbertResult
from .url_tools import normalize_url, stable_article_id, try_decode_google_url, url_looks_like_article


@lru_cache(maxsize=8192)
def _decode_google_url_cached(google_news_url: str) -> str:
    return try_decode_google_url(google_news_url)


@lru_cache(maxsize=1024)
def _extract_article_text_cached(url: str) -> str:
    return extract_article_text(url)


class TTLCache:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._store: dict[tuple, tuple[float, dict[str, object]]] = {}

    def get(self, key: tuple) -> dict[str, object] | None:
        record = self._store.get(key)
        if not record:
            return None
        expires_at, value = record
        if expires_at < time.time():
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: tuple, value: dict[str, object]) -> None:
        self._store[key] = (time.time() + self.ttl_seconds, value)


class NewsAnalysisService:
    def __init__(self) -> None:
        self.asset_resolver = AssetResolver()
        self.cache = TTLCache(CACHE_TTL_SECONDS)
        self.finbert = get_finbert_analyzer()

    def validate_request(self, request: AssetRequest) -> AssetRequest:
        asset_query = request.asset_query.strip()
        if not asset_query:
            raise ValueError("asset_query is required")
        lookback_hours = min(MAX_LOOKBACK_HOURS, max(1, int(request.lookback_hours or DEFAULT_LOOKBACK_HOURS)))
        max_articles = min(MAX_ARTICLES, max(1, int(request.max_articles or DEFAULT_MAX_ARTICLES)))
        bullish_threshold = float(request.bullish_threshold or 0.6)
        bearish_threshold = float(request.bearish_threshold or 0.6)
        bullish_threshold = min(0.99, max(0.0, bullish_threshold))
        bearish_threshold = min(0.99, max(0.0, bearish_threshold))
        heavy_hitter_count = min(25, max(1, int(request.heavy_hitter_count or 8)))
        return AssetRequest(
            asset_query=asset_query,
            asset_type=request.asset_type,
            market=request.market or DEFAULT_MARKET,
            lookback_hours=lookback_hours,
            max_articles=max_articles,
            include_full_text=bool(request.include_full_text),
            site_profile=request.site_profile,
            bullish_threshold=bullish_threshold,
            bearish_threshold=bearish_threshold,
            heavy_hitter_count=heavy_hitter_count,
        )

    def _cache_key(self, request: AssetRequest) -> tuple:
        return (
            request.asset_query.lower(),
            request.asset_type,
            request.market,
            request.lookback_hours,
            request.max_articles,
            request.include_full_text,
            request.site_profile,
            round(float(request.bullish_threshold), 4),
            round(float(request.bearish_threshold), 4),
            int(request.heavy_hitter_count),
        )

    def _enrich_candidate(self, candidate, asset, now: datetime) -> dict[str, object]:
        publisher_url = _decode_google_url_cached(candidate.google_news_url)
        if publisher_url:
            publisher_url = normalize_url(publisher_url)
        if not publisher_url or not url_looks_like_article(publisher_url):
            publisher_url = ""
        article_text = _extract_article_text_cached(publisher_url) if publisher_url else ""
        relevance_score, matched = score_article_text(
            candidate.headline,
            article_text,
            candidate.search_query,
            asset,
        )
        if relevance_score < 0.2:
            base_score, base_matches = score_candidate(candidate, asset)
            relevance_score = base_score
            matched = base_matches
        domain = ""
        if publisher_url:
            domain = publisher_url.split("/")[2].removeprefix("www.")
        return {
            "candidate": candidate,
            "publisher_url": publisher_url,
            "domain": domain,
            "article_text": article_text,
            "article_text_length": len(article_text),
            "relevance_score": relevance_score,
            "matched_aliases": matched,
            "age_minutes": max(0, int((now - candidate.published_dt).total_seconds() // 60)),
        }

    def _rank_candidates(self, candidates, asset):
        ranked = []
        source_counts: dict[str, int] = {}
        for candidate in candidates:
            if not candidate.headline or title_is_bad(candidate.headline):
                continue
            score, matches = score_candidate(candidate, asset)
            if score < 0.2 and not matches:
                continue
            source_key = candidate.source.lower()
            source_penalty = source_counts.get(source_key, 0) * SOURCE_DIVERSITY_BOOST
            composite = score - source_penalty
            ranked.append((candidate.published_dt, composite, matches, candidate))
            source_counts[source_key] = source_counts.get(source_key, 0) + 1
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[3] for item in ranked]

    def _article_preview_rows(self, response: dict[str, object]) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for article in response.get("articles", []):
            finbert = article.get("finbert", {})
            rows.append(
                {
                    "published_utc": article.get("published_utc"),
                    "source": article.get("source"),
                    "headline": article.get("headline"),
                    "domain": article.get("domain"),
                    "relevance_score": article.get("relevance_score"),
                    "finbert_label": finbert.get("label"),
                    "finbert_score": finbert.get("score"),
                }
            )
        return rows

    def _csv_rows(self, response: dict[str, object]) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for article in response.get("articles", []):
            finbert = article.get("finbert", {})
            probabilities = finbert.get("probabilities", {})
            row = dict(article)
            row.pop("finbert", None)
            row["finbert_label"] = finbert.get("label")
            row["finbert_score"] = finbert.get("score")
            row["finbert_positive"] = probabilities.get("positive")
            row["finbert_neutral"] = probabilities.get("neutral")
            row["finbert_negative"] = probabilities.get("negative")
            rows.append(row)
        return rows

    def _write_csv(self, response: dict[str, object]) -> str:
        temp_dir = Path(tempfile.gettempdir())
        filename = f"news_analysis_{int(time.time())}.csv"
        path = temp_dir / filename
        rows = self._csv_rows(response)
        if not rows:
            path.write_text("article_id,headline\n", encoding="utf-8")
            return str(path)
        fieldnames = list(rows[0].keys())
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return str(path)

    def supported_assets(self) -> dict[str, object]:
        payload = built_in_supported_assets()
        payload["limits"] = {
            "default_lookback_hours": DEFAULT_LOOKBACK_HOURS,
            "max_lookback_hours": MAX_LOOKBACK_HOURS,
            "default_max_articles": DEFAULT_MAX_ARTICLES,
            "max_articles": MAX_ARTICLES,
        }
        return payload

    def healthcheck(self) -> dict[str, object]:
        return {
            "status": "ok",
            "app_version": APP_VERSION,
            "market": DEFAULT_MARKET,
            "finbert_model_name": self.finbert.model_name,
            "finbert_loaded": self.finbert.loaded,
            "queue": {
                "enabled": True,
                "default_concurrency_limit": 1,
            },
            "cache_ttl_seconds": CACHE_TTL_SECONDS,
        }

    def analyze(self, request: AssetRequest) -> dict[str, object]:
        request = self.validate_request(request)
        cache_key = self._cache_key(request)
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        started = time.time()
        now = datetime.now(timezone.utc)
        resolved_asset = self.asset_resolver.resolve(request)
        queries = build_queries(resolved_asset, request, now=now)
        start_dt = now - timedelta(hours=request.lookback_hours)
        raw_candidates, queries_run = fetch_candidates(
            queries=queries,
            asset=resolved_asset,
            start_dt=start_dt,
            end_dt=now,
            max_articles=request.max_articles,
        )
        ranked_candidates = self._rank_candidates(raw_candidates, resolved_asset)
        pool_multiplier = 4 if request.include_full_text else 5
        candidate_pool = ranked_candidates[: max(request.max_articles * pool_multiplier, 80)]

        enriched: list[dict[str, object]] = []
        deduped_out = 0
        seen_keys: set[tuple[str, str, str]] = set()
        pre_seen: set[tuple[str, str]] = set()
        unique_candidate_pool = []
        for candidate in candidate_pool:
            pre_key = (candidate.source.lower(), candidate.headline.lower())
            if pre_key in pre_seen:
                deduped_out += 1
                continue
            pre_seen.add(pre_key)
            unique_candidate_pool.append(candidate)

        # Always extract and score full text for analysis; include_full_text controls JSON payload only.
        article_workers = max(1, min(MAX_ARTICLE_WORKERS, len(unique_candidate_pool)))
        with cf.ThreadPoolExecutor(max_workers=article_workers) as executor:
            futures = [
                executor.submit(self._enrich_candidate, candidate, resolved_asset, now)
                for candidate in unique_candidate_pool
            ]
            for future in cf.as_completed(futures):
                try:
                    item = future.result()
                except Exception:
                    continue
                candidate = item["candidate"]
                dedupe_key = (
                    candidate.google_id,
                    item["publisher_url"],
                    f"{candidate.source.lower()}::{candidate.headline.lower()}",
                )
                if dedupe_key in seen_keys:
                    deduped_out += 1
                    continue
                seen_keys.add(dedupe_key)
                enriched.append(item)

        enriched.sort(
            key=lambda item: (
                item["candidate"].published_dt,
                item["relevance_score"],
                item["article_text_length"] >= MIN_BODY_CHARS,
            ),
            reverse=True,
        )
        selected = enriched[: request.max_articles]
        sentiment_inputs = [
            (item["article_text"] or item["candidate"].headline)
            for item in selected
        ]
        finbert_results = self.finbert.analyze_texts(sentiment_inputs) if sentiment_inputs else []

        articles: list[ArticleRecord] = []
        for item, finbert_result in zip(selected, finbert_results):
            candidate = item["candidate"]
            article_text = item["article_text"] if request.include_full_text else ""
            text_used = clip_text_for_model(item["article_text"] or candidate.headline)
            articles.append(
                ArticleRecord(
                    article_id=stable_article_id(candidate.google_id, item["publisher_url"], candidate.headline),
                    published_utc=candidate.published_utc,
                    age_minutes=item["age_minutes"],
                    source=candidate.source,
                    domain=item["domain"],
                    headline=candidate.headline,
                    publisher_url=item["publisher_url"],
                    google_news_url=candidate.google_news_url,
                    search_query=candidate.search_query,
                    matched_aliases=item["matched_aliases"],
                    relevance_score=float(item["relevance_score"]),
                    article_text=article_text,
                    article_text_length=int(item["article_text_length"]),
                    text_used_for_finbert=text_used,
                    finbert=FinbertResult(
                        label=str(finbert_result["label"]),
                        score=float(finbert_result["score"]),
                        probabilities={
                            "positive": float(finbert_result["probabilities"].get("positive", 0.0)),
                            "neutral": float(finbert_result["probabilities"].get("neutral", 0.0)),
                            "negative": float(finbert_result["probabilities"].get("negative", 0.0)),
                        },
                    ),
                )
            )

        latest_published = articles[0].published_utc if articles else None
        oldest_published = articles[-1].published_utc if articles else None
        response = AnalysisResponse(
            request={
                **asdict(request),
                "requested_at_utc": now.isoformat().replace("+00:00", "Z"),
            },
            resolved_asset=resolved_asset_to_dict(resolved_asset),
            fetch_stats=FetchStats(
                queries_run=queries_run,
                unique_candidates=len(raw_candidates),
                articles_selected=len(articles),
                articles_with_body=sum(1 for article in articles if article.article_text_length >= MIN_BODY_CHARS),
                deduped_out=deduped_out,
                latest_published_utc=latest_published,
                oldest_published_utc=oldest_published,
                duration_seconds=time.time() - started,
            ),
            sentiment_summary=summarize_sentiment(
                articles,
                bullish_threshold=float(request.bullish_threshold),
                bearish_threshold=float(request.bearish_threshold),
                heavy_hitter_count=int(request.heavy_hitter_count),
            ),
            articles=articles,
        ).to_dict()
        self.cache.set(cache_key, response)
        return response


_shared_service = NewsAnalysisService()


def analyze_latest_news(
    asset_query: str,
    asset_type: str = "auto",
    market: str = "india",
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    max_articles: int = DEFAULT_MAX_ARTICLES,
    include_full_text: bool = False,
    site_profile: str = "india_finance",
    bullish_threshold: float = 0.6,
    bearish_threshold: float = 0.6,
    heavy_hitter_count: int = 8,
) -> dict[str, object]:
    request = AssetRequest(
        asset_query=asset_query,
        asset_type=asset_type,
        market=market,
        lookback_hours=lookback_hours,
        max_articles=max_articles,
        include_full_text=include_full_text,
        site_profile=site_profile,
        bullish_threshold=bullish_threshold,
        bearish_threshold=bearish_threshold,
        heavy_hitter_count=heavy_hitter_count,
    )
    return _shared_service.analyze(request)


def supported_assets() -> dict[str, object]:
    return _shared_service.supported_assets()


def build_healthcheck() -> dict[str, object]:
    return _shared_service.healthcheck()


def build_ui_payload(
    asset_query: str,
    asset_type: str,
    lookback_hours: int,
    max_articles: int,
    include_full_text: bool,
) -> tuple[dict[str, object], list[dict[str, object]], str, str]:
    response = analyze_latest_news(
        asset_query=asset_query,
        asset_type=asset_type,
        market="india",
        lookback_hours=lookback_hours,
        max_articles=max_articles,
        include_full_text=include_full_text,
        site_profile="india_finance",
    )
    articles = _shared_service._article_preview_rows(response)
    csv_path = _shared_service._write_csv(response)
    stats = response["fetch_stats"]
    summary = response["sentiment_summary"]
    status = (
        f"Fetched {stats['articles_selected']} articles from {stats['queries_run']} queries. "
        f"Sentiment score: {summary['sentiment_score']}."
    )
    return response, articles, csv_path, status
