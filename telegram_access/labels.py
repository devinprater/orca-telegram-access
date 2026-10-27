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


# Buttons that identify Telegram's main-menu drawer.  Matched by name, so only
# English Telegram is recognized; other languages fall through to the fallback.
DRAWER_MARKERS = {"My Profile", "New Group", "Saved Messages"}
DRAWER_LABELS = ("Profile picture", "Account, show or hide other accounts")


def _contains_marker(node, depth: int = 6) -> bool:
    if depth <= 0:
        return False
    for index in range(_safe(node.get_child_count, 0)):
        child = _safe(lambda i=index: node.get_child_at_index(i), None)
        if child is None:
            continue
        if _safe(child.get_name) in DRAWER_MARKERS or _contains_marker(child, depth - 1):
            return True
    return False


def drawer_label(node) -> str:
    """Label for the two unnamed buttons at the top of the main-menu drawer.

    The first is the round profile picture, the second the wide header row
    whose arrow shows or hides the other accounts (verified live: it reveals
    "Add Account").
    """

    if _safe(node.get_role_name) != "button":
        return ""
    parent = _safe(node.get_parent, None)
    if parent is None or not _contains_marker(parent):
        return ""
    own = _safe(node.get_index_in_parent, -1)
    unnamed = []
    for index in range(_safe(parent.get_child_count, 0)):
        child = _safe(lambda i=index: parent.get_child_at_index(i), None)
        if child is not None and _safe(child.get_role_name) == "button" and not _safe(child.get_name).strip():
            unnamed.append(_safe(child.get_index_in_parent, -2))
    if own in unnamed and unnamed.index(own) < len(DRAWER_LABELS):
        return DRAWER_LABELS[unnamed.index(own)]
    return ""


def _left_edge(node):
    coord = None
    try:
        import gi  # pylint: disable=import-outside-toplevel

        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi  # pylint: disable=import-outside-toplevel

        coord = Atspi.CoordType.SCREEN
    except (ImportError, ValueError):
        pass  # Only happens outside Orca (unit tests with fake nodes).
    try:
        return node.get_extents(coord).x
    except Exception:  # pylint: disable=broad-exception-caught
        return None


def search_icon_label(node) -> str:
    """Label for the magnifier button at the left of a Search field.

    In the emoji/sticker/GIF panel it sits in a one-child wrapper next to a
    text field named Search (verified live: clicking it focuses that field).
    Matched by being left of the field, so the buttons to its right are not
    mislabeled.
    """

    if _safe(node.get_role_name) != "button":
        return ""
    wrapper = _safe(node.get_parent, None)
    row = _safe(wrapper.get_parent, None) if wrapper is not None else None
    if row is None or _safe(wrapper.get_child_count, 0) != 1:
        return ""
    own_x = _left_edge(node)
    for index in range(_safe(row.get_child_count, 0)):
        sibling = _safe(lambda i=index: row.get_child_at_index(i), None)
        if (
            sibling is not None
            and _safe(sibling.get_role_name) == "text"
            and _safe(sibling.get_name) == "Search"
        ):
            field_x = _left_edge(sibling)
            if own_x is not None and field_x is not None and own_x < field_x:
                return "Search icon"
    return ""


def infer_label(node, user_labels: dict[str, str] | None = None) -> tuple[str, str]:
    """Returns (label, source) for an unnamed control.

    Order: user table, description/child text, then a generic fallback that at
    least says there is a button and where it is.
    """

    sig = signature(node)
    table = load_user_labels() if user_labels is None else user_labels
    if sig in table:
        return table[sig], "user"
    known = drawer_label(node)
    if known:
        return known, "builtin"
    known = search_icon_label(node)
    if known:
        return known, "builtin"
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
