"""
Fast, configurable ASR pipeline using faster-whisper with cached model loading and segment-level confidence metadata.
Transcribes audio into timestamped text segments using faster-whisper, with device-aware loading and optional ASR confidence/timing metadata.
"""
import os
import math
import time
from faster_whisper import WhisperModel

from .timing import TimingCollector
from .job_control import JobCancelledError

_model_name = os.getenv("WHISPER_MODEL", "tiny")


def _cpu_threads():
    override = os.getenv("WHISPER_CPU_THREADS")
    if override:
        try:
            return max(0, int(override))
        except ValueError:
            pass
    return max(1, os.cpu_count() or 1)


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

# Lazy load so env can be set before first request
_model = None
_use_batch = os.getenv("WHISPER_DISABLE_BATCH", "").lower() not in ("1", "true", "yes")


def _get_model():
    global _model
    if _model is None:
        compute = _compute_type
        # On CPU, try int8 for ~35% speedup; fall back to float32 if unsupported
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


def transcribe_audio(
    audio_path: str,
    language: str = "en",
    timing_collector: TimingCollector | None = None,
    cancel_checker=None,
):
    """
    Transcribe full audio using faster-whisper (CTranslate2).

    Faster and more accurate than OpenAI Whisper. For best accuracy use
    WHISPER_MODEL=small or medium; base is a good speed/accuracy balance.
    """
    global _use_batch

    model_loaded_before = is_model_loaded()
    load_started = time.perf_counter()
    model = _get_model()
    if timing_collector is not None and not model_loaded_before:
        timing_collector.record_stage(
            "asr_model_load",
            time.perf_counter() - load_started,
            device=_device,
            compute_type=_compute_type,
            model_name=_model_name,
            cpu_threads=_cpu_threads() if _device == "cpu" else None,
        )

    # Optional prompt to bias decoder toward meeting vocabulary (improves accuracy)
    initial_prompt = (
        "Meeting, agenda, action items, follow up, quarterly review, "
        "minutes, decision, discussion, next steps, deadline."
    )

    # beam_size=1 for tiny/turbo (speed); 5 for others (accuracy)
    beam_size = 1 if _model_name in ("tiny", "large-v3-turbo") else 5
    # VAD: use a lower threshold so quiet/low-volume speech is not filtered out as silence
    use_vad = os.getenv("WHISPER_NO_VAD", "").lower() not in ("1", "true", "yes")
    kwargs = dict(
        language=language,
        beam_size=beam_size,
        vad_filter=use_vad,
        initial_prompt=initial_prompt,
        word_timestamps=False,
    )
    if use_vad:
        kwargs["vad_parameters"] = dict(
            min_silence_duration_ms=300,
            speech_pad_ms=300,
            threshold=0.35,  # more sensitive than default 0.5 to capture quiet speech
        )
    started = time.perf_counter()
    try:
        segments_gen, _ = model.transcribe(audio_path, **kwargs)
    except Exception:
        _use_batch = False
        segments_gen, _ = model.transcribe(audio_path, **kwargs)

    segments = []
    for i, seg in enumerate(segments_gen):
        if cancel_checker and cancel_checker():
            raise JobCancelledError("Processing cancelled by user.")
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

    if timing_collector is not None:
        timing_collector.record_stage(
            "asr_decode",
            time.perf_counter() - started,
            device=_device,
            compute_type=_compute_type,
            model_name=_model_name,
            vad_enabled=use_vad,
            batched=bool(kwargs.get("batch_size")),
            cpu_threads=_cpu_threads() if _device == "cpu" else None,
        )

    return segments
