import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Sidebar from "./components/Sidebar";
import MeetingInsights from "./components/MeetingInsights";
import ProcessingStatusCard from "./components/ProcessingStatusCard";
import HomeStartView from "./components/HomeStartView";
import SavedMeetingsView from "./components/SavedMeetingsView";
import UploadsView from "./components/UploadsView";
import Modal from "./components/Modal";
import {
  getMeetings,
  getMeetingResult,
  deleteMeeting,
  getJobStatus,
  cancelJob,
} from "./api/gap1";

const POLL_INTERVAL_MS = 1000;
const VIEW_TITLES = {
  home: "Home",
  meetings: "Meetings",
  uploads: "Uploads",
};

function buildQueuedStatus(overrides = {}) {
  return {
    status: "queued",
    stage: "queued",
    stage_label: "Queued",
    progress: 0,
    eta_seconds: null,
    cancel_requested: false,
    ...overrides,
  };
}

function App() {
  const [activeView, setActiveView] = useState("home");
  const [processingSession, setProcessingSession] = useState(null);
  const [savedResult, setSavedResult] = useState(null);
  const [activeHomeResultMode, setActiveHomeResultMode] = useState("live");
  const [meetings, setMeetings] = useState([]);
  const [meetingsLoading, setMeetingsLoading] = useState(false);
  const [appNotice, setAppNotice] = useState(null);
  const [meetingPendingDelete, setMeetingPendingDelete] = useState(null);
  const processingSessionRef = useRef(null);

  useEffect(() => {
    processingSessionRef.current = processingSession;
  }, [processingSession]);

  const requestNotificationPermission = useCallback(async () => {
    if (typeof window === "undefined" || !("Notification" in window)) return;
    if (Notification.permission === "default") {
      try {
        await Notification.requestPermission();
      } catch (err) {
        console.error("Notification permission request failed:", err);
      }
    }
  }, []);

  const showCompletionNotice = useCallback((title, body) => {
    if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "granted") {
      try {
        new Notification(title, { body });
        return;
      } catch (err) {
        console.error("Notification failed:", err);
      }
    }
    setAppNotice({ type: "success", title, body });
  }, []);

  useEffect(() => {
    if (!processingSession?.fullJobId && !processingSession?.previewJobId) return undefined;

    let stopped = false;
    const pollJobs = async () => {
      try {
        const current = processingSessionRef.current;
        if (!current) return;

        const [fullStatusData, previewStatusData] = await Promise.all([
          current.fullJobId ? getJobStatus(current.fullJobId).catch((err) => {
            console.error("Full job polling error:", err);
            return null;
          }) : Promise.resolve(null),
          current.previewJobId ? getJobStatus(current.previewJobId).catch((err) => {
            console.error("Preview job polling error:", err);
            return null;
          }) : Promise.resolve(null),
        ]);
        if (stopped) return;

        let fullResultData = null;
        let previewResultData = null;

        if (fullStatusData?.status === "completed" && !current.fullResult) {
          fullResultData = await getMeetingResult(current.fullJobId);
        }
        if (previewStatusData?.status === "completed" && !current.previewResult) {
          previewResultData = await getMeetingResult(current.previewJobId);
        }
        if (stopped) return;

        setProcessingSession((prev) => {
          if (!prev) return prev;
          const next = { ...prev };

          if (fullStatusData) {
            next.fullStatus = { ...prev.fullStatus, ...fullStatusData };
            if (fullStatusData.partial_result) {
              next.partialResult = fullStatusData.partial_result;
            }
          }
          if (previewStatusData) {
            next.previewStatus = { ...prev.previewStatus, ...previewStatusData };
            if (!next.previewResult && previewStatusData.partial_result) {
              next.previewResult = previewStatusData.partial_result;
            }
          }
          if (fullResultData && !fullResultData.error) {
            next.fullResult = fullResultData;
            next.partialResult = fullResultData;
          }
          if (previewResultData && !previewResultData.error) {
            next.previewResult = previewResultData;
          }

          return next;
        });
      } catch (err) {
        console.error("Polling error:", err);
      }
    };

    pollJobs();
    const interval = setInterval(pollJobs, POLL_INTERVAL_MS);
    return () => {
      stopped = true;
      clearInterval(interval);
    };
  }, [processingSession?.fullJobId, processingSession?.previewJobId]);

  useEffect(() => {
    if (!processingSession) return;
    if (processingSession.notificationSent) return;

    if (processingSession.fullStatus?.status === "completed" && processingSession.fullResult) {
      showCompletionNotice(
        "Meeting analysis completed",
        `${processingSession.fullResult.filename || "Your meeting"} is ready to review.`,
      );
      setProcessingSession((prev) => (prev ? { ...prev, notificationSent: true } : prev));
      return;
    }

    if (processingSession.fullStatus?.status === "failed") {
      setAppNotice({
        type: "error",
        title: "Processing failed",
        body: processingSession.fullStatus?.error || "Audio processing failed.",
      });
      setProcessingSession((prev) => (prev ? { ...prev, notificationSent: true } : prev));
      return;
    }

    if (processingSession.fullStatus?.status === "cancelled") {
      setAppNotice({
        type: "info",
        title: "Processing cancelled",
        body: processingSession.fullStatus?.error || "Meeting processing was cancelled.",
      });
      setProcessingSession((prev) => (prev ? { ...prev, notificationSent: true } : prev));
    }
  }, [processingSession, showCompletionNotice]);

  const liveResult = useMemo(
    () => processingSession?.fullResult || processingSession?.partialResult || processingSession?.previewResult || null,
    [processingSession],
  );

  const homeResult =
    activeHomeResultMode === "saved"
      ? savedResult
      : liveResult || (!processingSession ? savedResult : null);

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

  const formatDate = (isoString) => {
    if (!isoString) return "";
    const d = new Date(isoString);
    return d.toLocaleDateString();
  };

  const formatTime = (isoString) => {
    if (!isoString) return "";
    const d = new Date(isoString);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };

  const formatDuration = (seconds) => {
    if (!seconds && seconds !== 0) return "";
    const total = Math.max(0, Math.round(seconds));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    if (h > 0) {
      return `${h}:${m.toString().padStart(2, "0")}:${s
        .toString()
        .padStart(2, "0")}`;
    }
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  const handleDeleteMeeting = async (id) => {
    setMeetingPendingDelete(id);
  };

  const confirmDeleteMeeting = async () => {
    if (!meetingPendingDelete) return;
    try {
      await deleteMeeting(meetingPendingDelete);
      await loadMeetings();
      setMeetingPendingDelete(null);
    } catch (err) {
      console.error("Failed to delete meeting:", err);
      alert("Could not delete meeting. Please try again.");
    }
  };

  const openMeeting = async (id) => {
    try {
      const data = await getMeetingResult(id);
      if (data && !data.error && data.transcript) {
        setSavedResult(data);
        setActiveHomeResultMode("live");
        setActiveView("meetings");
      } else {
        alert("Could not load that meeting.");
      }
    } catch (err) {
      console.error(err);
      alert("Could not load meeting.");
    }
  };

  const startProcessingSession = useCallback(async ({ fullJobId, previewJobId = null, previewEnabled = false, previewSeconds = null }) => {
    setProcessingSession({
      fullJobId,
      previewJobId,
      previewEnabled,
      previewSeconds,
      fullStatus: buildQueuedStatus({ is_preview: false }),
      previewStatus: previewJobId ? buildQueuedStatus({ is_preview: true }) : null,
      partialResult: null,
      previewResult: null,
      fullResult: null,
      notificationSent: false,
    });
    setSavedResult(null);
    setActiveHomeResultMode("live");
    setActiveView("home");
    setAppNotice(null);
    await requestNotificationPermission();
  }, [requestNotificationPermission]);

  const handleCancelProcessing = useCallback(async () => {
    if (!processingSessionRef.current) return;
    const current = processingSessionRef.current;
    const jobIds = [current.previewJobId, current.fullJobId].filter(Boolean);
    await Promise.allSettled(jobIds.map((jobId) => cancelJob(jobId)));
    setProcessingSession((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        fullStatus: {
          ...prev.fullStatus,
          status: "cancelling",
          cancel_requested: true,
          stage_label: "Cancelling",
        },
        previewStatus: prev.previewStatus
          ? {
              ...prev.previewStatus,
              status: "cancelling",
              cancel_requested: true,
              stage_label: "Cancelling",
            }
          : null,
      };
    });
  }, []);

  const showCompactProcessing = Boolean(processingSession) && (activeView !== "home" || liveResult);
  const showFullProcessing = Boolean(processingSession) && !liveResult;
  const meetingInsightsLoading = Boolean(processingSession) && processingSession.fullStatus?.status !== "completed";
  const showSavedMeetingDetail = activeView === "meetings" && Boolean(savedResult);
  const topbarTitle = VIEW_TITLES[activeView] || "Home";

  return (
    <div className="app-layout">
      <Sidebar activeId={activeView} onSelect={setActiveView} />

      <div className="app-content">
        <header className="app-topbar">
          <div className="app-topbar-copy">
            <span className="app-topbar-label">{topbarTitle}</span>
          </div>
          <div className="app-topbar-actions" />
        </header>

        <main className="app-main">
          <Modal
            isOpen={Boolean(meetingPendingDelete)}
            onClose={() => setMeetingPendingDelete(null)}
            title="Delete meeting"
          >
            <div className="saas-confirm-copy">
              <p className="saas-confirm-text">
                Delete this meeting and its recording permanently?
              </p>
            </div>
            <div className="saas-confirm-actions">
              <button
                type="button"
                className="action-button saas-btn-outline"
                onClick={() => setMeetingPendingDelete(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="action-button saas-btn-stop"
                onClick={confirmDeleteMeeting}
              >
                Delete meeting
              </button>
            </div>
          </Modal>

          {appNotice && (
            <div className={`saas-inline-notice is-${appNotice.type || "info"}`}>
              <div>
                <p className="saas-inline-notice-title">{appNotice.title}</p>
                <p className="saas-inline-notice-body">{appNotice.body}</p>
              </div>
              <button
                type="button"
                className="saas-inline-notice-dismiss"
                onClick={() => setAppNotice(null)}
                aria-label="Dismiss notice"
              >
                ✕
              </button>
            </div>
          )}

          {showCompactProcessing && (
            <div className="page-banner">
              <ProcessingStatusCard
                session={processingSession}
                compact
                onCancel={handleCancelProcessing}
                onOpenLive={() => {
                  setActiveHomeResultMode("live");
                  setActiveView("home");
                }}
              />
            </div>
          )}

          {activeView === "meetings" && (
            showSavedMeetingDetail ? (
              <MeetingInsights
                result={savedResult}
                loading={false}
                onBack={() => setSavedResult(null)}
              />
            ) : (
              <SavedMeetingsView
                meetings={meetings}
                meetingsLoading={meetingsLoading}
                onOpenMeeting={openMeeting}
                onDeleteMeeting={handleDeleteMeeting}
                formatDate={formatDate}
                formatTime={formatTime}
                formatDuration={formatDuration}
              />
            )
          )}

          {activeView === "uploads" && (
            <UploadsView
              processingSession={processingSession}
              onCancel={handleCancelProcessing}
              onOpenLive={() => {
                setActiveHomeResultMode("live");
                setActiveView("home");
              }}
            />
          )}

          {activeView === "home" && showFullProcessing && (
            <section className="page-section saas-processing-screen">
              <ProcessingStatusCard
                session={processingSession}
                onCancel={handleCancelProcessing}
                onOpenLive={() => {
                  setActiveHomeResultMode("live");
                }}
              />
            </section>
          )}

          {activeView === "home" && !processingSession && !homeResult && (
            <HomeStartView onJobCreated={startProcessingSession} />
          )}

          {activeView === "home" && homeResult && (
            <MeetingInsights
              result={homeResult}
              loading={meetingInsightsLoading && activeHomeResultMode === "live"}
              onBack={
                activeHomeResultMode === "saved"
                  ? () => setActiveView("meetings")
                  : undefined
              }
            />
          )}
        </main>
      </div>
    </div>
  );
}
export default App;
