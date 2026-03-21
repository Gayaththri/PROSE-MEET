import math
import re
from collections import Counter
from typing import Dict, Iterable, List, Optional, Tuple


def _tokenize_words(text: str) -> List[str]:
    if not text:
        return []
    return [t for t in re.split(r"\s+", text.strip().lower()) if t]


def _tokenize_chars(text: str) -> List[str]:
    return list((text or "").strip().lower())


def _levenshtein_distance(a: List[str], b: List[str]) -> int:
    n, m = len(a), len(b)
    if n == 0:
        return m
    if m == 0:
        return n
    dp = list(range(m + 1))
    for i in range(1, n + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, m + 1):
            tmp = dp[j]
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[j] = min(
                dp[j] + 1,      # deletion
                dp[j - 1] + 1,  # insertion
                prev + cost,    # substitution
            )
            prev = tmp
    return dp[m]


def wer(reference: str, hypothesis: str) -> Optional[float]:
    ref = _tokenize_words(reference)
    hyp = _tokenize_words(hypothesis)
    if len(ref) == 0:
        return None
    return _levenshtein_distance(ref, hyp) / len(ref)


def cer(reference: str, hypothesis: str) -> Optional[float]:
    ref = _tokenize_chars(reference)
    hyp = _tokenize_chars(hypothesis)
    if len(ref) == 0:
        return None
    return _levenshtein_distance(ref, hyp) / len(ref)


def _ngrams(tokens: List[str], n: int) -> Counter:
    if n <= 0 or len(tokens) < n:
        return Counter()
    return Counter(tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1))


def _rouge_n(reference: str, hypothesis: str, n: int) -> Optional[float]:
    ref_toks = _tokenize_words(reference)
    hyp_toks = _tokenize_words(hypothesis)
    ref_ngrams = _ngrams(ref_toks, n)
    hyp_ngrams = _ngrams(hyp_toks, n)
    if not ref_ngrams:
        return None
    overlap = sum(min(count, hyp_ngrams[ng]) for ng, count in ref_ngrams.items())
    precision = overlap / max(sum(hyp_ngrams.values()), 1)
    recall = overlap / max(sum(ref_ngrams.values()), 1)
    if precision + recall == 0:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)


def _lcs_length(a: List[str], b: List[str]) -> int:
    n, m = len(a), len(b)
    if n == 0 or m == 0:
        return 0
    dp = [0] * (m + 1)
    for i in range(1, n + 1):
        prev = 0
        for j in range(1, m + 1):
            cur = dp[j]
            if a[i - 1] == b[j - 1]:
                dp[j] = prev + 1
            else:
                dp[j] = max(dp[j], dp[j - 1])
            prev = cur
    return dp[m]


def rouge_l(reference: str, hypothesis: str) -> Optional[float]:
    ref_toks = _tokenize_words(reference)
    hyp_toks = _tokenize_words(hypothesis)
    if not ref_toks:
        return None
    lcs = _lcs_length(ref_toks, hyp_toks)
    precision = lcs / max(len(hyp_toks), 1)
    recall = lcs / len(ref_toks)
    if precision + recall == 0:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)


def rouge_scores(reference: str, hypothesis: str) -> Dict[str, Optional[float]]:
    return {
        "rouge1_f1": _rouge_n(reference, hypothesis, 1),
        "rouge2_f1": _rouge_n(reference, hypothesis, 2),
        "rougel_f1": rouge_l(reference, hypothesis),
    }


def precision_recall_f1_binary(y_true: List[int], y_pred: List[int]) -> Dict[str, float]:
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": float(tp),
        "fp": float(fp),
        "fn": float(fn),
    }


def accuracy(y_true: List[str], y_pred: List[str]) -> Optional[float]:
    if not y_true:
        return None
    c = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    return c / len(y_true)


def macro_f1(y_true: List[str], y_pred: List[str]) -> Optional[float]:
    if not y_true:
        return None
    labels = sorted(set(y_true) | set(y_pred))
    if not labels:
        return None
    f1s = []
    for lab in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p == lab)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != lab and p == lab)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p != lab)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        f1s.append(f1)
    return sum(f1s) / len(f1s)


def safe_mean(values: Iterable[Optional[float]]) -> Optional[float]:
    arr = [float(v) for v in values if v is not None and not math.isnan(v)]
    if not arr:
        return None
    return sum(arr) / len(arr)
