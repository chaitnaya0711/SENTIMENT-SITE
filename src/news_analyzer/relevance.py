from __future__ import annotations

import re
from functools import lru_cache

from .config import BAD_TITLE_TOKENS, FINANCE_TOKENS
from .types import Candidate, ResolvedAsset

_BAD_TITLE_TOKENS = tuple(token.lower() for token in BAD_TITLE_TOKENS)
_FINANCE_TOKENS = tuple(token.lower() for token in FINANCE_TOKENS)


@lru_cache(maxsize=512)
def _symbol_pattern(symbol: str) -> re.Pattern[str]:
    return re.compile(rf"\b{re.escape(symbol)}\b")


def title_is_bad(headline: str) -> bool:
    lowered = headline.lower()
    return any(token in lowered for token in _BAD_TITLE_TOKENS)


def matched_aliases(text: str, asset: ResolvedAsset) -> list[str]:
    lowered = text.lower()
    matches = [alias.lower() for alias in asset.aliases if alias.lower() in lowered]
    symbol = asset.primary_symbol.lower()
    if symbol and _symbol_pattern(symbol).search(lowered):
        matches.append(symbol)
    return sorted(set(matches))


def finance_relevance_score(text: str) -> float:
    lowered = text.lower()
    hits = sum(1 for token in _FINANCE_TOKENS if token in lowered)
    return min(1.0, hits / 6.0)


def score_candidate(candidate: Candidate, asset: ResolvedAsset) -> tuple[float, list[str]]:
    query_matches = matched_aliases(candidate.search_query, asset)
    headline_matches = matched_aliases(candidate.headline, asset)
    matches = sorted(set(query_matches + headline_matches))
    alias_score = min(1.0, 0.3 * len(matches))
    finance_score = finance_relevance_score(candidate.headline)
    source_bonus = 0.05 if "reuters" in candidate.source.lower() else 0.0
    score = alias_score * 0.7 + finance_score * 0.25 + source_bonus
    return round(min(1.0, score), 6), matches


def score_article_text(
    headline: str,
    body: str,
    query: str,
    asset: ResolvedAsset,
) -> tuple[float, list[str]]:
    composite = "\n".join(part for part in (headline, body[:2500], query) if part)
    matches = matched_aliases(composite, asset)
    alias_score = min(1.0, 0.3 * len(matches))
    finance_score = finance_relevance_score(composite)
    body_bonus = 0.1 if body else 0.0
    score = alias_score * 0.65 + finance_score * 0.25 + body_bonus
    return round(min(1.0, score), 6), matches


def candidate_is_relevant(candidate: Candidate, asset: ResolvedAsset) -> bool:
    if not candidate.headline or title_is_bad(candidate.headline):
        return False
    score, matches = score_candidate(candidate, asset)
    return score >= 0.2 or bool(matches)
