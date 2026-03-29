"""
Trains, calibrates, saves, and serves a logistic-regression importance classifier using TF-IDF text plus prosody/ASR/context features.
"""
import json
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import joblib
import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_curve
from sklearn.preprocessing import StandardScaler


MODEL_FILENAME = "importance_classifier.joblib"
METADATA_FILENAME = "importance_classifier_meta.json"
DEFAULT_THRESHOLD = 0.5

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

_HALLUCINATION_BLOCKLIST = frozenset(
    s.strip().lower()
    for s in (
        "mermaid",
        "whales",
        "they can swim",
        "television",
        "five remotes",
        "oh my god",
        "it's not a mermaid",
        "the reason i like whales",
    )
)


def _default_model_dir() -> str:
    backend_root = os.path.dirname(os.path.dirname(__file__))
    return os.path.join(backend_root, "models")


def model_paths(model_dir: Optional[str] = None) -> Tuple[str, str]:
    base_dir = model_dir or _default_model_dir()
    return (
        os.path.join(base_dir, MODEL_FILENAME),
        os.path.join(base_dir, METADATA_FILENAME),
    )


def _segment_numeric_features(seg: Dict[str, Any]) -> List[float]:
    text = (seg.get("text") or "").strip()
    text_lower = text.lower()
    words = [w for w in re.split(r"\s+", text) if w]
    word_count = len(words)
    keyword_hits = float(sum(1 for kw in _SEMANTIC_KEYWORDS if kw in text_lower))
    has_number = 1.0 if re.search(r"\b\d+(?:[\.,]\d+)?\b", text_lower) else 0.0
    low_information = 1.0 if text_lower in _LOW_INFORMATION_PHRASES else 0.0
    duration = float(max(0.0, (seg.get("end", 0.0) or 0.0) - (seg.get("start", 0.0) or 0.0)))
    asr_confidence = seg.get("asr_confidence")
    asr_confidence = float(asr_confidence) if asr_confidence is not None else 0.5
    hallucination_risk = 1.0 if _hallucination_risk(text_lower) else 0.0

    return [
        float(seg.get("pitch_variance", 0.0) or 0.0),
        float(seg.get("mean_energy", 0.0) or 0.0),
        float(seg.get("pause_ratio", 0.0) or 0.0),
        float(word_count),
        float(len(text)),
        keyword_hits,
        has_number,
        low_information,
        duration,
        asr_confidence,
        hallucination_risk,
    ]


def _hallucination_risk(text_lower: str) -> bool:
    if not text_lower:
        return True
    if any(p in text_lower for p in _HALLUCINATION_BLOCKLIST):
        return True
    alpha_chars = sum(1 for ch in text_lower if ch.isalpha())
    ratio_alpha = alpha_chars / max(len(text_lower), 1)
    if ratio_alpha < 0.45:
        return True
    return False


def build_feature_matrices(
    segments: Sequence[Dict[str, Any]],
    vectorizer: Optional[TfidfVectorizer] = None,
    scaler: Optional[StandardScaler] = None,
    fit: bool = False,
):
    texts = [(seg.get("text") or "").strip().lower() for seg in segments]
    base_numeric = np.array([_segment_numeric_features(seg) for seg in segments], dtype=np.float32)
    if len(base_numeric) == 0:
        numeric = base_numeric
    else:
        prev_numeric = np.vstack([np.zeros((1, base_numeric.shape[1]), dtype=np.float32), base_numeric[:-1]])
        next_numeric = np.vstack([base_numeric[1:], np.zeros((1, base_numeric.shape[1]), dtype=np.float32)])
        # Context-window features: previous and next segment cues.
        numeric = np.hstack([base_numeric, prev_numeric, next_numeric]).astype(np.float32)

    if fit:
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=6000, min_df=1)
        scaler = StandardScaler()
        text_matrix = vectorizer.fit_transform(texts)
        numeric_scaled = scaler.fit_transform(numeric)
    else:
        if vectorizer is None or scaler is None:
            raise ValueError("vectorizer and scaler are required when fit=False")
        text_matrix = vectorizer.transform(texts)
        numeric_scaled = scaler.transform(numeric)

    x = sparse.hstack([text_matrix, sparse.csr_matrix(numeric_scaled)], format="csr")
    return x, vectorizer, scaler


def train_classifier(
    segments: Sequence[Dict[str, Any]],
    labels: Sequence[int],
) -> Dict[str, Any]:
    x, vectorizer, scaler = build_feature_matrices(segments, fit=True)
    y = np.array(labels).astype(int)
    classifier = LogisticRegression(max_iter=1500, class_weight="balanced")
    classifier.fit(x, y)
    return {
        "vectorizer": vectorizer,
        "scaler": scaler,
        "classifier": classifier,
    }


def predict_probabilities(
    segments: Sequence[Dict[str, Any]],
    model_bundle: Dict[str, Any],
) -> np.ndarray:
    if not segments:
        return np.array([], dtype=np.float32)
    x, _, _ = build_feature_matrices(
        segments,
        vectorizer=model_bundle["vectorizer"],
        scaler=model_bundle["scaler"],
        fit=False,
    )
    probs = model_bundle["classifier"].predict_proba(x)[:, 1]
    return probs.astype(np.float32)


def calibrate_threshold(
    labels: Sequence[int],
    probabilities: Sequence[float],
    min_precision: Optional[float] = None,
) -> Dict[str, float]:
    y_true = np.array(labels).astype(int)
    y_prob = np.array(probabilities).astype(float)

    if len(y_true) == 0:
        return {"threshold": DEFAULT_THRESHOLD, "f1": 0.0, "precision": 0.0, "recall": 0.0}

    precision, recall, thresholds = precision_recall_curve(y_true, y_prob)
    if len(thresholds) == 0:
        return {"threshold": DEFAULT_THRESHOLD, "f1": 0.0, "precision": 0.0, "recall": 0.0}

    best = {"threshold": DEFAULT_THRESHOLD, "f1": -1.0, "precision": 0.0, "recall": 0.0}
    for idx, threshold in enumerate(thresholds):
        p = float(precision[idx])
        r = float(recall[idx])
        if min_precision is not None and p < min_precision:
            continue
        f1 = 0.0 if (p + r) == 0 else (2.0 * p * r) / (p + r)
        if f1 > best["f1"]:
            best = {
                "threshold": float(threshold),
                "f1": float(f1),
                "precision": p,
                "recall": r,
            }

    if best["f1"] < 0:
        return {"threshold": DEFAULT_THRESHOLD, "f1": 0.0, "precision": 0.0, "recall": 0.0}
    return best


def save_model(
    model_bundle: Dict[str, Any],
    threshold: float,
    model_dir: Optional[str] = None,
    metrics: Optional[Dict[str, float]] = None,
) -> Dict[str, str]:
    model_path, metadata_path = model_paths(model_dir=model_dir)
    os.makedirs(os.path.dirname(model_path), exist_ok=True)

    joblib.dump(model_bundle, model_path)
    metadata = {
        "threshold": float(threshold),
        "metrics": metrics or {},
    }
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    return {"model_path": model_path, "metadata_path": metadata_path}


def load_model(model_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    model_path, metadata_path = model_paths(model_dir=model_dir)
    if not os.path.isfile(model_path):
        return None

    bundle = joblib.load(model_path)
    threshold = DEFAULT_THRESHOLD
    metadata = {}
    if os.path.isfile(metadata_path):
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            threshold = float(metadata.get("threshold", DEFAULT_THRESHOLD))
        except Exception:
            threshold = DEFAULT_THRESHOLD
            metadata = {}

    bundle["threshold"] = threshold
    bundle["metadata"] = metadata
    bundle["model_path"] = model_path
    bundle["metadata_path"] = metadata_path
    return bundle
