"""Tests for meeting domain detection and adaptation."""

from pipeline.domain import (
    apply_domain_adaptation,
    detect_domain,
    get_domain_focus_keywords,
    get_domain_importance_threshold,
)


def test_detect_domain_corporate_keywords():
    transcript = [{"text": "Let's review the quarterly budget, stakeholders, and project timeline."}]
    result = detect_domain(transcript)

    assert result["predicted_domain"] == "corporate"
    assert result["domain_method"] == "keyword"
    assert 0.0 < result["confidence"] <= 1.0
    assert result["domain_label"] == "Corporate"


def test_detect_domain_medical_keywords():
    transcript = [{"text": "Patient symptoms improved after adjusting medication and care plan."}]
    result = detect_domain(transcript)

    assert result["predicted_domain"] == "medical"
    assert result["adaptation_strategy"] == "Outcome-Focused"


def test_detect_domain_empty_transcript_defaults():
    result = detect_domain([])

    assert result["predicted_domain"] == "corporate"
    assert result["domain_method"] == "keyword"


def test_get_domain_focus_keywords_follows_prediction():
    domain_result = {"predicted_domain": "academic"}
    keywords = get_domain_focus_keywords(domain_result)

    assert "research" in keywords
    assert "thesis" in keywords


def test_get_domain_importance_threshold_is_bounded():
    for domain in ("corporate", "academic", "medical"):
        threshold = get_domain_importance_threshold(
            {"predicted_domain": domain, "confidence": 0.8}
        )
        assert 0.45 <= threshold <= 0.75


def test_apply_domain_adaptation_preserves_ordering_metadata(sample_segments):
    ranked = [
        {"text": s["text"], "importance_score": 0.9 - i * 0.1, "importance_reasons": []}
        for i, s in enumerate(sample_segments)
    ]
    domain_result = detect_domain([{"text": s["text"]} for s in sample_segments])

    adapted = apply_domain_adaptation(ranked, domain_result)

    assert len(adapted) == len(ranked)
    assert all("importance_score" in seg for seg in adapted)
    assert all("base_importance_score" in seg for seg in adapted)
    assert adapted[0]["importance_score"] >= adapted[-1]["importance_score"]
