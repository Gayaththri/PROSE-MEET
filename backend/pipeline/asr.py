import whisper


def transcribe_audio(audio):
    """
    Transcribe audio using Whisper and return timestamped segments.

    Returns:
    - List of dicts with: segment_id, start, end, text
    """

    # Load Whisper model (base is sufficient for IPD)
    model = whisper.load_model("base")

    # Run transcription
    result = model.transcribe(audio, fp16=False)

    segments = []
    for i, seg in enumerate(result["segments"]):
        segments.append({
            "segment_id": i,
            "start": float(seg["start"]),
            "end": float(seg["end"]),
            "text": seg["text"].strip()
        })

    return segments
