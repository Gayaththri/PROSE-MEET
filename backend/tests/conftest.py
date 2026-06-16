"""Shared pytest fixtures for PROSE-MEET backend."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

# Run tests from backend/; ensure imports resolve.
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

# Avoid downloading Whisper / torch-heavy stacks during API import tests.
os.environ.setdefault("PROSE_DOMAIN_METHOD", "keyword")


@pytest.fixture(autouse=True)
def keyword_domain_method(monkeypatch):
    """Keep domain detection on the fast lexical path in CI."""
    monkeypatch.setenv("PROSE_DOMAIN_METHOD", "keyword")


@pytest.fixture
def sample_segments():
    return [
        {
            "text": "We need to finalize the budget by Friday and assign action items.",
            "pitch_variance": 0.12,
            "mean_energy": 0.45,
            "pause_ratio": 0.08,
            "start": 0.0,
            "end": 4.2,
            "asr_confidence": 0.92,
        },
        {
            "text": "okay",
            "pitch_variance": 0.02,
            "mean_energy": 0.15,
            "pause_ratio": 0.01,
            "start": 4.2,
            "end": 4.6,
            "asr_confidence": 0.88,
        },
        {
            "text": "The patient vitals improved after adjusting the medication dosage.",
            "pitch_variance": 0.09,
            "mean_energy": 0.38,
            "pause_ratio": 0.05,
            "start": 4.6,
            "end": 9.0,
            "asr_confidence": 0.90,
        },
    ]


@pytest.fixture
def mock_whisper_module():
    """Stub faster_whisper so main.py can import without GPU/model downloads."""
    mock_module = MagicMock()
    mock_module.WhisperModel = MagicMock()
    return mock_module
