import { useCallback, useEffect, useState } from "react";
import AudioUpload from "./components/AudioUpload";
import AudioRecorder from "./components/AudioRecorder";
import Sidebar from "./components/Sidebar";
import { getMeetings, getMeetingResult } from "./api/gap1";
import "./App.css";

function App() {
  const [activeView, setActiveView] = useState("home");
  const [jobId, setJobId] = useState(null);
  const [status, setStatus] = useState(null);
  const [result, setResult] = useState(null);
  const [meetings, setMeetings] = useState([]);
  const [meetingsLoading, setMeetingsLoading] = useState(false);

  useEffect(() => {
    if (!jobId) return;
    const interval = setInterval(async () => {
      try {
        const statusRes = await fetch(`http://127.0.0.1:8000/status/${jobId}`);
        const statusData = await statusRes.json();
        setStatus(statusData.status);

        if (statusData.status === "completed") {
          const resultData = await getMeetingResult(jobId);
          if (resultData && !resultData.error) setResult(resultData);
          clearInterval(interval);
        }

        if (statusData.status === "failed") {
          clearInterval(interval);
          alert("Audio processing failed.");
        }
      } catch (err) {
        console.error("Polling error:", err);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [jobId]);

  const loadMeetings = useCallback(async () => {
    setMeetingsLoading(true);
    try {
      const data = await getMeetings();
      setMeetings(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error("Failed to load meetings:", err);
      setMeetings([]);
    } finally {
      setMeetingsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeView === "meetings") loadMeetings();
  }, [activeView, loadMeetings]);

  const openMeeting = async (id) => {
    try {
      const data = await getMeetingResult(id);
      if (data && !data.error && data.transcript) {
        setResult(data);
        setActiveView("home");
      } else {
        alert("Could not load that meeting.");
      }
    } catch (err) {
      console.error(err);
      alert("Could not load meeting.");
    }
  };

  return (
    <div className="app-layout">
      <Sidebar activeId={activeView} onSelect={setActiveView} />

      <div className="app-content">
        <header className="app-topbar">
          <div className="app-topbar-search">
            <span className="app-topbar-search-icon" aria-hidden>
              ⌕
            </span>
            <input
              type="search"
              placeholder="Search meetings…"
              className="app-topbar-input"
            />
          </div>
          <div className="app-topbar-actions">
            <span className="app-topbar-avatar" aria-hidden>
              S
            </span>
          </div>
        </header>

        <main className="app-main">
          {activeView === "meetings" && (
            <section className="saas-meetings-list">
              <h2>Saved meetings</h2>
              <p className="saas-meetings-desc">
                Your processed meetings are saved here. Click one to open its summary and transcript.
              </p>
              {meetingsLoading ? (
                <p>Loading…</p>
              ) : meetings.length === 0 ? (
                <p className="saas-meetings-empty">No meetings yet. Import audio from Home to get started.</p>
              ) : (
                <ul className="saas-meetings-ul">
                  {meetings.map((m) => (
                    <li key={m.id} className="saas-meetings-li">
                      <button
                        type="button"
                        className="saas-meetings-btn"
                        onClick={() => openMeeting(m.id)}
                      >
                        <span className="saas-meetings-name">{m.filename}</span>
                        <span className="saas-meetings-date">
                          {m.created_at ? new Date(m.created_at).toLocaleString() : ""}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}

          {activeView === "home" && !result && (
            <section className="saas-hero-centered">
              <div className="saas-cta-card">
                <div className="saas-cta-header">
                  <h2>Start a new meeting</h2>
                  <p>Import a file or record live from your mic.</p>
                </div>
                <div className="saas-cta-buttons">
                  <AudioUpload
                    onJobCreated={(id) => {
                      setJobId(id);
                      setStatus("queued");
                      setResult(null);
                    }}
                  />
                  <AudioRecorder
                    onJobCreated={(id) => {
                      setJobId(id);
                      setStatus("queued");
                      setResult(null);
                    }}
                  />
                </div>
                {activeView === "home" && jobId && !result && (
                  <div className="saas-status">
                    <span className="saas-status-dot" />
                    <div>
                      <p className="saas-status-title">Processing…</p>
                      <p className="saas-status-desc">
                        Status: <strong>{status}</strong>. We’re analysing
                        prosody and transcript.
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </section>
          )}

          {activeView === "home" && result && result.transcript && (
            <section className="saas-results">
              <header className="saas-results-header">
                <h2>Meeting insights</h2>
                <p>Summary, highlights, and transcript from your recording.</p>
              </header>

              <div className="saas-cards">
                <article className="saas-card saas-card-summary">
                  <h3 className="saas-card-title">
                    <span className="saas-card-icon">📋</span> Summary
                  </h3>
                  {result.speaker_summaries &&
                  result.speaker_summaries.length > 0 ? (
                    <div className="saas-summary-list">
                      {result.speaker_summaries.map((sp, idx) => (
                        <div key={idx} className="saas-summary-block">
                          <h4>{sp.speaker}</h4>
                          <p>{sp.summary}</p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="saas-summary-block">
                      <p>{result.summary}</p>
                    </div>
                  )}
                </article>

                <article className="saas-card">
                  <h3 className="saas-card-title">
                    <span className="saas-card-icon">✨</span> Key moments
                  </h3>
                  <ul className="saas-highlights">
                    {(result.highlights || []).map((h, idx) => (
                      <li key={idx}>
                        <span className="saas-highlight-time">
                          {h.start.toFixed(1)}s – {h.end.toFixed(1)}s
                        </span>
                        <span className="saas-highlight-text">{h.text}</span>
                        <span className="saas-highlight-score">
                          Score {h.importance_score.toFixed(2)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </article>

                <article className="saas-card saas-card-prosody">
                  <h3 className="saas-card-title">
                    <span className="saas-card-icon">🎯</span> Prosodic Analysis
                  </h3>
                  <p className="saas-prosody-desc">
                    Why each moment was marked important (pitch, energy, pause).
                  </p>
                  <div className="saas-prosody-list">
                    {(result.highlights || []).map((h, idx) => {
                      const pitchLevel = h.pitch_variation_level || "—";
                      const energyLevel = h.energy_level || "—";
                      const pauseDetected = h.pause_emphasis === true;
                      const reasonBullets = [
                        pitchLevel !== "—" &&
                          `${pitchLevel} pitch variation detected`,
                        energyLevel !== "—" &&
                          (energyLevel === "High"
                            ? "Increased speaking energy"
                            : `${energyLevel} speaking energy`),
                        pauseDetected && "Pause emphasis detected",
                      ].filter(Boolean);
                      return (
                        <div key={idx} className="saas-prosody-item">
                          <div className="saas-prosody-item-head">
                            Important moment detected
                          </div>
                          <div className="saas-prosody-item-time">
                            {h.start.toFixed(1)}s – {h.end.toFixed(1)}s
                          </div>
                          <p className="saas-prosody-item-text">{h.text}</p>
                          <div className="saas-prosody-reason">
                            <span className="saas-prosody-reason-label">
                              Reason:
                            </span>
                            <ul className="saas-prosody-reason-list">
                              {reasonBullets.length > 0 ? (
                                reasonBullets.map((bullet, i) => (
                                  <li key={i}>{bullet}</li>
                                ))
                              ) : (
                                <li>
                                  Prosody contributed to importance score.
                                </li>
                              )}
                            </ul>
                          </div>
                          <div className="saas-prosody-meta">
                            <span>
                              Pitch: <strong>{pitchLevel}</strong>
                            </span>
                            <span>
                              Energy: <strong>{energyLevel}</strong>
                            </span>
                            <span>
                              Pause:{" "}
                              <strong>{pauseDetected ? "Yes" : "No"}</strong>
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </article>

                <article className="saas-card">
                  <h3 className="saas-card-title">
                    <span className="saas-card-icon">👥</span> Speaker
                    contribution
                  </h3>
                  <p className="saas-card-sub">
                    Estimated by turn-taking (pauses between speech).
                  </p>
                  <div className="saas-speakers">
                    {(result.speakers || []).slice(0, 10).map((sp, idx) => (
                      <div key={idx} className="saas-speaker-row">
                        <span className="saas-speaker-name">{sp.speaker}</span>
                        <div className="saas-speaker-bar-wrap">
                          <div
                            className="saas-speaker-bar"
                            style={{
                              width: `${Math.max(2, sp.importance_percentage)}%`,
                            }}
                          />
                        </div>
                        <span className="saas-speaker-pct">
                          {sp.importance_percentage.toFixed(1)}%
                        </span>
                      </div>
                    ))}
                  </div>
                </article>

                <article className="saas-card saas-card-full">
                  <h3 className="saas-card-title">
                    <span className="saas-card-icon">📜</span> Transcript
                  </h3>
                  <div className="saas-transcript">
                    {(() => {
                      const scores = result.transcript.map(
                        (seg) => seg.importance_score ?? 0,
                      );
                      const sorted = [...scores].sort((a, b) => a - b);
                      const threshold =
                        sorted[Math.floor(sorted.length * 0.7)] ?? 0;
                      return result.transcript.map((seg) => {
                        const isImportant =
                          (seg.importance_score ?? 0) >= threshold;
                        return (
                          <p
                            key={seg.segment_id}
                            className={`saas-transcript-line ${isImportant ? "is-important" : ""}`}
                          >
                            <span className="saas-transcript-time">
                              [{seg.start}s – {seg.end}s]
                            </span>{" "}
                            {seg.text}
                            {isImportant && (
                              <span className="saas-transcript-badge">
                                Important
                              </span>
                            )}
                          </p>
                        );
                      });
                    })()}
                  </div>
                </article>
              </div>
            </section>
          )}
        </main>
      </div>
    </div>
  );
}
export default App;
