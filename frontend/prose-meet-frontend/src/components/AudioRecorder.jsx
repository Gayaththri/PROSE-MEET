import { useRef, useState } from "react";
import { runGap1 } from "../api/gap1";

function AudioRecorder({ onJobCreated }) {
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [isStartingJob, setIsStartingJob] = useState(false);

  // Start recording
  const startRecording = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mediaRecorder = new MediaRecorder(stream);

    mediaRecorderRef.current = mediaRecorder;
    audioChunksRef.current = [];

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        audioChunksRef.current.push(event.data);
      }
    };

    mediaRecorder.onstop = async () => {
      const audioBlob = new Blob(audioChunksRef.current, {
        type: "audio/webm",
      });

      setIsStartingJob(true);

      try {
        // Send audio to backend bafor ckground job
        const response = await runGap1(audioBlob);

        if (!response?.job_id) {
          throw new Error("No job_id returned from backend");
        }

        onJobCreated(response.job_id);
      } catch (err) {
        console.error(err);
        alert("Failed to start background processing");
      } finally {
        setIsStartingJob(false);
      }
    };

    mediaRecorder.start();
    setIsRecording(true);
    setIsPaused(false);
  };

  // Pause/Resume recording
  const togglePause = () => {
    if (!mediaRecorderRef.current) return;

    if (isPaused) {
      mediaRecorderRef.current.resume();
      setIsPaused(false);
    } else {
      mediaRecorderRef.current.pause();
      setIsPaused(true);
    }
  };

  // Stop recording
  const stopRecording = () => {
    if (!mediaRecorderRef.current) return;

    mediaRecorderRef.current.stop();
    setIsRecording(false);
    setIsPaused(false);
  };

  return (
    <div className="saas-record-wrap">
      {!isRecording && (
        <button
          type="button"
          onClick={startRecording}
          className="action-button saas-btn-secondary"
        >
          <span className="saas-btn-icon saas-record-icon" aria-hidden>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="12" cy="12" r="8" fill="currentColor" />
            </svg>
          </span>
          Record
        </button>
      )}

      {isRecording && (
        <>
          <button
            type="button"
            onClick={togglePause}
            className="action-button saas-btn-outline"
          >
            {isPaused ? "▶ Resume" : "⏸ Pause"}
          </button>
          <button
            type="button"
            onClick={stopRecording}
            className="action-button saas-btn-stop"
          >
            ⏹ Stop
          </button>
        </>
      )}

      {isStartingJob && (
        <span className="saas-status-inline">Starting analysis…</span>
      )}
    </div>
  );
}

export default AudioRecorder;
