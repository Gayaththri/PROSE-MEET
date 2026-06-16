"""
explainable utterance importance by fusing supervised model probabilities with semantic/prosodic rule-based scoring and reliability penalties 
"""
import numpy as np
import re
from typing import Optional

#loading supervised importance model
try:
    from .importance_model import load_model, predict_probabilities
    _IMPORTANCE_MODEL_IMPORT_ERROR = None
except Exception as exc:  
    load_model = None
    predict_probabilities = None
    _IMPORTANCE_MODEL_IMPORT_ERROR = exc

# Simple list of urgency / decision keywords for semantic explanations.
_URGENCY_KEYWORDS = [
    "must",
    "should",
    "need to",
    "deadline",
    "due date",
    "decide",
    "decision",
    "finalise",
    "finalize",
    "action item",
    "assign",
    "deliverable",
    "commit",
]

_SEMANTIC_KEYWORDS = [
    "need to",
    "must",
    "should",
    "decide",
    "decision",
    "finalize",
    "finalise",
    "deadline",
    "due date",
    "budget",
    "plan",
    "design",
    "requirement",
    "action item",
    "follow up",
    "deliverable",
]

_LOW_INFORMATION_PHRASES = frozenset(
    s.strip().lower()
    for s in (
        "i don't know",
        "dont know",
        "some teeth",
        "okay",
        "ok",
        "yeah",
        "yes",
        "no",
        "right",
        "sure",
        "hmm",
        "uh",
        "um",
    )
)

# Detect filler so importance can be down weighted
def _contains_low_information(text_lower: str) -> bool:
    if not text_lower:
        return True

    if text_lower in _LOW_INFORMATION_PHRASES:
        return True

    if re.search(r"\b(i|we)\s*don['’]?t\b.*\bknow\b", text_lower):
        return True
    if re.search(r"\bdon['’]?t\b.*\bknow\b", text_lower):
        return True

    # Single-token backchannels.
    tokens = set(re.findall(r"[a-z']+", text_lower))
    short_backchannels = {
        "yeah",
        "yes",
        "no",
        "ok",
        "okay",
        "right",
        "sure",
        "hmm",
        "uh",
        "um",
    }
    return any(t in short_backchannels for t in tokens)

_MODEL_BUNDLE = None
_MODEL_LOAD_ATTEMPTED = False


def _level_from_percentiles(value, p33, p66):
    """Map a value to Low / Medium / High using 33rd and 66th percentiles."""
    if value <= p33:
        return "Low"
    if value >= p66:
        return "High"
    return "Medium"


# Rule based text score: length, planning/decision keywords, and numbers
def _semantic_score(text: str, word_count: int) -> tuple[float, list[str], int]:

    if not text:
        return 0.0, [], 0

    reasons = []
    text_lower = text.lower()
    matched_keywords = sorted({kw for kw in _SEMANTIC_KEYWORDS if kw in text_lower})
    keyword_hits = len(matched_keywords)

    # Baseline from sentence length: longer statements are more likely substantive.
    length_score = min(0.35, word_count / 20.0)
    score = length_score
    if word_count >= 8:
        reasons.append("Longer statement length suggests substantive content.")

    if keyword_hits > 0:
        keyword_score = min(0.45, 0.15 * keyword_hits)
        score += keyword_score
        shown = ", ".join(matched_keywords[:3])
        reasons.append(f"Decision/planning keywords detected ({shown}).")

    # Numeric references often indicate constraints, dates, or decisions.
    if re.search(r"\b\d+(?:[\.,]\d+)?\b", text_lower):
        score += 0.12
        reasons.append("Contains numeric details (often linked to targets/dates/budgets).")

    return min(1.0, score), reasons, keyword_hits


#loads the supervised importance model once and keeps it in memory
def _get_model_bundle() -> Optional[dict]:
    global _MODEL_BUNDLE, _MODEL_LOAD_ATTEMPTED
    if _MODEL_LOAD_ATTEMPTED:
        return _MODEL_BUNDLE
    _MODEL_LOAD_ATTEMPTED = True
    if load_model is None:
        _MODEL_BUNDLE = None
        return _MODEL_BUNDLE
    _MODEL_BUNDLE = load_model()
    return _MODEL_BUNDLE

# Flag empty or non word like text (low letter ratio), e.g. noisy ASR / symbols
def _is_low_reliability_text(text_lower: str) -> bool:
    if not text_lower:
        return True
    alpha_chars = sum(1 for ch in text_lower if ch.isalpha())
    ratio_alpha = alpha_chars / max(len(text_lower), 1)
    return ratio_alpha < 0.45


def _format_float_for_importance_reason(x: float) -> str:
    """Format scores in importance_reasons without collapsing e.g. 0.997 to '1.00'."""
    xf = float(x)
    if not np.isfinite(xf):
        return "?"
    s = f"{xf:.8f}".rstrip("0").rstrip(".")
    return s if s else "0"


def compute_importance(aligned_segments):
    """
    Compute prosody aware importance scores for each utterance.
    Importance is defined as deviation from meeting-level prosodic baselines.
    Also adds explainable prosody fields: pitch_variation_level, energy_level, pause_emphasis.
    """

    if not aligned_segments:
        return []

    # Extract feature arrays
    pitch_var = np.array([seg["pitch_variance"] for seg in aligned_segments])
    energy = np.array([seg["mean_energy"] for seg in aligned_segments])
    pause = np.array([seg["pause_ratio"] for seg in aligned_segments])

    # # Baseline mean/std per meeting for prosody comparison
    pitch_mean, pitch_std = np.mean(pitch_var), np.std(pitch_var) + 1e-6
    energy_mean, energy_std = np.mean(energy), np.std(energy) + 1e-6
    pause_mean, pause_std = np.mean(pause), np.std(pause) + 1e-6

    # Percentiles for explainable levels (Low / Medium / High)
    p_pitch_33, p_pitch_66 = np.percentile(pitch_var, 33), np.percentile(pitch_var, 66)
    p_energy_33, p_energy_66 = np.percentile(energy, 33), np.percentile(energy, 66)
    p_pause_66 = np.percentile(pause, 66)  

    model_bundle = _get_model_bundle()
    model_probs = None
    if model_bundle is not None and predict_probabilities is not None:
        try:
            model_probs = predict_probabilities(aligned_segments, model_bundle)
        except Exception:
            # If model inference fails for any reason, continue with rule based scoring.
            model_probs = None

    semantic_scores = []
    keyword_hits_all = []
    word_counts = []
    texts = []
    for seg in aligned_segments:
        text = (seg.get("text") or "").strip()
        words = [w for w in re.split(r"\s+", text) if w]
        word_count = len(words)
        semantic_score, _, keyword_hits = _semantic_score(text, word_count)
        semantic_scores.append(float(semantic_score))
        keyword_hits_all.append(int(keyword_hits))
        word_counts.append(word_count)
        texts.append(text)

    ranked_segments = []

    for idx, seg in enumerate(aligned_segments):
        z_pitch = abs((seg["pitch_variance"] - pitch_mean) / pitch_std)
        z_energy = abs((seg["mean_energy"] - energy_mean) / energy_std)
        z_pause = abs((seg["pause_ratio"] - pause_mean) / pause_std)

        # Prosodic deviation from meeting baselines.
        prosody_signal = (
            0.4 * z_pitch +
            0.4 * z_energy +
            0.2 * z_pause
        )
        prosody_boost = min(0.30, 0.18 * prosody_signal)

        text = texts[idx]
        text_lower = text.lower()
        word_count = word_counts[idx]
        semantic_score, semantic_reasons, keyword_hits = _semantic_score(text, word_count)

        prev_sem = semantic_scores[idx - 1] if idx > 0 else 0.0
        next_sem = semantic_scores[idx + 1] if idx < (len(aligned_segments) - 1) else 0.0
        prev_kw = keyword_hits_all[idx - 1] if idx > 0 else 0
        next_kw = keyword_hits_all[idx + 1] if idx < (len(aligned_segments) - 1) else 0
        context_boost = (0.08 * max(prev_sem, next_sem)) + (0.04 if (prev_kw > 0 or next_kw > 0) else 0.0)

        rule_score = semantic_score + prosody_boost + context_boost
        model_mode = model_probs is not None and idx < len(model_probs)
        fused_before_penalties = None
        if model_mode:
            model_prob = float(model_probs[idx])
            # Supervised + rule based fusion.
            # Requirement: Do NOT use model_prob directly as final score.
            fused_before_penalties = 0.7 * model_prob + 0.3 * rule_score
            importance_score = fused_before_penalties
        else:
            model_prob = None
            # Rule based fallback: semantic first + bounded prosody boost.
            importance_score = rule_score

        # Apply ALL reliability penalties even in supervised mode.
        # Short segments (<5 words)
        if word_count < 5:
            importance_score -= 0.18
            if word_count <= 2:
                importance_score -= 0.10

        # Filler/uncertainty phrases
        if text_lower in _LOW_INFORMATION_PHRASES or _contains_low_information(text_lower):
            importance_score -= 0.20

        # Low ASR confidence
        asr_confidence = seg.get("asr_confidence")
        if asr_confidence is not None:
            asr_conf = float(max(0.0, min(1.0, asr_confidence)))
            if asr_conf < 0.45:
                importance_score -= (0.45 - asr_conf) * 0.35

        # Low-information / hallucination-like patterns
        if _is_low_reliability_text(text_lower):
            importance_score -= 0.12

        importance_score = float(max(0.0, min(1.5, importance_score)))

        seg_with_score = seg.copy()
        seg_with_score["importance_score"] = importance_score
        if model_prob is not None:
            seg_with_score["model_importance_probability"] = model_prob
            seg_with_score["model_threshold"] = float(model_bundle.get("threshold", 0.5))
            # Analysis field requested: keep base_importance_score as the raw model prob
            seg_with_score["base_importance_score"] = model_prob

        # Explainable prosody (for Prosodic Analysis Panel + XAI layer)
        pitch_level = _level_from_percentiles(
            seg["pitch_variance"], p_pitch_33, p_pitch_66
        )
        energy_level = _level_from_percentiles(
            seg["mean_energy"], p_energy_33, p_energy_66
        )
        pause_emphasis = bool(seg["pause_ratio"] >= p_pause_66)

        seg_with_score["pitch_variation_level"] = pitch_level
        seg_with_score["energy_level"] = energy_level
        seg_with_score["pause_emphasis"] = pause_emphasis

        # Human readable explanation of why this segment was marked important
        reasons = []
        if model_prob is not None and fused_before_penalties is not None:
            reasons.append(
                "Supervised model probability="
                f"{_format_float_for_importance_reason(model_prob)}; "
                "fused raw score (0.7*model_prob+0.3*rule_score)="
                f"{_format_float_for_importance_reason(fused_before_penalties)}; "
                "after reliability penalties, importance_score="
                f"{_format_float_for_importance_reason(importance_score)}."
            )
        else:
            reasons.extend(semantic_reasons)

        if not model_mode and context_boost >= 0.06:
            reasons.append("Context-window boost: neighboring turns indicate related substantive discussion.")

        if not model_mode and prosody_boost >= 0.18:
            reasons.append("Strong prosodic emphasis boosted this segment's semantic relevance.")
        elif not model_mode and prosody_boost >= 0.08:
            reasons.append("Moderate prosodic emphasis added a small importance boost.")

        # Pitch / energy / pause cues
        if pitch_level == "High":
            reasons.append("High pitch variation detected (speaker changed tone noticeably).")
        if energy_level == "High":
            reasons.append("High speaking energy detected (louder or more forceful delivery).")
        if pause_emphasis:
            reasons.append("Pause emphasis detected before or after this segment (silence around it).")

        # Keep previous urgency explanation for compatibility with existing UI wording
        text_for_urgency = text_lower
        if text_for_urgency and keyword_hits == 0:
            matched_urgency = sorted({kw for kw in _URGENCY_KEYWORDS if kw in text_for_urgency})
            if matched_urgency:
                shown = ", ".join(matched_urgency[:3])
                reasons.append(f"Urgency / decision-oriented keywords detected in text ({shown}).")

        if not model_mode and word_count < 4:
            reasons.append("Very short utterance, so importance was down-weighted.")
        if not model_mode and text_lower in _LOW_INFORMATION_PHRASES:
            reasons.append("Filler/backchannel phrase detected, reducing final importance.")
        if not model_mode and seg.get("asr_confidence") is not None and float(seg.get("asr_confidence") or 0.0) < 0.45:
            reasons.append("Low ASR confidence reduced importance reliability.")
        if not model_mode and _is_low_reliability_text(text_lower):
            reasons.append("Hallucination/low-reliability text pattern detected, reducing importance.")

        seg_with_score["importance_reasons"] = reasons

        ranked_segments.append(seg_with_score)

    # Sort by importance (descending)
    ranked_segments.sort(
        key=lambda x: x["importance_score"],
        reverse=True
    )

    return ranked_segments

