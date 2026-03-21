import AudioUpload from "./AudioUpload";
import PageHeader from "./PageHeader";

export default function HomeStartView({ onJobCreated }) {
  return (
    <section className="page-section page-section-home">
      <div className="hero-shell">
        <PageHeader
          eyebrow="Workspace"
          title="Turn meetings into searchable insight"
          description="Import a recording, then review a structured transcript and analytics in one place."
        />

        <div className="hero-panel">
          <div className="hero-panel-copy">
            <span className="hero-kicker">New analysis</span>
            <h2 className="hero-panel-title">Start a new meeting</h2>
            <p className="hero-panel-description">
              Keep your workflow moving with uploads and saved sessions that
              are ready to revisit later.
            </p>
          </div>

          <div className="hero-actions">
            <AudioUpload onJobCreated={onJobCreated} />
          </div>
        </div>
      </div>
    </section>
  );
}
