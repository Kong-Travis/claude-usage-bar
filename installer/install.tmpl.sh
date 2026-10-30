#!/bin/bash
# Installer for the "Claude Code usage" menu bar plugin (SwiftBar).
# Double-click in Finder, or run: bash claude-usage-install.command
set -u

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
info() { printf '  %s\n' "$*"; }
fail() { printf '\n\033[31mLỗi: %s\033[0m\n' "$*"; pause; exit 1; }
pause() { printf '\nNhấn Enter để tiếp tục...'; read -r _ </dev/tty 2>/dev/null; }

[ "$(uname)" = "Darwin" ] || fail "Bộ cài này chỉ chạy trên macOS."

# 1. python3 (ships with the Xcode Command Line Tools)
say "1/4  Kiểm tra python3"
if ! /usr/bin/xcrun --find python3 >/dev/null 2>&1 || ! /usr/bin/python3 -c 'import sys' >/dev/null 2>&1; then
  info "Máy chưa có Command Line Tools (cần cho python3). Đang mở hộp thoại cài đặt..."
  xcode-select --install >/dev/null 2>&1
  fail "Bấm \"Cài đặt\" trong hộp thoại vừa hiện, chờ cài xong rồi chạy lại file này."
fi
info "OK: $(/usr/bin/python3 --version)"

# 2. SwiftBar
say "2/4  Cài SwiftBar (app hiển thị chữ trên thanh menu)"
APP=/Applications/SwiftBar.app
if [ -d "$APP" ]; then
  info "Đã có sẵn SwiftBar."
elif command -v brew >/dev/null 2>&1; then
  brew install --cask swiftbar || fail "brew install --cask swiftbar không thành công."
else
  info "Không có Homebrew, tải bản mới nhất từ GitHub..."
  URL=$(curl -fsSL https://api.github.com/repos/swiftbar/SwiftBar/releases/latest |
    /usr/bin/python3 -c 'import json,sys; print(next(a["browser_download_url"] for a in json.load(sys.stdin)["assets"] if a["name"].endswith(".zip")))') ||
    fail "Không lấy được link tải SwiftBar."
  TMP=$(mktemp -d)
  curl -fL -o "$TMP/SwiftBar.zip" "$URL" || fail "Tải SwiftBar không thành công."
  ditto -x -k "$TMP/SwiftBar.zip" "$TMP" || fail "Giải nén SwiftBar không thành công."
  mv "$TMP/SwiftBar.app" /Applications/ || fail "Không chép được SwiftBar vào /Applications."
  rm -rf "$TMP"
fi
[ -d "$APP" ] || fail "Không tìm thấy $APP sau khi cài."

# 3. Plugin. Reuse an existing SwiftBar plugin folder if one is configured.
say "3/4  Cài plugin Claude Code usage"
DIR=$(defaults read com.ameba.SwiftBar PluginDirectory 2>/dev/null || true)
if [ -z "$DIR" ]; then
  DIR="$HOME/.config/swiftbar"
  defaults write com.ameba.SwiftBar PluginDirectory -string "$DIR"
fi
mkdir -p "$DIR"
PLUGIN="$DIR/claude-usage.1m.py"
rm -f "$DIR/claude-usage.5m.py"  # earlier version
cat > "$PLUGIN" <<'PLUGIN_EOF'
__PLUGIN__
PLUGIN_EOF
chmod +x "$PLUGIN"
info "Đã cài: $PLUGIN"

info "Đang chạy thử..."
OUT=$(/usr/bin/python3 "$PLUGIN" 2>&1 | head -1 | sed 's/ |.*//')
info "Thanh menu sẽ hiện: $OUT"
case "$OUT" in
  "Claude ?") info "Chưa tìm thấy tài khoản nào. Xem mục \"Nếu thiếu tài khoản\" bên dưới." ;;
esac

# 4. Launch and guide through the macOS settings that need a human click.
say "4/4  Mở SwiftBar và các cài đặt cần thiết"
pkill -x SwiftBar 2>/dev/null
open "$APP"

cat <<'EOF'

  a) Lần đầu mở SwiftBar, macOS có thể hỏi "SwiftBar là app tải từ Internet,
     bạn có chắc muốn mở?" -> bấm "Mở" (Open).

  b) Nếu macOS hỏi "security muốn dùng thông tin bí mật 'Claude Code-credentials'
     trong chuỗi khoá (keychain)" -> nhập mật khẩu máy rồi bấm "Luôn cho phép"
     (Always Allow). Bước này để đọc hạn mức của tài khoản đăng nhập bằng `claude`.

  c) Nếu không thấy chữ trên thanh menu: thanh menu có thể đã đầy (nhất là máy
     có tai thỏ). Giữ phím Command rồi kéo bớt icon khác ra ngoài để nhường chỗ.
EOF
pause

say "Cho SwiftBar tự chạy khi bật máy"
cat <<'EOF'
  Sắp mở System Settings > General > Login Items.
  Ở phần "Open at Login", bấm dấu "+", chọn SwiftBar trong Applications rồi bấm "Open".
EOF
pause
open "x-apple.systempreferences:com.apple.LoginItems-Settings.extension"

cat <<EOF

$(printf '\033[1m%s\033[0m' "Xong.")
  Thanh menu hiện dạng "C 87/88/94  T 79/17/0": mỗi tài khoản là một chữ cái,
  ba số lần lượt là % giới hạn 5 giờ / tuần / Fable tuần. Bấm vào để xem
  tên tài khoản và giờ reset. Tự cập nhật mỗi 3 phút, có bản mới thì menu
  hiện nút "Cập nhật ngay". Nếu hiện "?", bấm vào để xem dòng "Lỗi: ..."
  hoặc xem file ~/.cache/claude-usage/last-run.log.

  Nếu thiếu tài khoản:
  - Đăng nhập trình duyệt: chạy \`claude\` một lần để đăng nhập.
  - Token (claude setup-token): plugin tự tìm alias/export CLAUDE_CODE_OAUTH_TOKEN
    trong ~/.zshrc, ~/.bashrc... và script trong ~/bin. Nếu token để chỗ khác,
    thêm một dòng "tên = /đường/dẫn/file-token" vào ~/.config/claude-usage.conf
    rồi bấm "Làm mới" trong menu.
  - Muốn ẩn tài khoản đăng nhập trình duyệt: thêm dòng "keychain = off" vào file trên.

  Lưu ý: mỗi tài khoản token tốn một request 1 token (Haiku) mỗi 5 phút để đọc hạn mức.
  Gỡ cài đặt: xoá $PLUGIN (và app SwiftBar nếu không cần).
EOF
pause
