"""Menu model: what to show, independent of how a frontend draws it."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Set, Tuple

from .domain import AccountRow, Clock
from .i18n import EN, VI, Translator

REFRESH, UPDATE, OPEN, QUIT, LANGUAGE = "refresh", "update", "open", "quit", "language"
GRAY, GREEN, ORANGE, RED = "gray", "#2e7d32", "orange", "red"


@dataclass(frozen=True)
class Action:
    kind: str       # REFRESH | UPDATE | OPEN | QUIT | LANGUAGE
    url: str = ""   # for OPEN
    value: str = ""  # for LANGUAGE: the language to switch to


@dataclass(frozen=True)
class MenuItem:
    text: str = ""
    color: Optional[str] = None
    size: Optional[int] = None
    action: Optional[Action] = None
    separator: bool = False


SEPARATOR = MenuItem(separator=True)


@dataclass(frozen=True)
class Menu:
    title: str                    # e.g. "C 13/8/1  T 0/65/1"
    title_color: Optional[str]    # ORANGE / RED when a limit is close
    update_available: bool
    worst: Optional[float]        # highest known percentage, None when nothing is known
    items: Tuple[MenuItem, ...]


def short_name(label: str, taken: Set[str]) -> str:
    """One letter per account (C, T, W...), with a digit when letters collide."""
    # "claude-token" -> T, "claude (work)" -> W; plain "claude" keeps its C.
    base = re.sub(r"^claude[\s(_.-]*", "", label, flags=re.I) or label
    s = base[:1].upper() or "?"
    n = 2
    while s in taken:
        s = base[:1].upper() + str(n)
        n += 1
    taken.add(s)
    return s


class Presenter:
    def __init__(self, clock: Clock, tr: Translator, version: str, repo_url: str, warn: float,
                 crit: float, max_in_title: int, show_support: bool = False):
        self._clock = clock
        self._show_support = show_support
        self._tr = tr
        self._version = version
        self._repo_url = repo_url
        self._warn = warn
        self._crit = crit
        self._max_in_title = max_in_title

    def color(self, pct: float) -> Optional[str]:
        return RED if pct >= self._crit else ORANGE if pct >= self._warn else None

    def time_left(self, epoch: int) -> str:
        """Time left until a reset, e.g. "sau 2 giờ 15 phút" / "in 2h 15m". Frontends redraw
        every minute, so the countdown stays current between probes."""
        tr = self._tr
        mins = -(-(epoch - int(self._clock.now())) // 60)  # round up: never "0 minutes" early
        if mins <= 0:
            return tr("left_now")
        days, rest = divmod(mins, 1440)
        hours, mins = divmod(rest, 60)
        if days:
            parts = [(days, "unit_day"), (hours, "unit_hour")]
        elif hours:
            parts = [(hours, "unit_hour"), (mins, "unit_minute")]
        else:
            parts = [(mins, "unit_minute")]
        return tr("left_prefix") + " ".join(tr(unit, n=n) for n, unit in parts if n)

    def update_items(self, tag: Optional[str]) -> List[MenuItem]:
        if not tag:
            return []
        tr = self._tr
        return [
            MenuItem(tr("update_available", tag=tag, version=self._version), color=GREEN),
            MenuItem(tr("update_now"), action=Action(UPDATE)),
            MenuItem(tr("view_changes"), action=Action(OPEN, "%s/releases/tag/%s" % (self._repo_url, tag))),
            SEPARATOR,
        ]

    def language_item(self) -> MenuItem:
        """Switches to the other language. Written in the target language, so a user who
        cannot read the current one still finds it."""
        target = EN if self._tr.lang == VI else VI
        return MenuItem(Translator(target)("switch_language"), action=Action(LANGUAGE, value=target))

    def present(self, rows: Sequence[AccountRow], new_tag: Optional[str]) -> Menu:
        """new_tag: the newer release to offer, or None."""
        tr = self._tr
        update = self.update_items(new_tag)
        if not rows:
            return Menu("Claude ?", None, bool(new_tag), None, tuple(update + [
                MenuItem(tr("no_accounts")),
                MenuItem(tr("no_accounts_hint"), size=11),
                SEPARATOR,
                self.language_item(),
            ]))

        known = [r.usage for r in rows if r.usage]
        worst = max([max(u.percentages()) for u in known] or [0])
        if len(rows) <= self._max_in_title:
            title = "  ".join(
                "%s %s" % (r.short, "/".join("%d" % round(x) for x in r.usage.percentages()))
                if r.usage else r.short + " ?"
                for r in rows)
        else:
            title = "Claude %d%%" % round(worst)

        items = list(update)
        for r in rows:
            items += self.account_items(r)
        items += [
            MenuItem(tr("refresh_every"), color=GRAY, size=11),
            MenuItem(tr("number_order"), color=GRAY, size=11),
            MenuItem(tr("version", version=self._version), color=GRAY, size=11,
                     action=Action(OPEN, self._repo_url)),
        ]
        if self._show_support:
            items.append(MenuItem(tr("support"), action=Action(OPEN, self._repo_url + "#support")))
        items += [
            self.language_item(),
            MenuItem(tr("refresh_now"), action=Action(REFRESH)),
        ]
        return Menu(title, self.color(worst), bool(new_tag), worst if known else None, tuple(items))

    def account_items(self, r: AccountRow) -> List[MenuItem]:
        head = "%s: %s" % (r.short, r.label)
        if r.detail:
            head += " - " + r.detail
        tr = self._tr
        items = [MenuItem(head, size=13)]
        u = r.usage
        if u is None:
            items.append(MenuItem(tr("usage_unreadable"), color=GRAY))
        else:
            for key, pct, reset in (("five_hour", u.five_hour, u.five_hour_reset),
                                    ("weekly", u.weekly, u.weekly_reset)):
                items.append(MenuItem(tr("usage_line", name=tr(key), pct="%d" % round(pct),
                                         left=self.time_left(reset)), color=self.color(pct)))
            for m in u.models:
                text = tr("model_line", name=tr("model_weekly", name=m.name), pct="%d" % round(m.pct))
                if m.reset:
                    text += tr("reset_suffix", left=self.time_left(m.reset))
                items.append(MenuItem(text, color=self.color(m.pct)))
            if r.error:
                items.append(MenuItem(tr("stale_data"), color=GRAY, size=11))
        if r.error:
            items.append(MenuItem(tr("error_line", error=r.error), color=GRAY, size=11))
        items.append(SEPARATOR)
        return items
