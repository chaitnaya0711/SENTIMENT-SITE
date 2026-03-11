from __future__ import annotations

from .types import ArticleRecord, SentimentSummary


def sentiment_score_from_result(result: dict[str, object]) -> float:
    probabilities = result["probabilities"]
    positive = float(probabilities.get("positive", 0.0))
    negative = float(probabilities.get("negative", 0.0))
    label = str(result.get("label", "neutral"))
    if label == "positive":
        return positive
    if label == "negative":
        return -negative
    return 0.0


def summarize_sentiment(
    articles: list[ArticleRecord],
    *,
    bullish_threshold: float = 0.6,
    bearish_threshold: float = 0.6,
    heavy_hitter_count: int = 8,
) -> SentimentSummary:
    total = len(articles)
    positive_count = sum(1 for article in articles if article.finbert.label == "positive")
    neutral_count = sum(1 for article in articles if article.finbert.label == "neutral")
    negative_count = sum(1 for article in articles if article.finbert.label == "negative")
    score_total = 0.0
    bullish_count = 0
    bearish_count = 0
    bullish_probability_total = 0.0
    bearish_probability_total = 0.0
    heavy: list[tuple[float, ArticleRecord]] = []

    for article in articles:
        probs = article.finbert.probabilities
        pos = float(probs.get("positive", 0.0))
        neg = float(probs.get("negative", 0.0))
        bullish_probability_total += pos
        bearish_probability_total += neg
        if pos >= bullish_threshold and pos > neg:
            bullish_count += 1
        elif neg >= bearish_threshold and neg > pos:
            bearish_count += 1

        # "Heavy hitter" = high-confidence directional signal weighted by relevance.
        direction_strength = abs(pos - neg)
        confidence = max(pos, neg, float(probs.get("neutral", 0.0)))
        impact = float(article.relevance_score) * (0.65 * direction_strength + 0.35 * confidence)
        heavy.append((impact, article))

        score_total += sentiment_score_from_result(
            {
                "label": article.finbert.label,
                "probabilities": article.finbert.probabilities,
            }
        )
    label_distribution = {
        "positive": positive_count / total if total else 0.0,
        "neutral": neutral_count / total if total else 0.0,
        "negative": negative_count / total if total else 0.0,
    }

    dominant_label = "neutral"
    if positive_count >= neutral_count and positive_count >= negative_count:
        dominant_label = "positive"
    if negative_count > positive_count and negative_count >= neutral_count:
        dominant_label = "negative"

    heavy.sort(key=lambda x: x[0], reverse=True)
    hitters = []
    for impact, article in heavy[: max(0, int(heavy_hitter_count))]:
        probs = article.finbert.probabilities
        pos = float(probs.get("positive", 0.0))
        neg = float(probs.get("negative", 0.0))
        neu = float(probs.get("neutral", 0.0))
        hitters.append(
            {
                "impact_score": round(float(impact), 6),
                "article_id": article.article_id,
                "published_utc": article.published_utc,
                "source": article.source,
                "domain": article.domain,
                "headline": article.headline,
                "publisher_url": article.publisher_url,
                "relevance_score": round(float(article.relevance_score), 6),
                "bullish": round(pos, 6),
                "neutral": round(neu, 6),
                "bearish": round(neg, 6),
                "direction": "bullish" if pos > neg else ("bearish" if neg > pos else "neutral"),
            }
        )

    return SentimentSummary(
        article_count=total,
        positive_count=positive_count,
        neutral_count=neutral_count,
        negative_count=negative_count,
        sentiment_score=(score_total / total) if total else 0.0,
        label_distribution=label_distribution,
        bullish_count=bullish_count,
        bearish_count=bearish_count,
        bullish_probability_total=bullish_probability_total,
        bearish_probability_total=bearish_probability_total,
        net_bull_bear=(bullish_probability_total - bearish_probability_total) / total if total else 0.0,
        dominant_label=dominant_label,
        heavy_hitters=hitters,
    )
