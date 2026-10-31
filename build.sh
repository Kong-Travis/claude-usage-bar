#!/bin/bash
# Build dist/claude-usage-install.command (installer with the plugin embedded)
# and dist/Claude-Usage.dmg (that installer wrapped in a disk image).
set -euo pipefail
cd "$(dirname "$0")"

PLUGIN=plugin/claude-usage.1m.py
TEMPLATE=installer/install.tmpl.sh
DIST=dist
CMD="$DIST/claude-usage-install.command"
DMG="$DIST/Claude-Usage.dmg"
DMG_ENTRY="Cài đặt Claude Usage.command"

rm -rf "$DIST" && mkdir -p "$DIST/dmg"

/usr/bin/python3 tools/bundle.py

/usr/bin/python3 - "$TEMPLATE" "$PLUGIN" "$CMD" <<'EOF'
import sys
tmpl, plugin, out = sys.argv[1:]
t = open(tmpl).read()
p = open(plugin).read().rstrip("\n")
assert t.count("__PLUGIN__") == 1, "template needs exactly one __PLUGIN__ marker"
assert "PLUGIN_EOF" not in p, "plugin must not contain the heredoc delimiter"
open(out, "w").write(t.replace("__PLUGIN__", p))
EOF
chmod +x "$CMD"
bash -n "$CMD"

# The embedded copy must match the plugin source byte for byte.
awk '/<<.PLUGIN_EOF./{f=1;next}/^PLUGIN_EOF$/{f=0}f' "$CMD" | diff -q - "$PLUGIN" >/dev/null

cp "$CMD" "$DIST/dmg/$DMG_ENTRY"
hdiutil create -quiet -volname "Claude Usage" -srcfolder "$DIST/dmg" -fs HFS+ -format UDZO "$DMG"
rm -rf "$DIST/dmg"

echo "Built:"
ls -lh "$CMD" "$DMG"
