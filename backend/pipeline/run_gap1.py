import concurrent.futures
import os

from .audio import preprocess_audio
from .asr import transcribe_audio, uses_cuda
from .prosody import extract_prosody
from .alignment import align_text_prosody
from .importance import compute_importance
from .summary import generate_summary, generate_speaker_summaries, top_substantive_highlights
from .speakers import compute_speaker_contribution, compute_speaker_contribution_from_labels, infer_and_apply_speaker_names
from .diarization import diarize_audio, assign_speakers_to_segments
from .domain import (
    detect_domain,
    apply_domain_adaptation,
    get_domain_focus_keywords,
    get_domain_importance_threshold,
)
from .timing import TimingCollector, timed_stage


class JobCancelledError(RuntimeError):
    pass


def _parallelize_diarization() -> bool:
    override = os.getenv("PIPELINE_PARALLEL_DIARIZATION", "").lower()
    if override in ("1", "true", "yes"):
        return True
    if override in ("0", "false", "no"):
        return False
    return not uses_cuda()


def _check_cancel(cancel_checker):
    if cancel_checker and cancel_checker():
        raise JobCancelledError("Processing cancelled by user.")


def _emit_progress(progress_callback, *, stage, stage_label, progress, partial_result=None):
    if progress_callback is None:
        return
    progress_callback(
        stage=stage,
        stage_label=stage_label,
        progress=progress,
        partial_result=partial_result,
    )


def _build_partial_result(
    *,
    transcript=None,
    duration_seconds=None,
    highlights=None,
    summary=None,
    speaker_summaries=None,
    domain=None,
    speakers=None,
    importance_threshold=None,
    metadata=None,
    partial_stage=None,
):
    result = {
        "transcript": transcript or [],
        "duration_seconds": duration_seconds,
        "highlights": highlights or [],
        "speaker_summaries": speaker_summaries or [],
        "speakers": speakers or [],
        "importance_threshold": importance_threshold,
        "summary": summary,
        "domain": domain,
        "is_partial": True,
        "partial_stage": partial_stage,
    }
    if metadata:
        result.update(metadata)
    return result


def run_gap1(
    audio_path: str,
    timing_collector: TimingCollector | None = None,
    progress_callback=None,
    cancel_checker=None,
    result_metadata=None,
) -> dict:
    """
    Runs Gap 1: Prosody-Aware Importance Detection.
    Speakers are identified by voice (diarization); names are inferred from transcript when present (e.g. "My name is Rose").
    """
    _emit_progress(
        progress_callback,
        stage="preparing_audio",
        stage_label="Preparing audio",
        progress=0.08,
    )
    _check_cancel(cancel_checker)
    # Preprocess audio once (mono, 16 kHz, normalised) – used for diarization and prosody
    with timed_stage(timing_collector, "preprocess_audio"):
        audio, sr = preprocess_audio(audio_path)
    duration_seconds = float(len(audio) / sr) if sr > 0 and len(audio) > 0 else 0.0

    # Run ASR and prosody extraction in parallel to reduce total time
    _emit_progress(
        progress_callback,
        stage="transcribing",
        stage_label="Transcribing meeting",
        progress=0.26,
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_asr = executor.submit(transcribe_audio, audio_path, "en", timing_collector)
        future_prosody = executor.submit(extract_prosody, audio, sr, timing_collector)
        segments = future_asr.result()
        prosody = future_prosody.result()
    _check_cancel(cancel_checker)

    # Align text with prosody
    _emit_progress(
        progress_callback,
        stage="aligning_transcript",
        stage_label="Aligning transcript",
        progress=0.42,
    )
    with timed_stage(timing_collector, "align_text_prosody"):
        aligned = align_text_prosody(segments, prosody, sr=sr)

    # Gap 1 base importance scoring (prosody + semantic fusion)
    _emit_progress(
        progress_callback,
        stage="scoring_importance",
        stage_label="Scoring importance",
        progress=0.54,
    )
    with timed_stage(timing_collector, "compute_importance"):
        ranked_base = compute_importance(aligned)
    _check_cancel(cancel_checker)

    parallelize_diarization = _parallelize_diarization()
    if timing_collector is not None:
        timing_collector.set_metadata("parallel_diarization", parallelize_diarization)

    diarization_segments = None
    diarization_future = None
    diarization_executor = None
    if parallelize_diarization:
        diarization_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        diarization_future = diarization_executor.submit(
            diarize_audio,
            audio_path=audio_path,
            waveform=audio,
            sample_rate=sr,
            min_speakers=2,
            max_speakers=20,
            timing_collector=timing_collector,
        )

    _emit_progress(
        progress_callback,
        stage="adapting_context",
        stage_label="Adapting to meeting context",
        progress=0.64,
    )
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
    transcript_partial = _build_partial_result(
        transcript=transcript_chronological,
        duration_seconds=duration_seconds,
        importance_threshold=domain_importance_threshold,
        metadata=result_metadata,
        partial_stage="transcript_ready",
    )
    _emit_progress(
        progress_callback,
        stage="transcript_ready",
        stage_label="Transcript ready",
        progress=0.72,
        partial_result=transcript_partial,
    )
    _check_cancel(cancel_checker)

    _emit_progress(
        progress_callback,
        stage="generating_highlights",
        stage_label="Generating highlights",
        progress=0.8,
    )
    with timed_stage(timing_collector, "highlight_generation"):
        highlights = top_substantive_highlights(
            ranked,
            n=5,
            focus_keywords=focus_keywords,
            min_importance_score=domain_importance_threshold,
        )
    highlights_partial = _build_partial_result(
        transcript=transcript_chronological,
        duration_seconds=duration_seconds,
        highlights=highlights,
        importance_threshold=domain_importance_threshold,
        metadata=result_metadata,
        partial_stage="highlights_ready",
    )
    _emit_progress(
        progress_callback,
        stage="highlights_ready",
        stage_label="Highlights ready",
        progress=0.86,
        partial_result=highlights_partial,
    )
    _check_cancel(cancel_checker)

    if diarization_future is not None:
        diarization_segments = diarization_future.result()
        diarization_executor.shutdown(wait=True)
    else:
        with timed_stage(timing_collector, "diarization_decode"):
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
    _emit_progress(
        progress_callback,
        stage="finalizing_insights",
        stage_label="Finalizing insights",
        progress=0.92,
    )
    with timed_stage(timing_collector, "speaker_assignment"):
        if diarization_segments and unique_diarization_speakers >= 2:
            assign_speakers_to_segments(ranked, diarization_segments)
            speakers = compute_speaker_contribution_from_labels(ranked)
        else:
            speakers = compute_speaker_contribution(ranked)
    _check_cancel(cancel_checker)

    # Transcript in chronological order (includes domain-adapted importance fields).
    sorted_transcript = sorted(transcript_chronological, key=lambda x: x["start"])
    result = {
        "transcript": sorted_transcript,
        "duration_seconds": duration_seconds,
        "summary": None,
        "speaker_summaries": [],
        "highlights": highlights,
        "speakers": speakers,
        "importance_threshold": domain_importance_threshold,
    }
    with timed_stage(timing_collector, "speaker_summary_generation"):
        result["speaker_summaries"] = generate_speaker_summaries(
            ranked,
            top_ratio=1.0,
            max_segments_per_speaker=80,
        )
    # Infer names from transcript (e.g. "My name is Rose", "I'm Alima") and replace Speaker_1, Speaker_2, ...
    with timed_stage(timing_collector, "speaker_name_inference"):
        infer_and_apply_speaker_names(ranked, result["speaker_summaries"], result["speakers"])
    with timed_stage(timing_collector, "summary_generation"):
        result["transcript"] = sorted(result["transcript"], key=lambda x: x["start"])
        result["summary"] = generate_summary(result["transcript"], top_ratio=1.0, max_segments=150)
    summary_partial = _build_partial_result(
        transcript=transcript_chronological,
        duration_seconds=duration_seconds,
        highlights=highlights,
        summary=result["summary"],
        speaker_summaries=result["speaker_summaries"],
        speakers=speakers,
        importance_threshold=domain_importance_threshold,
        metadata=result_metadata,
        partial_stage="summary_ready",
    )
    _emit_progress(
        progress_callback,
        stage="summary_ready",
        stage_label="Summary ready",
        progress=0.96,
        partial_result=summary_partial,
    )
    _check_cancel(cancel_checker)

    # Final Gap 2 metadata for overview panel and explainability.
    with timed_stage(timing_collector, "detect_domain_pass_2"):
        refreshed_domain = detect_domain(
            transcript=result["transcript"],
            summary=result.get("summary"),
            speaker_summaries=result.get("speaker_summaries"),
        )
    if refreshed_domain.get("predicted_domain") == domain_result.get("predicted_domain"):
        result["domain"] = refreshed_domain
    else:
        # Keep scoring-consistent domain, but expose second-pass estimate for diagnostics.
        stable_domain = dict(domain_result)
        stable_domain["second_pass_predicted_domain"] = refreshed_domain.get("predicted_domain")
        stable_domain["second_pass_confidence"] = refreshed_domain.get("confidence")
        result["domain"] = stable_domain
    if result_metadata:
        result.update(result_metadata)
    result["transcript"] = sorted(result["transcript"], key=lambda x: x["start"])
    _emit_progress(
        progress_callback,
        stage="completed",
        stage_label="Insights ready",
        progress=1.0,
    )
    return result
