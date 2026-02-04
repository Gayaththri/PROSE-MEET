import subprocess
import os
import uuid
import soundfile as sf


def is_16k_mono_wav(path: str) -> bool:
    """
    Check if audio is already WAV, 16kHz, mono
    """
    try:
        if not path.lower().endswith(".wav"):
            return False

        data, sr = sf.read(path)
        is_mono = len(data.shape) == 1
        return sr == 16000 and is_mono

    except Exception:
        return False


def convert_to_wav(input_path: str, target_sr: int = 16000) -> str:
    """
    Converts audio to WAV (16kHz, mono) ONLY if needed.
    Returns path to WAV file.
    """

    # ✅ Skip conversion if already correct format
    if is_16k_mono_wav(input_path):
        print("✔ Audio already 16kHz mono WAV. Skipping FFmpeg.")
        return input_path

    output_path = f"temp_audio/{uuid.uuid4()}.wav"

    command = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-ac", "1",              # mono
        "-ar", str(target_sr),   # 16kHz
        output_path
    ]

    subprocess.run(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True
    )

    if not os.path.exists(output_path):
        raise RuntimeError("Audio conversion failed")

    return output_path
