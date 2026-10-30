# claude-usage-bar

See your Claude Code usage limits in the macOS menu bar, for every account on your Mac.

```
C 85/88  T 60/14
```

Each letter is one account: first number = 5-hour limit %, second = weekly limit %.
Orange at 70%, red at 90%. Click it to see account names and reset times.

## Install

1. Download **`Claude-Usage.dmg`** from [Releases](../../releases/latest).
2. Open it and double-click **`Cài đặt Claude Usage.command`**.
3. Follow the steps in the Terminal window.

If macOS blocks the file, go to **System Settings > Privacy & Security > Open Anyway**,
or run it in Terminal:

```sh
bash "/Volumes/Claude Usage/Cài đặt Claude Usage.command"
```

## Good to know

- Works with browser logins (`claude`) and `claude setup-token` tokens (aliases using
  `CLAUDE_CODE_OAUTH_TOKEN`). Accounts are found automatically.
- Browser logins refresh every minute. Token accounts refresh every 5 minutes and use a tiny
  1-token request each time, because tokens cannot read usage any other way.
- Token not found? Add `name = /path/to/token-file` to `~/.config/claude-usage.conf`.
- Shows `?`: click it to see the error, or check `~/.cache/claude-usage/last-run.log`.

## Uninstall

Delete `~/.config/swiftbar/claude-usage.1m.py` (and the SwiftBar app if you don't need it).

## Build

`./build.sh` creates `dist/Claude-Usage.dmg`. Built on [SwiftBar](https://github.com/swiftbar/SwiftBar).
MIT license.
