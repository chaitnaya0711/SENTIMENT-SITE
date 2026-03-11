from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .config import BAD_URL_TOKENS, TRACKING_PARAMS

try:
    from googlenewsdecoder import new_decoderv1
except Exception:  # pragma: no cover - optional dependency fallback
    new_decoderv1 = None


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]
    cleaned = parsed._replace(
        scheme=(parsed.scheme or "https").lower(),
        netloc=parsed.netloc.lower(),
        query=urlencode(query_pairs),
        fragment="",
    )
    return urlunparse(cleaned).rstrip("/")


def url_looks_like_article(url: str) -> bool:
    lowered = url.lower()
    return not any(token in lowered for token in BAD_URL_TOKENS)


def try_decode_google_url(google_news_url: str) -> str:
    if not new_decoderv1:
        return ""
    if not google_news_url:
        return ""
    for attempt in range(3):
        try:
            result = new_decoderv1(google_news_url)
        except Exception:
            result = {"status": False}
        decoded_url = result.get("decoded_url") if result.get("status") else None
        if decoded_url:
            return normalize_url(decoded_url)
    return ""


def stable_article_id(*parts: str) -> str:
    digest = hashlib.sha1("||".join(parts).encode("utf-8")).hexdigest()
    return digest
