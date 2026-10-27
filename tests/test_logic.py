# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Devin Prater
import os
import sys
import unittest

import importlib.util

PKG = os.path.join(os.path.dirname(__file__), "..", "telegram_access")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(PKG, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Load the pure modules directly so the package __init__ (which needs Orca) is not run.
messages = _load("messages")
labels = _load("labels")

INCOMING = ("Sarah Cat\nIn reply to Devin Prater: ‎⁨/new⁩\n"
            "✨ Session reset! Starting fresh.\n\n◆ Model: x\nReceived at 8:19 AM")
OUTGOING = "Seen\nMe\n/new\nSent at 8:19 AM"
UNSEEN = "Me\nhello there\nSent at 8:20 AM"
PLAIN = "Sarah Cat\nPR is live.\nReceived at 9:01 AM"


class Parse(unittest.TestCase):
    def test_incoming_with_reply(self):
        m = messages.parse_message(INCOMING)
        self.assertEqual((m.sender, m.reply_to), ("Sarah Cat", "Devin Prater"))
        self.assertTrue(messages.is_incoming(m))
        self.assertTrue(m.body.startswith("✨ Session reset! Starting fresh. ◆ Model"))
        self.assertEqual(m.stamp, "Received at 8:19 AM")

    def test_outgoing(self):
        for name in (OUTGOING, UNSEEN):
            m = messages.parse_message(name)
            self.assertTrue(m.outgoing)
            self.assertFalse(messages.is_incoming(m))
        self.assertTrue(messages.parse_message(OUTGOING).seen)

    def test_service_message_not_incoming(self):
        self.assertFalse(messages.is_incoming(messages.parse_message("Today", False)))

    def test_announcement(self):
        self.assertEqual(messages.announcement(messages.parse_message(PLAIN)), "Sarah Cat: PR is live.")
        self.assertIn("replying to Devin Prater", messages.announcement(messages.parse_message(INCOMING)))

    def test_truncation(self):
        long = "Sarah Cat\n" + "word " * 300 + "\nReceived at 1:00 PM"
        text = messages.announcement(messages.parse_message(long), 100)
        self.assertLess(len(text), 160)
        self.assertIn("more characters", text)
        self.assertGreater(len(messages.announcement(messages.parse_message(long), 0)), 1000)

    def test_channel_post_without_sender(self):
        m = messages.parse_message("Big news today\nReceived at 2:00 PM", has_sender=False)
        self.assertEqual(m.sender, "")
        self.assertEqual(messages.announcement(m), "Big news today")

    def test_navigation_text(self):
        self.assertEqual(messages.navigation_text(OUTGOING), "You, seen: /new. Sent at 8:19 AM")
        self.assertEqual(messages.navigation_text(PLAIN), "Sarah Cat: PR is live.. Received at 9:01 AM".replace("..", "."))

    def test_clean(self):
        self.assertEqual(messages.clean("‎⁨Sarah⁩ – (3)"), "Sarah – (3)")
        self.assertTrue(messages.has_invisible("⁨x"))
        self.assertFalse(messages.has_invisible("x"))


class Diff(unittest.TestCase):
    def test_no_change(self):
        self.assertEqual(messages.new_items("c", ["a", "b", "c"]), [])

    def test_appended(self):
        self.assertEqual(messages.new_items("b", ["a", "b", "c", "d"]), ["c", "d"])

    def test_baseline_cases(self):
        self.assertIsNone(messages.new_items(None, ["a"]))
        self.assertIsNone(messages.new_items("zzz", ["a", "b"]))  # chat switched
        self.assertIsNone(messages.new_items("x", []))

    def test_old_history_loaded_above_is_not_new(self):
        self.assertEqual(messages.new_items("c", ["o1", "o2", "a", "b", "c"]), [])

    def test_lookback_limit(self):
        names = [str(i) for i in range(100)]
        self.assertEqual(messages.new_items("98", names), ["99"])
        self.assertIsNone(messages.new_items("2", names))


class Node:
    def __init__(self, role, name="", description="", children=()):
        self.role, self.name, self.description, self.kids = role, name, description, list(children)
        self.parent = None
        self.index = 0
        for i, kid in enumerate(self.kids):
            kid.parent, kid.index = self, i

    def get_role_name(self): return self.role
    def get_name(self): return self.name
    def get_description(self): return self.description
    def get_child_count(self): return len(self.kids)
    def get_child_at_index(self, i): return self.kids[i]
    def get_parent(self): return self.parent
    def get_index_in_parent(self): return self.index


class Labels(unittest.TestCase):
    def panel(self):
        target = Node("button")
        panel = Node("filler", children=[Node("text", "Search"), target, Node("button")])
        return target, panel

    def test_fallback_mentions_neighbor(self):
        target, _ = self.panel()
        self.assertEqual(labels.infer_label(target, {}), ("Unlabeled, next to Search", "fallback"))

    def test_user_table_wins_and_is_position_specific(self):
        target, panel = self.panel()
        sig = labels.signature(target)
        self.assertEqual(labels.infer_label(target, {sig: "Clear search"}), ("Clear search", "user"))
        self.assertNotEqual(sig, labels.signature(panel.kids[2]))

    def test_child_text_and_description(self):
        self.assertEqual(labels.infer_label(Node("button", children=[Node("label", "Send")]), {})[0], "Send")
        self.assertEqual(labels.infer_label(Node("button", description="Attach"), {})[0], "Attach")

    def test_main_menu_drawer(self):
        pic, header = Node("button"), Node("button")
        premium = Node("button", "Telegram Premium")
        rows = Node("filler", children=[Node("button", "My Profile"), Node("button", "New Group")])
        drawer = Node("filler", children=[pic, header, Node("label", "Set Emoji Status"), premium,
                                          Node("filler", children=[rows])])
        self.assertEqual(labels.infer_label(pic, {}), ("Profile picture", "builtin"))
        self.assertEqual(labels.infer_label(header, {})[0], "Account, show or hide other accounts")
        # Not in the drawer: unchanged fallback.
        other = Node("button")
        Node("filler", children=[Node("text", "Search"), other])
        self.assertEqual(labels.infer_label(other, {})[1], "fallback")

    def test_search_icon_in_emoji_panel(self):
        class Ext:
            def __init__(self, x): self.x = x

        def at(node, x):
            node.get_extents = lambda _coord, x=x: Ext(x)
            return node

        icon = at(Node("button"), 1014)
        field = at(Node("text", "Search"), 1047)
        clear = at(Node("button"), 1300)
        Node("filler", children=[Node("filler"), field, Node("filler"),
                                 Node("filler", children=[icon]), Node("filler", children=[clear])])
        self.assertEqual(labels.infer_label(icon, {}), ("Search icon", "builtin"))
        # Right of the field, or without geometry: not claimed.
        self.assertEqual(labels.infer_label(clear, {})[1], "fallback")

    def test_no_context(self):
        self.assertEqual(labels.infer_label(Node("button"), {})[0], "Unlabeled")


if __name__ == "__main__":
    unittest.main()
