"""Long-running tray frontend (Windows, Linux desktops without Argos).

TrayController owns the behaviour (when to refresh, what each action does); a TrayBackend only
draws a Menu and reports clicks, so each OS needs nothing but a small backend.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import webbrowser
from abc import ABC, abstractmethod
from typing import Callable, List, Optional, Sequence

from .view import OPEN, QUIT, REFRESH, UPDATE, Action, Menu, MenuItem, SEPARATOR

TRAY_REFRESH_SECONDS = 60
QUIT_ITEM = MenuItem("Thoát", action=Action(QUIT))


class TrayBackend(ABC):
    """A native tray icon. All methods except call_soon are called on the UI thread."""

    @abstractmethod
    def run(self, on_start: Callable[[], None]) -> None:
        """Create the icon, call on_start on the UI thread, then block in the UI loop."""

    @abstractmethod
    def show(self, menu: Menu) -> None:
        """Replace the icon text/tooltip and the menu. Clicking an item with an action must
        call the handler given to set_action_handler with that Action."""

    @abstractmethod
    def set_action_handler(self, handler: Callable[[Action], None]) -> None: ...

    @abstractmethod
    def call_soon(self, fn: Callable[[], None]) -> None:
        """Run fn on the UI thread. Safe to call from any thread."""

    @abstractmethod
    def every(self, seconds: int, fn: Callable[[], None]) -> None:
        """Call fn on the UI thread every `seconds`."""

    @abstractmethod
    def quit(self) -> None: ...


class TrayController:
    """Refreshes the tray every minute and runs menu actions.

    Network work happens on a worker thread; results go back to the UI thread through
    backend.call_soon, so a slow probe never freezes the icon.
    """

    def __init__(self, backend: TrayBackend, build_menu: Callable[[bool], Menu],
                 refresh: Callable[[], None], update: Callable[[], bool],
                 restart: Callable[[], None], open_url: Callable[[str], object] = webbrowser.open,
                 spawn: Callable[[Callable[[], None]], None] = None):
        self._backend = backend
        self._build_menu = build_menu
        self._refresh = refresh
        self._update = update
        self._restart = restart
        self._open_url = open_url
        self._spawn = spawn or _start_daemon_thread
        self._busy = threading.Lock()

    def run(self) -> None:
        self._backend.set_action_handler(self.on_action)
        self._backend.run(self.start)

    def start(self) -> None:
        self._backend.show(loading_menu())
        self._backend.every(TRAY_REFRESH_SECONDS, self.reload)
        self.reload()

    def reload(self, force: bool = False) -> None:
        """Rebuild the menu in the background; skip if a rebuild is already running."""
        if not self._busy.acquire(blocking=False):
            return

        def work():
            try:
                if force:
                    self._refresh()
                menu = with_quit(self._build_menu(False))
            except Exception as e:  # keep the icon alive whatever happens
                menu = error_menu(e)
            finally:
                self._busy.release()
            self._backend.call_soon(lambda: self._backend.show(menu))

        self._spawn(work)

    def on_action(self, action: Action) -> None:
        if action.kind == REFRESH:
            self.reload(force=True)
        elif action.kind == OPEN:
            self._open_url(action.url)
        elif action.kind == UPDATE:
            self._spawn(self._do_update)
        elif action.kind == QUIT:
            self._backend.quit()

    def _do_update(self) -> None:
        try:
            replaced = self._update()
        except Exception as e:
            self._backend.call_soon(lambda: self._backend.show(error_menu(e)))
            return
        if replaced:
            self._backend.call_soon(self._restart_now)
        else:
            self.reload()

    def _restart_now(self) -> None:
        self._restart()
        self._backend.quit()


def _start_daemon_thread(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, daemon=True).start()


def with_quit(menu: Menu) -> Menu:
    return Menu(menu.title, menu.title_color, menu.update_available, menu.worst,
                menu.items + (SEPARATOR, QUIT_ITEM))


def loading_menu() -> Menu:
    return Menu("Claude ...", None, False, None, (MenuItem("Đang đọc hạn mức..."), SEPARATOR, QUIT_ITEM))


def error_menu(e: Exception) -> Menu:
    return Menu("Claude ?", None, False, None, (
        MenuItem("Lỗi: %s: %s" % (type(e).__name__, str(e)[:160]), color="gray"),
        MenuItem("Làm mới ngay", action=Action(REFRESH)),
        SEPARATOR, QUIT_ITEM))


def relaunch_command(argv: Sequence[str], executable: str) -> List[str]:
    """The command that starts this tray again, e.g. after a self-update."""
    return [executable, os.path.realpath(argv[0])] + list(argv[1:])


def relaunch(argv: Optional[Sequence[str]] = None, executable: Optional[str] = None) -> None:
    cmd = relaunch_command(argv or sys.argv, executable or sys.executable)
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, close_fds=True, **kwargs)
