"""A minimal org.kde.StatusNotifierWatcher for tests: logs every tray item that registers and
prints its properties (Id, Title, IconName, Status, XAyatanaLabel) whenever they change.

Run on a session bus: python3 sni_watcher.py SECONDS. Needs PyGObject.
"""
from __future__ import annotations

import sys

from gi.repository import Gio, GLib

WATCHER_XML = """
<node>
  <interface name="org.kde.StatusNotifierWatcher">
    <method name="RegisterStatusNotifierItem"><arg name="service" type="s" direction="in"/></method>
    <method name="RegisterStatusNotifierHost"><arg name="service" type="s" direction="in"/></method>
    <property name="RegisteredStatusNotifierItems" type="as" access="read"/>
    <property name="IsStatusNotifierHostRegistered" type="b" access="read"/>
    <property name="ProtocolVersion" type="i" access="read"/>
    <signal name="StatusNotifierItemRegistered"><arg type="s"/></signal>
    <signal name="StatusNotifierItemUnregistered"><arg type="s"/></signal>
    <signal name="StatusNotifierHostRegistered"/>
  </interface>
</node>
"""
ITEM_PROPS = ("Id", "Title", "IconName", "Status", "XAyatanaLabel")

items = []          # (bus name, object path)
last_seen = {}      # item -> last printed properties


def log(text: str) -> None:
    print(text, flush=True)


def read_item(conn: Gio.DBusConnection, item) -> None:
    name, path = item
    props = {}
    for prop in ITEM_PROPS:
        try:
            reply = conn.call_sync(name, path, "org.freedesktop.DBus.Properties", "Get",
                                   GLib.Variant("(ss)", ("org.kde.StatusNotifierItem", prop)),
                                   GLib.VariantType("(v)"), Gio.DBusCallFlags.NONE, 2000, None)
            props[prop] = reply.unpack()[0]
        except GLib.Error as e:
            props[prop] = "<%s>" % e.message
    props["menu"] = read_menu(conn, name, path)
    if last_seen.get(item) != props:
        last_seen[item] = props
        log("ITEM %s%s %s" % (name, path, {k: v for k, v in props.items() if k != "menu"}))
        for line in props["menu"]:
            log("  MENU " + line)


def read_menu(conn: Gio.DBusConnection, name: str, path: str):
    """The item's dbusmenu as text lines: label, [off] when insensitive, --- for separators."""
    try:
        menu_path = conn.call_sync(name, path, "org.freedesktop.DBus.Properties", "Get",
                                   GLib.Variant("(ss)", ("org.kde.StatusNotifierItem", "Menu")),
                                   GLib.VariantType("(v)"), Gio.DBusCallFlags.NONE, 2000,
                                   None).unpack()[0]
        layout = conn.call_sync(name, menu_path, "com.canonical.dbusmenu", "GetLayout",
                                GLib.Variant("(iias)", (0, -1, [])), None,
                                Gio.DBusCallFlags.NONE, 2000, None).unpack()[1]
    except GLib.Error as e:
        return ["<%s>" % e.message]
    lines = []
    for _id, child_props, _children in layout[2]:
        if child_props.get("type") == "separator":
            lines.append("---")
        else:
            off = "" if child_props.get("enabled", True) else "  [off]"
            lines.append(child_props.get("label", "") + off)
    return lines


def on_call(conn, sender, path, iface, method, params, invocation):
    if method == "RegisterStatusNotifierItem":
        service = params.unpack()[0]
        item = (sender, service) if service.startswith("/") else (service, "/StatusNotifierItem")
        items.append(item)
        log("REGISTERED %s %s" % item)
        conn.emit_signal(None, "/StatusNotifierWatcher", "org.kde.StatusNotifierWatcher",
                         "StatusNotifierItemRegistered", GLib.Variant("(s)", ("%s%s" % item,)))
        GLib.timeout_add(500, lambda: (read_item(conn, item), False)[1])
    invocation.return_value(None)


def on_get(conn, sender, path, iface, prop):
    if prop == "RegisteredStatusNotifierItems":
        return GLib.Variant("as", ["%s%s" % i for i in items])
    if prop == "IsStatusNotifierHostRegistered":
        return GLib.Variant("b", True)
    return GLib.Variant("i", 0)


def on_bus(conn, name):
    node = Gio.DBusNodeInfo.new_for_xml(WATCHER_XML)
    conn.register_object("/StatusNotifierWatcher", node.interfaces[0], on_call, on_get, None)


def main() -> None:
    seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    loop = GLib.MainLoop()
    Gio.bus_own_name(Gio.BusType.SESSION, "org.kde.StatusNotifierWatcher",
                     Gio.BusNameOwnerFlags.NONE, on_bus,
                     lambda c, n: log("OWNED %s" % n), lambda c, n: log("LOST %s" % n))

    def poll():
        conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        for item in list(items):
            read_item(conn, item)
        return True

    GLib.timeout_add_seconds(2, poll)
    GLib.timeout_add_seconds(seconds, lambda: (loop.quit(), False)[1])
    loop.run()


if __name__ == "__main__":
    main()
