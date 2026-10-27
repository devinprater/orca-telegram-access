# Telegram Access (Orca 51 extension)

Local extension for Telegram Desktop (7.x, Qt AT-SPI). Not upstreamed.

- Speaks incoming messages in the open chat (polls the `Messages` list every 0.7 s; only
  received messages, not your own). Default: only while Telegram is the active window,
  because Telegram sends a desktop notification otherwise. Long messages are cut at 500 characters.
- Cleans message/chat speech: strips invisible direction marks, "Seen / Me" becomes "You, seen".
- Unnamed buttons are read as "Unlabeled, next to <neighbor>" (or their child text/description),
  and a user table `~/.local/share/orca/telegram_access_labels.json` ({signature: label}) overrides.
- Orca+Alt+T toggle announcements, Orca+Alt+R read last incoming in full,
  Orca+Alt+L describe focused control and log unnamed ones to
  `~/.local/state/orca-telegram-access/unlabeled.log` (signature column = key for the label table).

Tests: `python3 -I tests/test_logic.py` (17, pure logic). Orca-facing checks run through
`~/Projects/orca-extension-check.py` (see notes).
