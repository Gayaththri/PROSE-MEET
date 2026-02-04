from .audio import preprocess_audio
from .asr import transcribe_audio
from .prosody import extract_prosody
from .alignment import align_text_prosody
from .importance import compute_importance
from .summary import generate_summary
from .speakers import compute_speaker_contribution


def run_gap1(audio_path: str) -> dict:
    """
    Runs Gap 1: Prosody-Aware Importance Detection
    """

    # Preprocess audio (returns waveform + sr)
    audio, sr = preprocess_audio(audio_path)

    # ASR (uses file path internally)
    segments = transcribe_audio(audio_path)

    # Prosody extraction (uses waveform)
    prosody = extract_prosody(audio)

    # Align text with prosody
    aligned = align_text_prosody(segments, prosody)

    # Importance scoring
    ranked = compute_importance(aligned)

    return {
        "transcript": segments,
        "summary": generate_summary(ranked),
        "highlights": ranked[:5] if ranked else [],
        "speakers": compute_speaker_contribution(ranked),
    }
