"""Find setup-tokens and Claude config dirs written in shell, PowerShell and cmd files."""
from __future__ import annotations

import os
import re
from typing import List, Optional, Tuple

TOKEN_RE = re.compile(r"sk-ant-oat\d+-[A-Za-z0-9_-]+")
TOKEN_VAR = "CLAUDE_CODE_OAUTH_TOKEN"
CONFIG_DIR_VAR = "CLAUDE_CONFIG_DIR"
# Value read from a file: bash `$(cat FILE)`, PowerShell `Get-Content FILE` / `gc FILE`.
CAT_RE = re.compile(r"\$\(\s*cat\s+([^)]+?)\s*\)")
GET_CONTENT_RE = re.compile(r"\b(?:Get-Content|gc)\s+(?:-Raw\s+)?(?:-Path\s+)?([\"']?)([^\"'\s;)]+)\1",
                            re.I)
# The name a line gives its command: bash alias, PowerShell function, cmd doskey macro.
NAME_RES = [
    re.compile(r"^\s*alias\s+([\w.-]+)="),
    re.compile(r"^\s*function\s+([\w.-]+)", re.I),
    re.compile(r"^\s*doskey\s+([\w.-]+)=", re.I),
]
COMMENT_PREFIXES = ("#", "::", "rem ", "REM ")
MAX_SCAN_BYTES = 256 * 1024


def expand_path(path: str, home: str) -> str:
    """Expand ~, $HOME, ${HOME}, $env:USERPROFILE and %USERPROFILE% against `home`."""
    path = path.strip().strip("'\"")
    for var in ("${HOME}", "$HOME", "$env:USERPROFILE", "$env:HOME", "%USERPROFILE%", "%HOME%"):
        path = path.replace(var, home)
    if path == "~" or path.startswith("~/") or path.startswith("~\\"):
        path = home + path[1:]
    return path


def token_in_text(text: Optional[str]) -> Optional[str]:
    m = TOKEN_RE.search(text or "")
    return m.group(0) if m else None


def read_token_file(path: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return token_in_text(f.read())
    except OSError:
        return None


class ShellScanner:
    """Reads tokens and config dirs from the text of a script or profile file."""

    def __init__(self, home: str):
        self.home = home

    def token_from_value(self, value: str) -> Optional[str]:
        """Resolve what follows CLAUDE_CODE_OAUTH_TOKEN on a line to a token."""
        token = token_in_text(value)
        if token:
            return token
        m = CAT_RE.search(value)
        if m:
            return read_token_file(expand_path(m.group(1), self.home))
        m = GET_CONTENT_RE.search(value)
        if m:
            return read_token_file(expand_path(m.group(2), self.home))
        return None

    def lines(self, path: str) -> List[str]:
        try:
            if os.path.getsize(path) > MAX_SCAN_BYTES:
                return []
            with open(path, encoding="utf-8", errors="ignore") as f:
                return [ln for ln in f.read().splitlines() if not ln.lstrip().startswith(COMMENT_PREFIXES)]
        except OSError:
            return []

    def tokens(self, path: str, default_label: str) -> List[Tuple[str, str]]:
        """(label, token) for every line that sets the token variable."""
        found = []
        for line in self.lines(path):
            i = line.find(TOKEN_VAR)
            if i < 0:
                continue
            # Keep the rest of the line: a $(cat ...) path may contain spaces.
            token = self.token_from_value(line[i + len(TOKEN_VAR):])
            if token:
                found.append((self.command_name(line) or default_label, token))
        return found

    def config_dirs(self, path: str) -> List[str]:
        """Directories assigned to CLAUDE_CONFIG_DIR, e.g. alias claude-work='CLAUDE_CONFIG_DIR=~/.claude-work claude'."""
        dirs = []
        for line in self.lines(path):
            for m in re.finditer(CONFIG_DIR_VAR + r"[\"']?\s*=\s*([\"']?)([^\"'\s;]+)\1", line):
                dirs.append(expand_path(m.group(2), self.home))
        return dirs

    @staticmethod
    def command_name(line: str) -> Optional[str]:
        for rx in NAME_RES:
            m = rx.match(line)
            if m:
                return m.group(1)
        return None
