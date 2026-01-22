import { useState } from "react";
import { runGap1 } from "../api/gap1";

export default function AudioUpload({ onResult }) {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleRun = async () => {
    if (!file) return;
    setLoading(true);
    const result = await runGap1(file);
    console.log("Gap 1 Result:", result);
    onResult(result);
    setLoading(false);
  };

  return (
    <div style={{ marginTop: "20px" }}>
      <h2>Upload Meeting Audio</h2>

      <input
        type="file"
        accept="audio/*"
        onChange={(e) => setFile(e.target.files[0])}
      />

      {file && (
        <p>
          Selected file: <strong>{file.name}</strong>
        </p>
      )}

      <button
        onClick={handleRun}
        disabled={!file || loading}
        style={{ marginTop: "10px", padding: "8px 16px" }}
      >
        {loading ? "Processing..." : "Run Gap 1 Analysis"}
      </button>
    </div>
  );
}
