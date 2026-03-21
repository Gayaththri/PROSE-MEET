import io
import unittest
import os
import sys
from unittest.mock import patch

from fastapi.testclient import TestClient

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import main
from jobs import create_job, get_job, update_job_progress


class ApiFlowTests(unittest.TestCase):
    def test_run_gap1_to_result_flow(self):
        def fake_process(
            job_id: str,
            input_audio_path: str,
            filename: str = None,
            preview: bool = False,
            preview_seconds=None,
            related_job_id=None,
        ):
            result = {
                "transcript": [{"start": 0.0, "end": 1.0, "text": "hello world", "importance_score": 0.8}],
                "summary": "hello world",
                "speaker_summaries": [{"speaker": "Speaker_1", "summary": "hello world"}],
                "highlights": [{"start": 0.0, "end": 1.0, "text": "hello world", "importance_score": 0.8}],
                "duration_seconds": 1.0,
                "domain": {
                    "predicted_domain": "corporate",
                    "confidence": 0.8,
                    "adaptation_strategy": "Decision-Focused",
                    "domain_label": "Corporate",
                },
            }
            main.complete_job(job_id, result, filename=filename)

        with patch.object(main, "preload_model", lambda: None):
            with patch.object(main, "process_gap1_job", side_effect=fake_process):
                with TestClient(main.app) as client:
                    files = {"file": ("meeting.wav", io.BytesIO(b"RIFF....WAVE"), "audio/wav")}
                    run_resp = client.post("/run-gap1", files=files)
                    self.assertEqual(run_resp.status_code, 200)
                    body = run_resp.json()
                    self.assertEqual(body.get("status"), "queued")
                    job_id = body.get("job_id")
                    self.assertTrue(job_id)

                    status_resp = client.get(f"/status/{job_id}")
                    self.assertEqual(status_resp.status_code, 200)
                    self.assertEqual(status_resp.json().get("status"), "completed")

                    result_resp = client.get(f"/result/{job_id}")
                    self.assertEqual(result_resp.status_code, 200)
                    payload = result_resp.json()
                    self.assertIn("summary", payload)
                    self.assertIn("highlights", payload)
                    self.assertIn("domain", payload)
                    self.assertIsNotNone(get_job(job_id))

    def test_status_exposes_additive_progress_fields(self):
        job_id = create_job(filename="meeting.wav")
        update_job_progress(
            job_id,
            status="processing",
            stage="transcribing",
            stage_label="Transcribing meeting",
            progress=0.4,
            eta_seconds=12.0,
            partial_result={"transcript": [], "is_partial": True},
        )

        with patch.object(main, "preload_model", lambda: None):
            with TestClient(main.app) as client:
                status_resp = client.get(f"/status/{job_id}")
                self.assertEqual(status_resp.status_code, 200)
                payload = status_resp.json()
                self.assertEqual(payload.get("status"), "processing")
                self.assertEqual(payload.get("stage"), "transcribing")
                self.assertEqual(payload.get("stage_label"), "Transcribing meeting")
                self.assertAlmostEqual(payload.get("progress"), 0.4)
                self.assertIn("partial_result", payload)

    def test_cancel_endpoint_marks_job(self):
        job_id = create_job(filename="meeting.wav")
        with patch.object(main, "preload_model", lambda: None):
            with TestClient(main.app) as client:
                cancel_resp = client.post(f"/jobs/{job_id}/cancel")
                self.assertEqual(cancel_resp.status_code, 200)
                payload = cancel_resp.json()
                self.assertTrue(payload.get("cancel_requested"))
                status_resp = client.get(f"/status/{job_id}")
                status_payload = status_resp.json()
                self.assertEqual(status_payload.get("status"), "cancelled")


if __name__ == "__main__":
    unittest.main()
