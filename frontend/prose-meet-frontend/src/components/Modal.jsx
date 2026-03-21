import { XMarkIcon } from "@heroicons/react/24/outline";

export default function Modal({
  isOpen,
  onClose,
  children,
  title = "Import meeting audio",
}) {
  if (!isOpen) return null;

  return (
    <div className="saas-modal-backdrop" onClick={onClose}>
      <div className="saas-modal" onClick={(e) => e.stopPropagation()}>
        <div className="saas-modal-header">
          <h2>{title}</h2>
          <button type="button" onClick={onClose} className="saas-modal-close" aria-label="Close">
            <XMarkIcon width={16} height={16} aria-hidden="true" />
          </button>
        </div>
        <div className="saas-modal-body">{children}</div>
      </div>
    </div>
  );
}
