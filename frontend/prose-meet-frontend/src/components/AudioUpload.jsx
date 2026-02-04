import { useRef, useState } from "react";
import { runGap1 } from "../api/gap1";
import Modal from "./Modal";

export default function AudioUpload({ onJobCreated }) {
  const fileInputRef = useRef(null);

  const [open, setOpen] = useState(false);
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);

  // Open file picker
  const handleBrowseClick = () => {
    fileInputRef.current?.click();
  };

  // File selected
  const handleFileChange = (e) => {
    const selected = e.target.files?.[0];
    if (!selected) return;
    setFile(selected);
  };

  // Send file to backend (background job)
  const handleRun = async () => {
    if (!file) return;
    setLoading(true);

    try {
      const response = await runGap1(file);

      // Expect backend to return { job_id }
      if (!response?.job_id) {
        throw new Error("No job_id returned from backend");
      }

      onJobCreated(response.job_id);

      // Reset UI
      setOpen(false);
      setFile(null);
    } catch (err) {
      console.error(err);
      alert("Failed to start audio processing");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {/* Main import button */}
      <button
        onClick={() => setOpen(true)}
        className="action-button bg-indigo-600 text-white hover:bg-indigo-700 transition"
      >
        📁 Import Audio
      </button>

      {/* Modal */}
      <Modal isOpen={open} onClose={() => setOpen(false)}>
        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          accept="audio/*"
          onChange={handleFileChange}
          className="hidden"
        />

        {/* Drag & Drop state */}
        {!file && (
          <div className="border-2 border-dashed border-gray-300 rounded-lg p-10 text-center">
            <p className="text-lg font-medium">Drag & Drop</p>
            <p className="text-sm text-gray-500 mt-2">
              AAC, MP3, WAV, M4A, MP4
            </p>

            <button
              onClick={handleBrowseClick}
              className="mt-6 px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
            >
              Browse files
            </button>
          </div>
        )}

        {/* File selected */}
        {file && (
          <div className="space-y-4">
            <div className="flex justify-between items-center border rounded-lg p-4">
              <div>
                <p className="font-medium">{file.name}</p>
                <p className="text-sm text-gray-500">
                  {(file.size / (1024 * 1024)).toFixed(2)} MB
                </p>
              </div>

              {!loading && (
                <button
                  onClick={() => setFile(null)}
                  className="text-red-500 text-sm hover:underline"
                >
                  Remove
                </button>
              )}
            </div>

            {/* Start analysis */}
            <button
              onClick={handleRun}
              disabled={loading}
              className={`w-full py-3 rounded-lg font-medium transition ${
                loading
                  ? "bg-gray-400 text-white cursor-not-allowed"
                  : "bg-green-600 text-white hover:bg-green-700"
              }`}
            >
              {loading ? "Starting analysis…" : "Start Analysis"}
            </button>
          </div>
        )}
      </Modal>
    </>
  );
}
