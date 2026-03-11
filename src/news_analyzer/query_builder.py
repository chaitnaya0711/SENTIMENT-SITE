from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .config import (
    COMPANY_QUERY_SUFFIXES,
    INDEX_QUERY_SUFFIXES,
    MAX_QUERY_COUNT,
    SITE_PROFILES,
)
from .types import AssetRequest, ResolvedAsset


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = " ".join(value.split())
        if normalized and normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


def _quote_term(term: str) -> str:
    return f'"{term}"'


def _window_cutoffs(lookback_hours: int, now: datetime) -> list[datetime]:
    base_hours = [6, 24, 72, 168]
    windows = [hours for hours in base_hours if hours <= lookback_hours]
    if lookback_hours not in windows:
        windows.append(lookback_hours)
    cutoffs = []
    for hours in sorted(set(max(1, hours) for hours in windows)):
        cutoffs.append(now - timedelta(hours=hours))
    return cutoffs


def _build_base_queries(asset: ResolvedAsset) -> list[str]:
    suffixes = INDEX_QUERY_SUFFIXES if asset.asset_type == "index" else COMPANY_QUERY_SUFFIXES
    aliases = sorted(set(asset.aliases + [asset.canonical_name, asset.primary_symbol]), key=len)
    queries: list[str] = []
    for alias in aliases[:6]:
        if alias == asset.primary_symbol.lower():
            display = alias.upper()
        elif asset.asset_type == "index" and " " not in alias:
            display = alias.upper()
        else:
            display = alias.title()
        if asset.asset_type == "index" and display.lower().startswith("nifty "):
            display = display.upper()
        for suffix in suffixes:
            queries.append(f"{_quote_term(display)}{suffix}")
    return _ordered_unique(queries)


def _build_site_queries(base_queries: list[str], request: AssetRequest) -> list[str]:
    domains = SITE_PROFILES.get(request.site_profile, [])
    queries: list[str] = []
    top_domains = domains[:4] if not request.include_full_text else domains[:7]
    for base in base_queries[:8]:
        for domain in top_domains:
            queries.append(f"{base} site:{domain}")
    return _ordered_unique(queries)


def _build_day_slices(asset: ResolvedAsset, request: AssetRequest, now: datetime) -> list[str]:
    queries: list[str] = []
    daily_terms = sorted(set(asset.aliases + [asset.canonical_name.lower()]), key=len)[:3]
    total_days = max(1, min(4 if not request.include_full_text else 7, (request.lookback_hours + 23) // 24))
    for offset in range(total_days):
        day_end = (now - timedelta(days=offset)).date() + timedelta(days=1)
        day_start = day_end - timedelta(days=1)
        for alias in daily_terms:
            quoted = _quote_term(alias.title() if " " in alias else alias.upper())
            queries.append(f"{quoted} after:{day_start.isoformat()} before:{day_end.isoformat()}")
            if asset.asset_type == "index":
                queries.append(f"{quoted} outlook after:{day_start.isoformat()} before:{day_end.isoformat()}")
            else:
                queries.append(f"{quoted} stock after:{day_start.isoformat()} before:{day_end.isoformat()}")
    return _ordered_unique(queries)


def build_queries(
    asset: ResolvedAsset,
    request: AssetRequest,
    now: datetime | None = None,
) -> list[str]:
    now = now or datetime.now(timezone.utc)
    base_queries = _build_base_queries(asset)
    site_queries = _build_site_queries(base_queries, request)
    cutoff_queries: list[str] = []
    for cutoff in _window_cutoffs(request.lookback_hours, now):
        after_date = cutoff.date().isoformat()
        for query in base_queries[:14]:
            cutoff_queries.append(f"{query} after:{after_date}")
    day_slices = _build_day_slices(asset, request, now)
    queries = _ordered_unique(base_queries + cutoff_queries + site_queries + day_slices)
    dynamic_cap = max(42, min(MAX_QUERY_COUNT, request.max_articles * 2))
    return queries[:dynamic_cap]
