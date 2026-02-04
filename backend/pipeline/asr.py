import whisper

# Load model ONCE (very important for speed)
model = whisper.load_model("tiny")


def transcribe_audio(audio_path: str):
    """
    Transcribe full audio using Whisper (fast mode).
    Returns timestamped segments.
    """

    result = model.transcribe(
        audio_path,          
        fp16=False,          # CPU safe
        verbose=False,
        word_timestamps=False
    )

    segments = []
    for i, seg in enumerate(result["segments"]):
        segments.append({
            "segment_id": i,
            "start": float(seg["start"]),
            "end": float(seg["end"]),
            "text": seg["text"].strip(),
        })

    return segments
