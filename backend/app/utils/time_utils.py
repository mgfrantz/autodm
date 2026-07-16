"""Time helpers.

Provides ``utcnow`` — a drop-in replacement for the deprecated
``datetime.datetime.utcnow()`` (deprecated in Python 3.12, removed in a future
version).

It returns a **naive** datetime representing UTC, exactly matching the old
``datetime.utcnow()`` behaviour. This preserves:

* Storage in SQLAlchemy naive ``DateTime`` columns (``updated_at``, etc.)
* The ISO-8601 string produced by ``.isoformat()`` (no ``+00:00`` suffix)

so existing DB rows, serialised timestamps, and the single
``datetime.fromisoformat()`` consumer (``test_game_events``) are unaffected.

When the project is ready to adopt timezone-aware datetimes everywhere, this is
the single place to change.
"""

from datetime import datetime, timezone

__all__ = ["utcnow"]


def utcnow() -> datetime:
    """Return the current UTC time as a *naive* datetime.

    Behaviourally identical to the deprecated ``datetime.utcnow()``.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
