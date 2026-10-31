"""Fake Anthropic API for the tray check: one login token with 13/8/1 usage.
Usage: python3 fake_api.py URL_FILE SECONDS (writes the server URL to URL_FILE)."""
from __future__ import annotations

import sys
import time

from fakes import FakeServer, Plan

HOUR, DAY = 3600, 86400
plans = {"fake-linux-access-token": Plan(
    {"5h": (0.13, 2 * HOUR), "7d": (0.08, 3 * DAY), "7d_oi": (0.01, 3 * DAY)},
    email="linux.user@example.com")}
with FakeServer(plans) as server:
    with open(sys.argv[1], "w") as f:
        f.write(server.url)
    time.sleep(int(sys.argv[2]))
