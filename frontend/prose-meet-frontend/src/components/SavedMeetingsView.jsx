// Saved meetings view for browsing past sessions.
import LoadingSkeleton from "./LoadingSkeleton";
import EmptyState from "./EmptyState";
import PageHeader from "./PageHeader";
import { TrashIcon } from "@heroicons/react/24/outline";

function MeetingRowsSkeleton() {
  return (
    <ul className="saas-meetings-ul saas-meetings-table">
      <li className="saas-meetings-header">
        <span>Name</span>
        <span>Date</span>
        <span>Time</span>
        <span>Duration</span>
        <span>Actions</span>
      </li>
      {Array.from({ length: 4 }).map((_, index) => (
        <li key={index} className="saas-meetings-li saas-meetings-li-skeleton">
          <span data-label="Name">
            <LoadingSkeleton className="saas-skeleton-inline saas-skeleton-wide" />
          </span>
          <span data-label="Date">
            <LoadingSkeleton className="saas-skeleton-inline" />
          </span>
          <span data-label="Time">
            <LoadingSkeleton className="saas-skeleton-inline" />
          </span>
          <span data-label="Duration">
            <LoadingSkeleton className="saas-skeleton-inline" />
          </span>
          <span data-label="Actions">
            <LoadingSkeleton className="saas-skeleton-inline" />
          </span>
        </li>
      ))}
    </ul>
  );
}

export default function SavedMeetingsView({
  meetings,
  meetingsLoading,
  onOpenMeeting,
  onDeleteMeeting,
  formatDate,
  formatTime,
  formatDuration,
}) {
  return (
    <section className="page-section">
      <PageHeader
        eyebrow="Library"
        title="Saved meetings"
        description="Open prior analyses, revisit transcripts, and remove recordings that are no longer needed."
      />

      <div className="surface-panel">
        {meetingsLoading ? (
          <MeetingRowsSkeleton />
        ) : meetings.length === 0 ? (
          <EmptyState
            title="No meetings yet"
            description="Import audio from Home to generate your first saved meeting and insight report."
            compact
          />
        ) : (
          <ul className="saas-meetings-ul saas-meetings-table">
            <li className="saas-meetings-header">
              <span>Name</span>
              <span>Date</span>
              <span>Time</span>
              <span>Duration</span>
              <span>Actions</span>
            </li>
            {meetings.map((meeting) => (
              <li key={meeting.id} className="saas-meetings-li">
                <button
                  type="button"
                  className="saas-meetings-row-main"
                  onClick={() => onOpenMeeting(meeting.id)}
                >
                  <span className="saas-meetings-name" data-label="Name">
                    {meeting.filename}
                  </span>
                  <span className="saas-meetings-date" data-label="Date">
                    {formatDate(meeting.created_at)}
                  </span>
                  <span className="saas-meetings-time" data-label="Time">
                    {formatTime(meeting.created_at)}
                  </span>
                  <span className="saas-meetings-duration" data-label="Duration">
                    {meeting.duration_seconds != null
                      ? formatDuration(meeting.duration_seconds)
                      : ""}
                  </span>
                </button>
                <button
                  type="button"
                  className="saas-meetings-delete"
                  onClick={() => onDeleteMeeting(meeting.id)}
                  aria-label={`Delete ${meeting.filename}`}
                  title="Delete meeting"
                >
                  <TrashIcon width={16} height={16} aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
