"""Shared Stripe SDK helpers used by both billing.py (subscriptions) and
shop.py (one-time orders)."""


def as_dict(obj):
    """Stripe SDK responses are StripeObjects, not dicts, as of stripe>=9 —
    tests stub the SDK boundary with plain dicts directly, so only convert
    when the object actually offers to_dict()."""
    return obj.to_dict() if hasattr(obj, "to_dict") else obj
