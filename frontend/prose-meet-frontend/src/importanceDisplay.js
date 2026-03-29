/**
 * Shared transcript importance thresholds and display labels (quartile + semantic guardrails).
 * Used by MeetingInsights and ImportanceTimelineHeatmap — keep in sync in one place.
 */
import { sanitizeImportanceReasons } from "./reasonFilters";

export function getTranscriptImportanceThresholds(transcript) {
  const scores = (transcript || [])
    .map((seg) => seg.importance_score)
    .filter((v) => typeof v === "number" && Number.isFinite(v))
    .sort((a, b) => a - b);

  if (!scores.length) {
    return { p25: 0.25, p50: 0.5, p75: 0.75 };
  }

  const at = (ratio) => scores[Math.floor(scores.length * ratio)] ?? scores[0];

  return {
    p25: at(0.25),
    p50: at(0.5),
    p75: at(0.75),
  };
}

function getImportanceMeta(score, thresholds) {
  const value = typeof score === "number" && Number.isFinite(score) ? score : 0;
  // IMPORTANT: keep behavior tied to the transcript quartiles.
  // (No extra absolute minimum cutoffs, so "top quartile" actually stays top quartile.)
  const veryThreshold = thresholds.p75;
  const highThreshold = thresholds.p50;

  if (value >= veryThreshold) return { key: "very-high", label: "Very important" };
  if (value >= highThreshold) return { key: "high", label: "Important" };
  if (value >= thresholds.p25) return { key: "medium", label: "Moderately important" };
  return { key: "low", label: "Low importance" };
}

const ACTION_KEYWORDS = [
  "need to",
  "must",
  "should",
  "plan",
  "decide",
  "deadline",
  "budget",
  "aim",
  "goal",
  "will",
];
const FILLER_PHRASES = ["i don't know", "yeah", "okay", "i think"];
const TOPIC_KEYWORDS = [
  "remote",
  "project",
  "product",
  "requirements",
  "requirement",
  "budget",
  "design",
  "market",
  "profit",
  "aim",
  "goal",
  "decision",
  "plan",
  "deadline",
  "instructions",
  "email",
  "timeline",
];

function segmentText(seg) {
  return String(seg?.text || seg?.content || "").trim();
}

function containsAnyKeyword(textLower, keywords) {
  return keywords.some((k) => textLower.includes(k));
}

function getSemanticEvidenceScore(seg) {
  const textLower = segmentText(seg).toLowerCase();
  if (!textLower) return 0;

  const reasons = Array.isArray(seg?.importance_reasons) ? sanitizeImportanceReasons(seg?.importance_reasons) : [];
  const semanticReasons = reasons.filter((r) => !/(pitch|energy|pause|prosody|acoustic)/i.test(r));
  const semanticReasonHits = semanticReasons.length;

  const topicHits = TOPIC_KEYWORDS.reduce((acc, k) => acc + (textLower.includes(k) ? 1 : 0), 0);
  const actionHits = ACTION_KEYWORDS.reduce((acc, k) => acc + (textLower.includes(k) ? 1 : 0), 0);
  const wordCount = textLower.split(/\s+/).filter(Boolean).length;

  // Text based meaning signal (robust even when importance_reasons are missing/filtered).
  const semanticTextSignal = Math.min(1, (topicHits + actionHits) / 6 + (wordCount >= 10 ? 0.25 : 0));

  // Reasons based signal is only a small boost (not the primary driver).
  const reasonSignal = Math.min(1, semanticReasonHits / 3);

  return Math.max(0, Math.min(1, semanticTextSignal * 0.8 + reasonSignal * 0.2));
}

function isGreetingOrIntroSegment(seg) {
  const text = String(seg?.text || seg?.content || "").toLowerCase();
  if (!text) return false;

  const patterns = [
    /\bgood (morning|afternoon|evening)\b/,
    /\bhello\b/,
    /\bhi\b/,
    /\bwelcome\b/,
    /\bhere we go\b/,
    /\bacquainted\b/,
    /\bget acquainted\b/,
    /\bglad you could all come\b/,
    /\bexcited to start\b/,
    /\bthank(s| you) for joining\b/,
    /\bmy name is\b/,
    /\bi('| a)?m .*project manager\b/,
    /\bkickoff meeting\b/,
    /\bi forgot to say/i,
    /\blet'?s get started\b/,
  ];
  return patterns.some((pattern) => pattern.test(text));
}

function isNonSubstantiveChatterSegment(seg) {
  const text = String(seg?.text || seg?.content || "").toLowerCase().trim();
  if (!text) return true;

  const explicitChatterPatterns = [
    /\bblah\b/,
    /\bhow do you spell your name\b/,
    /\bspell your name\b/,
    /\byou can call me\b/,
    /\bcall me\b/,
    /\bi have no artistic talent\b/,
    /\bcan you hear me\b/,
    /\byou are on mute\b/,
    /\bsorry (about|for) (that|this)\b/,
  ];
  if (explicitChatterPatterns.some((pattern) => pattern.test(text))) {
    return true;
  }

  const words = text.split(/\s+/).filter(Boolean);
  // Likely "I'm <Name> ..." intro lines (short and proper-noun looking).
  const looksLikeNameIntro =
    /\bi['\u2019]?m\s+[a-z]+(?:\s+[a-z]+){1,2}\b/.test(text) && words.length <= 12;
  if (looksLikeNameIntro) {
    return true;
  }

  const fillerWords = new Set([
    "uh", "um", "ah", "oh", "hmm", "huh", "yeah", "yes", "no", "ok", "okay",
    "alright", "right", "like", "well", "so", "anyway",
  ]);
  const fillerCount = words.filter((word) => fillerWords.has(word)).length;
  if (words.length <= 8 && fillerCount >= 2) {
    return true;
  }

  return false;
}

export function getDisplayImportanceMeta(seg, thresholds) {
  const rawScore =
    typeof seg?.importance_score === "number" && Number.isFinite(seg.importance_score)
      ? seg.importance_score
      : 0;
  const textLower = segmentText(seg).toLowerCase();
  const wordCount = textLower.split(/\s+/).filter(Boolean).length;
  const hasActionKeyword = containsAnyKeyword(textLower, ACTION_KEYWORDS);

  // Base label comes purely from `seg.importance_score` percentiles.
  let base = getImportanceMeta(rawScore, thresholds);

  // Down rank intro/name/chatter lines even if their raw score is high.
  if (isGreetingOrIntroSegment(seg) || isNonSubstantiveChatterSegment(seg)) {
    return { key: "low", label: "Low importance" };
  }

  // Make "Important"/"Very important" more selective:
  // keep them only when semantic meaning is strong enough (and not filler/too short).
  const semanticEvidence = getSemanticEvidenceScore(seg);
  const isFillerish = FILLER_PHRASES.some((f) => textLower.includes(f));
  const tooShort = wordCount < 6;

  if (base.key === "very-high") {
    // Require meaning; don't let prosody heavy chatter sneak into the top quartile.
    if (semanticEvidence < 0.28) base = { key: "high", label: "Important" };
    // "Very important" should be action oriented, unless semantic evidence is very strong.
    else if (!hasActionKeyword && semanticEvidence < 0.45) base = { key: "high", label: "Important" };
    else if ((isFillerish || tooShort) && semanticEvidence < 0.30) base = { key: "high", label: "Important" };
  } else if (base.key === "high") {
    // If meaning is weak, fall back out of the top bucket.
    if (semanticEvidence < 0.15 || (isFillerish && semanticEvidence < 0.25)) base = { key: "low", label: "Low importance" };
    else if ((semanticEvidence < 0.22 && tooShort) || (semanticEvidence < 0.26 && isFillerish)) {
      base = { key: "medium", label: "Moderately important" };
    }
  }

  return base;
}
