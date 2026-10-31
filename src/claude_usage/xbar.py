"""Text output for SwiftBar (macOS) and Argos (GNOME), both BitBar-compatible."""
from __future__ import annotations

from typing import List

from .view import LANGUAGE, OPEN, QUIT, REFRESH, UPDATE, Menu, MenuItem

SWIFTBAR, ARGOS = "swiftbar", "argos"
CLI_FLAGS = {REFRESH: "--force", UPDATE: "--update"}


class XbarRenderer:
    """Renders a Menu as BitBar plugin output.

    self_path is the plugin file, which the menu runs again for its refresh and update items.
    """

    def __init__(self, self_path: str, flavor: str = SWIFTBAR):
        self._self_path = self_path
        self._flavor = flavor

    def render(self, menu: Menu) -> str:
        lines = [self.title(menu), "---"]
        for item in menu.items:
            if item.action and item.action.kind == QUIT:
                continue  # the host app has its own quit
            lines.append("---" if item.separator else self.item(item))
        return "\n".join(lines) + "\n"

    def title(self, menu: Menu) -> str:
        line = menu.title + " |"
        if menu.title_color:
            line += " color=" + menu.title_color
        if self._flavor == ARGOS:
            if menu.update_available:
                line += " iconName=software-update-available-symbolic"
            line += " dropdown=false"  # Argos repeats button lines in the menu otherwise
        elif menu.update_available:
            line += " sfimage=arrow.down.circle"
        return line

    def item(self, item: MenuItem) -> str:
        params: List[str] = []
        if item.color:
            params.append("color=" + item.color)
        if item.size:
            params.append("size=%d" % item.size)
        a = item.action
        if a and a.kind == OPEN:
            params.append("href=" + a.url)
        elif a and a.kind in CLI_FLAGS:
            params.append('bash="%s" param1=%s terminal=false refresh=true'
                          % (self._self_path, CLI_FLAGS[a.kind]))
        elif a and a.kind == LANGUAGE:
            params.append('bash="%s" param1=--lang param2=%s terminal=false refresh=true'
                          % (self._self_path, a.value))
        text = item.text.replace("|", "/")
        return text + (" | " + " ".join(params) if params else "")
