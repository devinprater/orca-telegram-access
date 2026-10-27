# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Devin Prater
"""Working out what a Backspace in a Telegram text field really deleted.

Telegram's text-changed:delete events always carry a single space as the
deleted text, so Orca says "space" for every Backspace.  The text before and
after the event, plus the offset and length, are enough to recover it.
"""

from __future__ import annotations

import time

RECENT_SECONDS = 1.0


def deleted_text(previous: str, current: str, offset: int, length: int) -> str | None:
    """Returns the text removed, or None if previous/current do not fit the event."""

    if offset < 0 or length <= 0 or offset + length > len(previous):
        return None
    if previous[:offset] + previous[offset + length :] != current:
        return None
    return previous[offset : offset + length]


class DeletionTracker:
    """Keeps a snapshot of a text field and remembers its last real deletion."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._snapshot = ""
        self._deleted = ""
        self._when = float("-inf")

    def observe(self, current: str) -> None:
        """Records the field's text after any change, focus or caret move."""

        self._snapshot = current

    def on_delete(self, current: str, offset: int, length: int) -> None:
        """Handles a delete event; the snapshot must predate it."""

        removed = deleted_text(self._snapshot, current, offset, length)
        self._snapshot = current
        if removed is None:
            self._deleted = ""
            return
        self._deleted = removed
        self._when = self._clock()

    def take(self) -> str:
        """Returns the most recent real deletion once, if it just happened."""

        if self._deleted and self._clock() - self._when <= RECENT_SECONDS:
            removed, self._deleted = self._deleted, ""
            return removed
        return ""
