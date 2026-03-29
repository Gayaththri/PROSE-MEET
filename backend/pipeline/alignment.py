"""Alignment helpers for transcript and prosody signals."""

import numpy as np


def align_text_prosody(segments, prosody_features, sr=16000):
    """
    Align transcript segments with prosodic features using time boundaries.
    """

    aligned_segments = []

    pitch = prosody_features["pitch"]
    energy = prosody_features["energy"]
    silence = prosody_features["silence"]
    hop_length = prosody_features.get("hop_length", 1)

    # All prosody features are computed on frames, not raw samples.
    # Convert segment start/end times into frame indices.
    num_frames = len(silence)

    for seg in segments:
        start_frame = int(seg["start"] * sr / hop_length)
        end_frame = int(seg["end"] * sr / hop_length)

        # Safety checks
        start_frame = max(0, start_frame)
        end_frame = min(num_frames, end_frame)

        # Use at least one frame when segment is very short so we don't drop segments
        if end_frame <= start_frame:
            end_frame = min(start_frame + 1, num_frames)

        seg_pitch = pitch[start_frame:end_frame]
        seg_energy = energy[start_frame:end_frame]
        seg_silence = silence[start_frame:end_frame]

        aligned_segments.append({
            "segment_id": seg["segment_id"],
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"],
            "asr_confidence": seg.get("asr_confidence"),
            "asr_avg_logprob": seg.get("asr_avg_logprob"),
            "asr_no_speech_prob": seg.get("asr_no_speech_prob"),
            "asr_compression_ratio": seg.get("asr_compression_ratio"),
            "mean_pitch": float(np.mean(seg_pitch)) if len(seg_pitch) > 0 else 0.0,
            "pitch_variance": float(np.var(seg_pitch)) if len(seg_pitch) > 0 else 0.0,
            "mean_energy": float(np.mean(seg_energy)) if len(seg_energy) > 0 else 0.0,
            "pause_ratio": float(np.mean(seg_silence)) if len(seg_silence) > 0 else 0.0
        })

    return aligned_segments
