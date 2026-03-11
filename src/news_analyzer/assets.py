from __future__ import annotations

import re
from dataclasses import asdict

from .config import BUILT_IN_ASSETS, DEFAULT_MARKET
from .types import AssetRequest, ResolvedAsset


def _normalize_key(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return re.sub(r"\s+", " ", cleaned)


def _title_case_query(value: str) -> str:
    words = [word for word in re.split(r"\s+", value.strip()) if word]
    if not words:
        return "Unknown Asset"
    rebuilt = []
    for word in words:
        if word.isupper() and len(word) <= 6:
            rebuilt.append(word)
        elif word.lower() in {"nifty", "bse"}:
            rebuilt.append(word.upper())
        else:
            rebuilt.append(word.capitalize())
    return " ".join(rebuilt)


def _guess_asset_type(asset_query: str) -> str:
    lowered = asset_query.lower()
    compact = re.sub(r"[^a-z0-9]", "", lowered)
    if any(token in lowered for token in ("nifty", "sensex", "index")):
        return "index"
    if compact.endswith("50") or compact.endswith("100") or compact.endswith("500"):
        return "index"
    if asset_query.isupper() and len(compact) <= 12:
        return "ticker"
    if len(asset_query.split()) == 1 and len(compact) <= 8:
        return "ticker"
    return "company"


def _generate_aliases(asset_query: str, asset_type: str) -> list[str]:
    normalized = _normalize_key(asset_query)
    compact = normalized.replace(" ", "")
    title_query = _title_case_query(asset_query)
    aliases = {normalized, compact, asset_query.lower().strip(), title_query.lower()}
    if asset_type in {"ticker", "company"}:
        aliases.add(f"{normalized} stock")
        aliases.add(f"{normalized} shares")
        aliases.add(compact.upper())
    if asset_type == "index":
        aliases.add(f"{normalized} index")
        aliases.add(f"{normalized} futures")
    cleaned = [alias.strip() for alias in aliases if alias and len(alias.strip()) > 1]
    return sorted(set(cleaned), key=lambda item: (len(item), item))


class AssetResolver:
    def resolve(self, request: AssetRequest) -> ResolvedAsset:
        raw_query = request.asset_query.strip()
        normalized_query = _normalize_key(raw_query)

        for payload in BUILT_IN_ASSETS.values():
            alias_keys = {_normalize_key(payload["canonical_name"]), *map(_normalize_key, payload["aliases"])}
            if normalized_query in alias_keys:
                return ResolvedAsset(
                    canonical_name=payload["canonical_name"],
                    asset_type=payload["asset_type"],
                    primary_symbol=payload["primary_symbol"],
                    aliases=sorted(set(payload["aliases"])),
                    market=request.market or DEFAULT_MARKET,
                    query_terms=sorted(set(payload["aliases"] + [payload["canonical_name"]])),
                )

        asset_type = request.asset_type if request.asset_type != "auto" else _guess_asset_type(raw_query)
        aliases = _generate_aliases(raw_query, asset_type)
        primary_symbol = re.sub(r"[^A-Z0-9]", "", raw_query.upper()) or aliases[0].upper().replace(" ", "")
        canonical_name = _title_case_query(raw_query)
        if asset_type == "index" and canonical_name.upper().startswith("NIFTY "):
            canonical_name = canonical_name.upper()
        return ResolvedAsset(
            canonical_name=canonical_name,
            asset_type=asset_type,
            primary_symbol=primary_symbol,
            aliases=aliases,
            market=request.market or DEFAULT_MARKET,
            query_terms=sorted(set(aliases + [canonical_name.lower(), primary_symbol.lower()])),
        )

    def supported_assets(self) -> dict[str, object]:
        examples = []
        for payload in BUILT_IN_ASSETS.values():
            examples.append(
                {
                    "canonical_name": payload["canonical_name"],
                    "asset_type": payload["asset_type"],
                    "primary_symbol": payload["primary_symbol"],
                    "aliases": payload["aliases"],
                }
            )
        return {
            "examples": examples,
            "notes": {
                "arbitrary_inputs_supported": True,
                "market": DEFAULT_MARKET,
                "normalization": "Unknown inputs are converted into generic ticker/company/index profiles with generated aliases.",
            },
        }


def supported_assets() -> dict[str, object]:
    return AssetResolver().supported_assets()


def resolved_asset_to_dict(asset: ResolvedAsset) -> dict[str, object]:
    return asdict(asset)
