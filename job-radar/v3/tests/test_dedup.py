"""Tests for deduplication engine."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.dedup.engine import canonical_url, content_hash, normalize_for_fuzzy, fuzzy_match


class TestCanonicalUrl:
    def test_strip_tracking_params(self):
        url = "https://boards.greenhouse.io/company/jobs/123?utm_source=indeed&gh_jid=abc"
        canon = canonical_url(url)
        assert "utm_source" not in canon
        assert "gh_jid" not in canon
        assert "company/jobs/123" in canon

    def test_strip_www(self):
        url = "https://www.lever.co/company/job/456"
        canon = canonical_url(url)
        assert "www." not in canon

    def test_strip_trailing_slash(self):
        url1 = canonical_url("https://jobs.lever.co/company/")
        url2 = canonical_url("https://jobs.lever.co/company")
        assert url1 == url2

    def test_lowercase(self):
        url = "https://BOARDS.GREENHOUSE.IO/Company/Jobs/123"
        canon = canonical_url(url)
        assert canon == canon.lower()

    def test_preserve_meaningful_params(self):
        url = "https://example.com/jobs?department=engineering&location=remote"
        canon = canonical_url(url)
        assert "department" in canon
        assert "location" in canon


class TestContentHash:
    def test_same_content_same_hash(self):
        h1 = content_hash("ML Engineer", "Acme", "Build ML models")
        h2 = content_hash("ML Engineer", "Acme", "Build ML models")
        assert h1 == h2

    def test_different_content_different_hash(self):
        h1 = content_hash("ML Engineer", "Acme", "Build ML models")
        h2 = content_hash("Data Scientist", "Acme", "Analyze data")
        assert h1 != h2

    def test_whitespace_normalization(self):
        h1 = content_hash("ML  Engineer", "Acme  Corp", "Build   ML models")
        h2 = content_hash("ML Engineer", "Acme Corp", "Build ML models")
        assert h1 == h2

    def test_case_insensitive(self):
        h1 = content_hash("ML Engineer", "ACME", "Build ML Models")
        h2 = content_hash("ml engineer", "acme", "build ml models")
        assert h1 == h2


class TestFuzzyMatch:
    def test_exact_match(self):
        assert fuzzy_match("ML Engineer", "Acme", "ML Engineer", "Acme") is True

    def test_seniority_stripped(self):
        # "Senior" stripped, so these should match
        assert fuzzy_match("ML Engineer", "Acme", "Senior ML Engineer", "Acme") is True

    def test_different_roles_no_match(self):
        assert fuzzy_match("ML Engineer", "Acme", "Product Manager", "Acme") is False

    def test_different_companies_no_match(self):
        assert fuzzy_match("ML Engineer", "Acme", "ML Engineer", "Totally Different Corp") is False

    def test_normalize_for_fuzzy(self):
        norm = normalize_for_fuzzy("Senior ML Engineer II")
        assert "senior" not in norm
        assert "ii" not in norm


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
