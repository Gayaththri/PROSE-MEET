import numpy as np


def compute_importance(aligned_segments):
    """
    Compute prosody-aware importance scores for each utterance.
    Importance is defined as deviation from meeting-level prosodic baselines.
    """

    if not aligned_segments:
        return []

    # Extract feature arrays
    pitch_var = np.array([seg["pitch_variance"] for seg in aligned_segments])
    energy = np.array([seg["mean_energy"] for seg in aligned_segments])
    pause = np.array([seg["pause_ratio"] for seg in aligned_segments])

    # Meeting-level statistics
    pitch_mean, pitch_std = np.mean(pitch_var), np.std(pitch_var) + 1e-6
    energy_mean, energy_std = np.mean(energy), np.std(energy) + 1e-6
    pause_mean, pause_std = np.mean(pause), np.std(pause) + 1e-6

    ranked_segments = []

    for seg in aligned_segments:
        z_pitch = abs((seg["pitch_variance"] - pitch_mean) / pitch_std)
        z_energy = abs((seg["mean_energy"] - energy_mean) / energy_std)
        z_pause = abs((seg["pause_ratio"] - pause_mean) / pause_std)

        # Weighted importance score
        importance_score = (
            0.4 * z_pitch +
            0.4 * z_energy +
            0.2 * z_pause
        )

        seg_with_score = seg.copy()
        seg_with_score["importance_score"] = float(importance_score)

        ranked_segments.append(seg_with_score)

    # Sort by importance (descending)
    ranked_segments.sort(
        key=lambda x: x["importance_score"],
        reverse=True
    )

    return ranked_segments

