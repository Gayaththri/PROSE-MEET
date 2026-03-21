import numpy as np
import librosa
import time


FRAME_LENGTH = 2048
HOP_LENGTH = 1024


def extract_prosody(audio, sr: int = 16000, timing_collector=None):
    """
    Extract lightweight prosodic features from audio.

    To keep processing fast on long meetings we avoid heavy
    fundamental frequency estimation (e.g. librosa.pyin) and
    instead compute:

    - pitch: approximated using spectral centroid (a proxy for
      brightness / pitch movement)
    - energy: short-term RMS energy
    - silence: frame-wise silence mask derived from energy

    All features are computed on the same frame grid controlled
    by FRAME_LENGTH / HOP_LENGTH, which downstream alignment
    code can use.
    """

    started = time.perf_counter()

    # Short-term energy
    energy = librosa.feature.rms(
        y=audio,
        frame_length=FRAME_LENGTH,
        hop_length=HOP_LENGTH,
    )[0]

    # Lightweight "pitch-like" contour using spectral centroid
    spectral_centroid = librosa.feature.spectral_centroid(
        y=audio,
        sr=sr,
        n_fft=FRAME_LENGTH,
        hop_length=HOP_LENGTH,
    )[0]

    # Simple silence detection from energy
    silence_threshold = float(np.percentile(energy, 10))
    silence = energy < silence_threshold

    result = {
        "pitch": spectral_centroid,
        "energy": energy,
        "silence": silence,
        "hop_length": HOP_LENGTH,
    }
    if timing_collector is not None:
        timing_collector.record_stage("prosody_extraction", time.perf_counter() - started)
    return result
