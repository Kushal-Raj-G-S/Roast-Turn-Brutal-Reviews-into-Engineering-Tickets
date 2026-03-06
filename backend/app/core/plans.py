"""
Plan limits — single source of truth.
Matches the 5 tiers on the pricing page exactly.
"""

from typing import Optional

PLAN_LIMITS: dict[str, dict] = {
    "free": {
        "uploads_per_month": 3,
        "max_reviews": 10_000,
        "label": "Free",
    },
    "starter": {
        "uploads_per_month": 10,
        "max_reviews": 10_000,
        "label": "Starter",
    },
    "pro": {
        "uploads_per_month": 50,
        "max_reviews": 100_000,
        "label": "Pro",
    },
    "business": {
        "uploads_per_month": 100,
        "max_reviews": 100_000,
        "label": "Business",
    },
    "enterprise": {
        "uploads_per_month": None,   # unlimited
        "max_reviews": None,          # unlimited
        "label": "Enterprise",
    },
}

VALID_PLANS = list(PLAN_LIMITS.keys())


def get_limits(plan: str) -> dict:
    """Return limit dict for a plan, falling back to free if unknown."""
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])


def uploads_unlimited(plan: str) -> bool:
    return PLAN_LIMITS.get(plan, {}).get("uploads_per_month") is None


def reviews_unlimited(plan: str) -> bool:
    return PLAN_LIMITS.get(plan, {}).get("max_reviews") is None
