import LoadingSkeleton from "./LoadingSkeleton";

/**
 * Meeting Overview Panel (top section): title, detected domain, confidence, adaptation strategy, duration.
 * Proves Gap 2 (domain detection) is connected to the rest of the insights.
 */
export default function MeetingOverview({ result, loading = false }) {
  if (!result && !loading) return null;

  const filename = result?.filename || "Meeting";
  const meetingTitle = filename.replace(/\.[^/.]+$/, "") || filename;
  const durationSeconds = result?.duration_seconds;
  const domain = result?.domain || {};
  const domainLabel = domain.domain_label || (domain.predicted_domain && domain.predicted_domain.charAt(0).toUpperCase() + domain.predicted_domain.slice(1)) || "—";
  const confidence = typeof domain.confidence === "number" ? domain.confidence : 0;
  const adaptationStrategy = domain.adaptation_strategy || "—";
  const domainReady = Boolean(domain.predicted_domain || domain.domain_label);

  const formatDuration = (seconds) => {
    if (seconds == null || seconds === undefined) return "—";
    const total = Math.max(0, Math.round(seconds));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    if (h > 0) {
      return `${h}h ${m}m`;
    }
    if (m > 0) {
      return `${m} min`;
    }
    return `${s} s`;
  };

  const domainBadgeClass = `saas-overview-domain-badge saas-overview-domain-${(domain.predicted_domain || "corporate").toLowerCase()}`;

  return (
    <div className="saas-overview-panel">
      <div className="saas-overview-header">
        <span className="saas-overview-kicker">Detected session</span>
        <h3 className="saas-overview-title">{meetingTitle}</h3>
      </div>
      <div className="saas-overview-grid">
        <div className="saas-overview-item saas-overview-domain">
          <span className="saas-overview-label">Detected domain</span>
          {domainReady ? (
            <>
              <span className={domainBadgeClass} title="Domain inferred from transcript and summary (Gap 2)">
                {domainLabel}
              </span>
              <span className="saas-overview-tooltip" title="Domain is inferred from meeting content so summaries and highlights can be adapted (e.g. decision-focused for corporate).">
                ⓘ
              </span>
            </>
          ) : (
            <LoadingSkeleton className="saas-skeleton-pill" />
          )}
        </div>
        <div className="saas-overview-item saas-overview-confidence">
          <span className="saas-overview-label">Confidence</span>
          {domainReady ? (
            <>
              <div className="saas-overview-confidence-bar-wrap">
                <div
                  className="saas-overview-confidence-bar"
                  style={{ width: `${Math.round(confidence * 100)}%` }}
                  role="progressbar"
                  aria-valuenow={Math.round(confidence * 100)}
                  aria-valuemin={0}
                  aria-valuemax={100}
                />
              </div>
              <span className="saas-overview-confidence-pct">{Math.round(confidence * 100)}%</span>
            </>
          ) : (
            <>
              <LoadingSkeleton className="saas-skeleton-bar" />
              <LoadingSkeleton className="saas-skeleton-inline" />
            </>
          )}
        </div>
        <div className="saas-overview-item saas-overview-strategy">
          <span className="saas-overview-label">Adaptation strategy</span>
          {domainReady ? (
            <span className="saas-overview-strategy-value" title="How insights are tailored to this domain">
              {adaptationStrategy}
            </span>
          ) : (
            <LoadingSkeleton className="saas-skeleton-inline saas-skeleton-wide" />
          )}
        </div>
        <div className="saas-overview-item saas-overview-duration">
          <span className="saas-overview-label">Duration</span>
          {durationSeconds != null || !loading ? (
            <span className="saas-overview-duration-value">{formatDuration(durationSeconds)}</span>
          ) : (
            <LoadingSkeleton className="saas-skeleton-inline" />
          )}
        </div>
      </div>
    </div>
  );
}
