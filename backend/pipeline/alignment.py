import numpy as np


def align_text_prosody(segments, prosody_features, sr=16000):
    """
    Align transcript segments with prosodic features using time boundaries.
    """

    aligned_segments = []

    pitch = prosody_features["pitch"]
    energy = prosody_features["energy"]
    silence = prosody_features["silence"]

    audio_length = len(silence)

    for seg in segments:
        start_sample = int(seg["start"] * sr)
        end_sample = int(seg["end"] * sr)

        # Safety checks
        start_sample = max(0, start_sample)
        end_sample = min(audio_length, end_sample)

        if end_sample <= start_sample:
            continue

        seg_pitch = pitch[start_sample:end_sample]
        seg_energy = energy[start_sample:end_sample]
        seg_silence = silence[start_sample:end_sample]

        aligned_segments.append({
            "segment_id": seg["segment_id"],
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"],
            "mean_pitch": float(np.mean(seg_pitch)) if len(seg_pitch) > 0 else 0.0,
            "pitch_variance": float(np.var(seg_pitch)) if len(seg_pitch) > 0 else 0.0,
            "mean_energy": float(np.mean(seg_energy)) if len(seg_energy) > 0 else 0.0,
            "pause_ratio": float(np.mean(seg_silence)) if len(seg_silence) > 0 else 0.0
        })

    return aligned_segments
