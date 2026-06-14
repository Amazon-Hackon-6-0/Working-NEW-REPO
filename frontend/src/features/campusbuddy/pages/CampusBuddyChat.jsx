import { useState } from "react";
import CampusBuddyHeader from "../components/CampusBuddyHeader.jsx";
import { campusbuddyApi } from "../services/campusbuddyApi.js";

const prompts = [
  "I feel lonely and I don't know how to make friends in college.",
  "I need help in DSA graphs but I feel awkward asking in the group.",
  "I want to start a chess group.",
  "Mess food quality has been bad for 3 days.",
];

const demoStudents = [
  { id: "student_001", label: "student_001 - Current Student" },
  { id: "student_002", label: "student_002 - Demo Student 002" },
  { id: "student_003", label: "student_003 - Demo Student 003" },
  { id: "student_004", label: "student_004 - Demo Student 004" },
  { id: "student_005", label: "student_005 - Demo Student 005" },
  { id: "student_006", label: "student_006 - Demo Student 006" },
  { id: "student_007", label: "student_007 - Demo Student 007" },
  { id: "student_008", label: "student_008 - Demo Student 008" },
  { id: "student_009", label: "student_009 - Demo Student 009" },
];

export default function CampusBuddyChat() {
  const [message, setMessage] = useState(prompts[0]);
  const [chat, setChat] = useState([]);
  const [remembered, setRemembered] = useState("");
  const [selectedStudentId, setSelectedStudentId] = useState("student_001");

  async function send(customMessage = message) {
    if (!customMessage.trim()) return;
    const result = await campusbuddyApi.chat(customMessage, selectedStudentId);
    setChat((current) => [...current, { role: "student", text: customMessage }, { role: "buddy", ...result }]);
    setMessage("");
  }

  async function remember(candidate) {
    const memoryText = candidate.label || candidate.text || "CampusBuddy memory";
    const saved = await campusbuddyApi.remember(
      memoryText,
      "Student-approved memory",
      candidate.used_for || inferMemoryUsage(memoryText),
      selectedStudentId
    );
    setRemembered(`Remembered for ${selectedStudentId}: ${saved.label}`);
  }

  function inferMemoryUsage(memoryText) {
    const lowerMemoryText = memoryText.toLowerCase();
    const groupTerms = [
      "hobby",
      "group",
      "interest",
      "interested",
      "sport",
      "sports",
      "music",
      "chess",
      "badminton",
      "football",
      "cricket",
      "coding",
      "anime",
      "gym",
      "dance",
      "photography",
    ];
    const helpTerms = [
      "dsa",
      "help",
      "can help",
      "can teach",
      "can mentor",
      "good at",
      "strong in",
      "academic",
      "career",
      "resume",
      "internship",
      "interview",
      "placement",
      "public speaking",
    ];
    const offerHelpTerms = ["can help", "can teach", "can mentor", "good at", "strong in"];
    const isOfferHelp = offerHelpTerms.some((term) => lowerMemoryText.includes(term));

    return {
      personalization: true,
      peer_matching: helpTerms.some((term) => lowerMemoryText.includes(term)),
      group_suggestions: isOfferHelp ? false : groupTerms.some((term) => lowerMemoryText.includes(term)),
      anonymous_campus_insight: false,
    };
  }

  return (
    <div>
      <CampusBuddyHeader eyebrow="Personal AI Friend" title="Talk freely first">
        Start with what you actually feel. CampusBuddy listens first, then helps you choose a safe next step.
      </CampusBuddyHeader>
      <section className="cb-note">
        <strong>Anonymity is a confidence bridge, not the destination.</strong>
        <span>You can stay private while you build confidence to connect.</span>
      </section>
      <section className="cb-form">
        <label className="cb-select-label cb-student-select">
          Current Demo Student
          <select value={selectedStudentId} onChange={(event) => setSelectedStudentId(event.target.value)}>
            {demoStudents.map((student) => (
              <option key={student.id} value={student.id}>
                {student.label}
              </option>
            ))}
          </select>
        </label>
        <p className="cb-small-note">
          Demo mode: this simulates which student is chatting. Memories are saved only after clicking Remember.
        </p>
      </section>
      <section className="cb-scenarios">
        {prompts.map((prompt) => (
          <button key={prompt} onClick={() => send(prompt)}>{prompt}</button>
        ))}
      </section>
      <section className="cb-chat-window">
        {chat.length === 0 ? (
          <div className="cb-welcome">
            <div className="cb-avatar">CB</div>
            <h2>Hi, I am here with you.</h2>
            <p>College can feel loud outside and lonely inside. You can talk here without being judged.</p>
          </div>
        ) : (
          chat.map((item, index) => (
            <div className={`cb-bubble ${item.role}`} key={`${item.role}-${index}`}>
              <p>{item.text || item.reply_text || item.reply}</p>
              {item.source ? <span className="cb-pill">Source: {item.source}</span> : null}
              {(item.detected_intent || item.intent) ? (
                <span className="cb-pill">Classified as {(item.detected_intent || item.intent).replaceAll("_", " ")}</span>
              ) : null}
              {(item.memory_suggestions?.[0] || item.memory_candidate) ? (
                <div className="cb-consent">
                  <strong>Consent prompt</strong>
                  <span>{(item.memory_suggestions?.[0] || item.memory_candidate).reason}</span>
                  <button onClick={() => remember(item.memory_suggestions?.[0] || item.memory_candidate)}>Remember</button>
                </div>
              ) : null}
              {(item.suggested_actions || item.actions)?.length ? (
                <ul className="cb-action-list">
                  {(item.suggested_actions || item.actions).map((action) => <li key={action}>{action}</li>)}
                </ul>
              ) : null}
              {item.privacy_note ? <p className="cb-small-note">{item.privacy_note}</p> : null}
              {item.matching_query ? (
                <div className="cb-consent">
                  <strong>Matching query</strong>
                  <span>{item.matching_query.query}</span>
                </div>
              ) : null}
              {item.escalation_preview ? (
                <div className="cb-consent">
                  <strong>Escalation preview</strong>
                  <span>{item.escalation_preview.summary}</span>
                </div>
              ) : null}
            </div>
          ))
        )}
      </section>
      {remembered ? <div className="cb-success">{remembered}</div> : null}
      <div className="cb-input-row">
        <input value={message} onChange={(event) => setMessage(event.target.value)} />
        <button className="cb-primary" onClick={() => send()}>Send</button>
      </div>
    </div>
  );
}
