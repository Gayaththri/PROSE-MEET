"""
Performs zero-shot meeting domain detection with frozen sentence-embedding prototypes and provides per-segment semantic relevance scores for domain-adaptive importance scaling.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

import numpy as np

from .domain import DEFAULT_DOMAIN, DEFAULT_STRATEGY, DOMAIN_LABELS

# Rich prototypes (not keyword lists) so semantic similarity can generalize.
DOMAIN_PROTOTYPES: Dict[str, List[str]] = {
    "corporate": [
        "A workplace meeting about projects, budgets, deadlines, clients, and business strategy.",
        "Discussion of quarterly goals, stakeholders, deliverables, and executive decisions.",
        "Team coordination on product roadmaps, contracts, and customer requirements.",
    ],
    "academic": [
        "A university or research discussion about papers, methodology, literature review, and findings.",
        "Seminar on thesis work, citations, course assignments, and peer review.",
        "Faculty and students discussing research hypotheses, experiments, and publications.",
        "A research group meeting about speech processing, transcripts, annotations, recognition, and acoustic features.",
        "Lab discussion of datasets, corpora, alignment, prosody, and experimental methodology.",
        "Panel or public forum on higher education, the mission of universities, and interdisciplinary teaching.",
        "Symposium on humanities, liberal arts, research funding for scholars, and academic public engagement.",
        "A student thesis or dissertation defense presenting research aims, gaps, methodology, evaluation, and contributions.",
        "Final-year or graduate research project presentation describing system design, experiments, results, and future work.",
        
        
    ],
    "medical": [
        "Clinical discussion of patient symptoms, diagnosis, treatment plan, and medication.",
        "Healthcare team reviewing vitals, prognosis, discharge, and care coordination.",
        "Doctor and staff discussing therapy, consultation, referral, and medical follow-up.",
    ],
}

_MODEL = None
_PROTO_EMBEDDINGS: Optional[Dict[str, np.ndarray]] = None
# Increment when DOMAIN_PROTOTYPES changes so running workers reload prototype vectors.
_PROTO_CACHE_VERSION = 2
_PROTO_CACHE_VERSION_LOADED: Optional[int] = None

# Lightweight lexical prior to stabilize low-confidence SSL predictions.
# This is intentionally small and only nudges near tie outcomes.
_ACADEMIC_CUE_PATTERNS = (
    r"\bsubject(?:s)?\b",
    r"\bontology\b",
    r"\blinguist(?:s)?\b",
    r"\bgraduate school\b",
    r"\bthesis\b",
    r"\bhigher education\b",
    r"\bhumanities\b",
    r"\bliberal arts\b",
    r"\bdissertation\b",
    r"\bmethodology\b",
    r"\bresearch gap\b",
    r"\bresearch gaps\b",
    r"\bresearch aim\b",
    r"\bresearch project\b",
    r"\bliterature\b",
    r"\bpublication\b",
    r"\bcitation\b",
    r"\bpeer review\b",
    r"\bcontribution to knowledge\b",
    r"\bexperimental evaluation\b",
    r"\bacademic\b",
    r"\buniversity\b",
    r"\bdefense\b",
    r"\bviva\b",
    r"\bcapstone\b",
)


def _session_context_academic_boost(session_context: Optional[str]) -> float:
    """Extra cosine nudge when filename or title looks like a thesis or academic submission."""
    if not session_context or not str(session_context).strip():
        return 0.0
    t = str(session_context).lower()
    t = re.sub(r"[_\-]+", " ", t)
    filename_patterns = (
        r"\bthesis\b",
        r"\bdissertation\b",
        r"\bphd\b",
        r"\bm\.?phil\b",
        r"\bdefense\b",
        r"\bviva\b",
        r"\bcapstone\b",
        r"\bfinal\s+year\b",
        r"\bpresentation\s+slides\b",
        r"\bw\d{5,}\b",  # student id token often embedded in academic filenames
    )
    hits = sum(1 for p in filename_patterns if re.search(p, t))
    return min(0.12, 0.04 * float(hits))


def _get_model():
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer

        name = os.getenv(
            "PROSE_SSL_MODEL",
            "sentence-transformers/all-MiniLM-L6-v2",
        )
        _MODEL = SentenceTransformer(name)
    return _MODEL


def _l2_normalize(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n < 1e-12:
        return v
    return v / n


def _encode_long_text(model, text: str, max_words_per_chunk: int = 220) -> np.ndarray:
    """Mean-pool chunk embeddings so long meetings are not single-truncated windows."""
    words = text.split()
    if not words:
        return np.zeros(model.get_sentence_embedding_dimension(), dtype=np.float32)
    chunks: List[str] = []
    for i in range(0, len(words), max_words_per_chunk):
        chunks.append(" ".join(words[i : i + max_words_per_chunk]))
    embs = model.encode(
        chunks,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return np.mean(embs, axis=0).astype(np.float32)


def _get_proto_embeddings(model) -> Dict[str, np.ndarray]:
    global _PROTO_EMBEDDINGS, _PROTO_CACHE_VERSION_LOADED
    if (
        _PROTO_EMBEDDINGS is not None
        and _PROTO_CACHE_VERSION_LOADED == _PROTO_CACHE_VERSION
    ):
        return _PROTO_EMBEDDINGS
    out: Dict[str, np.ndarray] = {}
    for domain, sentences in DOMAIN_PROTOTYPES.items():
        embs = model.encode(
            sentences,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        proto = np.mean(embs, axis=0).astype(np.float32)
        out[domain] = _l2_normalize(proto)
    _PROTO_EMBEDDINGS = out
    _PROTO_CACHE_VERSION_LOADED = _PROTO_CACHE_VERSION
    return out


def _softmax(x: np.ndarray, temperature: float = 1.35) -> np.ndarray:
    x = (x - np.max(x)) / max(temperature, 1e-6)
    e = np.exp(x)
    return e / np.sum(e)


def _calibrated_confidence(probs: np.ndarray) -> float:
    """
    Calibrate confidence from distribution sharpness instead of a hard floor.
    Uses top probability + top-vs-second margin so near ties stay low.
    """
    if probs.size == 0:
        return 0.5
    sorted_probs = np.sort(probs)
    top1 = float(sorted_probs[-1])
    top2 = float(sorted_probs[-2]) if probs.size > 1 else 0.0
    margin = max(0.0, top1 - top2)

    # Margin normalization tuned for 3 way classification.
    margin_signal = min(1.0, margin / 0.12)
    # Blend class probability and separability.
    confidence = (0.55 * top1) + (0.45 * margin_signal)
    return max(0.30, min(0.95, confidence))


def _gather_meeting_text(
    transcript: List[Dict[str, Any]],
    summary: Optional[str],
    speaker_summaries: Optional[List[Dict[str, Any]]],
    session_context: Optional[str] = None,
) -> str:
    parts: List[str] = []
    ctx = (session_context or "").strip()
    if ctx:
        parts.append(ctx)
    for s in transcript or []:
        t = (s.get("text") or "").strip()
        if t:
            parts.append(t)
    if summary:
        parts.append(summary.strip())
    if speaker_summaries:
        for sp in speaker_summaries:
            parts.append((sp.get("summary") or "").strip())
    text = " ".join(parts)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def detect_domain_ssl_zero_shot(
    transcript: List[Dict[str, Any]],
    summary: str = None,
    speaker_summaries: List[Dict[str, Any]] = None,
    session_context: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Zero-shot domain classification: cosine similarity of meeting embedding to
    frozen domain prototype embeddings (no training on labelled meetings).
    """
    text = _gather_meeting_text(
        transcript, summary, speaker_summaries, session_context=session_context
    )
    if not text:
        label, strategy = DOMAIN_LABELS.get(
            DEFAULT_DOMAIN, (DEFAULT_DOMAIN.title(), DEFAULT_STRATEGY)
        )
        return {
            "predicted_domain": DEFAULT_DOMAIN,
            "confidence": 0.5,
            "adaptation_strategy": strategy,
            "domain_label": label,
            "domain_method": "ssl_zero_shot",
            "ssl_model": os.getenv(
                "PROSE_SSL_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
            ),
            "ssl_domain_scores": {},
        }

    model = _get_model()
    meeting_emb = _l2_normalize(_encode_long_text(model, text))
    protos = _get_proto_embeddings(model)

    domains = ("corporate", "academic", "medical")
    sims = np.array([float(np.dot(meeting_emb, protos[d])) for d in domains], dtype=np.float64)
    # Small academic prior: when explicit research cues are present, nudge
    # the semantic similarity before softmax to reduce corporate false positives.
    academic_idx = domains.index("academic")
    academic_hits = sum(1 for p in _ACADEMIC_CUE_PATTERNS if re.search(p, text))
    if academic_hits > 0:
        # Stronger nudge when many academic cues appear (thesis-style talks).
        sims[academic_idx] += min(0.22, 0.03 * float(academic_hits))
    sims[academic_idx] += _session_context_academic_boost(session_context)
    # Default 1.35 modestly sharpens softmax vs 2.0; override with PROSE_SSL_TEMPERATURE.
    probs = _softmax(sims, temperature=float(os.getenv("PROSE_SSL_TEMPERATURE", "1.35")))
    best_idx = int(np.argmax(probs))
    best_domain = domains[best_idx]
    confidence = _calibrated_confidence(probs)

    label, strategy = DOMAIN_LABELS.get(best_domain, (best_domain.title(), "General"))

    return {
        "predicted_domain": best_domain,
        "confidence": round(confidence, 2),
        "adaptation_strategy": strategy,
        "domain_label": label,
        "domain_method": "ssl_zero_shot",
        "ssl_model": os.getenv(
            "PROSE_SSL_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
        ),
        "ssl_domain_scores": {d: round(float(probs[i]), 4) for i, d in enumerate(domains)},
    }


def batch_segment_prototype_relevance(
    ranked_segments: List[Dict[str, Any]],
    predicted_domain: str,
) -> List[float]:
    """
    Per-segment cosine similarity (mapped to [0,1]) between each utterance embedding
    and the frozen prototype vector for the predicted domain. Used for SSL zero-shot
    domain-adaptive importance (no keyword overlap required).
    """
    if not ranked_segments:
        return []
    domain = predicted_domain if predicted_domain in DOMAIN_PROTOTYPES else DEFAULT_DOMAIN
    model = _get_model()
    proto = _get_proto_embeddings(model)[domain]

    relevances = [0.0] * len(ranked_segments)
    indexed_texts: List[tuple] = []
    for i, seg in enumerate(ranked_segments):
        t = (seg.get("text") or "").strip()
        if t:
            indexed_texts.append((i, t))

    if not indexed_texts:
        return relevances

    indices, texts = zip(*indexed_texts)
    embs = model.encode(
        list(texts),
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    for j, idx in enumerate(indices):
        e = _l2_normalize(embs[j].astype(np.float32))
        sim = float(np.dot(e, proto))
        # Cosine in [-1, 1] → [0, 1] relevance for boosting
        rel = max(0.0, min(1.0, (sim + 1.0) / 2.0))
        relevances[idx] = rel

    return relevances
