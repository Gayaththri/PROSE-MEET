"""
Extract prosodic signals (pitch proxy, energy, and silence) 
"""
import numpy as np
import librosa
import time

from .job_control import JobCancelledError


FRAME_LENGTH = 2048 #size of each analysis window
HOP_LENGTH = 1024 #how much to move forward between windows

# Process long audio in chunks so cancellation can be detected between librosa calls.
_PROSODY_CHUNK_SECONDS = 30.0


# Extract frame level prosody features: energy, pitch, and silence
def _extract_prosody_single(audio, sr: int, timing_collector, started: float):
    energy = librosa.feature.rms(
        y=audio,
        frame_length=FRAME_LENGTH,
        hop_length=HOP_LENGTH,
    )[0]

    spectral_centroid = librosa.feature.spectral_centroid(
        y=audio,
        sr=sr,
        n_fft=FRAME_LENGTH,
        hop_length=HOP_LENGTH,
    )[0]

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


def extract_prosody(audio, sr: int = 16000, timing_collector=None, cancel_checker=None):
    started = time.perf_counter()

    if len(audio) == 0:
        return {
            "pitch": np.array([]),
            "energy": np.array([]),
            "silence": np.array([]),
            "hop_length": HOP_LENGTH,
        }

    if cancel_checker is None:
        return _extract_prosody_single(audio, sr, timing_collector, started)

    chunk_samples = max(int(_PROSODY_CHUNK_SECONDS * sr), 1)
    energy_chunks = []
    pitch_chunks = []
    for start in range(0, len(audio), chunk_samples):
        if cancel_checker():
            raise JobCancelledError("Processing cancelled by user.")
        chunk = audio[start : start + chunk_samples]
        e = librosa.feature.rms(
            y=chunk,
            frame_length=FRAME_LENGTH,
            hop_length=HOP_LENGTH,
        )[0]
        sc = librosa.feature.spectral_centroid(
            y=chunk,
            sr=sr,
            n_fft=FRAME_LENGTH,
            hop_length=HOP_LENGTH,
        )[0]
        energy_chunks.append(e)
        pitch_chunks.append(sc)

    energy = np.concatenate(energy_chunks)
    spectral_centroid = np.concatenate(pitch_chunks)
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
