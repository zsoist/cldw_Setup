"""Tests for conversation engine search helpers.

Tests the _extract_search_terms function in isolation (no DB deps).
"""
import re
import sys
from unittest.mock import MagicMock

# Stub heavy modules before importing conversation
sys.modules.setdefault('asyncpg', MagicMock())
sys.modules.setdefault('telegram', MagicMock())
sys.modules.setdefault('telegram.ext', MagicMock())
sys.modules.setdefault('httpx', MagicMock())

from app.telegram.conversation import _extract_search_terms


class TestExtractSearchTerms:
    def test_single_tech_term(self):
        like, tech = _extract_search_terms("python")
        assert "%python%" in like
        assert "python" in tech

    def test_multi_word_tech(self):
        like, tech = _extract_search_terms("python machine learning")
        assert "machine learning" in tech
        assert "python" in tech
        assert "%machine learning%" in like
        assert "%python%" in like

    def test_noise_words_stripped(self):
        like, tech = _extract_search_terms("RAG jobs")
        assert "rag" in tech
        assert "jobs" not in tech

    def test_full_query_in_like(self):
        like, tech = _extract_search_terms("pytorch startup")
        assert "%pytorch startup%" in like  # full query always included
        assert "%pytorch%" in like
        assert "%startup%" in like

    def test_location_noise_stripped(self):
        like, tech = _extract_search_terms("remote python jobs")
        assert "python" in tech
        assert "remote" not in tech
        assert "jobs" not in tech

    def test_empty_after_noise(self):
        like, tech = _extract_search_terms("remote jobs")
        # Both are noise words, so tech is empty
        assert tech == []

    def test_spanish_noise(self):
        like, tech = _extract_search_terms("buscar trabajos de python")
        assert "python" in tech
        assert "buscar" not in tech
        assert "trabajos" not in tech
        assert "de" not in tech
