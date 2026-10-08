from datetime import datetime, timezone


def utcnow():
    """Naive UTC timestamp (DB columns are naive UTC)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
