"""
Normalizes input audio to 16kHz mono WAV (or skips when already compliant) and creates optional preview clips for fast pipeline processing.
"""
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

        info = sf.info(path)
        return int(info.samplerate) == 16000 and int(info.channels) == 1

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

    os.makedirs("temp_audio", exist_ok=True)
    output_path = f"temp_audio/{uuid.uuid4()}.wav"

    command = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-ac", "1",              # mono
        "-ar", str(target_sr),   # 16kHz
        output_path
    ]

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=300,
            text=True,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Audio conversion timed out after 5 minutes")
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip() or "(no stderr)"
        if len(stderr) > 500:
            stderr = stderr[:500] + "..."
        raise RuntimeError(f"FFmpeg conversion failed: {stderr}")

    if not os.path.exists(output_path):
        raise RuntimeError("Audio conversion failed: output file was not created")

    return output_path


def create_preview_clip(input_path: str, preview_seconds: int, target_sr: int = 16000) -> str:
    """
    Create a short 16kHz mono WAV clip from the start of the recording.
    """
    preview_seconds = int(max(1, preview_seconds))
    os.makedirs("temp_audio", exist_ok=True)
    output_path = f"temp_audio/{uuid.uuid4()}_preview.wav"
    command = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-t",
        str(preview_seconds),
        "-ac",
        "1",
        "-ar",
        str(target_sr),
        output_path,
    ]
    try:
        subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=300,
            text=True,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Preview audio conversion timed out after 5 minutes")
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip() or "(no stderr)"
        if len(stderr) > 500:
            stderr = stderr[:500] + "..."
        raise RuntimeError(f"Preview audio conversion failed: {stderr}")

    if not os.path.exists(output_path):
        raise RuntimeError("Preview audio conversion failed: output file was not created")

    return output_path
