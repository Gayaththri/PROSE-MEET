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
    <div className="flex items-center gap-4">
      {/* Record button */}
      {!isRecording && (
        <button
          onClick={startRecording}
          className="action-button bg-gray-900 text-white hover:bg-gray-800 transition"
        >
          🎤 Record
        </button>
      )}

      {/* Pause/Resume + Stop buttons */}
      {isRecording && (
        <>
          <button
            onClick={togglePause}
            className="action-button bg-gray-200 text-gray-800 hover:bg-gray-300 transition"
          >
            {isPaused ? "▶ Resume" : "⏸ Pause"}
          </button>

          <button
            onClick={stopRecording}
            className="action-button bg-red-600 text-white hover:bg-red-700 transition"
          >
            ⏹ Stop
          </button>
        </>
      )}

      {/* Status */}
      {isStartingJob && (
        <span className="text-sm text-gray-500 ml-2">Starting analysis…</span>
      )}
    </div>
  );
}

export default AudioRecorder;
