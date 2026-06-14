import { useState } from "react";
import CampusBuddyHeader from "../components/CampusBuddyHeader.jsx";
import { campusbuddyApi } from "../services/campusbuddyApi.js";

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

export default function CommitteeEscalation() {
  const [complaintText, setComplaintText] = useState("Hostel WiFi is not working properly.");
  const [data, setData] = useState(null);
  const [outbox, setOutbox] = useState([]);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoadingOutbox, setIsLoadingOutbox] = useState(false);
  const [selectedStudentId, setSelectedStudentId] = useState("student_001");

  async function submitComplaint() {
    const trimmedText = complaintText.trim();
    if (!trimmedText) return;

    setError("");
    setIsSubmitting(true);

    try {
      const response = await campusbuddyApi.submitComplaint({
        studentId: selectedStudentId,
        complaintText: trimmedText,
      });
      setData(response);
      if (response.ready_for_escalation) {
        await loadOutbox();
      }
    } catch (requestError) {
      setError("Could not submit the anonymous complaint right now. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function loadOutbox() {
    setError("");
    setIsLoadingOutbox(true);

    try {
      const response = await campusbuddyApi.complaintEscalations();
      setOutbox(response.outbox || []);
    } catch (requestError) {
      setError("Could not load mock Discord escalations right now.");
    } finally {
      setIsLoadingOutbox(false);
    }
  }

  function progressPercent() {
    if (!data) return 0;
    return Math.min(100, Math.round((data.similar_complaint_count / data.threshold) * 100));
  }

  return (
    <div>
      <CampusBuddyHeader eyebrow="Anonymous Complaint Escalation" title="Pattern before escalation">
        CampusBuddy stores complaints privately, groups similar issues, and prepares a generalized mock Discord message only after enough anonymous reports match.
      </CampusBuddyHeader>
      <section className="cb-note">
        <strong>Committee-safe by design.</strong>
        <span>Individual complaints and student identities are never shown in the escalation outbox.</span>
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
          Demo mode: choose a student to simulate who is submitting the anonymous complaint.
        </p>
        <textarea
          placeholder="Describe a campus issue privately..."
          value={complaintText}
          onChange={(event) => setComplaintText(event.target.value)}
        />
        <div className="cb-actions">
          <button className="cb-primary" disabled={isSubmitting} onClick={submitComplaint} type="button">
            {isSubmitting ? "Submitting..." : "Submit anonymous complaint"}
          </button>
          <button className="cb-secondary" disabled={isLoadingOutbox} onClick={loadOutbox} type="button">
            {isLoadingOutbox ? "Loading..." : "View Mock Discord Escalations"}
          </button>
        </div>
      </section>

      {error ? <div className="cb-success cb-alert">{error}</div> : null}

      {data ? (
        <article className="cb-card cb-section">
          <div className="cb-result-meta">
            <span className="cb-pill">{data.category}</span>
            <span className="cb-pill">{data.target_group}</span>
          </div>
          <h3>Complaint recorded anonymously</h3>
          <dl className="cb-detail-list">
            <div>
              <dt>Stored anonymously</dt>
              <dd>{data.stored_anonymously ? "Yes" : "No"}</dd>
            </div>
            <div>
              <dt>Topic key</dt>
              <dd>{data.topic_key}</dd>
            </div>
            <div>
              <dt>Unique student reports</dt>
              <dd>{data.similar_complaint_count} / {data.threshold}</dd>
            </div>
            <div>
              <dt>Ready for escalation</dt>
              <dd>{data.ready_for_escalation ? "Yes" : "No"}</dd>
            </div>
            <div>
              <dt>Mock Discord destination</dt>
              <dd>{data.mock_discord_destination || "Not prepared yet"}</dd>
            </div>
          </dl>
          <div className="cb-progress" aria-label="Unique student complaint threshold progress">
            <span style={{ width: `${progressPercent()}%` }} />
          </div>
          {data.duplicate_student_topic ? (
            <div className="cb-success cb-warning">
              You already reported a similar issue. Your complaint was stored, but it does not increase the escalation threshold.
            </div>
          ) : null}
          <div className={data.ready_for_escalation ? "cb-success" : "cb-consent"}>
            {data.ready_for_escalation
              ? "Status: Generalized escalation prepared"
              : "Status: Waiting for more similar anonymous reports"}
          </div>
          {data.generalized_summary ? (
            <div className="cb-consent">
              <strong>Generalized summary</strong>
              <span>{data.generalized_summary}</span>
              <span>Summary source: {data.summary_source === "gemini" ? "Gemini" : "Fallback"}</span>
              {data.summary_fallback_reason ? (
                <span>Fallback reason: {data.summary_fallback_reason}</span>
              ) : null}
            </div>
          ) : null}
          <p className="cb-small-note">{data.message}</p>
        </article>
      ) : null}

      <section className="cb-section">
        <div className="cb-inbox-header">
          <div>
            <span className="cb-eyebrow">Mock Discord Outbox</span>
            <h2>Escalations</h2>
            <p className="cb-small-note">
              Mock Discord Outbox contains only generalized anonymous summaries. Student IDs and raw complaints are never shown here.
            </p>
          </div>
          <button className="cb-secondary" disabled={isLoadingOutbox} onClick={loadOutbox} type="button">
            {isLoadingOutbox ? "Loading..." : "View Mock Discord Escalations"}
          </button>
        </div>

        {outbox.length ? (
          <div className="cb-grid">
            {outbox.map((item) => (
              <article className="cb-card" key={item.escalation_id}>
                <div className="cb-result-meta">
                  <span className="cb-pill">{item.status}</span>
                  <span className="cb-pill">{item.destination}</span>
                </div>
                <h3>{item.escalation_id}</h3>
                <dl className="cb-detail-list">
                  <div>
                    <dt>Category</dt>
                    <dd>{item.category}</dd>
                  </div>
                  <div>
                    <dt>Target group</dt>
                    <dd>{item.target_group}</dd>
                  </div>
                  <div>
                    <dt>Complaint count</dt>
                    <dd>{item.complaint_count}</dd>
                  </div>
                </dl>
                <div className="cb-consent">
                  <strong>Generalized summary</strong>
                  <span>{item.generalized_summary}</span>
                  <span>Summary source: {item.summary_source === "gemini" ? "Gemini" : "Fallback"}</span>
                  {item.summary_fallback_reason ? (
                    <span>Fallback reason: {item.summary_fallback_reason}</span>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <article className="cb-card cb-inbox-empty">
            <h3>No mock Discord escalations yet</h3>
            <p>Submit three similar anonymous complaints to prepare a generalized escalation.</p>
          </article>
        )}
      </section>
    </div>
  );
}
