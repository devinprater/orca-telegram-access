"""Parsing and speech formatting for Telegram Desktop's accessible message names.

Telegram exposes each chat message as a list item whose name is several lines:
[Seen] / sender / [In reply to NAME: quote] / body... / (Received|Sent) at TIME.
Everything here is pure text handling, so it can be tested without AT-SPI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Bidirectional marks and isolates Telegram wraps around quoted names.
_INVISIBLE = re.compile("[‎‏‪-‮⁦-⁩﻿​]")
_STAMP = re.compile(r"^(Received|Sent) at (.+)$")
_REPLY = re.compile(r"^In reply to ([^:]*):\s*(.*)$")

DEFAULT_MAX_CHARS = 500
LOOKBACK = 30


@dataclass(frozen=True)
class Message:
    """A parsed Telegram message."""

    sender: str
    outgoing: bool
    seen: bool
    reply_to: str
    body: str
    stamp: str
    has_stamp: bool


def clean(text: str) -> str:
    """Removes invisible direction marks and normalizes spacing characters."""

    return _INVISIBLE.sub("", text).replace(" ", " ").replace("\xa0", " ")


def has_invisible(text: str) -> bool:
    """Returns True if text contains characters clean() would remove."""

    return bool(_INVISIBLE.search(text))


def parse_message(name: str, has_sender: bool = True) -> Message:
    """Parses a message list item's accessible name."""

    lines = [line.strip() for line in clean(name).split("\n")]
    seen = False
    if lines and lines[0] == "Seen":
        seen = True
        lines.pop(0)
    sender = ""
    if has_sender and lines:
        sender = lines.pop(0)
    reply_to = ""
    if lines:
        match = _REPLY.match(lines[0])
        if match:
            reply_to = match.group(1).strip()
            lines.pop(0)
    stamp = ""
    has_stamp = False
    while lines and not lines[-1]:
        lines.pop()
    if lines:
        match = _STAMP.match(lines[-1])
        if match:
            stamp = lines.pop()
            has_stamp = True
    body = " ".join(line for line in lines if line)
    outgoing = sender == "Me" or stamp.startswith("Sent at")
    return Message(sender, outgoing, seen, reply_to, body, stamp, has_stamp)


def is_incoming(message: Message) -> bool:
    """Returns True for a received (not sent, not service/date) message."""

    return message.has_stamp and not message.outgoing


def announcement(message: Message, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Text spoken when a message arrives."""

    who = message.sender
    if message.reply_to:
        who = f"{who}, replying to {message.reply_to}" if who else f"Reply to {message.reply_to}"
    body = message.body
    if max_chars and len(body) > max_chars:
        cut = body[:max_chars].rsplit(" ", 1)[0]
        body = f"{cut}… {len(body) - len(cut)} more characters"
    return f"{who}: {body}" if who else body


def navigation_text(name: str, has_sender: bool = True) -> str:
    """Cleaner text for a message item that is focused or navigated to."""

    message = parse_message(name, has_sender)
    who = "You" if message.outgoing else message.sender
    if message.seen:
        who = f"{who}, seen" if who else "seen"
    if message.reply_to:
        who = f"{who}, replying to {message.reply_to}" if who else f"Reply to {message.reply_to}"
    text = f"{who}: {message.body}" if who else message.body
    if message.stamp:
        text = f"{text}{' ' if text.endswith(('.', '!', '?')) else '. '}{message.stamp}"
    return text


def new_items(previous_last: str | None, names: list[str]) -> list[str] | None:
    """Returns names added after previous_last, or None if the list was replaced.

    names is the current list of item names, oldest first.  None means the
    caller should simply adopt the new last item as its baseline (first run,
    chat switch, or a change too large/edited to match up).
    """

    if previous_last is None or not names:
        return None
    if names[-1] == previous_last:
        return []
    tail = names[-LOOKBACK - 1 : -1]
    for offset in range(len(tail) - 1, -1, -1):
        if tail[offset] == previous_last:
            return names[len(names) - len(tail) + offset :]
    return None
