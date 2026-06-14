import { ArrowRight, ShieldCheck } from "lucide-react";
import CampusBuddyHeader from "../components/CampusBuddyHeader.jsx";

const demoSteps = [
  ["Personal AI Friend", "A lonely student speaks safely and gets warm support.", "/campusbuddy/chat"],
  ["Consent-Based Memory", "The student clicks Remember before anything is saved.", "/campusbuddy/trust-dashboard"],
  ["Mutual Anonymous Connector", "Requester and helper choose what to reveal.", "/campusbuddy/connect"],
  ["Community Group Builder", "Chess interest becomes an opt-in invite.", "/campusbuddy/groups"],
  ["WhatsApp Committee Escalation", "Mess issue becomes an anonymous confirmed summary.", "/campusbuddy/escalation"],
];

export default function CampusBuddyHome({ navigate }) {
  return (
    <div>
      <section className="cb-hero">
        <div>
          <CampusBuddyHeader eyebrow="CampusBuddy AI" title="Speak. Connect. Resolve. Belong.">
            CampusBuddy helps students speak, connect, resolve, and belong. It starts as a personal AI friend, then helps students take safe consent-based steps toward people, groups, and campus support.
          </CampusBuddyHeader>
          <div className="cb-actions">
            <button className="cb-primary" onClick={() => navigate("/campusbuddy/chat")}>
              Talk to CampusBuddy <ArrowRight size={18} />
            </button>
            <button className="cb-secondary" onClick={() => navigate("/campusbuddy/trust-dashboard")}>
              <ShieldCheck size={18} /> View trust controls
            </button>
          </div>
        </div>
        <article className="cb-card">
          <strong>Why anonymity?</strong>
          <p>Anonymity is a confidence bridge, not the destination.</p>
          <p>Raw chats stay private. Identity is revealed only by consent.</p>
        </article>
      </section>

      <section className="cb-section">
        <span className="cb-eyebrow">Visible demo guide</span>
        <h2>Five judge demo steps</h2>
        <div className="cb-flow-grid">
          {demoSteps.map(([title, detail, href], index) => (
            <article key={title} onClick={() => navigate(href)}>
              <strong>{index + 1}</strong>
              <h3>{title}</h3>
              <p>{detail}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
