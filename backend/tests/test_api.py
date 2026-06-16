"""FastAPI smoke tests (no Whisper model download)."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_client(mock_whisper_module):
    sys.modules["faster_whisper"] = mock_whisper_module

    with patch("pipeline.asr.preload_model", return_value=None):
        import main

        with TestClient(main.app) as client:
            yield client


def test_health_endpoint(api_client):
    response = api_client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "prose-meet-api"


def test_status_unknown_job(api_client):
    response = api_client.get("/status/does-not-exist")

    assert response.status_code == 200
    assert response.json()["status"] == "not_found"


def test_run_gap1_requires_file(api_client):
    response = api_client.post("/run-gap1")

    assert response.status_code == 400
    assert "file" in response.json()["detail"].lower()
