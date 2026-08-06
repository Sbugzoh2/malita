"""
Malita (Pty) Ltd — Subscription tier definitions.

Change prices/limits here in ONE place; app.py and the PayFast checkout
builder both read from this file so they can never drift out of sync.
"""

TIER_CONFIG = {
    "free": {
        "label": "Free",
        "price_zar": 0,
        "ai_tutor_daily_limit": 5,   # solves per day, resets at midnight
        "ocr_enabled": False,
        "pdf_enabled": False,
        "past_papers_enabled": False,
    },
    "learner": {
        "label": "Learner",
        "price_zar": 49.99,
        "ai_tutor_daily_limit": None,  # None = unlimited
        "ocr_enabled": True,
        "pdf_enabled": True,
        # Past Papers Library is the one thing that separates Learner from
        # Premium - previously the two tiers were identical in every way
        # except price, which is its own bug (nothing to "upgrade" to).
        "past_papers_enabled": False,
    },
    "premium": {
        "label": "Premium",
        "price_zar": 99.99,
        "ai_tutor_daily_limit": None,
        "ocr_enabled": True,
        "pdf_enabled": True,
        "past_papers_enabled": True,
    },
}

TIER_ORDER = ["free", "learner", "premium"]


def tier_config(tier: str) -> dict:
    return TIER_CONFIG.get(tier, TIER_CONFIG["free"])


def can_use_ocr(tier: str) -> bool:
    return tier_config(tier)["ocr_enabled"]


def can_use_pdf(tier: str) -> bool:
    return tier_config(tier)["pdf_enabled"]


def can_use_past_papers(tier: str) -> bool:
    return tier_config(tier)["past_papers_enabled"]


def daily_limit(tier: str):
    return tier_config(tier)["ai_tutor_daily_limit"]
