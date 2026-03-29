"""
Detects meeting domain and applies domain-adaptive reweighting to importance scores for more context-aware highlights and summaries.
"""
import math
import os
import re
from typing import Dict, Any, List

# Domain keywords (lowercase) – presence boosts that domain's score
DOMAIN_SIGNALS = {
    "corporate": [
        # Note: "meeting" is omitted — it appears in corporate, academic, and medical
        # recordings alike and skews lexical scores toward Corporate.
        "agenda", "minutes", "project", "plan", "discuss", "decision",
        "stakeholder", "team", "action", "follow up", "schedule", "deadline",
        "review", "kickoff", "manager", "goal", "objective", "budget", "quarter",
        "kpi", "roi", "client", "customer", "contract", "proposal", "presentation",
        "board", "executive", "strategy", "metrics", "timeline", "milestone",
    ],
    "academic": [
        "lecture", "research", "paper", "thesis", "dissertation", "supervisor",
        "conference", "citation", "methodology", "hypothesis", "findings",
        "literature", "seminar", "course", "assignment", "grading", "student",
        "professor", "department", "publication", "journal", "peer review",
        # Research-lab / speech & language meetings (e.g. ICSI-style transcripts)
        "transcript", "annotation", "annotations", "corpus", "dataset",
        "utterance", "discourse", "prosody", "alignment", "recognizer",
        "recognition", "speaker", "channel", "overlap", "segment", "lattice",
        "phoneme", "encoding", "xml",
    ],
    "medical": [
        "patient", "treatment", "diagnosis", "symptoms", "clinical", "therapy",
        "medication", "prescription", "consultation", "referral", "discharge",
        "vitals", "prognosis", "care plan", "rounds", "attending", "resident",
    ],
}

# Human-readable labels and adaptation strategies per domain
DOMAIN_LABELS = {
    "corporate": ("Corporate", "Decision-Focused"),
    "academic": ("Academic", "Evidence-Focused"),
    "medical": ("Medical", "Outcome-Focused"),
}

# Strategy profile used to adapt Gap 1 importance ranking per domain.
DOMAIN_ADAPTATION_PROFILES = {
    "corporate": {
        "keyword_weight": 0.22,
        "numeric_bonus": 0.10,  # budgets / dates / targets often matter.
        "max_domain_boost": 1.2,
    },
    "academic": {
        "keyword_weight": 0.20,
        "numeric_bonus": 0.08,
        "max_domain_boost": 1.1,
    },
    "medical": {
        "keyword_weight": 0.24,
        "numeric_bonus": 0.10,  # dosage / vitals / timings are often critical.
        "max_domain_boost": 1.25,
    },
}

DEFAULT_DOMAIN = "corporate"
DEFAULT_CONFIDENCE = 0.72
DEFAULT_STRATEGY = "Decision-Focused"


def _text_from_segments(segments: List[Dict[str, Any]]) -> str:
    """Concatenate segment text for analysis."""
    if not segments:
        return ""
    return " ".join((s.get("text") or "").strip() for s in segments).lower()


def _detect_domain_keyword(
    transcript: List[Dict[str, Any]],
    summary: str = None,
    speaker_summaries: List[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Lexical keyword baseline (no neural encoder)."""
    text = _text_from_segments(transcript)
    if summary:
        text += " " + (summary or "").strip().lower()
    if speaker_summaries:
        for sp in speaker_summaries:
            text += " " + (sp.get("summary") or "").strip().lower()
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return {
            "predicted_domain": DEFAULT_DOMAIN,
            "confidence": 0.5,
            "adaptation_strategy": DEFAULT_STRATEGY,
            "domain_label": DOMAIN_LABELS.get(DEFAULT_DOMAIN, (DEFAULT_DOMAIN.title(), DEFAULT_STRATEGY))[0],
            "domain_method": "keyword",
        }

    scores = {}
    for domain, keywords in DOMAIN_SIGNALS.items():
        count = sum(1 for kw in keywords if kw in text)
        # Normalize by number of keywords so no domain is favoured by size
        scores[domain] = count / max(len(keywords), 1)

    if not scores or max(scores.values()) == 0:
        label, strategy = DOMAIN_LABELS.get(DEFAULT_DOMAIN, (DEFAULT_DOMAIN.title(), DEFAULT_STRATEGY))
        return {
            "predicted_domain": DEFAULT_DOMAIN,
            "confidence": DEFAULT_CONFIDENCE,
            "adaptation_strategy": strategy,
            "domain_label": label,
            "domain_method": "keyword",
        }

    best_domain = max(scores, key=scores.get)
    raw = scores[best_domain]
    # Map to a plausible confidence (e.g. 0.5–0.95) so we don't show 0.02
    confidence = min(0.95, 0.5 + raw * 0.6)
    label, strategy = DOMAIN_LABELS.get(best_domain, (best_domain.title(), "General"))

    return {
        "predicted_domain": best_domain,
        "confidence": round(confidence, 2),
        "adaptation_strategy": strategy,
        "domain_label": label,
        "domain_method": "keyword",
    }


def detect_domain(
    transcript: List[Dict[str, Any]],
    summary: str = None,
    speaker_summaries: List[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Predict meeting domain from transcript and optional summary text.

    Default: **self-supervised zero-shot** — frozen pretrained sentence encoder
    (MiniLM / Sentence-BERT family) + prototype similarity; no fine-tuning on
    meeting-domain labels. Set PROSE_DOMAIN_METHOD=keyword for lexical baseline
    only. If sentence-transformers is unavailable, falls back to keyword matching.

    Returns:
        {
            "predicted_domain": "corporate" | "academic" | "medical",
            "confidence": float in [0, 1],
            "adaptation_strategy": str,
            "domain_label": str,
            "domain_method": "keyword" | "ssl_zero_shot",
            optional: "ssl_model", "ssl_domain_scores" (ssl path only)
        }
    """
    method = (os.getenv("PROSE_DOMAIN_METHOD") or "ssl_zero_shot").strip().lower()
    if method in ("keyword", "lexical"):
        return _detect_domain_keyword(
            transcript, summary=summary, speaker_summaries=speaker_summaries
        )
    try:
        from .ssl_zero_shot_domain import detect_domain_ssl_zero_shot

        return detect_domain_ssl_zero_shot(
            transcript=transcript,
            summary=summary,
            speaker_summaries=speaker_summaries,
        )
    except Exception:
        return _detect_domain_keyword(
            transcript, summary=summary, speaker_summaries=speaker_summaries
        )


def get_domain_focus_keywords(domain_result: Dict[str, Any]) -> List[str]:
    """Return keyword list for the detected domain."""
    domain = (domain_result or {}).get("predicted_domain", DEFAULT_DOMAIN)
    return list(DOMAIN_SIGNALS.get(domain, DOMAIN_SIGNALS[DEFAULT_DOMAIN]))


def get_domain_importance_threshold(domain_result: Dict[str, Any]) -> float:
    """
    Domain-calibrated threshold for selecting high-importance highlights.
    Corporate/medical meetings often need slightly stricter thresholding.
    """
    domain = (domain_result or {}).get("predicted_domain", DEFAULT_DOMAIN)
    confidence = float((domain_result or {}).get("confidence", 0.5) or 0.5)
    confidence = max(0.0, min(1.0, confidence))

    base = {
        "corporate": 0.58,
        "academic": 0.52,
        "medical": 0.60,
    }.get(domain, 0.56)

    # If domain certainty is low, relax threshold slightly to avoid over-filtering.
    relax = (0.6 - confidence) * 0.08 if confidence < 0.6 else 0.0
    threshold = max(0.45, min(0.75, base - relax))
    return round(threshold, 3)


def apply_domain_adaptation(
    ranked_segments: List[Dict[str, Any]],
    domain_result: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Adapt importance scores using domain focus cues so Gap 2 influences Gap 1 output.

    With SSL zero-shot domain detection, uses **prototype embedding similarity** per
    segment (self-supervised encoder, no keyword lists). Otherwise uses lexical
    keyword overlap. Keeps the original score in `base_importance_score` and writes
    adapted score to `importance_score`.
    """
    if not ranked_segments:
        return []

    domain = (domain_result or {}).get("predicted_domain", DEFAULT_DOMAIN)
    confidence = float((domain_result or {}).get("confidence", 0.5) or 0.5)
    confidence = max(0.0, min(1.0, confidence))

    profile = DOMAIN_ADAPTATION_PROFILES.get(
        domain, DOMAIN_ADAPTATION_PROFILES[DEFAULT_DOMAIN]
    )
    focus_keywords = DOMAIN_SIGNALS.get(domain, DOMAIN_SIGNALS[DEFAULT_DOMAIN])
    keyword_weight = float(profile.get("keyword_weight", 0.07))
    numeric_bonus = float(profile.get("numeric_bonus", 0.03))
    max_domain_boost = float(profile.get("max_domain_boost", 1.1))

    use_ssl = (domain_result or {}).get("domain_method") == "ssl_zero_shot"
    ssl_rel: List[float] | None = None
    if use_ssl:
        try:
            from .ssl_zero_shot_domain import batch_segment_prototype_relevance

            ssl_rel = batch_segment_prototype_relevance(ranked_segments, domain)
        except Exception:
            use_ssl = False

    adapted = []
    for i, seg in enumerate(ranked_segments):
        text = (seg.get("text") or "").strip().lower()
        # For Gap-2 ranking, domain adaptation must start from the current
        # `importance_score` (which may already include supervised fusion + penalties).
        ranking_base_score = float(seg.get("importance_score", 0.0) or 0.0)

        # For analysis, preserve the raw supervised model probability when provided.
        analysis_base = seg.get("base_importance_score")
        analysis_base_score = (
            float(analysis_base)
            if isinstance(analysis_base, (int, float)) and math.isfinite(float(analysis_base))
            else ranking_base_score
        )

        if use_ssl and ssl_rel is not None:
            rel = float(ssl_rel[i])
            kw_hits = int(round(rel * 10.0))
            keyword_boost = keyword_weight * math.log1p(rel * 8.0)
        else:
            kw_hits = sum(1 for kw in focus_keywords if kw in text)
            keyword_boost = keyword_weight * math.log1p(kw_hits)

        number_boost = 0.0
        if re.search(r"\b\d+(?:[\.,]\d+)?\b", text):
            number_boost = numeric_bonus

        domain_boost = max(0.0, min(max_domain_boost, keyword_boost + number_boost))
        # Balanced multiplicative adaptation:
        # importance_score = base_score * (1 + 0.3 * domain_boost * confidence)
        adapted_score = ranking_base_score * (1.0 + 0.3 * domain_boost * confidence)

        # Penalize domain-irrelevant segments (requested).
        if use_ssl and ssl_rel is not None:
            if ssl_rel[i] < 0.05:
                adapted_score *= 0.95
        elif kw_hits == 0:
            adapted_score *= 0.95

        # Safety blending to keep adaptation impact controlled.
        adapted_score = (0.9 * ranking_base_score) + (0.1 * adapted_score)

        # Do not reduce below 50% of base score.
        adapted_score = max(adapted_score, 0.5 * ranking_base_score)

        # Normalize to maintain stable range while increasing spread.
        adapted_score = max(0.0, min(1.8, adapted_score))

        seg_out = seg.copy()
        seg_out["base_importance_score"] = float(analysis_base_score)
        seg_out["domain_relevance_hits"] = kw_hits
        if use_ssl and ssl_rel is not None:
            seg_out["domain_ssl_relevance"] = round(float(ssl_rel[i]), 4)
        seg_out["domain_score_boost"] = round(domain_boost * confidence, 4)
        seg_out["importance_score"] = float(adapted_score)

        reasons = list(seg_out.get("importance_reasons") or [])
        if use_ssl and ssl_rel is not None:
            r = float(ssl_rel[i])
            if r >= 0.05:
                reasons.append(
                    f"SSL zero-shot scaling: semantic match to {domain} prototype (relevance={r:.2f})."
                )
            else:
                reasons.append(
                    "SSL zero-shot penalty: low semantic match to domain prototype; score down-weighted."
                )
        elif kw_hits > 0:
            reasons.append(
                f"Domain-adaptive scaling: {domain} keywords matched ({kw_hits} hit(s)); multiplicative boost applied."
            )
        else:
            reasons.append("Domain-adaptive penalty: no domain-relevant keywords detected; score down-weighted.")
        if number_boost > 0:
            reasons.append(
                f"Domain-adaptive numeric boost applied for {domain} strategy before scaling."
            )
        seg_out["importance_reasons"] = reasons
        adapted.append(seg_out)

    adapted.sort(key=lambda x: x.get("importance_score", 0.0), reverse=True)
    return adapted
