"""Unit tests for Researcher 2.0 normalization utilities (Stage 3.2 Step 2).

Scope: URL normalization, canonical identities (URL + GitHub owner/repo)
and title normalization. Pure functions, no network, no fixtures needed.

Out of scope: classification, dedup policies, scoring, ranking, adapter
HTTP behavior.
"""

import unittest

from src.research.normalize import (
    github_repo_identity,
    normalize_title,
    normalize_url,
    url_identity,
)


class TestUrlNormalization(unittest.TestCase):
    def test_tracking_parameters_removed(self) -> None:
        cases = [
            ("https://example.com/post?utm_source=hn&utm_campaign=x",
             "https://example.com/post"),
            ("https://example.com/post?id=7&utm_medium=social",
             "https://example.com/post?id=7"),
            ("https://example.com/a?FBCLID=abc",
             "https://example.com/a"),
            ("https://example.com/a?gclid=1&fbclid=2&keep=1",
             "https://example.com/a?keep=1"),
            # yt short share link (www stripped + tracking param removed)
            ("https://www.youtube.com/watch?v=abc&si=xyz",
             "https://youtube.com/watch?v=abc"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_url(raw), expected)

    def test_meaningful_query_parameters_preserved(self) -> None:
        self.assertEqual(
            normalize_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            "https://youtube.com/watch?v=dQw4w9WgXcQ",
        )
        # "ref" is semantic on GitHub (branch links) — must survive.
        self.assertEqual(
            normalize_url("https://github.com/owner/repo/blob/main/file.py?ref=main"),
            "https://github.com/owner/repo/blob/main/file.py?ref=main",
        )
        # Query order is preserved; blank values kept.
        self.assertEqual(
            normalize_url("https://example.com/search?q=ai+tools&lang=en"),
            "https://example.com/search?q=ai+tools&lang=en",
        )

    def test_fragments_removed(self) -> None:
        self.assertEqual(
            normalize_url("https://example.com/docs/page#section-2"),
            "https://example.com/docs/page",
        )

    def test_host_and_scheme_normalization(self) -> None:
        self.assertEqual(
            normalize_url("HTTP://WWW.Example.COM/Path"),
            "http://example.com/Path",
        )
        # Path casing preserved (paths are case-sensitive).
        self.assertEqual(
            normalize_url("https://example.com/Repo/file.PY"),
            "https://example.com/Repo/file.PY",
        )
        # Only scheme+host case-fold; userinfo dropped.
        self.assertEqual(
            normalize_url("https://user:pass@Example.com/x"),
            "https://example.com/x",
        )
        # Default port dropped; custom port preserved.
        self.assertEqual(
            normalize_url("https://example.com:443/a"),
            "https://example.com/a",
        )
        self.assertEqual(
            normalize_url("http://example.com:8080/a"),
            "http://example.com:8080/a",
        )

    def test_trailing_slash_behavior(self) -> None:
        self.assertEqual(
            normalize_url("https://example.com/article/"),
            "https://example.com/article",
        )
        self.assertEqual(
            normalize_url("https://example.com/a/b/"),
            "https://example.com/a/b",
        )
        # Root stays root.
        self.assertEqual(normalize_url("https://example.com/"), "https://example.com")
        self.assertEqual(normalize_url("https://example.com"), "https://example.com")

    def test_www_only_stripped_conservatively(self) -> None:
        self.assertEqual(
            normalize_url("https://www.example.com/a"),
            "https://example.com/a",
        )
        # "www." reduces to the dotless host "www" — not a meaningful
        # public content URL, so it is refused rather than guessed.
        self.assertIsNone(normalize_url("https://www./a"))

    def test_malformed_or_empty_urls_return_none(self) -> None:
        for bad in (
            None,
            "",
            "   ",
            "not-a-url",
            "example.com/no-scheme",
            "ftp://example.com/file",
            "javascript:alert(1)",
            "http://",
        ):
            with self.subTest(bad=bad):
                self.assertIsNone(normalize_url(bad))

    def test_no_false_conservative_rewrites(self) -> None:
        # Mobile subdomains are preserved: m.example.com may differ from example.com.
        self.assertEqual(
            normalize_url("https://m.example.com/story"),
            "https://m.example.com/story",
        )

    def test_url_identity_matches_normalization(self) -> None:
        self.assertEqual(
            url_identity("https://www.example.com/a/?utm_source=x"),
            url_identity("https://example.com/a"),
        )
        self.assertIsNone(url_identity("bogus"))


class TestGithubRepoIdentity(unittest.TestCase):
    def test_basic_repo_url(self) -> None:
        self.assertEqual(
            github_repo_identity("https://github.com/Owner/Repo"),
            "owner/repo",
        )

    def test_deep_links_collapse_to_same_identity(self) -> None:
        base = "owner/repo"
        for url in (
            "https://github.com/Owner/Repo",
            "https://github.com/Owner/Repo/",
            "https://github.com/Owner/Repo/tree/main/src",
            "https://github.com/Owner/Repo/blob/main/README.md",
            "https://github.com/Owner/Repo/releases/tag/v1.2.3",
            "https://github.com/Owner/Repo/issues/42",
            "https://github.com/Owner/Repo.git",
        ):
            with self.subTest(url=url):
                self.assertEqual(github_repo_identity(url), base)

    def test_non_repo_urls_return_none(self) -> None:
        for url in (
            "https://github.com/owner",              # user only
            "https://github.com/owner/",             # user only
            "https://gist.github.com/owner/abc123",  # gists are not repos
            "https://gitlab.com/owner/repo",         # other forges
            "https://example.com/owner/repo",        # not github
            "https://github.com",                    # bare domain
            "not a url",
            None,
        ):
            with self.subTest(url=url):
                self.assertIsNone(github_repo_identity(url))

    def test_tracking_params_do_not_break_identity(self) -> None:
        self.assertEqual(
            github_repo_identity("https://github.com/owner/repo?utm_source=x"),
            "owner/repo",
        )


class TestTitleNormalization(unittest.TestCase):
    def test_casefold_and_whitespace(self) -> None:
        self.assertEqual(
            normalize_title("  New   AI\tTool  Released "),
            "new ai tool released",
        )

    def test_unicode_variants_unified(self) -> None:
        # Curly quotes, en/em dashes, NBSP, ellipsis all fold to ASCII.
        self.assertEqual(
            normalize_title("The \u2018Best\u201d AI\u2013Tools \u2014 2026\u2026\u00a0Now"),
            "the 'best\" ai-tools - 2026... now",
        )

    def test_fullwidth_and_compatibility_forms_folded(self) -> None:
        # NFKC folds fullwidth latin and other compatibility forms.
        self.assertEqual(
            normalize_title("ＡＩ ＴＯＯＬＳ"),
            "ai tools",
        )

    def test_punctuation_conservative_not_stripped(self) -> None:
        # Version-number dots are information-bearing: never removed.
        self.assertEqual(
            normalize_title("Release v2.1.0 of ToolX"),
            "release v2.1.0 of toolx",
        )
        # Distinct titles must not collide merely due to punctuation.
        self.assertNotEqual(normalize_title("Tool: A"), normalize_title("Tool A"))

    def test_empty_inputs(self) -> None:
        self.assertEqual(normalize_title(None), "")
        self.assertEqual(normalize_title(""), "")
        self.assertEqual(normalize_title("   "), "")

    def test_original_title_preserved_by_caller_contract(self) -> None:
        # The function must not mutate or receive state; same input -> same key.
        original = "The \u2018Best\u201d AI Tools"
        first = normalize_title(original)
        second = normalize_title(original)
        self.assertEqual(first, second)
        self.assertEqual(original, "The \u2018Best\u201d AI Tools")  # untouched


if __name__ == "__main__":
    unittest.main()
