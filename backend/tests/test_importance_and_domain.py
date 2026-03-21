import unittest
import os
import sys
from unittest.mock import patch

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from pipeline.domain import apply_domain_adaptation
from pipeline.importance import compute_importance
from pipeline.summary import generate_summary, top_substantive_highlights


class ImportanceDomainTests(unittest.TestCase):
    def test_short_filler_is_downweighted(self):
        segments = [
            {
                "segment_id": "a",
                "start": 0.0,
                "end": 1.0,
                "text": "I don't know",
                "pitch_variance": 5.0,
                "mean_energy": 5.0,
                "pause_ratio": 0.5,
            },
            {
                "segment_id": "b",
                "start": 1.0,
                "end": 4.0,
                "text": "We need to finalize the deadline by Friday",
                "pitch_variance": 2.0,
                "mean_energy": 2.0,
                "pause_ratio": 0.2,
            },
        ]
        ranked = compute_importance(segments)
        by_id = {s["segment_id"]: s for s in ranked}
        self.assertGreater(by_id["b"]["importance_score"], by_id["a"]["importance_score"])

    def test_domain_adaptation_boosts_domain_relevant_segments(self):
        base = [
            {
                "segment_id": "x",
                "text": "We should discuss agenda and budget for this quarter",
                "importance_score": 0.5,
                "importance_reasons": [],
                "start": 0.0,
                "end": 2.0,
            },
            {
                "segment_id": "y",
                "text": "Nice to meet you all",
                "importance_score": 0.5,
                "importance_reasons": [],
                "start": 2.0,
                "end": 3.0,
            },
        ]
        domain = {"predicted_domain": "corporate", "confidence": 0.9}
        adapted = apply_domain_adaptation(base, domain)
        by_id = {s["segment_id"]: s for s in adapted}
        self.assertGreater(by_id["x"]["importance_score"], by_id["y"]["importance_score"])
        self.assertGreater(by_id["x"]["domain_relevance_hits"], 0)

    def test_highlights_respect_focus_keywords(self):
        ranked = [
            {"text": "patient treatment plan updated", "importance_score": 0.7, "start": 0.0, "end": 1.0},
            {"text": "team meeting went well", "importance_score": 0.8, "start": 1.0, "end": 2.0},
        ]
        out = top_substantive_highlights(ranked, n=1, focus_keywords=["patient", "treatment"])
        self.assertEqual(len(out), 1)
        self.assertIn("patient", out[0]["text"])

    def test_generate_summary_returns_full_meeting_output(self):
        ranked = [
            {
                "text": "Today is our kickoff meeting for the remote control project and we reviewed the agenda.",
                "importance_score": 0.6,
                "start": 0.0,
                "end": 4.0,
            },
            {
                "text": "Team members introduced themselves and described their roles on the project.",
                "importance_score": 0.5,
                "start": 5.0,
                "end": 8.0,
            },
            {
                "text": "We discussed the need for a simple remote with fewer buttons, clear layout, and longer battery life.",
                "importance_score": 0.9,
                "start": 9.0,
                "end": 14.0,
            },
            {
                "text": "Next steps are for each role to complete individual work and receive instructions by email before the next meeting.",
                "importance_score": 0.8,
                "start": 15.0,
                "end": 20.0,
            },
        ]
        out = generate_summary(ranked)
        self.assertIn("kickoff meeting", out.lower())
        self.assertIn("simple remote", out.lower())
        self.assertIn("individual work", out.lower())
        self.assertIn("next meeting", out.lower())
        self.assertNotIn("1) Meeting objective", out)

    def test_generate_summary_falls_back_when_ai_unavailable(self):
        ranked = [
            {
                "text": "We are starting the kickoff meeting for a remote control project.",
                "importance_score": 0.7,
                "start": 0.0,
                "end": 2.0,
            },
            {
                "text": "Next steps are to send instructions by email before the next meeting.",
                "importance_score": 0.8,
                "start": 3.0,
                "end": 5.0,
            },
        ]
        with patch("pipeline.summary.try_generate_ai_summary", return_value=None):
            out = generate_summary(ranked)
        self.assertIn("kickoff meeting", out.lower())
        self.assertIn("next meeting", out.lower())


if __name__ == "__main__":
    unittest.main()
