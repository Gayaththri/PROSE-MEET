"""
Runs the main Gap 1 meeting pipeline end-to-end with progress updates: audio preprocessing, ASR+prosody, alignment, importance scoring, domain adaptation, highlights, speaker insights, and summary output.
"""
import concurrent.futures
import time

from .audio import preprocess_audio
from .asr import transcribe_audio, uses_cuda
from .prosody import extract_prosody
from .alignment import align_text_prosody
from .importance import compute_importance
from .summary import generate_summary, generate_speaker_summaries, top_substantive_highlights
from .domain import (
    detect_domain,
    apply_domain_adaptation,
    get_domain_focus_keywords,
    get_domain_importance_threshold,
)
from .job_control import JobCancelledError


def _check_cancel(cancel_checker):
    if cancel_checker and cancel_checker():
        raise JobCancelledError("Processing cancelled by user.")


def _emit_progress(
    progress_callback,
    *,
    stage,
    stage_label,
    progress,
    partial_result=None,
    audio_duration_seconds=None,
):
    if progress_callback is None:
        return
    progress_callback(
        stage=stage,
        stage_label=stage_label,
        progress=progress,
        partial_result=partial_result,
        audio_duration_seconds=audio_duration_seconds,
    )


def _build_partial_result(
    *,
    transcript=None,
    duration_seconds=None,
    highlights=None,
    summary=None,
    speaker_summaries=None,
    domain=None,
    importance_threshold=None,
    metadata=None,
    partial_stage=None,
):
    result = {
        "transcript": transcript or [],
        "duration_seconds": duration_seconds,
        "highlights": highlights or [],
        "speaker_summaries": speaker_summaries or [],
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
    timing_collector=None,
    progress_callback=None,
    cancel_checker=None,
    result_metadata=None,
) -> dict:
    _check_cancel(cancel_checker)
    # Preprocess audio once (mono, 16 kHz, normalised) for prosody extraction
    audio, sr = preprocess_audio(audio_path)
    duration_seconds = float(len(audio) / sr) if sr > 0 and len(audio) > 0 else 0.0
    _check_cancel(cancel_checker)
    # Emit first progress only after we know duration so ETA can use a length-based budget
    # (avoids implying a seconds-left estimate with no audio length).
    _emit_progress(
        progress_callback,
        stage="preparing_audio",
        stage_label="Preparing audio",
        progress=0.08,
        audio_duration_seconds=duration_seconds,
    )
    _check_cancel(cancel_checker)

    # Run ASR + prosody in parallel on CUDA, but avoid CPU over-saturation on CPU-only hosts.
    _emit_progress(
        progress_callback,
        stage="transcribing",
        stage_label="Transcribing meeting",
        progress=0.26,
        audio_duration_seconds=duration_seconds,
    )
    asr_prog_state = {"p": 0.26, "t": 0.0}

    def _asr_segment_progress(through_audio: float) -> None:
        frac = max(0.0, min(1.0, float(through_audio)))
        p = 0.26 + (0.42 - 0.26) * frac
        now = time.monotonic()
        if (
            frac < 0.997
            and p - asr_prog_state["p"] < 0.014
            and (now - asr_prog_state["t"]) < 0.3
        ):
            return
        asr_prog_state["p"] = p
        asr_prog_state["t"] = now
        _emit_progress(
            progress_callback,
            stage="transcribing",
            stage_label="Transcribing meeting",
            progress=p,
            audio_duration_seconds=duration_seconds,
        )

    if uses_cuda():
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        hard_shutdown = False
        try:
            future_asr = executor.submit(
                transcribe_audio,
                audio_path,
                "en",
                timing_collector,
                cancel_checker,
                audio_duration_seconds=duration_seconds,
                segment_progress_callback=_asr_segment_progress,
            )
            future_prosody = executor.submit(
                extract_prosody, audio, sr, timing_collector, cancel_checker
            )
            pending = {future_asr, future_prosody}
            while pending:
                done, pending = concurrent.futures.wait(
                    pending,
                    timeout=0.5,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
                try:
                    _check_cancel(cancel_checker)
                except JobCancelledError:
                    hard_shutdown = True
                    executor.shutdown(wait=False)
                    raise
                for f in done:
                    try:
                        f.result()
                    except JobCancelledError:
                        hard_shutdown = True
                        executor.shutdown(wait=False)
                        raise
            segments = future_asr.result()
            prosody = future_prosody.result()
        finally:
            if not hard_shutdown:
                executor.shutdown(wait=True)
    else:
        # On CPU, faster-whisper already uses many threads; running prosody concurrently
        # can starve ASR and appear stuck at the transcribing stage.
        segments = transcribe_audio(
            audio_path,
            "en",
            timing_collector,
            cancel_checker,
            audio_duration_seconds=duration_seconds,
            segment_progress_callback=_asr_segment_progress,
        )
        _check_cancel(cancel_checker)
        prosody = extract_prosody(audio, sr, timing_collector, cancel_checker)
    _check_cancel(cancel_checker)

    # Align text with prosody
    _emit_progress(
        progress_callback,
        stage="aligning_transcript",
        stage_label="Aligning transcript",
        progress=0.42,
        audio_duration_seconds=duration_seconds,
    )
    aligned = align_text_prosody(segments, prosody, sr=sr)
    _check_cancel(cancel_checker)

    # Gap 1 base importance scoring (prosody + semantic fusion)
    _emit_progress(
        progress_callback,
        stage="scoring_importance",
        stage_label="Scoring importance",
        progress=0.54,
        audio_duration_seconds=duration_seconds,
    )
    ranked_base = compute_importance(aligned)
    _check_cancel(cancel_checker)

    _emit_progress(
        progress_callback,
        stage="adapting_context",
        stage_label="Adapting to meeting context",
        progress=0.64,
        audio_duration_seconds=duration_seconds,
    )
    _session_ctx = (result_metadata or {}).get("filename") if result_metadata else None
    domain_result = detect_domain(
        transcript=sorted(ranked_base, key=lambda x: x["start"]),
        summary=None,
        speaker_summaries=None,
        session_context=_session_ctx,
    )
    _check_cancel(cancel_checker)
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
        audio_duration_seconds=duration_seconds,
    )
    _check_cancel(cancel_checker)

    _emit_progress(
        progress_callback,
        stage="generating_highlights",
        stage_label="Generating highlights",
        progress=0.8,
        audio_duration_seconds=duration_seconds,
    )
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
        audio_duration_seconds=duration_seconds,
    )
    _check_cancel(cancel_checker)

    _emit_progress(
        progress_callback,
        stage="finalizing_insights",
        stage_label="Finalizing insights",
        progress=0.92,
        audio_duration_seconds=duration_seconds,
    )

    # Transcript in chronological order (includes domain-adapted importance fields).
    sorted_transcript = sorted(transcript_chronological, key=lambda x: x["start"])
    result = {
        "transcript": sorted_transcript,
        "duration_seconds": duration_seconds,
        "summary": None,
        "speaker_summaries": [],
        "highlights": highlights,
        "importance_threshold": domain_importance_threshold,
    }
    result["speaker_summaries"] = generate_speaker_summaries(
        ranked,
        top_ratio=1.0,
        max_segments_per_speaker=80,
    )
    _check_cancel(cancel_checker)
    result["transcript"] = sorted(result["transcript"], key=lambda x: x["start"])
    result["summary"] = generate_summary(result["transcript"], top_ratio=1.0, max_segments=150)
    summary_partial = _build_partial_result(
        transcript=transcript_chronological,
        duration_seconds=duration_seconds,
        highlights=highlights,
        summary=result["summary"],
        speaker_summaries=result["speaker_summaries"],
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
        audio_duration_seconds=duration_seconds,
    )
    _check_cancel(cancel_checker)

    # Final Gap 2 metadata for overview panel and explainability.
    refreshed_domain = detect_domain(
        transcript=result["transcript"],
        summary=result.get("summary"),
        speaker_summaries=result.get("speaker_summaries"),
        session_context=_session_ctx,
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
        audio_duration_seconds=duration_seconds,
    )
    return result
