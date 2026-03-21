import EmptyState from "./EmptyState";
import PageHeader from "./PageHeader";
import ProcessingStatusCard from "./ProcessingStatusCard";

export default function UploadsView({ processingSession, onCancel, onOpenLive }) {
  return (
    <section className="page-section">
      <PageHeader
        eyebrow="Processing"
        title="Current processing"
        description="Track the active meeting pipeline, keep working elsewhere, and jump back into live insights whenever they are ready."
      />

      {processingSession ? (
        <ProcessingStatusCard
          session={processingSession}
          onCancel={onCancel}
          onOpenLive={onOpenLive}
        />
      ) : (
        <EmptyState
          title="No active processing jobs"
          description="Start a new upload from Home and progress will appear here automatically."
        />
      )}
    </section>
  );
}
