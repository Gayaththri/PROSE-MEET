"""Tests for utterance importance scoring."""

from pipeline.importance import compute_importance


def test_compute_importance_ranks_substantive_above_filler(sample_segments):
    ranked = compute_importance(sample_segments)

    assert len(ranked) == 3
    texts = [seg["text"] for seg in ranked]
    assert texts[0] != "okay"
    assert ranked[0]["importance_score"] >= ranked[-1]["importance_score"]


def test_compute_importance_adds_explainability_fields(sample_segments):
    ranked = compute_importance(sample_segments)

    for seg in ranked:
        assert "importance_score" in seg
        assert "importance_reasons" in seg
        assert isinstance(seg["importance_reasons"], list)
        assert seg["pitch_variation_level"] in ("Low", "Medium", "High")
        assert seg["energy_level"] in ("Low", "Medium", "High")
        assert isinstance(seg["pause_emphasis"], bool)


def test_compute_importance_empty_input():
    assert compute_importance([]) == []
