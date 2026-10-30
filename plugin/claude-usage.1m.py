#!/usr/bin/python3
# <xbar.title>Claude Code usage</xbar.title>
# <xbar.desc>5-hour and weekly plan usage for every Claude Code account on this Mac.</xbar.desc>
# <xbar.dependencies>python3</xbar.dependencies>
# Apple's /usr/bin/python3 on purpose: it trusts the system certificate store,
# while a python.org build may fail every request with CERTIFICATE_VERIFY_FAILED.
#
# Accounts are found automatically:
#   - keychain logins: every "Claude Code-credentials*" item (plain `claude`
#     and any CLAUDE_CONFIG_DIR variant).
#   - setup-tokens: any line in shell rc files or ~/bin, ~/.local/bin scripts
#     that sets CLAUDE_CODE_OAUTH_TOKEN to a literal token or to $(cat FILE).
# Usage is read from the rate-limit headers of a 1-token request, every
# PROBE_EVERY s. /api/oauth/usage is not used: setup-tokens lack the scope for
# it and it returns 429 for long stretches when polled. A Fable request also
# returns the per-model weekly windows (e.g. 7d_oi), which a Haiku one omits.
# Once every UPDATE_EVERY s the latest GitHub release is checked; the menu then
# offers a one-click update that replaces this file (`--update`).
# Optional ~/.config/claude-usage.conf, one entry per line:
#   label = /path/to/token-file     add a token the scan cannot find
#   keychain = off                  hide keychain logins
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

VERSION = "1.1.0"
REPO = "Kong-Travis/claude-usage-bar"
PLUGIN_PATH_IN_REPO = "plugin/claude-usage.1m.py"
API = "https://api.anthropic.com"
HOME = os.path.expanduser("~")
CACHE_DIR = os.path.join(HOME, ".cache", "claude-usage")
CONF = os.path.join(HOME, ".config", "claude-usage.conf")
RC_FILES = [".zshrc", ".zprofile", ".zshenv", ".bashrc", ".bash_profile", ".profile"]
SCRIPT_DIRS = ["bin", ".local/bin"]
SECURITY = "/usr/bin/security"
KEYCHAIN_SERVICE = "Claude Code-credentials"
WARN, CRIT = 70, 90
PROBE_EVERY = 180      # each probe costs a few tokens of quota
PROBE_MODELS = ["claude-fable-5-1", "claude-haiku-5-5"]  # fall back if Fable is unavailable
# Per-model weekly windows seen in the headers, by suffix of "7d_<suffix>".
MODEL_WINDOWS = {"oi": "Fable"}
EMAIL_EVERY = 86400
UPDATE_EVERY = 6 * 3600
MAX_IN_TITLE = 3

TOKEN_RE = re.compile(r"sk-ant-oat\d+-[A-Za-z0-9_-]+")
ASSIGN_RE = re.compile(r"CLAUDE_CODE_OAUTH_TOKEN=(\S+)")
CAT_RE = re.compile(r"\$\(\s*cat\s+([^)]+?)\s*\)")
ALIAS_RE = re.compile(r"^\s*alias\s+([\w.-]+)=")


# ---------- discovery ----------

def read_conf():
    tokens, keychain = [], True
    try:
        with open(CONF) as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if "=" not in line:
                    continue
                key, val = (s.strip() for s in line.split("=", 1))
                if key == "keychain":
                    keychain = val.lower() not in ("off", "no", "false", "0")
                elif val:
                    tokens.append((key, expand(val)))
    except OSError:
        pass
    return tokens, keychain


def expand(path):
    path = path.strip().strip("'\"")
    path = path.replace("${HOME}", HOME).replace("$HOME", HOME)
    return os.path.expanduser(path)


def token_from_value(value):
    """Resolve the right-hand side of CLAUDE_CODE_OAUTH_TOKEN=... to a token."""
    m = TOKEN_RE.search(value)
    if m:
        return m.group(0)
    m = CAT_RE.search(value)
    if m:
        return read_token_file(expand(m.group(1)))
    return None


def read_token_file(path):
    try:
        with open(path) as f:
            m = TOKEN_RE.search(f.read())
        return m.group(0) if m else None
    except OSError:
        return None


def scan_file(path, default_label):
    found = []
    try:
        if os.path.getsize(path) > 256 * 1024:
            return found
        with open(path, errors="ignore") as f:
            lines = f.readlines()
    except OSError:
        return found
    for line in lines:
        if line.lstrip().startswith("#"):
            continue
        m = ASSIGN_RE.search(line)
        if not m:
            continue
        # Keep the whole $(cat ...) expression even if it contains spaces.
        value = line[m.start(1):]
        token = token_from_value(value)
        if token:
            a = ALIAS_RE.match(line)
            found.append((a.group(1) if a else default_label, token))
    return found


def discover_tokens():
    found = []
    for name in RC_FILES:
        found += scan_file(os.path.join(HOME, name), name)
    for d in SCRIPT_DIRS:
        d = os.path.join(HOME, d)
        try:
            entries = sorted(os.listdir(d))
        except OSError:
            continue
        for e in entries:
            p = os.path.join(d, e)
            try:
                st = os.stat(p)
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode) and st.st_mode & 0o111:
                found += scan_file(p, e)
    return found


def keychain_services():
    out = subprocess.run([SECURITY, "dump-keychain"], capture_output=True,
                         text=True, timeout=15).stdout
    names = set(re.findall(r'"svce"<blob>="(%s[^"]*)"' % re.escape(KEYCHAIN_SERVICE), out))
    return sorted(names, key=lambda s: (s != KEYCHAIN_SERVICE, s))


def keychain_token(service):
    out = subprocess.run([SECURITY, "find-generic-password", "-s", service, "-w"],
                         capture_output=True, text=True, timeout=10).stdout
    return json.loads(out)["claudeAiOauth"]["accessToken"]


def accounts():
    """List of dicts: label, kind ('keychain' | 'token'), secret source."""
    conf_tokens, use_keychain = read_conf()
    result = []
    if use_keychain:
        try:
            for svc in keychain_services():
                result.append({"label": None, "kind": "keychain", "service": svc})
        except Exception:
            pass
    seen = set()
    for label, token in discover_tokens() + [(l, read_token_file(p)) for l, p in conf_tokens]:
        if not token or token in seen:
            continue
        seen.add(token)
        result.append({"label": label, "kind": "token", "token": token})
    return result


# ---------- cache ----------

def cache_path(name):
    return os.path.join(CACHE_DIR, name + ".json")


def load(name):
    try:
        with open(cache_path(name)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save(name, data):
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = cache_path(name) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, cache_path(name))


def age(name):
    try:
        return time.time() - os.path.getmtime(cache_path(name))
    except OSError:
        return float("inf")


# ---------- usage ----------

def oauth_get(path, token):
    req = urllib.request.Request(API + path, headers={
        "Authorization": "Bearer " + token,
        "anthropic-beta": "oauth-2025-04-20",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def iso_to_epoch(s):
    return int(datetime.fromisoformat(s).timestamp())


def usage_probe(token):
    """Read usage from the rate-limit headers of a 1-token request."""
    p = "anthropic-ratelimit-unified-"
    for model in PROBE_MODELS:
        body = json.dumps({
            "model": model,
            "max_tokens": 1,
            "system": "You are Claude Code, Anthropic's official CLI for Claude.",
            "messages": [{"role": "user", "content": "hi"}],
        }).encode()
        req = urllib.request.Request(API + "/v1/messages", data=body, headers={
            "Authorization": "Bearer " + token,
            "anthropic-beta": "oauth-2025-04-20",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                h = r.headers
        except urllib.error.HTTPError as e:
            # A rate-limited account still returns the usage headers.
            h = e.headers
        if h.get(p + "5h-utilization") is not None:
            break
    else:
        raise RuntimeError("no rate-limit headers")
    data = {
        "5h": float(h[p + "5h-utilization"]) * 100,
        "5h_reset": int(h[p + "5h-reset"]),
        "7d": float(h[p + "7d-utilization"]) * 100,
        "7d_reset": int(h[p + "7d-reset"]),
        "models": [],
    }
    for name in h.keys():
        m = re.match(re.escape(p) + r"7d_(\w+)-utilization$", name.lower())
        if m:
            suffix = m.group(1)
            data["models"].append({
                "name": MODEL_WINDOWS.get(suffix, suffix),
                "pct": float(h[name]) * 100,
                "reset": int(h.get(p + "7d_" + suffix + "-reset") or 0),
            })
    return data


def keychain_email(acc, key):
    name = key + "-email"
    cached_email = load(name)
    if age(name) < EMAIL_EVERY and cached_email:
        return cached_email.get("email", "")
    try:
        email = oauth_get("/api/oauth/profile", keychain_token(acc["service"]))["account"]["email"]
        save(name, {"email": email})
        return email
    except Exception:
        return (cached_email or {}).get("email", "")


def account_token(acc):
    return keychain_token(acc["service"]) if acc["kind"] == "keychain" else acc["token"]


def cache_key(acc):
    raw = acc.get("service") or acc["token"]
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def cached(acc, force=False):
    """Return (data, error). On failure fall back to the last good result."""
    key = cache_key(acc)
    if not force and age(key) < PROBE_EVERY and load(key):
        return load(key), None
    try:
        data = usage_probe(account_token(acc))
        save(key, data)
        return data, None
    except Exception as e:
        return load(key), "%s: %s" % (type(e).__name__, str(e)[:160])


def log_errors(rows):
    """Keep the last run's errors on disk so a blank menu can be diagnosed."""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(os.path.join(CACHE_DIR, "last-run.log"), "w") as f:
            f.write("%s v%s python=%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), VERSION, sys.executable))
            for s, acc, _, err in rows:
                f.write("%s %s: %s\n" % (s, acc["label"], err or "ok"))
    except OSError:
        pass


# ---------- updates ----------

def parse_version(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def latest_release():
    """Return the newest release tag, checking GitHub at most every UPDATE_EVERY s."""
    cached_rel = load("update")
    if age("update") < UPDATE_EVERY and cached_rel:
        return cached_rel.get("tag")
    try:
        req = urllib.request.Request("https://api.github.com/repos/%s/releases/latest" % REPO,
                                     headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            tag = json.load(r)["tag_name"]
        save("update", {"tag": tag})
        return tag
    except Exception:
        return (cached_rel or {}).get("tag")


def self_update():
    """Replace this file with the plugin from the latest release, after sanity checks."""
    tag = latest_release()
    if not tag or parse_version(tag) <= parse_version(VERSION):
        return
    url = "https://raw.githubusercontent.com/%s/%s/%s" % (REPO, tag, PLUGIN_PATH_IN_REPO)
    with urllib.request.urlopen(url, timeout=30) as r:
        code = r.read().decode()
    want = 'VERSION = "%s"' % ".".join(str(n) for n in parse_version(tag))
    if not code.startswith("#!/usr/bin/python3") or want not in code:
        raise RuntimeError("downloaded plugin failed sanity check")
    compile(code, "plugin", "exec")
    me = os.path.realpath(__file__)
    tmp = me + ".new"
    with open(tmp, "w") as f:
        f.write(code)
    os.chmod(tmp, 0o755)
    os.replace(tmp, me)


# ---------- output ----------

def short_name(label, taken):
    base = re.sub(r"^claude[-_.]?", "", label, flags=re.I) or label
    s = base[:1].upper() or "?"
    n = 2
    while s in taken:
        s = base[:1].upper() + str(n)
        n += 1
    taken.add(s)
    return s


def color(pct):
    return "red" if pct >= CRIT else "orange" if pct >= WARN else None


def fmt_reset(epoch):
    return time.strftime("%H:%M %d/%m", time.localtime(epoch))


def print_update_items(tag):
    if not tag or parse_version(tag) <= parse_version(VERSION):
        return
    me = os.path.realpath(__file__)
    print("Có bản mới %s (đang dùng v%s) | color=#2e7d32" % (tag, VERSION))
    print('Cập nhật ngay | bash="%s" param1=--update terminal=false refresh=true' % me)
    print("Xem thay đổi | href=https://github.com/%s/releases/tag/%s" % (REPO, tag))
    print("---")


def main():
    if sys.argv[1:] == ["--update"]:
        self_update()
        return
    if sys.argv[1:] == ["--force"]:
        for acc in accounts():
            cached(acc, force=True)
        return

    accs = accounts()
    tag = latest_release()
    has_update = bool(tag) and parse_version(tag) > parse_version(VERSION)
    badge = " sfimage=arrow.down.circle" if has_update else ""

    if not accs:
        print("Claude ? |" + badge)
        print("---")
        print_update_items(tag)
        print("Không tìm thấy tài khoản Claude Code nào")
        print("Đăng nhập bằng `claude`, hoặc khai báo token trong ~/.config/claude-usage.conf | size=11")
        return

    taken, rows = set(), []
    for acc in accs:
        data, err = cached(acc)
        if acc["kind"] == "keychain":
            default = acc["service"] == KEYCHAIN_SERVICE
            acc["label"] = "claude" if default else "claude (" + acc["service"][len(KEYCHAIN_SERVICE):].strip("-") + ")"
            acc["detail"] = keychain_email(acc, cache_key(acc))
        else:
            acc["detail"] = "token"
        rows.append((short_name(acc["label"], taken), acc, data, err))
    log_errors(rows)

    known = [r for r in rows if r[2]]
    worst = max([max(d["5h"], d["7d"]) for _, _, d, _ in known] or [0])
    if len(rows) <= MAX_IN_TITLE:
        title = "  ".join("%s %d/%d" % (s, round(d["5h"]), round(d["7d"])) if d else s + " ?"
                          for s, _, d, _ in rows)
    else:
        title = "Claude %d%%" % round(worst)
    c = color(worst)
    print(title + " |" + (" color=" + c if c else "") + badge)
    print("---")
    print_update_items(tag)

    for s, acc, d, err in rows:
        head = "%s: %s" % (s, acc["label"])
        if acc["detail"]:
            head += " - " + acc["detail"]
        print(head + " | size=13")
        if d is None:
            print("Không đọc được hạn mức | color=gray")
        else:
            for key, name in (("5h", "5 giờ"), ("7d", "Tuần")):
                line = "%s: %d%%  (reset %s)" % (name, round(d[key]), fmt_reset(d[key + "_reset"]))
                c = color(d[key])
                print(line + (" | color=" + c if c else ""))
            for m in d.get("models", []):
                line = "%s (tuần): %d%%" % (m["name"], round(m["pct"]))
                if m["reset"]:
                    line += "  (reset %s)" % fmt_reset(m["reset"])
                c = color(m["pct"])
                print(line + (" | color=" + c if c else ""))
            if err:
                print("Số liệu cũ, lần cập nhật vừa rồi bị lỗi | color=gray size=11")
        if err:
            print("Lỗi: %s | color=gray size=11" % err.replace("|", "/"))
        print("---")
    print("Cập nhật mỗi 3 phút | color=gray size=11")
    print("Số đầu: % giới hạn 5 giờ, số sau: % giới hạn tuần | color=gray size=11")
    print("Phiên bản v%s | color=gray size=11 href=https://github.com/%s" % (VERSION, REPO))
    me = os.path.realpath(__file__)
    print('Làm mới ngay | bash="%s" param1=--force terminal=false refresh=true' % me)


main()
