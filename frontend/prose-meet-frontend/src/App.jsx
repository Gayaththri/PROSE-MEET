import { useEffect, useState } from "react";
import AudioUpload from "./components/AudioUpload";
import AudioRecorder from "./components/AudioRecorder";
import "./App.css";

function App() {
  const [jobId, setJobId] = useState(null);
  const [status, setStatus] = useState(null);
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (!jobId) return;

    const interval = setInterval(async () => {
      try {
        const statusRes = await fetch(`http://127.0.0.1:8000/status/${jobId}`);
        const statusData = await statusRes.json();
        setStatus(statusData.status);

        if (statusData.status === "completed") {
          const resultRes = await fetch(
            `http://127.0.0.1:8000/result/${jobId}`,
          );
          const resultData = await resultRes.json();
          setResult(resultData);
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

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Page container */}
      <div className="max-w-6xl mx-auto px-6 py-10">
        {/* Header */}
        <header className="mb-10">
          <h1 className="text-4xl font-bold text-gray-900">PROSE-MEET</h1>
          <p className="text-gray-600 mt-2">
            Prosody-Aware Meeting Intelligence System
          </p>
        </header>

        {/* Input card */}
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 mb-10">
          <h2 className="text-xl font-semibold mb-4">
            Upload or Record Meeting Audio
          </h2>

          <div className="flex items-center gap-6">
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
        </div>

        {/* Processing state */}
        {jobId && !result && (
          <div className="bg-white p-6 rounded-xl border border-gray-200 mb-10">
            <p className="text-lg font-medium">⏳ Processing meeting audio…</p>
            <p className="text-sm text-gray-500 mt-2">
              Status: <strong>{status}</strong>
            </p>
          </div>
        )}

        {/* Results */}
        {result && (
          <div className="space-y-10">
            {/* Summary */}
            <div className="bg-white p-6 rounded-xl border border-gray-200">
              <h2 className="text-xl font-semibold mb-3">Meeting Summary</h2>
              <p className="summary-box">{result.summary}</p>
            </div>

            {/* Highlights + Speakers */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              <div className="bg-white p-6 rounded-xl border border-gray-200">
                <h2 className="text-xl font-semibold mb-4">
                  Key Prosodic Moments
                </h2>

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
              </div>

              {/* Speakers */}
              <div className="bg-white p-6 rounded-xl border border-gray-200">
                <h2 className="text-xl font-semibold mb-4">
                  Speaker Contribution
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
              </div>
            </div>

            {/* Transcript */}
            <div className="bg-white p-6 rounded-xl border border-gray-200">
              <h2 className="text-xl font-semibold mb-4">
                Transcript (Prosody-Aware)
              </h2>

              <div className="transcript-box">
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
                        className={`transcript-line ${
                          isImportant ? "important" : ""
                        }`}
                      >
                        <strong>
                          [{seg.start}s – {seg.end}s]
                        </strong>{" "}
                        {seg.text}
                        {isImportant && (
                          <span className="important-tag">★ Important</span>
                        )}
                      </p>
                    );
                  });
                })()}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
