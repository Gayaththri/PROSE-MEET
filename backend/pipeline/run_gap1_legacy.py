import concurrent.futures

import librosa
import numpy as np

from .alignment import align_text_prosody
from .asr import transcribe_audio
from .diarization import assign_speakers_to_segments, diarize_audio
from .domain import (
    apply_domain_adaptation,
    detect_domain,
    get_domain_focus_keywords,
    get_domain_importance_threshold,
)
from .importance import compute_importance
from .speakers import (
    compute_speaker_contribution,
    compute_speaker_contribution_from_labels,
    infer_and_apply_speaker_names,
)
from .summary import generate_speaker_summaries, generate_summary, top_substantive_highlights
from .timing import TimingCollector, timed_stage


FRAME_LENGTH = 2048
HOP_LENGTH = 1024


def _legacy_preprocess_audio(audio_path: str, target_sr: int = 16000):
    audio, sr = librosa.load(audio_path, sr=target_sr, mono=True)
    if np.max(np.abs(audio)) > 0:
        audio = audio / np.max(np.abs(audio))
    return audio, target_sr


def _legacy_extract_prosody(audio, sr: int = 16000, timing_collector: TimingCollector | None = None):
    with timed_stage(timing_collector, "prosody_extraction"):
        energy = librosa.feature.rms(
            y=audio,
            frame_length=FRAME_LENGTH,
            hop_length=HOP_LENGTH,
        )[0]
        spectral_centroid = librosa.feature.spectral_centroid(
            y=audio,
            sr=sr,
            n_fft=FRAME_LENGTH,
            hop_length=HOP_LENGTH,
        )[0]
        silence_threshold = float(np.percentile(energy, 10))
        silence = energy < silence_threshold
        return {
            "pitch": spectral_centroid,
            "energy": energy,
            "silence": silence,
            "hop_length": HOP_LENGTH,
        }


def run_gap1_legacy(audio_path: str, timing_collector: TimingCollector | None = None) -> dict:
    with timed_stage(timing_collector, "preprocess_audio"):
        audio, sr = _legacy_preprocess_audio(audio_path)
    duration_seconds = float(len(audio) / sr) if sr > 0 and len(audio) > 0 else 0.0

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_asr = executor.submit(transcribe_audio, audio_path, "en", timing_collector)
        future_prosody = executor.submit(_legacy_extract_prosody, audio, sr, timing_collector)
        segments = future_asr.result()
        prosody = future_prosody.result()

    with timed_stage(timing_collector, "align_text_prosody"):
        aligned = align_text_prosody(segments, prosody, sr=sr)
    with timed_stage(timing_collector, "compute_importance"):
        ranked_base = compute_importance(aligned)

    diarization_segments = diarize_audio(
        audio_path=audio_path,
        waveform=audio,
        sample_rate=sr,
        min_speakers=2,
        max_speakers=20,
        timing_collector=timing_collector,
    )
    unique_diarization_speakers = (
        len(set(sp for _, _, sp in diarization_segments))
        if diarization_segments else 0
    )
    with timed_stage(timing_collector, "speaker_assignment"):
        if diarization_segments and unique_diarization_speakers >= 2:
            assign_speakers_to_segments(ranked_base, diarization_segments)
            speakers = compute_speaker_contribution_from_labels(ranked_base)
        else:
            speakers = compute_speaker_contribution(ranked_base)

    with timed_stage(timing_collector, "detect_domain_pass_1"):
        domain_result = detect_domain(
            transcript=sorted(ranked_base, key=lambda x: x["start"]),
            summary=None,
            speaker_summaries=None,
        )
    with timed_stage(timing_collector, "apply_domain_adaptation"):
        ranked = apply_domain_adaptation(ranked_base, domain_result)
    focus_keywords = get_domain_focus_keywords(domain_result)
    domain_importance_threshold = get_domain_importance_threshold(domain_result)

    transcript_chronological = sorted(ranked, key=lambda x: x["start"])
    with timed_stage(timing_collector, "speaker_summary_generation"):
        speaker_summaries = generate_speaker_summaries(
            ranked,
            top_ratio=1.0,
            max_segments_per_speaker=80,
        )
    with timed_stage(timing_collector, "highlight_generation"):
        highlights = top_substantive_highlights(
            ranked,
            n=5,
            focus_keywords=focus_keywords,
            min_importance_score=domain_importance_threshold,
        )

    sorted_transcript = sorted(transcript_chronological, key=lambda x: x["start"])
    result = {
        "transcript": sorted_transcript,
        "duration_seconds": duration_seconds,
        "summary": None,
        "speaker_summaries": speaker_summaries,
        "highlights": highlights,
        "speakers": speakers,
        "importance_threshold": domain_importance_threshold,
    }
    with timed_stage(timing_collector, "speaker_name_inference"):
        infer_and_apply_speaker_names(ranked, result["speaker_summaries"], result["speakers"])
    with timed_stage(timing_collector, "summary_generation"):
        result["transcript"] = sorted(result["transcript"], key=lambda x: x["start"])
        result["summary"] = generate_summary(result["transcript"], top_ratio=1.0, max_segments=150)
    with timed_stage(timing_collector, "detect_domain_pass_2"):
        refreshed_domain = detect_domain(
            transcript=result["transcript"],
            summary=result.get("summary"),
            speaker_summaries=result.get("speaker_summaries"),
        )
    if refreshed_domain.get("predicted_domain") == domain_result.get("predicted_domain"):
        result["domain"] = refreshed_domain
    else:
        stable_domain = dict(domain_result)
        stable_domain["second_pass_predicted_domain"] = refreshed_domain.get("predicted_domain")
        stable_domain["second_pass_confidence"] = refreshed_domain.get("confidence")
        result["domain"] = stable_domain
    result["transcript"] = sorted(result["transcript"], key=lambda x: x["start"])
    return result
