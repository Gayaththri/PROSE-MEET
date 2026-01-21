import numpy as np
import librosa


def extract_prosody(audio, sr=16000):
    """
    Extract basic prosodic features from audio.

    Returns:
    - pitch: fundamental frequency contour
    - energy: short-term energy
    - silence: boolean array indicating silence frames
    """

    # Pitch (fundamental frequency)
    pitch, voiced_flag, _ = librosa.pyin(
        audio,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C7")
    )

    # Replace NaNs in pitch with 0
    pitch = np.nan_to_num(pitch)

    # Energy (RMS)
    energy = librosa.feature.rms(y=audio)[0]

    # Silence detection
    silence_threshold = 0.01
    silence = np.abs(audio) < silence_threshold

    return {
        "pitch": pitch,
        "energy": energy,
        "silence": silence
    }
