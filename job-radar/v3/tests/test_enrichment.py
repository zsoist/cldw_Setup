"""Tests for Brave Search enrichment module."""
import pytest
from app.enrichment.brave_enrich import (
    should_enrich, _merge_fragments, _clean_html, _get_domain,
)


class TestShouldEnrich:
    def test_remote_unspecified_high_score(self):
        assert should_enrich({"remote_policy": "remote_unspecified", "score_composite": 60})

    def test_unknown_high_score(self):
        assert should_enrich({"remote_policy": "unknown", "score_composite": 40})

    def test_worldwide_skip(self):
        """Already classified — don't waste API calls."""
        assert not should_enrich({"remote_policy": "worldwide", "score_composite": 80})

    def test_low_score_skip(self):
        assert not should_enrich({"remote_policy": "remote_unspecified", "score_composite": 20})

    def test_hybrid_skip(self):
        assert not should_enrich({"remote_policy": "hybrid", "score_composite": 50})


class TestMergeFragments:
    def test_dedup_similar_sentences(self):
        frags = [
            "This is a remote job worldwide. Apply now and join our great team.",
            "This is a remote job worldwide. Full benefits package included for all employees.",
        ]
        merged = _merge_fragments(frags)
        # "This is a remote job worldwide." should appear only once
        assert merged.count("This is a remote job worldwide") == 1
        assert "join our great team" in merged
        assert "Full benefits" in merged

    def test_short_sentences_skipped(self):
        frags = ["OK.", "This is a meaningful sentence about the role."]
        merged = _merge_fragments(frags)
        assert "OK" not in merged
        assert "meaningful sentence" in merged

    def test_empty_fragments(self):
        assert _merge_fragments([]) == ""


class TestCleanHtml:
    def test_strip_tags(self):
        assert "Hello world" in _clean_html("<b>Hello</b> <i>world</i>")

    def test_strip_entities(self):
        assert _clean_html("a&amp;b") == "a b"


class TestGetDomain:
    def test_normal_url(self):
        assert _get_domain("https://example.com/path") == "example.com"

    def test_hn_url(self):
        assert _get_domain("https://news.ycombinator.com/item?id=123") == "news.ycombinator.com"
