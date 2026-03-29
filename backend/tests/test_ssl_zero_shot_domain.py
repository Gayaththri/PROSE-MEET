"""
Tests keyword and SSL zero-shot domain-detection paths, including routing behavior, predicted-domain correctness, and SSL score metadata output.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


class SSLZeroShotDomainTests(unittest.TestCase):
    def test_keyword_detect_includes_domain_method(self):
        from pipeline.domain import _detect_domain_keyword

        t = [{"text": "We discussed the project budget and deadline.", "start": 0.0, "end": 2.0}]
        r = _detect_domain_keyword(t)
        self.assertEqual(r["domain_method"], "keyword")
        self.assertEqual(r["predicted_domain"], "corporate")

    def test_keyword_detect_research_speech_meeting_is_academic(self):
        """Lexical path: speech/NLP lab discussion should not default to corporate."""
        from pipeline.domain import _detect_domain_keyword

        t = [
            {
                "text": (
                    "We need a database format linking word transcripts, annotations, "
                    "utterance boundaries, and forced alignment from the recognizer. "
                    "Frame-level prosody goes in a separate file; the lattice links segments."
                ),
                "start": 0.0,
                "end": 10.0,
            }
        ]
        r = _detect_domain_keyword(t)
        self.assertEqual(r["domain_method"], "keyword")
        self.assertEqual(r["predicted_domain"], "academic")

    def test_detect_domain_ssl_routing_medical(self):
        """SSL path: meeting embedding aligned with medical prototype wins."""
        os.environ["PROSE_DOMAIN_METHOD"] = "ssl_zero_shot"
        try:
            fake_protos = {
                "corporate": np.array([1.0, 0.0, 0.0], dtype=np.float32),
                "academic": np.array([0.0, 1.0, 0.0], dtype=np.float32),
                "medical": np.array([0.0, 0.0, 1.0], dtype=np.float32),
            }

            with patch("pipeline.ssl_zero_shot_domain._get_model", return_value=MagicMock()), patch(
                "pipeline.ssl_zero_shot_domain._get_proto_embeddings", return_value=fake_protos
            ), patch(
                "pipeline.ssl_zero_shot_domain._encode_long_text",
                return_value=np.array([0.0, 0.0, 1.0], dtype=np.float32),
            ):
                from pipeline.domain import detect_domain

                r = detect_domain(
                    [{"text": "patient treatment and diagnosis discussion", "start": 0.0, "end": 2.0}]
                )
            self.assertEqual(r["domain_method"], "ssl_zero_shot")
            self.assertEqual(r["predicted_domain"], "medical")
            self.assertIn("ssl_domain_scores", r)
        finally:
            os.environ.pop("PROSE_DOMAIN_METHOD", None)


if __name__ == "__main__":
    unittest.main()
