import subprocess
import os
import uuid

# Explicit FFmpeg path (Windows-safe)
FFMPEG_PATH = r"C:\ffmpeg\bin\ffmpeg.exe"

def convert_to_wav(input_path, target_sr=16000):
    """
    Converts any audio format to WAV (16kHz, mono)
    Returns path to converted wav file
    """

    output_dir = "temp_audio"
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, f"{uuid.uuid4()}.wav")

    command = [
        FFMPEG_PATH,
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
