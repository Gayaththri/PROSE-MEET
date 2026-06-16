"""Converts raw meeting audio into a clean, consistent signal for ASR/prosody steps."""

import librosa
import numpy as np
import soundfile as sf


def preprocess_audio(audio_path: str, target_sr: int = 16000):

    try:
        audio, sr = sf.read(audio_path, dtype="float32", always_2d=False)
        if getattr(audio, "ndim", 1) > 1:
            audio = np.mean(audio, axis=1)
        if int(sr) != int(target_sr):
            audio = librosa.resample(audio, orig_sr=sr, target_sr=target_sr)
            sr = target_sr
    except Exception:
        audio, sr = librosa.load(audio_path, sr=target_sr, mono=True)

    # Normalise audio amplitude
    peak = float(np.max(np.abs(audio))) if len(audio) > 0 else 0.0
    if peak > 0:
        audio = audio / peak

    return audio, int(sr)
