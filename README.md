# Telegram Access (Orca extension)

An [Orca](https://orca.gnome.org) 51 user extension that makes Telegram Desktop (7.x, Qt) easier to use with a screen reader on Linux.

Telegram already exposes most of its interface through AT-SPI. This extension fills the gaps that remain:

- **Speaks incoming messages** in the open chat (polls the `Messages` list every 0.7 s; received messages only, not your own). By default only while Telegram is the active window, since Telegram sends a desktop notification otherwise. Automatic speech is cut at 500 characters (configurable); `Orca+Alt+R` reads the last one in full.
- **Tidies speech**: strips invisible direction marks, reads "Seen / Me" as "You, seen", and drops the spurious "read only" Orca announces for Telegram's text-field wrapper nodes (the message box and every Search field).
- **Labels unnamed buttons**: profile picture and account header in the main menu, and the search icon in the emoji/sticker/GIF panel. Other unnamed buttons are read as "Unlabeled, next to ..."; add your own in `~/.local/share/orca/telegram_access_labels.json` (`{signature: label}`).

| Key | Action |
| --- | --- |
| `Orca+Alt+T` | Turn automatic message speech on or off |
| `Orca+Alt+R` | Speak the most recent incoming message in full |
| `Orca+Alt+L` | Describe the focused control; unnamed ones are logged to `~/.local/state/orca-telegram-access/unlabeled.log` with the signature to use in the labels file |

Settings are under Orca's extension preferences.

## Install

```sh
mkdir -p ~/.local/share/orca/extensions
cp -r telegram_access ~/.local/share/orca/extensions/
orca --approve-extension telegram_access
```

Then restart Orca. Roll back with `orca --revoke-extension telegram_access` and delete the directory.

## Known limits

- Telegram draws some popups itself and does not expose them to AT-SPI at all: the chat (three-dot) menu, the bot command list behind the "Menu" button, and the emoji/sticker/GIF tabs and grid. This extension cannot label what is not in the accessibility tree.
- Built-in labels and the drawer detection match English Telegram names.
- Written and checked against Telegram Desktop 7.3.1 and Orca 51.0 on NixOS. Receiving a real message end to end with live speech has not been verified.

## Tests

```sh
python3 -I tests/test_logic.py      # pure logic, no Orca needed
```

`tests/orca_check.py` loads the extension with Orca's real extension loader against a fake accessibility tree; run it with a Python that can import Orca's modules.
