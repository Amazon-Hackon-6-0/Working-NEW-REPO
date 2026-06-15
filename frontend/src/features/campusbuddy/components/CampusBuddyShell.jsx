import {
  ArrowLeft,
  HeartHandshake,
  LayoutDashboard,
  MessageCircle,
  Network,
  Send,
  ShieldCheck,
  Users,
} from "lucide-react";

const links = [
  ["/campusbuddy", "Home", HeartHandshake],
  ["/campusbuddy/chat", "Friend Chat", MessageCircle],
  ["/campusbuddy/trust-dashboard", "Trust", ShieldCheck],
  ["/campusbuddy/connect", "Connect", Network],
  ["/campusbuddy/groups", "Groups", Users],
  ["/campusbuddy/escalation", "Escalation", Send],
  ["/campusbuddy/committee-dashboard", "Committee", LayoutDashboard],
];

export default function CampusBuddyShell({ children, path, navigate }) {
  return (
    <section className="cb-shell">
      <aside className="cb-side">
        <div className="cb-brand">
          <div className="cb-mark">CB</div>
          <div>
            <strong>CampusBuddy AI</strong>
            <span>Inside CampusFlow</span>
          </div>
        </div>
        <button
          className="cb-back"
          type="button"
          onClick={() => window.location.assign("/")}
        >
          <ArrowLeft size={16} />
          Back to CampusFlow Dashboard
        </button>
        <nav>
          {links.map(([href, label, Icon]) => (
            <button
              className={path === href ? "cb-nav active" : "cb-nav"}
              key={href}
              onClick={() => navigate(href)}
            >
              <Icon size={17} />
              {label}
            </button>
          ))}
        </nav>
      </aside>
      <div className="cb-content">{children}</div>
    </section>
  );
}
