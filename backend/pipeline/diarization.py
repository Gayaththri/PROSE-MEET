"""
Voice-based speaker diarization using pyannote.audio.

Pipeline: VAD (in pyannote) → speaker embeddings → clustering → labeling.
Uses preprocessed mono 16 kHz audio when provided for best accuracy.
Requires HUGGINGFACE_TOKEN and accepting conditions for pyannote/speaker-diarization-3.1.
Falls back to pause-based estimation if unavailable.
"""
from __future__ import annotations

import logging
import os
import time
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Optional: only import when used so rest of app works without pyannote
_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is not None:
        return _pipeline
    token = os.getenv("HUGGINGFACE_TOKEN") or os.getenv("HF_TOKEN")
    try:
        from pyannote.audio import Pipeline
        # Support both legacy use_auth_token and current token (huggingface_hub)
        load_kw = {"use_auth_token": token} if token else {"use_auth_token": True}
        try:
            _pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                **load_kw,
            )
        except TypeError:
            load_kw = {"token": token} if token else {}
            _pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                **load_kw,
            )
        # Use GPU if available
        try:
            import torch
            if torch.cuda.is_available():
                _pipeline.to(torch.device("cuda"))
        except Exception:
            pass
        return _pipeline
    except Exception as e:
        logger.info(
            "Speaker diarization unavailable (%s). Using pause-based speaker estimation. "
            "Set HUGGINGFACE_TOKEN and accept model conditions to enable voice-based diarization.",
            e,
        )
        return None


def preload_pipeline():
    return _get_pipeline()


def reset_pipeline_cache():
    global _pipeline
    _pipeline = None


def diarize_audio(
    audio_path: Optional[str] = None,
    waveform: Optional[np.ndarray] = None,
    sample_rate: Optional[int] = None,
    num_speakers: Optional[int] = None,
    min_speakers: Optional[int] = None,
    max_speakers: Optional[int] = None,
    timing_collector=None,
) -> Optional[List[Tuple[float, float, str]]]:
    """
    Run speaker diarization (VAD → embeddings → clustering → labels).

    Prefer passing preprocessed mono 16 kHz audio for best accuracy:
    - waveform: (n_samples,) float array
    - sample_rate: 16000 recommended

    If waveform/sample_rate are omitted, uses audio_path (pyannote will load and resample).

    Returns a list of (start_sec, end_sec, speaker_id) in chronological order.
    Returns None if diarization is unavailable or fails.
    """
    pipeline_loaded_before = _pipeline is not None
    load_started = time.perf_counter()
    pipeline = _get_pipeline()
    if timing_collector is not None and pipeline is not None and not pipeline_loaded_before:
        timing_collector.record_stage(
            "diarization_model_load",
            time.perf_counter() - load_started,
        )
    if pipeline is None:
        return None
    if waveform is None and audio_path is None:
        return None
    try:
        started = time.perf_counter()
        kwargs = {}
        if num_speakers is not None:
            kwargs["num_speakers"] = num_speakers
        if min_speakers is not None:
            kwargs["min_speakers"] = min_speakers
        if max_speakers is not None:
            kwargs["max_speakers"] = max_speakers

        if waveform is not None and sample_rate is not None and len(waveform) > 0:
            import torch
            # pyannote expects (channel, time); mono -> (1, n_samples)
            if isinstance(waveform, np.ndarray):
                wav_tensor = torch.from_numpy(waveform).float()
            else:
                wav_tensor = torch.tensor(waveform, dtype=torch.float32)
            if wav_tensor.dim() == 1:
                wav_tensor = wav_tensor.unsqueeze(0)
            input_dict = {"waveform": wav_tensor, "sample_rate": sample_rate}
            diarization = pipeline(input_dict, **kwargs)
        else:
            diarization = pipeline(audio_path, **kwargs)

        segments = []
        for segment, track, speaker in diarization.itertracks(yield_label=True):
            segments.append((float(segment.start), float(segment.end), speaker))
        segments.sort(key=lambda x: (x[0], x[1]))
        n_speakers = len(set(sp for _, _, sp in segments))
        if timing_collector is not None:
            timing_collector.record_stage(
                "diarization_decode",
                time.perf_counter() - started,
                speaker_count=n_speakers,
            )
        if n_speakers < 2:
            logger.debug(
                "Diarization returned %d speaker(s); falling back to pause-based estimation.",
                n_speakers,
            )
        return segments if segments else None
    except Exception as e:
        logger.debug("Diarization failed: %s", e)
        return None


def assign_speakers_to_segments(
    asr_segments: List[dict],
    diarization_segments: List[Tuple[float, float, str]],
) -> None:
    """
    Assign each ASR segment to the diarization speaker with the largest overlap.
    Modifies asr_segments in place, setting "speaker" to a normalized label
    (Speaker_1, Speaker_2, ...) by order of first appearance.
    """
    if not diarization_segments or not asr_segments:
        for seg in asr_segments:
            seg["speaker"] = seg.get("speaker", "Speaker_1")
        return

    # Build ordered list of unique speaker IDs (order of first appearance)
    seen = []
    for _, _, sp in diarization_segments:
        if sp not in seen:
            seen.append(sp)
    raw_to_normalized = {sp: f"Speaker_{i + 1}" for i, sp in enumerate(seen)}

    for seg in asr_segments:
        start = seg["start"]
        end = seg["end"]
        best_speaker = None
        best_overlap = 0.0
        for d_start, d_end, speaker in diarization_segments:
            overlap_start = max(start, d_start)
            overlap_end = min(end, d_end)
            if overlap_end > overlap_start:
                overlap = overlap_end - overlap_start
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_speaker = speaker
        if best_speaker is not None:
            seg["speaker"] = raw_to_normalized[best_speaker]
        else:
            # No overlapping diarization: assign to closest segment by segment center
            mid = (start + end) / 2
            for d_start, d_end, speaker in diarization_segments:
                if d_start <= mid <= d_end:
                    seg["speaker"] = raw_to_normalized[speaker]
                    break
            else:
                seg["speaker"] = raw_to_normalized[diarization_segments[0][2]]
    return
