"""Tests for apply info parser."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.scoring.apply_parser import parse_apply_info


class TestApplyParser:
    def test_greenhouse_url(self):
        result = parse_apply_info(
            "https://boards.greenhouse.io/company/jobs/123",
            "Apply on our website", "greenhouse"
        )
        assert result["apply_method"] == "ats_form"
        assert "#app" in result["apply_url"]
        assert "Greenhouse" in result["apply_notes"]

    def test_lever_url(self):
        result = parse_apply_info(
            "https://jobs.lever.co/company/abc-def",
            "Apply via Lever", "lever"
        )
        assert result["apply_method"] == "ats_form"
        assert "/apply" in result["apply_url"]

    def test_ashby_url(self):
        result = parse_apply_info(
            "https://jobs.ashbyhq.com/company/123",
            "Apply via Ashby", "ashby"
        )
        assert result["apply_method"] == "ats_form"
        assert "Ashby" in result["apply_notes"]

    def test_workable_url(self):
        result = parse_apply_info(
            "https://apply.workable.com/company/j/abc/",
            "Apply online", "workable"
        )
        assert result["apply_method"] == "ats_form"
        assert "Workable" in result["apply_notes"]

    def test_wellfound_url(self):
        result = parse_apply_info(
            "https://wellfound.com/company/jobs/123",
            "Apply on Wellfound", ""
        )
        assert result["apply_method"] == "ats_form"
        assert "Wellfound" in result["apply_notes"]

    def test_email_apply(self):
        result = parse_apply_info(
            "https://example.com/job",
            "Send your resume to hiring@company.com", ""
        )
        assert result["apply_method"] == "email"
        assert "hiring@company.com" in result["apply_url"]

    def test_custom_apply_link(self):
        result = parse_apply_info(
            "https://example.com/job",
            "Apply here: https://custom-apply.com/form/123", ""
        )
        assert result["apply_method"] == "custom"
        assert "custom-apply.com" in result["apply_url"]

    def test_unknown_url(self):
        result = parse_apply_info(
            "https://randomsite.com/jobs/456",
            "Interesting role for AI engineers", ""
        )
        assert result["apply_method"] == "unknown"
        assert result["apply_url"] == "https://randomsite.com/jobs/456"

    def test_lever_already_has_apply(self):
        result = parse_apply_info(
            "https://jobs.lever.co/company/abc/apply",
            "", "lever"
        )
        assert result["apply_url"] == "https://jobs.lever.co/company/abc/apply"
        assert "/apply/apply" not in result["apply_url"]


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
