"""Telegram Desktop accessibility for Orca.

Speaks incoming messages in the open chat, cleans up how messages are read,
and supplies labels for controls Telegram leaves unnamed.
"""

from __future__ import annotations

import os
import time

import gi

gi.require_version("Atspi", "2.0")
# pylint: disable=wrong-import-position
from gi.repository import Atspi, GLib

from orca import debug, keybindings
from orca.command import Command, KeyboardCommand
from orca.extension import Extension, ExtensionPreference, SpeechOutputResult

from . import labels, messages

APP_NAME = "TelegramDesktop"
POLL_MS = 700
REDISCOVER_SECONDS = 4.0
BUTTON_ROLES = {"button", "push button", "toggle button"}
STATE_DIR = os.path.expanduser("~/.local/state/orca-telegram-access")

SETTING_ANNOUNCE = "announce-incoming"
SETTING_WHEN = "announce-when"
SETTING_MAX_CHARS = "max-characters"
SETTING_CLEAN = "clean-message-speech"
SETTING_LABELS = "label-unnamed-controls"


def _log(*tokens: object) -> None:
    debug.print_tokens(debug.LEVEL_INFO, ["TELEGRAM ACCESS:", *tokens], True)


def _is_telegram(obj) -> bool:
    try:
        return obj.get_application().get_name() == APP_NAME
    except Exception:  # pylint: disable=broad-exception-caught
        return False


class TelegramAccess(Extension):
    """Makes Telegram Desktop easier to use with Orca."""

    GROUP_LABEL = "Telegram Access"
    DESCRIPTION = (
        "Speaks incoming Telegram Desktop messages, tidies how messages are "
        "read, and labels unnamed controls."
    )
    VERSION = "1.0.0"

    def __init__(self) -> None:
        super().__init__()
        self._timer = 0
        self._list = None
        self._last_name: str | None = None
        self._last_discovery = 0.0
        self._last_incoming = ""
        self._session_muted = False

    # -- lifecycle -------------------------------------------------------

    def on_ready(self) -> None:
        self._start()

    def on_enabled(self) -> None:
        self._start()

    def on_disabled(self) -> None:
        self._stop()

    def on_shutdown(self) -> None:
        self._stop()

    def _start(self) -> None:
        if not self._timer:
            self._timer = GLib.timeout_add(POLL_MS, self._poll)

    def _stop(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0
        self._list = None
        self._last_name = None

    # -- settings --------------------------------------------------------

    def get_preferences(self) -> list[ExtensionPreference]:
        return [
            ExtensionPreference.boolean(
                SETTING_ANNOUNCE, "Speak incoming messages in the open chat", True
            ),
            ExtensionPreference.enum(
                SETTING_WHEN,
                "Speak incoming messages",
                (
                    ("active", "only while Telegram is the active window"),
                    ("always", "even when Telegram is in the background"),
                ),
                "active",
            ),
            ExtensionPreference.integer(
                SETTING_MAX_CHARS,
                "Longest message to speak automatically, in characters (0 = no limit)",
                messages.DEFAULT_MAX_CHARS,
                0,
                20000,
            ),
            ExtensionPreference.boolean(
                SETTING_CLEAN, "Tidy how Telegram messages and chats are read", True
            ),
            ExtensionPreference.boolean(
                SETTING_LABELS, "Say something useful for Telegram buttons without a name", True
            ),
        ]

    def _get(self, key: str, default):
        return self.settings.get(key, default)

    # -- commands --------------------------------------------------------

    def _get_commands(self) -> list[Command]:
        def command(name, function, description, key):
            binding = keybindings.KeyBinding(key, keybindings.ORCA_ALT_MODIFIER_MASK)
            return KeyboardCommand(
                name,
                function,
                self.GROUP_LABEL,
                description,
                desktop_keybinding=binding,
                laptop_keybinding=binding,
            )

        return [
            command(
                "telegram_access_toggle",
                self.toggle_announcements,
                "Turns automatic speaking of incoming Telegram messages on or off.",
                "t",
            ),
            command(
                "telegram_access_repeat",
                self.repeat_last_message,
                "Speaks the most recent incoming Telegram message in full.",
                "r",
            ),
            command(
                "telegram_access_describe",
                self.describe_current_control,
                "Describes the focused Telegram control and records it if it has no name.",
                "l",
            ),
        ]

    def toggle_announcements(self) -> bool:
        self._session_muted = not self._session_muted
        self.controller.present_message_internal(
            "Telegram messages off" if self._session_muted else "Telegram messages on"
        )
        return True

    def repeat_last_message(self) -> bool:
        text = self._last_incoming or "No Telegram message received yet"
        self.controller.present_message_internal(text)
        return True

    def describe_current_control(self) -> bool:
        obj = self.controller.get_current_object_internal()
        if obj is None or not _is_telegram(obj):
            self.controller.present_message_internal("Not in Telegram")
            return True
        name = (obj.get_name() or "").strip()
        if name:
            self.controller.present_message_internal(messages.clean(name))
            return True
        label, source = labels.infer_label(obj)
        sig = labels.signature(obj)
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(os.path.join(STATE_DIR, "unlabeled.log"), "a", encoding="utf-8") as out:
                out.write(f"{time.strftime('%F %T')}\t{obj.get_role_name()}\t{label}\t{sig}\n")
        except OSError:
            pass
        self.controller.present_message_internal(f"{label}. Recorded for labeling.")
        return True

    # -- speech hook -----------------------------------------------------

    def on_speech_output(self, output):
        obj = getattr(output, "obj", None)
        text = getattr(output, "text", "")
        if obj is None or not isinstance(text, str) or not text:
            return None
        wants_labels = self._get(SETTING_LABELS, True) and text.strip().lower() in labels.GENERIC_BUTTON_TEXT
        wants_clean = self._get(SETTING_CLEAN, True) and (
            messages.has_invisible(text) or "Received at" in text or "Sent at" in text
        )
        if not (wants_labels or wants_clean) or not _is_telegram(obj):
            return None
        try:
            if wants_labels:
                return self._label_result(obj, text)
            return self._clean_result(obj, text)
        except Exception as error:  # pylint: disable=broad-exception-caught
            _log("speech hook failed:", error)
            return None

    def _label_result(self, obj, text):
        if obj.get_role_name() not in BUTTON_ROLES or (obj.get_name() or "").strip():
            return None
        label, _source = labels.infer_label(obj)
        return SpeechOutputResult.replace(f"{label}, {text}")

    def _clean_result(self, obj, text):
        name = obj.get_name() or ""
        if name and name in text and "\n" in name:
            parent = obj.get_parent()
            if parent is not None and parent.get_name() == "Messages":
                cells = [
                    obj.get_child_at_index(i).get_name()
                    for i in range(obj.get_child_count())
                ]
                replacement = messages.navigation_text(name, "Sender" in cells or not cells)
                return SpeechOutputResult.replace(text.replace(name, replacement))
        return SpeechOutputResult.replace(messages.clean(text))

    # -- incoming message monitor ---------------------------------------

    def _find_app(self):
        desktop = Atspi.get_desktop(0)
        for index in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(index)
            if app is not None and app.get_name() == APP_NAME:
                return app
        return None

    def _find_list(self, node, depth: int = 0):
        """Depth-first search for the Messages list, skipping list contents."""

        if depth > 16:
            return None
        for index in range(node.get_child_count()):
            child = node.get_child_at_index(index)
            if child is None:
                continue
            role = child.get_role_name()
            if role == "list":
                if child.get_name() == "Messages":
                    return child
                continue
            if role in ("list item", "table cell", "menu", "popup menu", "menu bar"):
                continue
            found = self._find_list(child, depth + 1)
            if found is not None:
                return found
        return None

    def _locate_list(self):
        if self._list is not None:
            try:
                if self._list.get_name() == "Messages":
                    return self._list
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            self._list = None
            self._last_name = None
        now = time.monotonic()
        if now - self._last_discovery < REDISCOVER_SECONDS:
            return None
        self._last_discovery = now
        app = self._find_app()
        if app is not None:
            self._list = self._find_list(app)
        return self._list

    def _window_is_active(self) -> bool:
        node = self._list
        try:
            while node is not None:
                parent = node.get_parent()
                if parent is None or parent.get_role_name() == "application":
                    return node.get_state_set().contains(Atspi.StateType.ACTIVE)
                node = parent
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        return False

    def _poll(self) -> bool:
        try:
            self._check()
        except Exception as error:  # pylint: disable=broad-exception-caught
            _log("poll failed:", error)
            self._list = None
        return True

    def _check(self) -> None:
        message_list = self._locate_list()
        if message_list is None:
            return
        count = message_list.get_child_count()
        if count == 0:
            self._last_name = None
            return
        last = message_list.get_child_at_index(count - 1)
        last_name = last.get_name() if last is not None else ""
        if self._last_name is None:
            self._last_name = last_name
            return
        if last_name == self._last_name:
            return
        start = max(0, count - messages.LOOKBACK - 1)
        names = [
            (message_list.get_child_at_index(i).get_name() or "") for i in range(start, count)
        ]
        added = messages.new_items(self._last_name, names)
        self._last_name = last_name
        if not added:
            return
        for offset, name in enumerate(added):
            item = message_list.get_child_at_index(count - len(added) + offset)
            self._announce(item, name)

    def _announce(self, item, name: str) -> None:
        cells = []
        try:
            cells = [item.get_child_at_index(i).get_name() for i in range(item.get_child_count())]
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        message = messages.parse_message(name, "Sender" in cells or not cells)
        if not messages.is_incoming(message):
            return
        self._last_incoming = messages.announcement(message, 0)
        if self._session_muted or not self._get(SETTING_ANNOUNCE, True):
            return
        if self._get(SETTING_WHEN, "active") == "active" and not self._window_is_active():
            return
        limit = int(self._get(SETTING_MAX_CHARS, messages.DEFAULT_MAX_CHARS))
        self.controller.present_message_internal(messages.announcement(message, limit))
