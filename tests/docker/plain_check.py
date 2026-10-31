"""Plain (Argos/SwiftBar) mode of the bundle on Linux, with a fake ~/.claude/.credentials.json.

Run inside a Linux container: python3 plain_check.py BUNDLE. Needs tests/fakes.py next to this
file or on PYTHONPATH. Exits 1 on the first failed check.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

from fakes import FakeHome, FakeServer, Plan

HOUR, DAY = 3600, 86400
TOKEN = "fake-linux-access-token"
EMAIL = "linux.user@example.com"


def credentials(expires_at_ms: int) -> str:
    return json.dumps({"claudeAiOauth": {"accessToken": TOKEN, "refreshToken": "fake-refresh",
                                         "expiresAt": expires_at_ms, "scopes": ["user:inference"]}})


def run(bundle: str, home: FakeHome, server: FakeServer, **env: str) -> str:
    full_env = {"HOME": home.path, "PATH": os.environ.get("PATH", ""),
                "CLAUDE_USAGE_API": server.url, "CLAUDE_USAGE_GITHUB": server.url}
    full_env.update(env)
    out = subprocess.run([sys.executable, bundle], env=full_env, capture_output=True, text=True,
                         timeout=60)
    if out.returncode != 0 or "Traceback" in out.stderr:
        sys.exit("plugin failed (%d): %s" % (out.returncode, out.stderr))
    return out.stdout


def check(cond: bool, what: str, output: str) -> None:
    print(("[ok] " if cond else "[x] ") + what)
    if not cond:
        print(output)
        sys.exit(1)


def main() -> None:
    bundle = sys.argv[1]
    plans = {TOKEN: Plan({"5h": (0.13, 2 * HOUR), "7d": (0.08, 3 * DAY), "7d_oi": (0.01, 3 * DAY)},
                         email=EMAIL)}
    now_ms = int(time.time() * 1000)
    with FakeServer(plans) as server:
        with FakeHome() as home:
            home.write(".claude/.credentials.json", credentials(now_ms + 6 * HOUR * 1000), 0o600)
            out = run(bundle, home, server)
            print("--- plain output (valid login) ---\n" + out)
            check("claude - " + EMAIL in out, "row 'claude - %s'" % EMAIL, out)
            check(out.splitlines()[0].startswith("C 13/8/1"), "title shows 13/8/1", out)

            out = run(bundle, home, server, ARGOS_MENU_OPEN="false")
            print("--- Argos title line ---\n" + out.splitlines()[0])
            check(out.splitlines()[0].endswith("dropdown=false"), "Argos title ends with dropdown=false", out)

        with FakeHome() as home:
            home.write(".claude/.credentials.json", credentials(now_ms - HOUR * 1000), 0o600)
            out = run(bundle, home, server)
            print("--- plain output (expired login) ---\n" + out)
            check("C: claude" in out, "expired login still has its row", out)
            check("đăng nhập đã hết hạn" in out, "row shows 'đăng nhập đã hết hạn'", out)
    print("plain mode: all checks passed")


if __name__ == "__main__":
    main()
