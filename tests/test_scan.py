"""Finding setup-tokens and config dirs in bash, PowerShell and cmd files."""
import srcpath  # noqa: F401  (must come first)

import os
import shutil
import tempfile
import unittest

from claude_usage.scan import (MAX_SCAN_BYTES, ShellScanner, expand_path, read_token_file,
                               token_in_text)


def tok(name):
    return "sk-ant-oat01-" + name


class ScanCase(unittest.TestCase):
    def setUp(self):
        self.home = os.path.realpath(tempfile.mkdtemp(prefix="cub-scan-"))
        self.addCleanup(shutil.rmtree, self.home, True)
        self.scanner = ShellScanner(self.home)

    def write(self, rel, text):
        p = os.path.join(self.home, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="") as f:  # exact byte sizes on Windows too
            f.write(text)
        return p

    def tokens(self, text, default="default"):
        return self.scanner.tokens(self.write("rc", text), default)


class TokensFromShellFiles(ScanCase):
    def test_bash_alias_gives_the_alias_name_as_label(self):
        got = self.tokens("alias claude-work='CLAUDE_CODE_OAUTH_TOKEN=%s claude'\n" % tok("W"))
        self.assertEqual(got, [("claude-work", tok("W"))])

    def test_bash_export_uses_the_default_label(self):
        got = self.tokens("export CLAUDE_CODE_OAUTH_TOKEN=%s\n" % tok("E"), default=".zshrc")
        self.assertEqual(got, [(".zshrc", tok("E"))])

    def test_cat_of_a_file(self):
        self.write(".ci-token", tok("CI") + "\n")
        got = self.tokens("export CLAUDE_CODE_OAUTH_TOKEN=$(cat ~/.ci-token)\n")
        self.assertEqual(got, [("default", tok("CI"))])

    def test_cat_with_spaces_in_the_path(self):
        self.write("my tokens/work token.txt", tok("SP"))
        got = self.tokens("alias w='CLAUDE_CODE_OAUTH_TOKEN=$(cat ~/my tokens/work token.txt) claude'\n")
        self.assertEqual(got, [("w", tok("SP"))])

    def test_cat_with_home_variable(self):
        self.write("t.txt", tok("HV"))
        got = self.tokens('export CLAUDE_CODE_OAUTH_TOKEN="$(cat $HOME/t.txt)"\n')
        self.assertEqual(got, [("default", tok("HV"))])

    def test_cat_of_a_missing_file_gives_nothing(self):
        self.assertEqual(self.tokens("export CLAUDE_CODE_OAUTH_TOKEN=$(cat ~/nope)\n"), [])

    def test_powershell_env_assignment(self):
        got = self.tokens('$env:CLAUDE_CODE_OAUTH_TOKEN = "%s"\n' % tok("PS"))
        self.assertEqual(got, [("default", tok("PS"))])

    def test_powershell_function_label(self):
        got = self.tokens('function claude-work { $env:CLAUDE_CODE_OAUTH_TOKEN = "%s"; claude @args }\n'
                          % tok("FN"))
        self.assertEqual(got, [("claude-work", tok("FN"))])

    def test_powershell_get_content(self):
        self.write("tok.txt", tok("GC"))
        got = self.tokens('$env:CLAUDE_CODE_OAUTH_TOKEN = (Get-Content "$env:USERPROFILE/tok.txt")\n')
        self.assertEqual(got, [("default", tok("GC"))])

    def test_powershell_gc_alias_with_raw_switch(self):
        self.write("tok2.txt", tok("GR"))
        got = self.tokens("$env:CLAUDE_CODE_OAUTH_TOKEN = gc -Raw ~/tok2.txt\n")
        self.assertEqual(got, [("default", tok("GR"))])

    def test_powershell_set_environment_variable(self):
        got = self.tokens('[Environment]::SetEnvironmentVariable("CLAUDE_CODE_OAUTH_TOKEN","%s","User")\n'
                          % tok("SEV"))
        self.assertEqual(got, [("default", tok("SEV"))])

    def test_cmd_set(self):
        got = self.tokens("@echo off\r\nset CLAUDE_CODE_OAUTH_TOKEN=%s\r\n" % tok("CMD"))
        self.assertEqual(got, [("default", tok("CMD"))])

    def test_cmd_doskey_label(self):
        got = self.tokens("doskey claude-work=set CLAUDE_CODE_OAUTH_TOKEN=%s $T claude $*\n" % tok("DK"))
        self.assertEqual(got, [("claude-work", tok("DK"))])

    def test_commented_lines_are_ignored(self):
        text = "\n".join([
            "# export CLAUDE_CODE_OAUTH_TOKEN=%s" % tok("HASH"),
            "   # alias a='CLAUDE_CODE_OAUTH_TOKEN=%s claude'" % tok("INDENT"),
            ":: set CLAUDE_CODE_OAUTH_TOKEN=%s" % tok("COLON"),
            "REM set CLAUDE_CODE_OAUTH_TOKEN=%s" % tok("REM"),
            "rem set CLAUDE_CODE_OAUTH_TOKEN=%s" % tok("rem"),
            "set CLAUDE_CODE_OAUTH_TOKEN=%s" % tok("LIVE"),
        ])
        self.assertEqual(self.tokens(text), [("default", tok("LIVE"))])

    def test_several_tokens_in_one_file_keep_their_order(self):
        text = ("alias a='CLAUDE_CODE_OAUTH_TOKEN=%s claude'\n"
                "alias b='CLAUDE_CODE_OAUTH_TOKEN=%s claude'\n" % (tok("A"), tok("B")))
        self.assertEqual(self.tokens(text), [("a", tok("A")), ("b", tok("B"))])

    def test_a_line_without_a_token_value_is_skipped(self):
        self.assertEqual(self.tokens("export CLAUDE_CODE_OAUTH_TOKEN=\nunset CLAUDE_CODE_OAUTH_TOKEN\n"), [])

    def test_missing_file(self):
        self.assertEqual(self.scanner.tokens(os.path.join(self.home, "absent"), "x"), [])

    def test_file_over_the_size_limit_is_skipped(self):
        line = "export CLAUDE_CODE_OAUTH_TOKEN=%s\n" % tok("BIG")
        body = line + "#" * (MAX_SCAN_BYTES + 1 - len(line))
        p = self.write("big", body)
        self.assertEqual(os.path.getsize(p), MAX_SCAN_BYTES + 1)
        self.assertEqual(self.scanner.tokens(p, "x"), [])

    def test_file_at_the_size_limit_is_read(self):
        line = "export CLAUDE_CODE_OAUTH_TOKEN=%s\n" % tok("OK")
        p = self.write("edge", line + "#" * (MAX_SCAN_BYTES - len(line)))
        self.assertEqual(os.path.getsize(p), MAX_SCAN_BYTES)
        self.assertEqual(self.scanner.tokens(p, "x"), [("x", tok("OK"))])


class ConfigDirs(ScanCase):
    def dirs(self, text):
        return self.scanner.config_dirs(self.write("rc", text))

    def test_alias_with_tilde(self):
        got = self.dirs("alias claude-work='CLAUDE_CONFIG_DIR=~/.claude-work claude'\n")
        self.assertEqual(got, [self.home + "/.claude-work"])

    def test_export_with_quotes_and_home_variable(self):
        got = self.dirs('export CLAUDE_CONFIG_DIR="$HOME/.claude-a"\nexport CLAUDE_CONFIG_DIR=${HOME}/.claude-b\n')
        self.assertEqual(got, [self.home + "/.claude-a", self.home + "/.claude-b"])

    def test_powershell_assignment(self):
        got = self.dirs('$env:CLAUDE_CONFIG_DIR = "$env:USERPROFILE/.claude-ps"\n')
        self.assertEqual(got, [self.home + "/.claude-ps"])

    def test_comments_are_ignored(self):
        self.assertEqual(self.dirs("# export CLAUDE_CONFIG_DIR=~/.claude-x\n"), [])

    def test_missing_file(self):
        self.assertEqual(self.scanner.config_dirs(os.path.join(self.home, "absent")), [])

    def test_big_file_is_skipped(self):
        p = self.write("big", "export CLAUDE_CONFIG_DIR=~/.claude-x\n" + "#" * MAX_SCAN_BYTES)
        self.assertEqual(self.scanner.config_dirs(p), [])


class ExpandPath(unittest.TestCase):
    HOME = os.path.join(os.sep, "home", "u")

    def test_variants(self):
        h = self.HOME
        cases = {
            "~": h,
            "~/x": h + "/x",
            "~\\x": h + "\\x",
            "$HOME/x": h + "/x",
            "${HOME}/x": h + "/x",
            "%USERPROFILE%\\x": h + "\\x",
            "%HOME%/x": h + "/x",
            "$env:USERPROFILE/x": h + "/x",
            "$env:HOME/x": h + "/x",
        }
        for raw, want in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(expand_path(raw, h), want)

    def test_quotes_and_spaces_are_stripped(self):
        self.assertEqual(expand_path('  "~/a b"  ', "/h"), "/h/a b")
        self.assertEqual(expand_path("'$HOME/c'", "/h"), "/h/c")

    def test_plain_and_tilde_user_paths_are_untouched(self):
        self.assertEqual(expand_path("/etc/x", "/h"), "/etc/x")
        self.assertEqual(expand_path("~other/x", "/h"), "~other/x")


class TokenHelpers(ScanCase):
    def test_token_in_text(self):
        self.assertEqual(token_in_text("a sk-ant-oat01-AbC_d-9 b"), "sk-ant-oat01-AbC_d-9")
        self.assertEqual(token_in_text("sk-ant-oat12-x"), "sk-ant-oat12-x")
        self.assertIsNone(token_in_text("sk-ant-api03-xyz"))
        self.assertIsNone(token_in_text(""))
        self.assertIsNone(token_in_text(None))

    def test_read_token_file(self):
        p = self.write("t", "\n  %s \n" % tok("F"))
        self.assertEqual(read_token_file(p), tok("F"))
        self.assertIsNone(read_token_file(os.path.join(self.home, "absent")))
        self.assertIsNone(read_token_file(self.write("empty", "")))

    def test_binary_garbage_is_tolerated(self):
        p = os.path.join(self.home, "bin")
        with open(p, "wb") as f:
            f.write(b"\xff\xfe\x00" + tok("BIN").encode())
        self.assertEqual(read_token_file(p), tok("BIN"))


if __name__ == "__main__":
    unittest.main()
