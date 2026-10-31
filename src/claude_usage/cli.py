"""Entry point. Without arguments it prints BitBar output (SwiftBar, Argos)."""
from __future__ import annotations

import sys
from typing import List, Optional

from .platform_setup import LINUX, WINDOWS, Host, build
from .tray import TrayBackend, TrayController, relaunch
from .xbar import ARGOS, SWIFTBAR, XbarRenderer

USAGE = """usage: claude-usage [--force | --update | --tray]
  (none)    print the menu for SwiftBar (macOS) or Argos (GNOME)
  --force   probe every account now, ignoring the cache
  --update  install the latest release over this file
  --tray    run as a tray icon (Windows, Linux desktops without Argos)"""


def tray_backend(os_name: str) -> TrayBackend:
    if os_name == WINDOWS:
        from .tray_win32 import Win32TrayBackend
        return Win32TrayBackend()
    if os_name == LINUX:
        from .tray_gtk import GtkTrayBackend
        return GtkTrayBackend()
    raise SystemExit("--tray is for Windows and Linux; on macOS use SwiftBar")


def main(argv: Optional[List[str]] = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    host = Host.current()
    services = build(host)
    if args == ["--update"]:
        services.updater.update()
    elif args == ["--force"]:
        services.app.refresh()
    elif args == ["--tray"]:
        TrayController(
            backend=tray_backend(host.os_name),
            build_menu=lambda force: services.app.menu(force=force),
            refresh=services.app.refresh,
            update=services.updater.update,
            restart=relaunch,
        ).run()
    elif not args:
        flavor = ARGOS if "ARGOS_MENU_OPEN" in host.env else SWIFTBAR
        sys.stdout.write(XbarRenderer(host.self_path, flavor).render(services.app.menu()))
    else:
        print(USAGE, file=sys.stderr)
        return 2
    return 0
