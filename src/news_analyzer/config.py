from __future__ import annotations

import os

APP_VERSION = "0.1.0"
DEFAULT_MARKET = "india"
DEFAULT_ASSET_TYPE = "auto"
DEFAULT_LOOKBACK_HOURS = 24
DEFAULT_MAX_ARTICLES = 120
MAX_LOOKBACK_HOURS = 168
MAX_ARTICLES = 500
MIN_BODY_CHARS = 350
_CPU_COUNT = max(2, os.cpu_count() or 2)
MAX_ARTICLE_WORKERS = min(24, max(8, _CPU_COUNT * 2))
FINBERT_BATCH_SIZE = 8
FINBERT_MODEL_NAME = "ProsusAI/finbert"
CACHE_TTL_SECONDS = 600
QUERY_SLEEP_SECONDS = 0.2
MODEL_TEXT_CHAR_LIMIT = 3500
MAX_QUERY_COUNT = 160
MIN_QUERY_COUNT_BEFORE_EARLY_STOP = 6
SOURCE_DIVERSITY_BOOST = 0.05
MAX_QUERY_WORKERS = min(24, max(8, _CPU_COUNT * 2))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

SITE_PROFILES = {
    "india_finance": [
        "moneycontrol.com",
        "economictimes.indiatimes.com",
        "livemint.com",
        "business-standard.com",
        "cnbctv18.com",
        "ndtvprofit.com",
        "thehindubusinessline.com",
        "financialexpress.com",
        "reuters.com",
    ]
}

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ocid",
    "gaa_at",
    "gaa_ts",
    "ved",
    "ei",
    "hl",
    "gl",
    "ceid",
}

BLOCK_PAGE_MARKERS = (
    "Access Denied",
    "Attention Required! | Cloudflare",
    "enable javascript and cookies to continue",
    "errors.edgesuite.net",
    "sorry, you have been blocked",
)

LOW_VALUE_LINES = (
    "download the mint app",
    "log in to our website",
    "you are just one step away",
    "your session has expired",
    "this is a subscriber only feature",
    "see the top gainers, losers",
    "discover the secret world of unlisted shares",
    "business markets stocks india news",
    "read and get insights from specially curated",
    "the toi business desk is a vigilant and dedicated team",
)

BAD_TITLE_TOKENS = (
    "archives",
    "page ",
    "podcast",
    "photo gallery",
    "photos",
    "videos",
    "group stocks",
)

BAD_URL_TOKENS = (
    "/page/",
    "/about/",
    "/topic/",
    "/tag/",
    "/group-stocks/",
    "/podcast/",
    "/market_page_data_tag/",
    "/photos/",
    "/videos/",
)

FINANCE_TOKENS = (
    "market",
    "index",
    "indices",
    "trade",
    "trading",
    "stocks",
    "stock",
    "shares",
    "share",
    "settles",
    "ends",
    "opens",
    "opening bell",
    "closing bell",
    "support",
    "resistance",
    "futures",
    "options",
    "target",
    "outlook",
    "gains",
    "falls",
    "slips",
    "rally",
    "surges",
    "tumbles",
    "hits",
    "week ahead",
    "pre-open",
    "price",
    "brokerage",
    "earnings",
    "results",
    "market cap",
    "buy",
    "sell",
)

INDEX_QUERY_SUFFIXES = (
    "",
    " outlook",
    " support resistance",
    " opening bell",
    " closing bell",
    " futures",
    " options",
    " market",
)

COMPANY_QUERY_SUFFIXES = (
    "",
    " stock",
    " shares",
    " share price",
    " target price",
    " brokerage",
    " earnings",
    " results",
    " market cap",
    " buy sell",
)

BUILT_IN_ASSETS = {
    "reliance industries": {
        "canonical_name": "Reliance Industries",
        "asset_type": "company",
        "primary_symbol": "RELIANCE",
        "aliases": [
            "reliance industries",
            "reliance",
            "ril",
            "reliance stock",
            "reliance shares",
        ],
    },
    "bank nifty": {
        "canonical_name": "NIFTY Bank",
        "asset_type": "index",
        "primary_symbol": "BANKNIFTY",
        "aliases": ["nifty bank", "bank nifty", "banknifty"],
    },
    "nifty 50": {
        "canonical_name": "NIFTY 50",
        "asset_type": "index",
        "primary_symbol": "NIFTY50",
        "aliases": ["nifty 50", "nifty50"],
    },
    "nifty 500": {
        "canonical_name": "NIFTY 500",
        "asset_type": "index",
        "primary_symbol": "NIFTY500",
        "aliases": ["nifty 500", "nifty500"],
    },
    "sensex": {
        "canonical_name": "BSE Sensex",
        "asset_type": "index",
        "primary_symbol": "SENSEX",
        "aliases": ["sensex", "bse sensex"],
    },
}
