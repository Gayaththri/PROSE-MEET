import { useEffect, useMemo, useRef, useState } from "react";
import {
  PlayCircleIcon,
  DocumentTextIcon,
} from "@heroicons/react/24/outline";
import { API_BASE_URL } from "../api/gap1";
import MeetingOverview from "./MeetingOverview";
import HighestImportanceActionBoard, {
  getTopImportanceSegments,
} from "./HighestImportanceActionBoard";
import ImportanceTimelineHeatmap from "./ImportanceTimelineHeatmap";
import AcousticAnalysisPanel from "./AcousticAnalysisPanel";
import LoadingSkeleton from "./LoadingSkeleton";
import PageHeader from "./PageHeader";
import { sanitizeImportanceReasons } from "../reasonFilters";

function getTranscriptImportanceThresholds(transcript) {
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

  // Text-based meaning signal (robust even when importance_reasons are missing/filtered).
  const semanticTextSignal = Math.min(1, (topicHits + actionHits) / 6 + (wordCount >= 10 ? 0.25 : 0));

  // Reasons-based signal is only a small boost (not the primary driver).
  const reasonSignal = Math.min(1, semanticReasonHits / 3);

  return Math.max(0, Math.min(1, semanticTextSignal * 0.8 + reasonSignal * 0.2));
}

function getAdjustedTranscriptImportanceScore(seg) {
  const textLower = segmentText(seg).toLowerCase();
  const words = textLower.split(/\s+/).filter(Boolean);
  const raw = typeof seg?.importance_score === "number" && Number.isFinite(seg.importance_score) ? seg.importance_score : 0;

  let s = raw;

  const hasActionKeyword = containsAnyKeyword(textLower, ACTION_KEYWORDS);
  if (hasActionKeyword) s += 0.15;
  else s *= 0.92;

  if (words.length < 5) s *= 0.85;

  if (FILLER_PHRASES.some((f) => textLower.includes(f))) {
    s *= 0.75;
  }

  if (containsAnyKeyword(textLower, TOPIC_KEYWORDS)) {
    s += 0.08;
  }

  return s;
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
  // Example: "I'm Abigail Claffman" / "I'm John Smith".
  const looksLikeNameIntro = /\bi['’]m\s+[a-z]+(?:\s+[a-z]+){1,2}\b/.test(text) && words.length <= 12;
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

function getDisplayImportanceMeta(seg, thresholds) {
  const rawScore = typeof seg?.importance_score === "number" && Number.isFinite(seg.importance_score) ? seg.importance_score : 0;
  const textLower = segmentText(seg).toLowerCase();
  const wordCount = textLower.split(/\s+/).filter(Boolean).length;
  const hasActionKeyword = containsAnyKeyword(textLower, ACTION_KEYWORDS);

  // Base label comes purely from `seg.importance_score` percentiles.
  let base = getImportanceMeta(rawScore, thresholds);

  // Down-rank intro/name/chatter lines even if their raw score is high.
  if (isGreetingOrIntroSegment(seg) || isNonSubstantiveChatterSegment(seg)) {
    return { key: "low", label: "Low importance" };
  }

  // Make "Important"/"Very important" more selective:
  // keep them only when semantic meaning is strong enough (and not filler/too short).
  const semanticEvidence = getSemanticEvidenceScore(seg);
  const isFillerish = FILLER_PHRASES.some((f) => textLower.includes(f));
  const tooShort = wordCount < 6;

  if (base.key === "very-high") {
    // Require meaning; don't let prosody-heavy chatter sneak into the top quartile.
    if (semanticEvidence < 0.28) base = { key: "high", label: "Important" };
    // "Very important" should be action-oriented, unless semantic evidence is very strong.
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

function CardSkeleton({ title, icon, full = false, lines = 3, className = "" }) {
  return (
    <article className={`saas-card ${full ? "saas-card-full" : ""} ${className}`.trim()}>
      <h3 className="saas-card-title">
        <span className="saas-card-icon" aria-hidden="true">
          {icon}
        </span>{" "}
        {title}
      </h3>
      <div className="saas-skeleton-stack">
        {Array.from({ length: lines }).map((_, index) => (
          <LoadingSkeleton
            key={index}
            className={`saas-skeleton-line ${index === lines - 1 ? "is-short" : ""}`}
          />
        ))}
      </div>
    </article>
  );
}

function SectionIntro({ eyebrow, title, description }) {
  return (
    <div className="saas-results-section-intro">
      <span className="saas-results-section-eyebrow">{eyebrow}</span>
      <h2 className="saas-results-section-title">{title}</h2>
      {description && <p className="saas-results-section-description">{description}</p>}
    </div>
  );
}

export default function MeetingInsights({ result, onBack, loading = false }) {
  const transcript = useMemo(() => result?.transcript ?? [], [result?.transcript]);
  const hasTranscript = transcript.length > 0;
  const transcriptScrollRef = useRef(null);
  const [advancedInsightsReadyKey, setAdvancedInsightsReadyKey] = useState(null);
  const meetingTitle = (result?.filename || "Meeting").replace(/\.[^/.]+$/, "") || "Meeting";
  const advancedInsightsKey = `${result?.job_id || "current"}:${result?.partial_stage || "base"}`;
  const previewNote =
    result?.is_preview && !result?.domain
      ? "Quick preview from the first part of the meeting. Full insights will replace this automatically."
      : result?.is_preview
        ? "Quick preview mode is showing a provisional snapshot while the full analysis continues."
        : null;

  const topImportanceForBoard = useMemo(
    () => getTopImportanceSegments(transcript, 8),
    [transcript]
  );
  const showAdvancedInsights = hasTranscript && advancedInsightsReadyKey === advancedInsightsKey;

  useEffect(() => {
    if (!hasTranscript) return undefined;
    const timer = window.setTimeout(() => {
      setAdvancedInsightsReadyKey(advancedInsightsKey);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [advancedInsightsKey, hasTranscript]);

  // Ensure transcript view starts from the earliest segment for each new job.
  useEffect(() => {
    if (!hasTranscript) return;
    if (transcriptScrollRef.current) {
      transcriptScrollRef.current.scrollTop = 0;
    }
  }, [result?.job_id, hasTranscript]);

  if (!result && !loading) return null;

  return (
    <section className="saas-results">
      <PageHeader
        eyebrow="Insights dashboard"
        title={meetingTitle}
        description={null}
        actions={
          onBack ? (
            <button
              type="button"
              onClick={onBack}
              className="action-button saas-btn-outline saas-btn-compact"
            >
              Back to meetings
            </button>
          ) : null
        }
      />

      {previewNote && (
        <div className="saas-status">
          <span className="saas-status-dot" aria-hidden />
          <div>
            <p className="saas-status-title">Quick preview</p>
            <p className="saas-status-desc">{previewNote}</p>
          </div>
        </div>
      )}

      <div className="saas-results-stack">
        <section className="saas-results-section">
          <SectionIntro
            eyebrow="Overview"
            title="Meeting context"
            description={null}
          />
          <div className="saas-results-grid saas-results-grid-overview">
            <MeetingOverview result={result} loading={loading} />
            {result?.recording_path && result?.job_id && (
              <article className="saas-card saas-card-audio">
                <h3 className="saas-card-title">
                  <span className="saas-card-icon" aria-hidden="true">
                    <PlayCircleIcon width={18} height={18} />
                  </span>{" "}
                  Original recording
                </h3>
                <p className="saas-card-sub">
                  Play back the source audio alongside the generated transcript and insights.
                </p>
                <audio
                  controls
                  className="saas-audio-player"
                  src={`${API_BASE_URL}/recording/${result.job_id}`}
                />
              </article>
            )}
          </div>
        </section>

        {(hasTranscript || loading) && (
          <section className="saas-results-section">
            <SectionIntro
              eyebrow="Transcript"
              title="Full conversation"
            description={null}
            />
            {hasTranscript ? (
              <article className="saas-card saas-card-full">
                <h3 className="saas-card-title">
                  <span className="saas-card-icon" aria-hidden="true">
                    <DocumentTextIcon width={18} height={18} />
                  </span>{" "}
                  Transcript
                </h3>
                <div className="saas-transcript" ref={transcriptScrollRef}>
                  {(() => {
                    const thresholds = getTranscriptImportanceThresholds(transcript);

                    return transcript.map((seg, index) => {
                      const importanceMeta = getDisplayImportanceMeta(seg, thresholds);
                      const showImportanceBadge =
                        importanceMeta.key === "high" || importanceMeta.key === "very-high";
                      return (
                        <p
                          key={seg.segment_id ?? index}
                          className={`saas-transcript-line is-${importanceMeta.key}`}
                        >
                          <span className="saas-transcript-time">
                            [{seg.start}s - {seg.end}s]
                          </span>{" "}
                          {seg.text}
                          {showImportanceBadge && (
                            <span className={`saas-transcript-badge is-${importanceMeta.key}`}>
                              {importanceMeta.label}
                            </span>
                          )}
                        </p>
                      );
                    });
                  })()}
                </div>
              </article>
            ) : (
              loading && (
                <CardSkeleton
                  title="Transcript"
                  icon={<DocumentTextIcon width={18} height={18} />}
                  full
                  lines={5}
                />
              )
            )}
          </section>
        )}

        {(hasTranscript || loading) && (
          <section className="saas-results-section">
            <SectionIntro
              eyebrow="Priorities"
              title="Action items"
            description={null}
            />
            {hasTranscript ? (
              <article className="saas-card saas-card-full saas-action-items-card">
                <HighestImportanceActionBoard segments={topImportanceForBoard} />
              </article>
            ) : (
              loading && (
                <article className="saas-card saas-card-full saas-action-items-card">
                  <div className="saas-action-items-skeleton">
                    {Array.from({ length: 6 }).map((_, i) => (
                      <LoadingSkeleton key={i} className="saas-action-items-skeleton-row" />
                    ))}
                  </div>
                </article>
              )
            )}
          </section>
        )}
      </div>

      {showAdvancedInsights ? (
        <section className="saas-results-section">
          <SectionIntro
            eyebrow="Advanced analysis"
            title="Importance and prosody"
            description={null}
          />
          <ImportanceTimelineHeatmap
            transcript={transcript}
            durationSeconds={result?.duration_seconds}
            loading={loading}
          />

          <AcousticAnalysisPanel transcript={transcript} loading={loading} />

        </section>
      ) : (
        hasTranscript && (
          <div className="saas-deferred-insights-placeholder">
            <LoadingSkeleton className="saas-skeleton-line" />
            <LoadingSkeleton className="saas-skeleton-line is-short" />
          </div>
        )
      )}
    </section>
  );
}
