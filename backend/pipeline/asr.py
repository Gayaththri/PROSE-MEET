"""
ASR using faster-whisper (CTranslate2): 4–6x faster than OpenAI Whisper.

Optimization summary (aligned with best practices):
- faster-whisper + CTranslate2  → 4–6x speedup (GPU/CPU)
- Quantization: float16 on GPU, int8 on CPU (fallback to float32 if int8 fails)
- Small model: tiny (default) for speed; base/small for balance; large-v3-turbo for accuracy+speed
- VAD: vad_filter=True to skip silence and reduce work
- Batching: batch_size=4 for parallel segments (disable with WHISPER_DISABLE_BATCH=1)

Env vars:
- WHISPER_MODEL: tiny (default for reliability). For better accuracy use base, small, or
  large-v3-turbo (Whisper Turbo). Presets: tiny, base, small, medium, large-v3, large-v3-turbo.
  Set in .env or env to use turbo: WHISPER_MODEL=large-v3-turbo. Or path to CTranslate2 model dir.
- USE_CUDA: set to 1/true/yes to force GPU; otherwise auto-detected.
- WHISPER_DISABLE_BATCH: set to 1 to disable batching (if you see transcription errors).
"""
import os
from faster_whisper import WhisperModel

_model_name = os.getenv("WHISPER_MODEL", "tiny")


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

# Lazy load so env can be set before first request
_model = None
_use_batch = os.getenv("WHISPER_DISABLE_BATCH", "").lower() not in ("1", "true", "yes")


def _get_model():
    global _model
    if _model is None:
        compute = _compute_type
        # On CPU, try int8 for ~35% speedup; fall back to float32 if unsupported
        if _device == "cpu" and _compute_type == "float32":
            try:
                _model = WhisperModel(_model_name, device="cpu", compute_type="int8")
                compute = "int8"
            except Exception:
                _model = WhisperModel(_model_name, device="cpu", compute_type="float32")
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


def transcribe_audio(audio_path: str, language: str = "en"):
    """
    Transcribe full audio using faster-whisper (CTranslate2).

    Faster and more accurate than OpenAI Whisper. For best accuracy use
    WHISPER_MODEL=small or medium; base is a good speed/accuracy balance.
    """
    global _use_batch
    model = _get_model()

    # Optional prompt to bias decoder toward meeting vocabulary (improves accuracy)
    initial_prompt = (
        "Meeting, agenda, action items, follow up, quarterly review, "
        "minutes, decision, discussion, next steps, deadline."
    )

    # beam_size=1 for tiny/turbo (speed); 5 for others (accuracy)
    beam_size = 1 if _model_name in ("tiny", "large-v3-turbo") else 5
    # Batching + VAD for 2–4x throughput; fall back to no batch if it fails
    kwargs = dict(
        language=language,
        beam_size=beam_size,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=300, speech_pad_ms=200),
        initial_prompt=initial_prompt,
        word_timestamps=False,
    )
    if _use_batch:
        kwargs["batch_size"] = 4
    try:
        segments_gen, _ = model.transcribe(audio_path, **kwargs)
    except Exception:
        _use_batch = False
        kwargs.pop("batch_size", None)
        segments_gen, _ = model.transcribe(audio_path, **kwargs)

    segments = []
    for i, seg in enumerate(segments_gen):
        text = (seg.text or "").strip()
        if text:
            segments.append({
                "segment_id": i,
                "start": float(seg.start),
                "end": float(seg.end),
                "text": text,
            })

    return segments
