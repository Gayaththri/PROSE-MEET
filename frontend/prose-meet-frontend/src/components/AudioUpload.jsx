// Audio upload component for local file submissions.
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

  // File selected via input
  const handleFileChange = (e) => {
    const selected = e.target.files?.[0];
    if (!selected) return;
    setFile(selected);
  };

  // File dropped onto dropzone
  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    const dropped = e.dataTransfer?.files?.[0];
    if (!dropped) return;
    setFile(dropped);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  // Send file to backend (background job)
  const handleRun = async () => {
    if (!file) return;
    setLoading(true);

    try {
      const response = await runGap1(file);
      if (!response?.job_id) {
        throw new Error("No job_id returned from backend");
      }
      onJobCreated({ fullJobId: response.job_id });

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
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="action-button saas-btn-primary"
      >
        <img
          src="https://cdn-icons-png.flaticon.com/512/3185/3185902.png"
          alt=""
          className="saas-btn-icon saas-btn-icon-img saas-btn-icon-white"
          width={20}
          height={20}
        />
        Upload Audio
      </button>

      <Modal isOpen={open} onClose={() => setOpen(false)}>
        <div className="saas-modal-copy">
          <p className="saas-modal-eyebrow">Upload audio or video</p>
          <p className="saas-modal-description">
            Supported formats: all audio files, plus MP4, WebM, and AVI video files.
          </p>
        </div>

        <input
          ref={fileInputRef}
          type="file"
          accept="audio/*,video/mp4,video/webm,video/x-msvideo"
          onChange={handleFileChange}
          className="hidden"
        />

        {!file && (
          <div
            className="saas-dropzone"
            onDragOver={handleDragOver}
            onDrop={handleDrop}
            onClick={handleBrowseClick}
            onKeyDown={(e) => e.key === "Enter" && handleBrowseClick()}
            role="button"
            tabIndex={0}
          >
            <p className="saas-dropzone-title">Drop your file here</p>
            <p className="saas-dropzone-hint">
              or click to browse - audio files, MP4, WebM, AVI
            </p>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                handleBrowseClick();
              }}
              className="action-button saas-btn-primary saas-dropzone-btn"
            >
              Browse files
            </button>
          </div>
        )}

        {file && (
          <div className="saas-file-selected">
            <div className="saas-file-info">
              <p className="saas-file-name">{file.name}</p>
              <p className="saas-file-size">
                {(file.size / (1024 * 1024)).toFixed(2)} MB
              </p>
              {!loading && (
                <button
                  type="button"
                  onClick={() => setFile(null)}
                  className="saas-file-remove"
                >
                  Remove
                </button>
              )}
            </div>
            <button
              type="button"
              onClick={handleRun}
              disabled={loading}
              className={`action-button saas-btn-primary saas-btn-submit ${loading ? "is-loading" : ""}`}
            >
              {loading ? "Starting..." : "Start analysis"}
            </button>
          </div>
        )}
      </Modal>
    </>
  );
}
