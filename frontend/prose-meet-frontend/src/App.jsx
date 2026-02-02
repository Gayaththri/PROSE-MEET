import { useState } from "react";
import AudioUpload from "./components/AudioUpload";
import AudioRecorder from "./components/AudioRecorder";
import "./App.css";

function App() {
  const [result, setResult] = useState(null);

  return (
    <div className="app-container">
      <h1>PROSE-MEET</h1>
      <p className="subtitle">Prosody-Aware Meeting Intelligence System</p>

      <AudioUpload onResult={setResult} />
      <AudioRecorder onResult={setResult} />

      {result && (
        <div className="section">
          {/* ================= SUMMARY ================= */}
          <h2>Meeting Summary</h2>
          <p className="summary-box">{result.summary}</p>

          {/* ================= PROSODY HIGHLIGHTS ================= */}
          <h2 className="section">Key Prosodic Moments</h2>
          <ul className="highlights-list">
            {result.highlights.map((h, idx) => (
              <li key={idx}>
                <strong>
                  [{h.start.toFixed(1)}s – {h.end.toFixed(1)}s]
                </strong>{" "}
                {h.text}
                <br />
                <em>Importance score: {h.importance_score.toFixed(2)}</em>
              </li>
            ))}
          </ul>

          {/* ================= SPEAKER CONTRIBUTION ================= */}
          <h2 className="section">
            Speaker Contribution (Prosody-Weighted)
          </h2>

          <div className="speaker-container">
            {result.speakers.slice(0, 10).map((sp, idx) => (
              <div key={idx} className="speaker-item">
                <strong>{sp.speaker}</strong>
                <div className="speaker-bar-bg">
                  <div
                    className="speaker-bar-fill"
                    style={{
                      width: `${sp.importance_percentage}%`,
                    }}
                  />
                </div>
                <small>
                  Importance contribution:{" "}
                  {sp.importance_percentage.toFixed(2)}%
                </small>
              </div>
            ))}
          </div>

          {/* ================= TRANSCRIPT ================= */}
          <h2 className="section">Transcript (Prosody-Aware)</h2>

          <div className="transcript-box">
            {(() => {
              // Top 30% threshold
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
                    className={`transcript-line ${
                      isImportant ? "important" : ""
                    }`}
                  >
                    <strong>
                      [{seg.start}s – {seg.end}s]
                    </strong>{" "}
                    {seg.text}
                    {isImportant && (
                      <span className="important-tag">
                        ★ Important
                      </span>
                    )}
                  </p>
                );
              });
            })()}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
