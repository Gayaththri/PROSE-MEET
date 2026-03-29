// Sidebar navigation for primary application sections.
import brandLogo from "../assets/brand-logo.png";
import {
  HomeIcon as HomeIconOutline,
  CalendarDaysIcon as CalendarDaysIconOutline,
} from "@heroicons/react/24/outline";
import {
  HomeIcon as HomeIconSolid,
  CalendarDaysIcon as CalendarDaysIconSolid,
} from "@heroicons/react/24/solid";

const NAV_ITEMS = [
  { id: "home", label: "Home", IconOutline: HomeIconOutline, IconSolid: HomeIconSolid },
  { id: "meetings", label: "Meetings", IconOutline: CalendarDaysIconOutline, IconSolid: CalendarDaysIconSolid },
];

function NavLink({ item, activeId, onSelect }) {
  const isActive = activeId === item.id;
  const IconComponent = isActive ? item.IconSolid : item.IconOutline;
  return (
    <button
      type="button"
      onClick={() => onSelect(item.id)}
      className={`sidebar-link ${isActive ? "sidebar-link-active" : ""}`}
    >
      <span className="sidebar-link-icon" aria-hidden="true">
        {IconComponent ? (
          <IconComponent className="sidebar-link-icon-img" width={20} height={20} />
        ) : null}
      </span>
      <span className="sidebar-link-label">{item.label}</span>
      {item.badge && <span className="sidebar-badge">{item.badge}</span>}
    </button>
  );
}

export default function Sidebar({ activeId = "home", onSelect }) {
  const setActiveId = onSelect || (() => {});

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="sidebar-logo" aria-hidden>
          <img src={brandLogo} alt="" className="sidebar-logo-image" />
        </span>
        <div className="sidebar-brand-copy">
          <span className="sidebar-brand-name">PROSE-MEET</span>
        </div>
      </div>

      <nav className="sidebar-nav">
        <div className="sidebar-group">
          <span className="sidebar-group-label">Workspace</span>
          <NavLink
            item={NAV_ITEMS[0]}
            activeId={activeId}
            onSelect={setActiveId}
          />
        </div>
        <div className="sidebar-group">
          <span className="sidebar-group-label">Library</span>
          {NAV_ITEMS.slice(1).map((item) => (
            <NavLink
              key={item.id}
              item={item}
              activeId={activeId}
              onSelect={setActiveId}
            />
          ))}
        </div>
      </nav>

      <div className="sidebar-footer">
        <p className="sidebar-footer-title">Always-on processing</p>
        <p className="sidebar-footer-copy">
          Start from Home, then track long running jobs without leaving the app.
        </p>
      </div>
    </aside>
  );
}
