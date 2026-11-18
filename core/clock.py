"""A demo clock that can be fast-forwarded.

Retention clocks, SLA chasers and scheduled steps (card revocation at 18:00 on
the last working day) all read time from here, so the demo can jump a week
ahead and tests can inject clock skew without patching ``datetime``.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from core.db import Store


class Clock:
    def __init__(self, store: Store):
        self.store = store

    def offset(self) -> timedelta:
        row = self.store.one("SELECT value FROM settings WHERE key='clock_offset_seconds'")
        return timedelta(seconds=float(row["value"])) if row else timedelta()

    def now(self) -> datetime:
        return datetime.now(timezone.utc).replace(microsecond=0) + self.offset()

    def now_iso(self) -> str:
        return self.now().isoformat()

    def today(self) -> str:
        return self.now().date().isoformat()

    def advance(self, seconds: float) -> datetime:
        total = self.offset().total_seconds() + seconds
        with self.store.tx() as conn:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES('clock_offset_seconds', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(total),),
            )
        return self.now()

    def reset(self) -> None:
        with self.store.tx() as conn:
            conn.execute("DELETE FROM settings WHERE key='clock_offset_seconds'")


def new_id(prefix: str) -> str:
    """Short, sortable-enough identifiers for runs, receipts and queue items."""
    stamp = datetime.now(timezone.utc).strftime("%y%m%d%H%M%S")
    return f"{prefix}_{stamp}{secrets.token_hex(3)}"


def parse_ts(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
