from datetime import UTC, datetime


def utc_now():
    return datetime.now(UTC)


def parse_datetime(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed
