"""Entry point. Without arguments it prints BitBar output (SwiftBar, Argos)."""
from __future__ import annotations

import sys
from typing import List, Optional

from .i18n import LANGUAGES, Translator, normalize_language
from .platform_setup import LINUX, WINDOWS, Host, build
from .sources import set_conf_value
from .tray import TrayBackend, TrayController, relaunch
from .xbar import ARGOS, SWIFTBAR, XbarRenderer

USAGE = """usage: claude-usage [--force | --update | --tray | --lang vi|en]
  (none)       print the menu for SwiftBar (macOS) or Argos (GNOME)
  --force      probe every account now, ignoring the cache
  --update     install the latest release over this file
  --tray       run as a tray icon (Windows, Linux desktops without Argos)
  --lang LANG  menu language: vi (default) or en"""


def tray_backend(os_name: str, tr: Translator) -> TrayBackend:
    if os_name == WINDOWS:
        from .tray_win32 import Win32TrayBackend
        return Win32TrayBackend(tr)
    if os_name == LINUX:
        from .tray_gtk import GtkTrayBackend
        return GtkTrayBackend(tr)
    raise SystemExit("--tray is for Windows and Linux; on macOS use SwiftBar")


def set_language(host: Host, lang: str) -> None:
    set_conf_value(host.conf_path, "language", lang)


def run_tray(host: Host) -> None:
    # Services are rebuilt on every refresh so edits to the conf file (language, tokens)
    # apply without restarting the tray.
    services = build(host)
    TrayController(
        backend=tray_backend(host.os_name, services.tr),
        build_menu=lambda force: build(host).app.menu(force=force),
        refresh=lambda: build(host).app.refresh(),
        update=services.updater.update,
        restart=relaunch,
        translator=lambda: build(host).tr,
        set_language=lambda lang: set_language(host, lang),
    ).run()


def print_menu(host: Host) -> None:
    flavor = ARGOS if "ARGOS_MENU_OPEN" in host.env else SWIFTBAR
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # the menu text is not ASCII
    sys.stdout.write(XbarRenderer(host.self_path, flavor).render(build(host).app.menu()))


def main(argv: Optional[List[str]] = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    host = Host.current()
    if args == ["--update"]:
        build(host).updater.update()
    elif args == ["--force"]:
        build(host).app.refresh()
    elif args == ["--tray"]:
        run_tray(host)
    elif len(args) == 2 and args[0] == "--lang" and normalize_language(args[1]) in LANGUAGES:
        set_language(host, normalize_language(args[1]))
    elif not args:
        print_menu(host)
    else:
        print(USAGE, file=sys.stderr)
        return 2
    return 0
