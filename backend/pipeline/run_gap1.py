import concurrent.futures

from .audio import preprocess_audio
from .asr import transcribe_audio
from .prosody import extract_prosody
from .alignment import align_text_prosody
from .importance import compute_importance
from .summary import generate_summary, generate_speaker_summaries, top_substantive_highlights
from .speakers import compute_speaker_contribution


def run_gap1(audio_path: str) -> dict:
    """
    Runs Gap 1: Prosody-Aware Importance Detection
    """

    # Preprocess audio once (returns waveform + sr)
    audio, sr = preprocess_audio(audio_path)

    # Run ASR and prosody extraction in parallel to reduce total time
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_asr = executor.submit(transcribe_audio, audio_path, "en")
        future_prosody = executor.submit(extract_prosody, audio)
        segments = future_asr.result()
        prosody = future_prosody.result()

    # Align text with prosody
    aligned = align_text_prosody(segments, prosody, sr=sr)

    # Importance scoring
    ranked = compute_importance(aligned)

    # Speaker grouping + contribution also annotates segments with "speaker"
    speakers = compute_speaker_contribution(ranked)

    # Transcript: prosody-annotated segments in chronological order (so UI has importance_score)
    transcript_chronological = sorted(ranked, key=lambda x: x["start"])

    return {
        "transcript": transcript_chronological,
        # Overall summary (all speakers)
        "summary": generate_summary(ranked, top_ratio=1.0, max_segments=150),
        # Per‑speaker summaries (chronological, full coverage so nothing is missing)
        "speaker_summaries": generate_speaker_summaries(ranked, top_ratio=1.0, max_segments_per_speaker=80),
        "highlights": top_substantive_highlights(ranked, n=5),
        "speakers": speakers,
    }
