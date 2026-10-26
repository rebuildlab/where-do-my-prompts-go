#!/usr/bin/env python3
"""URL selection and the browser fallback decision. No network."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_policies import is_challenge, merge_index_urls, needs_render


def test_index_urls_are_not_dropped():
    cited = {"https://example.com/cited": ["acme"]}
    index = {
        "https://example.com/cited": {"last_checked": "2026-10-25", "vendors": ["acme"]},
        "https://trust.mistral.ai/": {"last_attempt": "2026-10-21",
                                      "last_error": "only 0 chars of text (likely JavaScript-rendered)"},
        "https://x.ai/security": {"last_checked": "2026-10-21", "vendors": ["xai"], "last_error": None},
    }
    merged = merge_index_urls(dict(cited), index)
    assert set(merged) == set(index)
    assert merged["https://example.com/cited"] == ["acme"]
    assert merged["https://x.ai/security"] == ["xai"]
    assert merged["https://trust.mistral.ai/"] == []


def test_needs_render_covers_empty_shell_and_bot_wall():
    assert needs_render(200, 0)
    assert needs_render(200, 199)
    assert not needs_render(200, 200)
    assert needs_render(403, 5000)
    assert needs_render(401, 0)
    assert not needs_render(404, 0)
    assert not needs_render(500, 0)


def test_challenge_page_is_not_a_document():
    assert is_challenge("Attention Required! | Cloudflare\nPlease enable cookies")
    assert is_challenge("Just a moment...\nChecking your browser")
    assert not is_challenge("Security at Mistral AI\nWelcome to Mistral Trust Center")


if __name__ == "__main__":
    test_index_urls_are_not_dropped()
    test_needs_render_covers_empty_shell_and_bot_wall()
    test_challenge_page_is_not_a_document()
    print("ok")
