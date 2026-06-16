// Meeting insights panel for key analysis outputs.
import { useEffect, useMemo, useRef, useState } from "react";
import {
  PlayCircleIcon,
  DocumentTextIcon,
} from "@heroicons/react/24/outline";
import { API_BASE_URL } from "../api/gap1";
import MeetingOverview from "./MeetingOverview";
import HighestImportanceActionBoard from "./HighestImportanceActionBoard";
import ImportanceTimelineHeatmap from "./ImportanceTimelineHeatmap";
import AcousticAnalysisPanel from "./AcousticAnalysisPanel";
import LoadingSkeleton from "./LoadingSkeleton";
import PageHeader from "./PageHeader";
import {
  getTranscriptImportanceThresholds,
  getDisplayImportanceMeta,
} from "../importanceDisplay";

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
                <HighestImportanceActionBoard segments={transcript} />
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
