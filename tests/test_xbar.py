"""SwiftBar / Argos text output."""
import srcpath  # noqa: F401  (must come first)

import unittest

from claude_usage.view import (LANGUAGE, OPEN, QUIT, REFRESH, SEPARATOR, UPDATE, Action, Menu,
                               MenuItem)
from claude_usage.xbar import ARGOS, SWIFTBAR, XbarRenderer

SELF = "/opt/claude usage/plugin.py"


def menu(items=(), title="C 1/2/3", color=None, update=False):
    return Menu(title, color, update, None, tuple(items))


class Title(unittest.TestCase):
    def test_swiftbar_plain_color_and_update_icon(self):
        r = XbarRenderer(SELF, SWIFTBAR)
        self.assertEqual(r.title(menu()), "C 1/2/3 |")
        self.assertEqual(r.title(menu(color="orange")), "C 1/2/3 | color=orange")
        self.assertEqual(r.title(menu(color="red", update=True)),
                         "C 1/2/3 | color=red sfimage=arrow.down.circle")
        self.assertNotIn("dropdown", r.title(menu()))

    def test_argos_uses_icon_name_and_hides_the_dropdown_line(self):
        r = XbarRenderer(SELF, ARGOS)
        self.assertEqual(r.title(menu()), "C 1/2/3 | dropdown=false")
        self.assertEqual(r.title(menu(color="red", update=True)),
                         "C 1/2/3 | color=red iconName=software-update-available-symbolic dropdown=false")
        self.assertNotIn("sfimage", r.title(menu(update=True)))

    def test_default_flavor_is_swiftbar(self):
        self.assertEqual(XbarRenderer(SELF).title(menu(update=True)),
                         "C 1/2/3 | sfimage=arrow.down.circle")


class Items(unittest.TestCase):
    def test_render_layout(self):
        out = XbarRenderer(SELF).render(menu([
            MenuItem("plain"),
            SEPARATOR,
            MenuItem("styled", color="gray", size=11),
        ]))
        self.assertEqual(out, "C 1/2/3 |\n---\nplain\n---\nstyled | color=gray size=11\n")

    def test_actions(self):
        r = XbarRenderer(SELF)
        self.assertEqual(r.item(MenuItem("Open", action=Action(OPEN, "https://x/y#z"))),
                         "Open | href=https://x/y#z")
        self.assertEqual(r.item(MenuItem("Refresh", action=Action(REFRESH))),
                         'Refresh | bash="%s" param1=--force terminal=false refresh=true' % SELF)
        self.assertEqual(r.item(MenuItem("Update", color="#2e7d32", action=Action(UPDATE))),
                         'Update | color=#2e7d32 bash="%s" param1=--update terminal=false refresh=true' % SELF)

    def test_language_action_runs_the_plugin_with_the_language(self):
        line = XbarRenderer(SELF).item(MenuItem("EN", action=Action(LANGUAGE, value="en")))
        self.assertEqual(line, 'EN | bash="%s" param1=--lang param2=en terminal=false refresh=true' % SELF)

    def test_quit_items_are_skipped(self):
        out = XbarRenderer(SELF).render(menu([MenuItem("a"), MenuItem("Quit", action=Action(QUIT)),
                                              MenuItem("b")]))
        self.assertEqual(out, "C 1/2/3 |\n---\na\nb\n")

    def test_pipe_in_text_is_replaced(self):
        line = XbarRenderer(SELF).item(MenuItem("Lỗi: a | b", color="gray", size=11))
        self.assertEqual(line, "Lỗi: a / b | color=gray size=11")
        self.assertEqual(line.count("|"), 1)


if __name__ == "__main__":
    unittest.main()
