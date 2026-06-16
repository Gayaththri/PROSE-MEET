"""
Speech to text module (Whisper via faster-whisper/CTranslate2)
"""
import os
import math
import re
import time
from typing import Callable, List, Optional

from faster_whisper import WhisperModel
from .job_control import JobCancelledError

_model_name = os.getenv("WHISPER_MODEL", "tiny")

# Choose CPU threads for Whisper, leaving one core free by default.
def _cpu_threads():
    override = os.getenv("WHISPER_CPU_THREADS")
    if override:
        try:
            return max(0, int(override))
        except ValueError:
            pass
    cpu_count = os.cpu_count() or 1
    return max(1, cpu_count - 1)


def _int_env(name: str, default: int, *, min_v: int, max_v: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        v = default
    else:
        try:
            v = int(raw)
        except ValueError:
            v = default
    return max(min_v, min(max_v, v))


def _device_and_compute():
    if os.getenv("USE_CUDA", "").lower() in ("1", "true", "yes"):
        return "cuda", "float16"
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "float32"


_device, _compute_type = _device_and_compute()
_default_batch_size = 4
_batch_size = max(1, int(os.getenv("WHISPER_BATCH_SIZE", str(_default_batch_size)) or _default_batch_size))

# Lazy load, cache the Whisper model so after preload it is reused and not loaded again for every request.
_model = None
_use_batch = os.getenv("WHISPER_DISABLE_BATCH", "").lower() not in ("1", "true", "yes")


def _get_model():
    global _model
    if _model is None:
        compute = _compute_type
        if _device == "cpu" and _compute_type == "float32":
            cpu_threads = _cpu_threads()
            try:
                _model = WhisperModel(
                    _model_name,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=cpu_threads,
                )
                compute = "int8"
            except Exception:
                _model = WhisperModel(
                    _model_name,
                    device="cpu",
                    compute_type="float32",
                    cpu_threads=cpu_threads,
                )
        else:
            _model = WhisperModel(
                _model_name,
                device=_device,
                compute_type=_compute_type,
            )
    return _model


def preload_model():
    """Load the Whisper model at startup so the first request doesn't wait for download."""
    _get_model()


def reset_model_cache():
    global _model, _use_batch
    _model = None
    _use_batch = os.getenv("WHISPER_DISABLE_BATCH", "").lower() not in ("1", "true", "yes")


def is_model_loaded() -> bool:
    return _model is not None


def uses_cuda() -> bool:
    return _device == "cuda"


def _merge_adjacent_asr_segments(segments: list, max_gap_sec: float) -> list:
    """
    Join consecutive segments when the pause between them is short (or zero).
    Whisper often ends one segment and starts the next at the same instant with no
    real silence — e.g. 'human' then 'touch' — which is confusing in the UI.
    """
    if max_gap_sec <= 0 or len(segments) < 2:
        return segments
    ordered = sorted(segments, key=lambda s: (float(s["start"]), float(s["end"])))
    out: list = []
    for seg in ordered:
        if not out:
            out.append(dict(seg))
            continue
        prev = out[-1]
        gap = float(seg["start"]) - float(prev["end"])
        if gap <= max_gap_sec:
            prev["end"] = max(float(prev["end"]), float(seg["end"]))
            a = (prev.get("text") or "").strip()
            b = (seg.get("text") or "").strip()
            prev["text"] = f"{a} {b}".strip() if b else a
            c_prev = prev.get("asr_confidence")
            c_new = seg.get("asr_confidence")
            if c_prev is not None and c_new is not None:
                prev["asr_confidence"] = min(c_prev, c_new)
            elif c_new is not None:
                prev["asr_confidence"] = c_new
            lp_prev = prev.get("asr_avg_logprob")
            lp_new = seg.get("asr_avg_logprob")
            if lp_prev is not None and lp_new is not None:
                prev["asr_avg_logprob"] = min(lp_prev, lp_new)
            elif lp_new is not None:
                prev["asr_avg_logprob"] = lp_new
        else:
            out.append(dict(seg))
    for i, s in enumerate(out):
        s["segment_id"] = i
    return out


_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def _split_segments_by_sentences(segments: List[dict]) -> List[dict]:
    """One UI row per sentence; times interpolated by character length."""
    out: List[dict] = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        parts = [p.strip() for p in _SENTENCE_BOUNDARY.split(text) if p.strip()]
        if len(parts) <= 1:
            out.append(dict(seg))
            continue
        t0 = float(seg["start"])
        t1 = float(seg["end"])
        span = max(t1 - t0, 1e-6)
        lens = [max(1, len(p)) for p in parts]
        total = float(sum(lens))
        cursor = t0
        for i, p in enumerate(parts):
            frac = lens[i] / total
            if i == len(parts) - 1:
                end = t1
            else:
                end = cursor + span * frac
            piece = dict(seg)
            piece["text"] = p
            piece["start"] = round(cursor, 2)
            piece["end"] = round(end, 2)
            out.append(piece)
            cursor = end
    for i, s in enumerate(out):
        s["segment_id"] = i
    return out


def _round_segment_times(segments: List[dict]) -> List[dict]:
    for s in segments:
        s["start"] = round(float(s["start"]), 2)
        s["end"] = round(float(s["end"]), 2)
    return segments


# Run Whisper ASR and return cleaned timestamped transcript segments with confidence
def transcribe_audio(
    audio_path: str,
    language: str = "en",
    timing_collector=None,
    cancel_checker=None,
    *,
    audio_duration_seconds: Optional[float] = None,
    segment_progress_callback: Optional[Callable[[float], None]] = None,
):

    global _use_batch

    _asr_started = time.perf_counter()
    model = _get_model()

    # Optional prompt to bias decoder toward meeting vocabulary (improves accuracy)
    initial_prompt = (
        "Meeting, agenda, action items, follow up, quarterly review, "
        "minutes, decision, discussion, next steps, deadline."
    )

    # beam_size=1 for tiny/turbo (speed); 5 for others (accuracy)
    beam_size = 1 if _model_name in ("tiny", "large-v3-turbo") else 5
    use_vad = os.getenv("WHISPER_NO_VAD", "").lower() not in ("1", "true", "yes")
    kwargs = dict(
        language=language,
        beam_size=beam_size,
        vad_filter=use_vad,
        initial_prompt=initial_prompt,
        word_timestamps=False,
    )
    if use_vad:
        # Override with WHISPER_VAD_* (defaults tuned for fewer mid-phrase chunk breaks).
        min_silence_ms = _int_env("WHISPER_VAD_MIN_SILENCE_MS", 650, min_v=50, max_v=3000)
        speech_pad_ms = _int_env("WHISPER_VAD_SPEECH_PAD_MS", 300, min_v=0, max_v=2000)
        vad_threshold = float(os.getenv("WHISPER_VAD_THRESHOLD", "0.35"))
        vad_threshold = max(0.0, min(1.0, vad_threshold))
        kwargs["vad_parameters"] = dict(
            min_silence_duration_ms=min_silence_ms,
            speech_pad_ms=speech_pad_ms,
            threshold=vad_threshold,
        )
    try:
        segments_gen, _ = model.transcribe(audio_path, **kwargs)
    except Exception:
        _use_batch = False
        segments_gen, _ = model.transcribe(audio_path, **kwargs)

    segments = []
    for i, seg in enumerate(segments_gen):
        if cancel_checker and cancel_checker():
            raise JobCancelledError("Processing cancelled by user.")
        if (
            segment_progress_callback
            and audio_duration_seconds
            and audio_duration_seconds > 0
        ):
            frac = min(1.0, max(0.0, float(seg.end) / float(audio_duration_seconds)))
            segment_progress_callback(frac)
        text = (seg.text or "").strip()
        if text:
            avg_logprob = getattr(seg, "avg_logprob", None)
            no_speech_prob = getattr(seg, "no_speech_prob", None)
            compression_ratio = getattr(seg, "compression_ratio", None)

            asr_confidence = None
            if avg_logprob is not None:
                try:
                    # Convert log-probability to a bounded confidence-like signal in [0, 1].
                    asr_confidence = float(max(0.0, min(1.0, math.exp(float(avg_logprob)))))
                except Exception:
                    asr_confidence = None
            segments.append({
                "segment_id": i,
                "start": float(seg.start),
                "end": float(seg.end),
                "text": text,
                "asr_confidence": asr_confidence,
                "asr_avg_logprob": float(avg_logprob) if avg_logprob is not None else None,
                "asr_no_speech_prob": float(no_speech_prob) if no_speech_prob is not None else None,
                "asr_compression_ratio": float(compression_ratio) if compression_ratio is not None else None,
            })

    disable_merge = os.getenv("WHISPER_DISABLE_SEGMENT_MERGE", "").lower() in ("1", "true", "yes")
    if disable_merge:
        merge_gap = 0.0
    else:
        raw_gap = os.getenv("WHISPER_MERGE_SEGMENT_GAP_SEC") or os.getenv("WHISPER_MERGE_MAX_GAP_SECONDS", "0.45")
        try:
            merge_gap = float(raw_gap)
        except ValueError:
            merge_gap = 0.45
    merge_gap = max(0.0, min(3.0, merge_gap))
    if merge_gap > 0 and len(segments) > 1:
        segments = _merge_adjacent_asr_segments(segments, merge_gap)

    if os.getenv("WHISPER_DISABLE_SENTENCE_SPLIT", "").lower() not in ("1", "true", "yes"):
        segments = _split_segments_by_sentences(segments)
    else:
        segments = _round_segment_times(segments)

    if timing_collector is not None:
        timing_collector.record_stage(
            "asr_transcription", time.perf_counter() - _asr_started
        )

    return segments
