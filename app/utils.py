from datetime import UTC, datetime


def utcnow():
    """Naive UTC timestamp (DB columns are naive UTC)."""
    return datetime.now(UTC).replace(tzinfo=None)
