import librosa
import numpy as np


def preprocess_audio(audio_path: str, target_sr: int = 16000):
    """
    Load and preprocess meeting audio.
    
    Steps:
    - Load audio
    - Convert to mono
    - Resample to target sample rate
    - Normalise amplitude
    
    Returns:
    - audio (np.ndarray)
    - sample_rate (int)
    """

    # Load audio file
    audio, sr = librosa.load(audio_path, sr=target_sr, mono=True)

    # Normalise audio amplitude
    if np.max(np.abs(audio)) > 0:
        audio = audio / np.max(np.abs(audio))

    return audio, target_sr
