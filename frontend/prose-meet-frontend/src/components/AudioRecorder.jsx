import { useRef, useState } from "react";

function AudioRecorder({ onResult }) {
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [audioURL, setAudioURL] = useState(null);

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

      const url = URL.createObjectURL(audioBlob);
      setAudioURL(url);

      // === SEND TO BACKEND ===
      const formData = new FormData();
      formData.append("file", audioBlob, "recorded_meeting.webm");

      setIsProcessing(true);

      try {
        const response = await fetch(
          "http://127.0.0.1:8000/run-gap1",
          {
            method: "POST",
            body: formData,
          },
        );

        const data = await response.json();
        onResult(data);
      } catch (err) {
        alert("Backend processing failed");
        console.error(err);
      } finally {
        setIsProcessing(false);
      }
    };

    mediaRecorder.start();
    setIsRecording(true);
  };

  const stopRecording = () => {
    mediaRecorderRef.current.stop();
    setIsRecording(false);
  };

  return (
    <div style={{ marginTop: "32px" }}>
      <h3>Record Meeting Audio</h3>

      <button onClick={startRecording} disabled={isRecording}>
        🎤 Start Recording
      </button>

      <button
        onClick={stopRecording}
        disabled={!isRecording}
        style={{ marginLeft: "10px" }}
      >
        ⏹ Stop Recording
      </button>

      {isProcessing && (
        <p style={{ marginTop: "12px" }}>⏳ Processing meeting...</p>
      )}

      {audioURL && (
        <div style={{ marginTop: "16px" }}>
          <audio controls src={audioURL} />
        </div>
      )}
    </div>
  );
}

export default AudioRecorder;
