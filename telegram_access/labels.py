"""Finding labels for Telegram controls that have no accessible name.

Works on any object with the Atspi.Accessible methods used below, so tests can
pass simple fakes.
"""

from __future__ import annotations

import json
import os

LABEL_FILE = os.path.expanduser("~/.local/share/orca/telegram_access_labels.json")
GENERIC_BUTTON_TEXT = {"button", "push button", "toggle button", "menu button"}
MAX_DEPTH = 3


def _safe(call, default=""):
    try:
        value = call()
    except Exception:  # pylint: disable=broad-exception-caught
        return default
    return default if value is None else value


def named_descendant(node, depth: int = MAX_DEPTH) -> str:
    """Returns the first non-empty name or description below node."""

    if depth <= 0:
        return ""
    for index in range(_safe(node.get_child_count, 0)):
        child = _safe(lambda i=index: node.get_child_at_index(i), None)
        if child is None:
            continue
        name = _safe(child.get_name).strip()
        if name:
            return name
        text = _safe(child.get_description).strip()
        if text:
            return text
        found = named_descendant(child, depth - 1)
        if found:
            return found
    return ""


def signature(node) -> str:
    """A stable description of where an unnamed control sits.

    Built from its role, the roles/names of its siblings and its position, so
    the same control gives the same signature across sessions.
    """

    parent = _safe(node.get_parent, None)
    if parent is None:
        return _safe(node.get_role_name, "unknown")
    parts = []
    position = -1
    for index in range(_safe(parent.get_child_count, 0)):
        sibling = _safe(lambda i=index: parent.get_child_at_index(i), None)
        if sibling is None:
            continue
        if _safe(lambda s=sibling: s.get_index_in_parent(), -2) == _safe(
            node.get_index_in_parent, -1
        ):
            position = index
        parts.append(f"{_safe(sibling.get_role_name)}={_safe(sibling.get_name)[:20]}")
    return f"{_safe(node.get_role_name)}@{position}|{';'.join(parts)}"


def load_user_labels(path: str = LABEL_FILE) -> dict[str, str]:
    """Reads the user's signature -> label table."""

    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def neighbor_name(node) -> str:
    """Name of the nearest named sibling, used as context in the fallback."""

    parent = _safe(node.get_parent, None)
    if parent is None:
        return ""
    own = _safe(node.get_index_in_parent, -1)
    best = ""
    for index in range(_safe(parent.get_child_count, 0)):
        sibling = _safe(lambda i=index: parent.get_child_at_index(i), None)
        if sibling is None or _safe(sibling.get_index_in_parent, -2) == own:
            continue
        name = _safe(sibling.get_name).strip()
        if name:
            best = name
            if index > own:
                break
    return best


def infer_label(node, user_labels: dict[str, str] | None = None) -> tuple[str, str]:
    """Returns (label, source) for an unnamed control.

    Order: user table, description/child text, then a generic fallback that at
    least says there is a button and where it is.
    """

    sig = signature(node)
    table = load_user_labels() if user_labels is None else user_labels
    if sig in table:
        return table[sig], "user"
    description = _safe(node.get_description).strip()
    if description:
        return description, "description"
    inner = named_descendant(node)
    if inner:
        return inner, "child"
    near = neighbor_name(node)
    if near:
        return f"Unlabeled, next to {near}", "fallback"
    return "Unlabeled", "fallback"
