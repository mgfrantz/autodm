"""Tests for the utcnow() helper — a drop-in for the deprecated datetime.utcnow().

These lock in the two safety properties that make the refactor behaviour-preserving:
  1. Returns a *naive* datetime (tzinfo is None).
  2. Produces an ISO string with no timezone suffix (matching the old output),
     so DB rows and the single datetime.fromisoformat() consumer are unaffected.
"""

from datetime import datetime, timezone, timedelta

from app.utils.time_utils import utcnow


def test_utcnow_returns_naive_datetime():
    """utcnow() must return a naive datetime — no tzinfo."""
    result = utcnow()
    assert isinstance(result, datetime)
    assert result.tzinfo is None


def test_utcnow_matches_real_utc_time():
    """utcnow() should be within a small window of the true UTC time."""
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    result = utcnow()
    after = datetime.now(timezone.utc).replace(tzinfo=None)
    assert before - timedelta(seconds=1) <= result <= after + timedelta(seconds=1)


def test_utcnow_isoformat_has_no_timezone_suffix():
    """isoformat() output must contain no '+' tz suffix (preserves old format)."""
    iso = utcnow().isoformat()
    assert "+" not in iso
    # And it must round-trip through fromisoformat (the test_game_events consumer)
    parsed = datetime.fromisoformat(iso)
    assert parsed.tzinfo is None


def test_utcnow_is_callable_signature_for_sqlalchemy_defaults():
    """utcnow is a zero-arg callable returning a datetime — usable as Column default."""
    assert callable(utcnow)
    assert isinstance(utcnow(), datetime)
