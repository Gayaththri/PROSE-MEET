/**
 * Importance Timeline Heatmap — horizontal timeline of importance (Low / Medium / High).
 * Each segment is clickable; shows transcript, prosodic features, and explanation.
 * Visualizes prosody → importance for Gap 1.
 */
import { useMemo, useState } from "react";
import { ChartBarSquareIcon, XMarkIcon } from "@heroicons/react/24/outline";
import LoadingSkeleton from "./LoadingSkeleton";
import { sanitizeImportanceReasons } from "../reasonFilters";

const LEVEL_COLORS = {
  Low: "#22c55e",    // green
  Medium: "#94a3b8", // gray (Moderately important)
  High: "#eab308",   // yellow (Important)
  VeryHigh: "#ef4444", // red (Very important)
};

function importanceLevelLabel(level) {
  // Keep internal keys for styling/counting; adjust only visible label.
  if (level === "Medium") return "Moderately important";
  if (level === "High") return "Important";
  if (level === "VeryHigh") return "Very important";
  return level;
}

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

  // IMPORTANT: keep behavior tied to transcript quartiles.
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
  "remote", "project", "product", "requirements", "requirement", "budget", "design",
  "market", "profit", "aim", "goal", "decision", "plan", "deadline", "instructions",
  "email", "timeline",
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

  const semanticTextSignal = Math.min(1, (topicHits + actionHits) / 6 + (wordCount >= 10 ? 0.25 : 0));
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
  const rawScore =
    typeof seg?.importance_score === "number" && Number.isFinite(seg.importance_score)
      ? seg.importance_score
      : 0;
  const textLower = segmentText(seg).toLowerCase();
  const wordCount = textLower.split(/\s+/).filter(Boolean).length;
  const hasActionKeyword = containsAnyKeyword(textLower, ACTION_KEYWORDS);

  let base = getImportanceMeta(rawScore, thresholds);

  // Keep obvious chatter/greeting segments low.
  if (isGreetingOrIntroSegment(seg) || isNonSubstantiveChatterSegment(seg)) {
    return { key: "low", label: "Low importance" };
  }

  const semanticEvidence = getSemanticEvidenceScore(seg);
  const isFillerish = FILLER_PHRASES.some((f) => textLower.includes(f));
  const tooShort = wordCount < 6;

  if (base.key === "very-high") {
    if (semanticEvidence < 0.28) base = { key: "high", label: "Important" };
    else if (!hasActionKeyword && semanticEvidence < 0.45) base = { key: "high", label: "Important" };
    else if ((isFillerish || tooShort) && semanticEvidence < 0.30) base = { key: "high", label: "Important" };
  } else if (base.key === "high") {
    if (semanticEvidence < 0.15 || (isFillerish && semanticEvidence < 0.25)) base = { key: "low", label: "Low importance" };
    else if ((semanticEvidence < 0.22 && tooShort) || (semanticEvidence < 0.26 && isFillerish)) {
      base = { key: "medium", label: "Moderately important" };
    }
  }

  return base;
}

function formatTimeMinutes(seconds) {
  const m = Math.floor(seconds / 60);
  return `${m}m`;
}

export default function ImportanceTimelineHeatmap({ transcript = [], durationSeconds = 0, loading = false }) {
  const [selectedIndex, setSelectedIndex] = useState(null);

  const { segmentsWithLevel, countsByLevel } = useMemo(() => {
    if (!transcript.length) {
      return { segmentsWithLevel: [], countsByLevel: { Low: 0, Medium: 0, High: 0, VeryHigh: 0 } };
    }
    const thresholds = getTranscriptImportanceThresholds(transcript);

    const segmentsWithLevel = transcript.map((seg, idx) => {
      const importanceMeta = getDisplayImportanceMeta(seg, thresholds);
      const importanceLevel =
        importanceMeta.key === "low" ? "Low"
          : importanceMeta.key === "medium" ? "Medium"
            : importanceMeta.key === "high" ? "High"
              : "VeryHigh";

      return {
        ...seg,
        index: idx,
        importanceLevel,
      };
    });
    const countsByLevel = segmentsWithLevel.reduce((acc, segment) => {
      acc[segment.importanceLevel] = (acc[segment.importanceLevel] || 0) + 1;
      return acc;
    }, { Low: 0, Medium: 0, High: 0, VeryHigh: 0 });
    return { segmentsWithLevel, countsByLevel };
  }, [transcript]);

  const selectedSegment = selectedIndex != null ? segmentsWithLevel[selectedIndex] : null;

  // Derive duration from transcript if not provided (e.g. from /result API)
  const effectiveDuration = durationSeconds > 0
    ? durationSeconds
    : transcript.length
      ? Math.max(...transcript.map((s) => s.end || 0), 1)
      : 0;

  if ((!transcript.length || effectiveDuration <= 0) && !loading) return null;
  if (!transcript.length || effectiveDuration <= 0) {
    return (
      <article className="saas-card saas-timeline-card">
        <h3 className="saas-card-title">
          <span className="saas-card-icon" aria-hidden="true">
            <ChartBarSquareIcon width={18} height={18} />
          </span>{" "}
          Importance timeline
        </h3>
        <p className="saas-timeline-desc">Timeline will appear as soon as transcript segments are ready.</p>
        <LoadingSkeleton className="saas-skeleton-legend" />
        <LoadingSkeleton className="saas-skeleton-timeline" />
        <LoadingSkeleton className="saas-skeleton-axis" />
      </article>
    );
  }

  const durationForBar = Math.max(effectiveDuration, 1);
  const axisTicks = Array.from({ length: 5 }, (_, index) => (durationForBar / 4) * index);

  return (
    <article className="saas-card saas-timeline-card">
      <h3 className="saas-card-title">
        <span className="saas-card-icon" aria-hidden="true">
          <ChartBarSquareIcon width={18} height={18} />
        </span>{" "}
        Importance timeline
      </h3>
      <p className="saas-timeline-desc">
        Click a segment to see transcript, prosodic features, and why it was marked important.
      </p>
      <div className="saas-timeline-summary">
        <span className="saas-timeline-summary-item">Low {countsByLevel.Low}</span>
        <span className="saas-timeline-summary-item">Moderately important {countsByLevel.Medium}</span>
        <span className="saas-timeline-summary-item">Important {countsByLevel.High}</span>
        <span className="saas-timeline-summary-item">Very important {countsByLevel.VeryHigh}</span>
      </div>

      <div className="saas-timeline-legend">
        <span className="saas-timeline-legend-item">
          <span className="saas-timeline-legend-swatch saas-timeline-low" /> Low
        </span>
        <span className="saas-timeline-legend-item">
          <span className="saas-timeline-legend-swatch saas-timeline-medium" /> Moderately important
        </span>
        <span className="saas-timeline-legend-item">
          <span className="saas-timeline-legend-swatch saas-timeline-high" /> Important
        </span>
        <span className="saas-timeline-legend-item">
          <span className="saas-timeline-legend-swatch saas-timeline-very-high" /> Very important
        </span>
      </div>

      <div className="saas-timeline-wrap">
        <div className="saas-timeline-bar" role="list">
          {segmentsWithLevel.map((seg) => {
            const widthPct = (100 * (seg.end - seg.start)) / durationForBar;
            const color = LEVEL_COLORS[seg.importanceLevel] || "#94a3b8";
            const isSelected = seg.index === selectedIndex;
            return (
              <button
                key={seg.segment_id ?? seg.index}
                type="button"
                className={`saas-timeline-segment ${isSelected ? "is-selected" : ""}`}
                style={{
                  width: `${Math.max(widthPct, 0.5)}%`,
                  backgroundColor: color,
                }}
                title={`${seg.start.toFixed(0)}s – ${seg.end.toFixed(0)}s · ${importanceLevelLabel(seg.importanceLevel)}`}
                onClick={() => setSelectedIndex(seg.index)}
                aria-pressed={isSelected}
                aria-label={`Segment ${seg.index + 1}, ${importanceLevelLabel(seg.importanceLevel)} importance`}
              />
            );
          })}
        </div>
        <div className="saas-timeline-axis">
          {axisTicks.map((seconds, index) => {
            const isLast = index === axisTicks.length - 1;
            return (
              <span
                key={`${seconds}-${index}`}
                className={isLast ? "saas-timeline-tick-end" : "saas-timeline-tick"}
                style={isLast ? undefined : { left: `${(100 * seconds) / durationForBar}%` }}
              >
                {formatTimeMinutes(seconds)}
              </span>
            );
          })}
        </div>
      </div>

      {selectedSegment && (
        <div className="saas-timeline-detail">
          <div className="saas-timeline-detail-header">
            <span className="saas-timeline-detail-badge" data-level={selectedSegment.importanceLevel}>
              {importanceLevelLabel(selectedSegment.importanceLevel)}
            </span>
            <span className="saas-timeline-detail-time">
              {selectedSegment.start.toFixed(1)}s - {selectedSegment.end.toFixed(1)}s
            </span>
            <button
              type="button"
              className="saas-timeline-detail-close"
              onClick={() => setSelectedIndex(null)}
              aria-label="Close"
            >
              <XMarkIcon width={16} height={16} aria-hidden="true" />
            </button>
          </div>
          <p className="saas-timeline-detail-transcript">{selectedSegment.text || selectedSegment.content || "(no text)"}</p>
          <div className="saas-timeline-detail-prosody">
            <span className="saas-timeline-detail-label">Prosodic features</span>
            <div className="saas-timeline-detail-meta">
              <span>Pitch variation: <strong>{selectedSegment.pitch_variation_level ?? "—"}</strong></span>
              <span>Energy: <strong>{selectedSegment.energy_level ?? "—"}</strong></span>
              <span>Pause emphasis: <strong>{selectedSegment.pause_emphasis ? "Yes" : "No"}</strong></span>
              <span>Score: <strong>{(typeof selectedSegment.importance_score === "number" && Number.isFinite(selectedSegment.importance_score) ? selectedSegment.importance_score : 0).toFixed(2)}</strong></span>
            </div>
          </div>
          <div className="saas-timeline-detail-reasons">
            <span className="saas-timeline-detail-label">Why this segment</span>
            {(() => {
              const reasons = sanitizeImportanceReasons(selectedSegment.importance_reasons);
              return reasons.length > 0 ? (
                <ul className="saas-timeline-detail-reason-list">
                  {reasons.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
              ) : null;
            })()}
          </div>
        </div>
      )}
    </article>
  );
}
