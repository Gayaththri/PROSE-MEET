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

    audio, sr = preprocess_audio(audio_path)
    segments = transcribe_audio(audio)
    prosody = extract_prosody(audio)
    aligned = align_text_prosody(segments, prosody)
    ranked = compute_importance(aligned)

    return {
        "transcript": segments,
        "summary": generate_summary(ranked),
        "highlights": ranked[:5] if ranked else [],
        "speakers": compute_speaker_contribution(ranked)
    }
