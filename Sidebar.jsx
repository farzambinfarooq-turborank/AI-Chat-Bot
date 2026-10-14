import {
  LayoutGrid,
  MessagesSquare,
  Package,
  LifeBuoy,
  Bell,
} from "lucide-react";

const NAV = [
  { id: "overview", label: "Overview", icon: LayoutGrid },
  { id: "conversations", label: "Conversations", icon: MessagesSquare },
  { id: "orders", label: "Orders", icon: Package },
  { id: "support", label: "Support", icon: LifeBuoy, key: "escalations" },
  { id: "followups", label: "Follow-ups", icon: Bell, key: "followUps" },
];

export default function Sidebar({ active, onChange, counts, open, onClose }) {
  function handleSelect(id) {
    onChange(id);
    onClose?.();
  }

  return (
    <>
      <div
        className={"sidebar-overlay" + (open ? " visible" : "")}
        onClick={onClose}
      />

      <aside className={"sidebar" + (open ? " open" : "")}>
        <div className="sidebar-mark">
          <div className="shop">RH Clothing Store</div>
          <div className="sub">Front desk</div>
        </div>

        <nav className="sidebar-nav">
          {NAV.map(({ id, label, icon: Icon, key }) => {
            const count = counts?.[key || id];
            return (
              <button
                key={id}
                className={"sidebar-link" + (active === id ? " active" : "")}
                onClick={() => handleSelect(id)}
              >
                <Icon size={16} strokeWidth={2} />
                <span>{label}</span>
                {typeof count === "number" && count > 0 && (
                  <span className="count">{count}</span>
                )}
              </button>
            );
          })}
        </nav>

        <div className="sidebar-foot">
          <span className="dot" />
          Agent online
        </div>
      </aside>
    </>
  );
}