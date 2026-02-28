"""Tests for deterministic scoring engine."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.scoring.rules import (
    score_job, score_opportunity, score_junior, score_colombia,
    extract_tech_stack, parse_salary, parse_yoe, detect_seniority,
    detect_remote_policy, count_requirements, is_hidden_junior,
    compute_composite, confidence_level,
)


class TestExtractors:
    def test_tech_stack_ai(self):
        ai, adj = extract_tech_stack("We use Python, PyTorch, and CUDA for deep learning")
        assert 'python' in ai
        assert 'pytorch' in ai
        assert 'cuda' in ai
        assert 'deep learning' in ai

    def test_tech_stack_adjacent(self):
        ai, adj = extract_tech_stack("Docker, Kubernetes, AWS, Redis")
        assert 'docker' in adj
        assert 'kubernetes' in adj
        assert 'aws' in adj

    def test_parse_salary_range(self):
        low, high = parse_salary("Salary: $120,000 - $180,000")
        assert low == 120000
        assert high == 180000

    def test_parse_salary_k(self):
        low, high = parse_salary("$120K-$180K")
        assert low == 120000
        assert high == 180000

    def test_parse_salary_none(self):
        low, high = parse_salary("Competitive compensation")
        assert low is None
        assert high is None

    def test_parse_yoe_range(self):
        mn, mx = parse_yoe("3-5 years of experience")
        assert mn == 3
        assert mx == 5

    def test_parse_yoe_plus(self):
        mn, mx = parse_yoe("5+ years experience in ML")
        assert mn == 5

    def test_parse_yoe_none(self):
        mn, mx = parse_yoe("No experience required")
        assert mn is None
        assert mx is None

    def test_detect_seniority_junior(self):
        assert detect_seniority("Junior ML Engineer", "") == 'junior'

    def test_detect_seniority_senior(self):
        assert detect_seniority("Senior AI Engineer", "") == 'senior'

    def test_detect_seniority_staff(self):
        assert detect_seniority("Staff ML Engineer", "") == 'staff'

    def test_detect_remote_worldwide(self):
        assert detect_remote_policy("Fully remote, anywhere in the world") == 'worldwide'

    def test_detect_remote_americas(self):
        assert detect_remote_policy("Remote (Americas timezone)") == 'americas'

    def test_detect_remote_us_only(self):
        assert detect_remote_policy("US only, must be located in US") == 'us_only'

    def test_count_requirements_bullets(self):
        text = """Requirements:
- Python proficiency
- ML experience
- Good communication
Nice to have:
- PyTorch
"""
        assert count_requirements(text) == 3


class TestScoring:
    def test_high_opportunity_ai_funded(self):
        score, signals = score_opportunity(
            "ML Engineer",
            "We use Python, PyTorch, and CUDA. Series A funded. $150K-$200K salary.",
            "AI Startup"
        )
        assert score >= 70
        assert signals >= 3

    def test_low_opportunity_crypto(self):
        score, signals = score_opportunity(
            "Blockchain Developer",
            "Build DeFi protocols with web3 and smart contracts",
            "CryptoDAO"
        )
        assert score < 40

    def test_junior_accessible(self):
        score, signals = score_junior(
            "Junior ML Engineer",
            "0-2 years experience. Mentorship program. Entry-level welcome."
        )
        assert score >= 70

    def test_senior_not_junior(self):
        score, signals = score_junior(
            "Senior Staff ML Engineer",
            "10+ years of experience required. Lead a team of 15 engineers."
        )
        assert score < 30

    def test_colombia_worldwide(self):
        score, signals = score_colombia(
            "Fully remote, worldwide. Async culture. Contractor OK via Deel."
        )
        assert score >= 70

    def test_colombia_blocked(self):
        score, signals = score_colombia(
            "US only. Must have US work authorization. Security clearance required."
        )
        assert score == 0

    def test_colombia_americas(self):
        score, signals = score_colombia(
            "Remote, Americas timezone. LATAM welcome. B2B contractor."
        )
        assert score >= 70

    def test_composite_weights(self):
        # 30% opp + 40% junior + 30% colombia
        assert compute_composite(100, 100, 100) == 100
        assert compute_composite(0, 0, 0) == 0
        assert compute_composite(50, 50, 50) == 50

    def test_confidence_levels(self):
        assert confidence_level(0) == 'low'
        assert confidence_level(1) == 'medium'
        assert confidence_level(3) == 'high'


class TestHiddenJunior:
    def test_hidden_junior_detected(self):
        # No seniority in title, good JA score, few requirements
        assert is_hidden_junior(
            "AI Engineer",
            "Python, PyTorch. 3 requirements.",
            65
        ) is True

    def test_not_hidden_when_senior_title(self):
        assert is_hidden_junior(
            "Senior AI Engineer",
            "Python, PyTorch.",
            65
        ) is False

    def test_not_hidden_when_low_score(self):
        assert is_hidden_junior(
            "AI Engineer",
            "Python, PyTorch.",
            40
        ) is False


class TestScoreJob:
    def test_full_pipeline_good_match(self):
        result = score_job(
            "ML Engineer",
            "Python, PyTorch, deep learning. Remote worldwide. "
            "0-2 years. Mentorship. Series A. $130K-$170K. Contractor OK via Deel.",
            "AI Startup"
        )
        assert result.composite >= 60
        assert result.method == 'rules'
        assert 'python' in result.tech_stack
        assert result.remote_policy == 'worldwide'
        assert result.contractor_ok is True

    def test_full_pipeline_bad_match(self):
        result = score_job(
            "Senior Director of Engineering",
            "10+ years. US only. Security clearance. Lead 50 engineers. "
            "Blockchain and DeFi focus.",
            "CryptoBank"
        )
        assert result.composite < 30
        assert result.colombia == 0

    def test_full_pipeline_hidden_junior(self):
        result = score_job(
            "AI Engineer",
            "Python, machine learning, NLP. Remote Americas. "
            "No strict experience requirement. We value curiosity. "
            "Mentorship available. LATAM welcome.",
            "NLP Startup"
        )
        assert result.hidden_junior is True


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
