// Shared page header for branding and controls.
export default function PageHeader({
  eyebrow,
  title,
  description,
  actions = null,
  align = "left",
}) {
  return (
    <header className={`page-header page-header-${align}`}>
      <div className="page-header-copy">
        {eyebrow && <span className="page-header-eyebrow">{eyebrow}</span>}
        <h1 className="page-header-title">{title}</h1>
        {description && <p className="page-header-description">{description}</p>}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </header>
  );
}
