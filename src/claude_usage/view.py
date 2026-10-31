"""Menu model: what to show, independent of how a frontend draws it."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Set, Tuple

from .domain import AccountRow, Clock

REFRESH, UPDATE, OPEN, QUIT = "refresh", "update", "open", "quit"
GRAY, GREEN, ORANGE, RED = "gray", "#2e7d32", "orange", "red"


@dataclass(frozen=True)
class Action:
    kind: str       # REFRESH | UPDATE | OPEN | QUIT
    url: str = ""   # for OPEN


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
    base = re.sub(r"^claude[-_.]?", "", label, flags=re.I) or label
    s = base[:1].upper() or "?"
    n = 2
    while s in taken:
        s = base[:1].upper() + str(n)
        n += 1
    taken.add(s)
    return s


class Presenter:
    def __init__(self, clock: Clock, version: str, repo_url: str, warn: float, crit: float,
                 max_in_title: int):
        self._clock = clock
        self._version = version
        self._repo_url = repo_url
        self._warn = warn
        self._crit = crit
        self._max_in_title = max_in_title

    def color(self, pct: float) -> Optional[str]:
        return RED if pct >= self._crit else ORANGE if pct >= self._warn else None

    def time_left(self, epoch: int) -> str:
        """Time left until a reset, e.g. "sau 2 giờ 15 phút". Frontends redraw every
        minute, so the countdown stays current between probes."""
        mins = -(-(epoch - int(self._clock.now())) // 60)  # round up: never "0 phút" early
        if mins <= 0:
            return "ngay bây giờ"
        days, rest = divmod(mins, 1440)
        hours, mins = divmod(rest, 60)
        if days:
            parts = [(days, "ngày"), (hours, "giờ")]
        elif hours:
            parts = [(hours, "giờ"), (mins, "phút")]
        else:
            parts = [(mins, "phút")]
        return "sau " + " ".join("%d %s" % (n, u) for n, u in parts if n)

    def update_items(self, tag: Optional[str]) -> List[MenuItem]:
        if not tag:
            return []
        return [
            MenuItem("Có bản mới %s (đang dùng v%s)" % (tag, self._version), color=GREEN),
            MenuItem("Cập nhật ngay", action=Action(UPDATE)),
            MenuItem("Xem thay đổi", action=Action(OPEN, "%s/releases/tag/%s" % (self._repo_url, tag))),
            SEPARATOR,
        ]

    def present(self, rows: Sequence[AccountRow], new_tag: Optional[str]) -> Menu:
        """new_tag: the newer release to offer, or None."""
        update = self.update_items(new_tag)
        if not rows:
            return Menu("Claude ?", None, bool(new_tag), None, tuple(update + [
                MenuItem("Không tìm thấy tài khoản Claude Code nào"),
                MenuItem("Đăng nhập bằng `claude`, hoặc khai báo token trong ~/.config/claude-usage.conf",
                         size=11),
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
            MenuItem("Cập nhật mỗi 3 phút", color=GRAY, size=11),
            MenuItem("Thứ tự số: % giới hạn 5 giờ / tuần / Fable tuần", color=GRAY, size=11),
            MenuItem("Phiên bản v%s" % self._version, color=GRAY, size=11,
                     action=Action(OPEN, self._repo_url)),
            MenuItem("Ủng hộ tác giả", action=Action(OPEN, self._repo_url + "#support")),
            MenuItem("Làm mới ngay", action=Action(REFRESH)),
        ]
        return Menu(title, self.color(worst), bool(new_tag), worst if known else None, tuple(items))

    def account_items(self, r: AccountRow) -> List[MenuItem]:
        head = "%s: %s" % (r.short, r.label)
        if r.detail:
            head += " - " + r.detail
        items = [MenuItem(head, size=13)]
        u = r.usage
        if u is None:
            items.append(MenuItem("Không đọc được hạn mức", color=GRAY))
        else:
            for name, pct, reset in (("5 giờ", u.five_hour, u.five_hour_reset),
                                     ("Tuần", u.weekly, u.weekly_reset)):
                items.append(MenuItem("%s: %d%%  (reset %s)" % (name, round(pct), self.time_left(reset)),
                                      color=self.color(pct)))
            for m in u.models:
                text = "%s (tuần): %d%%" % (m.name, round(m.pct))
                if m.reset:
                    text += "  (reset %s)" % self.time_left(m.reset)
                items.append(MenuItem(text, color=self.color(m.pct)))
            if r.error:
                items.append(MenuItem("Số liệu cũ, lần cập nhật vừa rồi bị lỗi", color=GRAY, size=11))
        if r.error:
            items.append(MenuItem("Lỗi: %s" % r.error, color=GRAY, size=11))
        items.append(SEPARATOR)
        return items
