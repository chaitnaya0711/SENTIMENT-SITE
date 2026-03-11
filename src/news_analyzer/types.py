from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal


AssetType = Literal["auto", "ticker", "index", "company"]
ResolvedAssetType = Literal["ticker", "index", "company"]
MarketType = Literal["india"]
SiteProfileType = Literal["india_finance"]


@dataclass(slots=True)
class AssetRequest:
    asset_query: str
    asset_type: AssetType = "auto"
    market: MarketType = "india"
    lookback_hours: int = 24
    max_articles: int = 80
    include_full_text: bool = True
    site_profile: SiteProfileType = "india_finance"
    bullish_threshold: float = 0.6
    bearish_threshold: float = 0.6
    heavy_hitter_count: int = 8


@dataclass(slots=True)
class ResolvedAsset:
    canonical_name: str
    asset_type: ResolvedAssetType
    primary_symbol: str
    aliases: list[str]
    market: MarketType
    query_terms: list[str]


@dataclass(slots=True)
class Candidate:
    google_id: str
    google_news_url: str
    search_query: str
    headline: str
    source: str
    published_dt: datetime

    @property
    def published_utc(self) -> str:
        return self.published_dt.isoformat()


@dataclass(slots=True)
class FinbertResult:
    label: str
    score: float
    probabilities: dict[str, float]


@dataclass(slots=True)
class ArticleRecord:
    article_id: str
    published_utc: str
    age_minutes: int
    source: str
    domain: str
    headline: str
    publisher_url: str
    google_news_url: str
    search_query: str
    matched_aliases: list[str]
    relevance_score: float
    article_text: str
    article_text_length: int
    text_used_for_finbert: str
    finbert: FinbertResult

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["finbert"]["score"] = round(payload["finbert"]["score"], 6)
        payload["relevance_score"] = round(payload["relevance_score"], 6)
        for key, value in payload["finbert"]["probabilities"].items():
            payload["finbert"]["probabilities"][key] = round(value, 6)
        return payload


@dataclass(slots=True)
class FetchStats:
    queries_run: int
    unique_candidates: int
    articles_selected: int
    articles_with_body: int
    deduped_out: int
    latest_published_utc: str | None
    oldest_published_utc: str | None
    duration_seconds: float

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["duration_seconds"] = round(payload["duration_seconds"], 3)
        return payload


@dataclass(slots=True)
class SentimentSummary:
    article_count: int
    positive_count: int
    neutral_count: int
    negative_count: int
    sentiment_score: float
    label_distribution: dict[str, float]
    bullish_count: int = 0
    bearish_count: int = 0
    bullish_probability_total: float = 0.0
    bearish_probability_total: float = 0.0
    net_bull_bear: float = 0.0
    dominant_label: str = "neutral"
    heavy_hitters: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["sentiment_score"] = round(payload["sentiment_score"], 6)
        payload["bullish_probability_total"] = round(payload["bullish_probability_total"], 6)
        payload["bearish_probability_total"] = round(payload["bearish_probability_total"], 6)
        payload["net_bull_bear"] = round(payload["net_bull_bear"], 6)
        for key, value in payload["label_distribution"].items():
            payload["label_distribution"][key] = round(value, 6)
        return payload


@dataclass(slots=True)
class AnalysisResponse:
    request: dict[str, Any]
    resolved_asset: dict[str, Any]
    fetch_stats: FetchStats
    sentiment_summary: SentimentSummary
    articles: list[ArticleRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "resolved_asset": self.resolved_asset,
            "fetch_stats": self.fetch_stats.to_dict(),
            "sentiment_summary": self.sentiment_summary.to_dict(),
            "articles": [article.to_dict() for article in self.articles],
        }
