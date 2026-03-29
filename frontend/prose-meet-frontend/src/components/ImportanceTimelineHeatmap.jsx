/**
 * Importance Timeline Heatmap: horizontal timeline of importance (Low / Medium / High).
 * Each segment is clickable; shows transcript, prosodic features, and explanation.
 * Visualizes prosody importance for Gap 1.
 */
import { useMemo, useState } from "react";
import { ChartBarSquareIcon, XMarkIcon } from "@heroicons/react/24/outline";
import LoadingSkeleton from "./LoadingSkeleton";
import {
  getTranscriptImportanceThresholds,
  getDisplayImportanceMeta,
} from "../importanceDisplay";
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
