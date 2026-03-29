// Audio upload component for local file submissions.
import { useRef, useState } from "react";
import { runGap1, runGap1WithOptions } from "../api/gap1";
import Modal from "./Modal";

export default function AudioUpload({ onJobCreated }) {
  const fileInputRef = useRef(null);

  const [open, setOpen] = useState(false);
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [quickPreview, setQuickPreview] = useState(false);

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
      const fullResponse = await runGap1(file);

      if (!fullResponse?.job_id) {
        throw new Error("No job_id returned from backend");
      }

      let previewResponse = null;
      if (quickPreview) {
        try {
          previewResponse = await runGap1WithOptions(file, {
            preview: true,
            previewSeconds: 45,
            relatedJobId: fullResponse.job_id,
          });
        } catch (previewError) {
          console.error("Quick preview could not be started:", previewError);
        }
      }

      onJobCreated({
        fullJobId: fullResponse.job_id,
        previewJobId: previewResponse?.job_id || null,
        previewEnabled: Boolean(previewResponse?.job_id),
        previewSeconds: quickPreview ? 45 : null,
      });

      // Reset UI
      setOpen(false);
      setFile(null);
      setQuickPreview(false);
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
            <label className="saas-option-row">
              <input
                type="checkbox"
                checked={quickPreview}
                onChange={(e) => setQuickPreview(e.target.checked)}
                disabled={loading}
              />
              <span>
                Quick preview mode
                <small> Show a fast 45s preview while the full analysis continues.</small>
              </span>
            </label>
            <button
              type="button"
              onClick={handleRun}
              disabled={loading}
              className={`action-button saas-btn-primary saas-btn-submit ${loading ? "is-loading" : ""}`}
            >
              {loading ? "Starting..." : quickPreview ? "Start preview + full analysis" : "Start analysis"}
            </button>
          </div>
        )}
      </Modal>
    </>
  );
}
