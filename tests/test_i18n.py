"""Translator and language names."""
import srcpath  # noqa: F401  (must come first)

import unittest

from claude_usage.i18n import (CATALOG, DEFAULT_LANGUAGE, EN, LANGUAGES, VI, Translator,
                               normalize_language)


class Normalize(unittest.TestCase):
    def test_known_forms(self):
        for value, want in [("en", EN), ("EN", EN), ("en_US.UTF-8", EN), ("English", EN),
                            ("vi", VI), ("vi_VN.UTF-8", VI), ("  Vi ", VI),
                            ("Tiếng Việt", VI)]:
            with self.subTest(value=value):
                self.assertEqual(normalize_language(value), want)

    def test_unknown_forms(self):
        for value in (None, "", "   ", "fr", "de_DE", "xx"):
            with self.subTest(value=value):
                self.assertIsNone(normalize_language(value))


class TranslatorTest(unittest.TestCase):
    def test_default_is_vietnamese(self):
        self.assertEqual(DEFAULT_LANGUAGE, VI)
        self.assertEqual(Translator().lang, VI)
        self.assertEqual(Translator()("quit"), "Thoát")

    def test_english(self):
        self.assertEqual(Translator("en")("quit"), "Quit")
        self.assertEqual(Translator("en_US.UTF-8").lang, EN)

    def test_unknown_language_falls_back_to_vietnamese(self):
        for lang in ("fr", "", None):
            with self.subTest(lang=lang):
                self.assertEqual(Translator(lang).lang, VI)

    def test_format_kwargs(self):
        self.assertEqual(Translator("en")("update_available", tag="v2.0.0", version="1.2.2"),
                         "New version v2.0.0 (you have v1.2.2)")
        self.assertEqual(Translator("vi")("version", version="1.2.2"), "Phiên bản v1.2.2")

    def test_text_without_kwargs_is_not_formatted(self):
        extra = {"braces": {VI: "{x}", EN: "{x}"}}
        self.assertEqual(Translator("en").with_catalog(extra)("braces"), "{x}")

    def test_unknown_key_raises(self):
        with self.assertRaises(KeyError):
            Translator()("no_such_key")

    def test_missing_language_in_an_entry_falls_back_to_vietnamese(self):
        t = Translator("en", {"only_vi": {VI: "chỉ tiếng Việt"}})
        self.assertEqual(t("only_vi"), "chỉ tiếng Việt")

    def test_with_catalog_adds_and_overrides_without_touching_the_original(self):
        base = Translator("en")
        extra = base.with_catalog({"hello": {VI: "xin chào", EN: "hello"}, "quit": {VI: "Đóng", EN: "Close"}})
        self.assertEqual(extra.lang, EN)
        self.assertEqual(extra("hello"), "hello")
        self.assertEqual(extra("quit"), "Close")
        self.assertEqual(extra("refresh_now"), "Refresh now")
        self.assertEqual(base("quit"), "Quit")
        with self.assertRaises(KeyError):
            base("hello")
        self.assertNotIn("hello", CATALOG)


class CatalogTest(unittest.TestCase):
    def test_every_key_has_both_languages(self):
        for key, entry in CATALOG.items():
            for lang in LANGUAGES:
                with self.subTest(key=key, lang=lang):
                    self.assertTrue(entry.get(lang), "%s has no %s text" % (key, lang))

    def test_both_languages_use_the_same_placeholders(self):
        import string
        fields = lambda s: {f for _, f, _, _ in string.Formatter().parse(s) if f}  # noqa: E731
        for key, entry in CATALOG.items():
            with self.subTest(key=key):
                self.assertEqual(fields(entry[VI]), fields(entry[EN]))


if __name__ == "__main__":
    unittest.main()
