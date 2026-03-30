import { SparklesIcon } from "@heroicons/react/24/solid";

// Status card showing processing progress and state.
const PROCESS_STEPS = [
  { id: "preparing_audio", label: "Preparing audio", matches: ["queued", "starting", "preparing_audio"] },
  { id: "transcribing", label: "Transcribing", matches: ["transcribing", "aligning_transcript"] },
  { id: "scoring_importance", label: "Scoring insights", matches: ["scoring_importance", "adapting_context"] },
  { id: "transcript_ready", label: "Transcript ready", matches: ["transcript_ready"] },
  { id: "highlights_ready", label: "Highlights ready", matches: ["generating_highlights", "highlights_ready"] },
  { id: "summary_ready", label: "Summary and domain", matches: ["finalizing_insights", "summary_ready", "completed"] },
];

function formatEta(seconds) {
  if (seconds == null || Number.isNaN(seconds)) return "Calculating...";
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  if (minutes <= 0) return `${secs}s remaining`;
  return `${minutes}m ${secs.toString().padStart(2, "0")}s remaining`;
}

function getActiveStepIndex(stage) {
  const idx = PROCESS_STEPS.findIndex((step) => step.matches.includes(stage));
  return idx === -1 ? 0 : idx;
}

export default function ProcessingStatusCard({
  session,
  onCancel,
  onOpenLive,
  compact = false,
}) {
  if (!session) return null;

  const fullStatus = session.fullStatus || {};
  const previewStatus = session.previewStatus || {};
  const progress = Math.max(
    0,
    Math.min(100, Math.round((fullStatus.progress ?? 0) * 100)),
  );
  const stage = fullStatus.stage || "queued";
  const activeStepIndex = getActiveStepIndex(stage);
  const fullDone = ["completed", "failed", "cancelled"].includes(fullStatus.status);
  const fullCancelling = fullStatus.status === "cancelling";
  const previewEnabled = Boolean(session.previewJobId);
  const previewReady = previewStatus.status === "completed";
  const previewRunning =
    previewEnabled && !["completed", "failed", "cancelled", "cancelling"].includes(previewStatus.status);
  const hasLivePreview = Boolean(session.previewResult || session.partialResult || session.fullResult);

  if (compact) {
    return (
      <div className="saas-processing-banner">
        <div className="saas-processing-banner-main">
          <p className="saas-processing-banner-title">
            {fullDone
              ? "Meeting analysis updated"
              : fullCancelling
                ? fullStatus.stage_label || "Cancelling"
                : fullStatus.stage_label || "Meeting analysis in progress"}
          </p>
          <p className="saas-processing-banner-meta">
            {progress}% complete
            {" - "}
            {fullDone ? "Ready to review" : fullCancelling ? "Stopping" : formatEta(fullStatus.eta_seconds)}
            {previewRunning ? " - Quick preview running" : ""}
            {previewReady ? " - Quick preview ready" : ""}
          </p>
        </div>
        <div className="saas-processing-banner-actions">
          {hasLivePreview && onOpenLive && (
            <button
              type="button"
              className="action-button saas-btn-outline saas-btn-compact"
              onClick={onOpenLive}
            >
              View live insights
            </button>
          )}
          {!fullDone && !fullCancelling && onCancel && (
            <button
              type="button"
              className="action-button saas-btn-outline saas-btn-compact"
              onClick={onCancel}
            >
              Cancel
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="saas-processing-card">
      <div className="saas-processing-illustration" aria-hidden>
        <SparklesIcon className="saas-processing-illustration-icon" />
      </div>
      <span className="saas-processing-kicker">Background analysis</span>
      <h2 className="saas-processing-title">
        {fullCancelling ? "Stopping analysis…" : "Meeting summary is processing..."}
      </h2>
      <p className="saas-processing-subtitle">
        Follow the pipeline in real time. Transcript appears first, then highlights, then summary and domain.
      </p>

      <div className="saas-processing-progress">
        <div className="saas-processing-progress-head">
          <span>{fullStatus.stage_label || "Queued"}</span>
          <strong>{progress}%</strong>
        </div>
        <div className="saas-processing-progress-bar" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
          <div className="saas-processing-progress-fill" style={{ width: `${progress}%` }} />
        </div>
        <p className="saas-processing-status">
          {fullDone
            ? "Final result is ready."
            : fullCancelling
              ? "Wrapping up and releasing resources."
              : formatEta(fullStatus.eta_seconds)}
        </p>
      </div>

      <div className="saas-processing-metrics">
        <div className="saas-processing-metric">
          <span className="saas-processing-metric-label">Current stage</span>
          <strong>{fullStatus.stage_label || "Queued"}</strong>
        </div>
        <div className="saas-processing-metric">
          <span className="saas-processing-metric-label">Live insights</span>
          <strong>{hasLivePreview ? "Available" : "Preparing"}</strong>
        </div>
        <div className="saas-processing-metric">
          <span className="saas-processing-metric-label">Status</span>
          <strong>{fullDone ? "Ready to review" : fullCancelling ? "Cancelling" : "Running"}</strong>
        </div>
      </div>

      <ol className="saas-processing-steps">
        {PROCESS_STEPS.map((step, index) => {
          const state =
            index < activeStepIndex ? "done" : index === activeStepIndex ? "active" : "pending";
          return (
            <li key={step.id} className={`saas-processing-step is-${state}`}>
              <span className="saas-processing-step-dot" aria-hidden />
              <span>{step.label}</span>
            </li>
          );
        })}
      </ol>

      {previewEnabled && (
        <div className="saas-status">
          <span className="saas-status-dot" aria-hidden />
          <div>
            <p className="saas-status-title">Quick preview mode</p>
            <p className="saas-status-desc">
              {previewReady
                ? "A preview is ready while the full analysis continues."
                : previewRunning
                  ? "Generating a fast preview from the first moments of the meeting."
                  : "Preview is linked to this full analysis session."}
            </p>
          </div>
        </div>
      )}

      <div className="saas-processing-actions">
        {hasLivePreview && onOpenLive && (
          <button
            type="button"
            className="action-button saas-btn-outline"
            onClick={onOpenLive}
          >
            Open live insights
          </button>
        )}
        {!fullDone && !fullCancelling && onCancel && (
          <button
            type="button"
            className="action-button saas-btn-outline"
            onClick={onCancel}
          >
            Cancel processing
          </button>
        )}
      </div>
    </div>
  );
}
