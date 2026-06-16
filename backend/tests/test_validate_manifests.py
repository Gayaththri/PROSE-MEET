"""Tests for manifest validation."""

import csv
import os

from validate_manifests import validate_manifest


def test_validate_manifest_missing_file(tmp_path):
    manifest = tmp_path / "bad.csv"
    manifest.write_text(
        "id,audio_path,transcript_ref_path,summary_ref_path,domain,split\n"
        "m1,missing.wav,transcript.txt,summary.txt,corporate,test\n",
        encoding="utf-8",
    )

    result = validate_manifest(str(manifest), str(tmp_path))

    assert result["valid"] is False
    assert result["rows"] == 1
    assert len(result["missing_files"]) >= 1


def test_validate_manifest_valid_row(tmp_path):
    audio = tmp_path / "clip.wav"
    transcript = tmp_path / "transcript.txt"
    summary = tmp_path / "summary.txt"
    audio.write_bytes(b"RIFF")
    transcript.write_text("hello", encoding="utf-8")
    summary.write_text("summary", encoding="utf-8")

    manifest = tmp_path / "good.csv"
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "id",
                "audio_path",
                "transcript_ref_path",
                "summary_ref_path",
                "domain",
                "split",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "id": "m1",
                "audio_path": "clip.wav",
                "transcript_ref_path": "transcript.txt",
                "summary_ref_path": "summary.txt",
                "domain": "corporate",
                "split": "test",
            }
        )

    result = validate_manifest(str(manifest), str(tmp_path))

    assert result["valid"] is True
    assert result["rows"] == 1
    assert result["missing_files"] == []
