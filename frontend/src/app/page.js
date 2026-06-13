"use client";

import { useEffect, useMemo, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000/api/v1";

const subjects = [
  {
    code: "DBMS",
    name: "Database Management Systems",
    faculty: "Prof. Mehra",
    held: 26,
    attended: 20,
    nextClass: "Mon, 9:00 AM",
  },
  {
    code: "OS",
    name: "Operating Systems",
    faculty: "Dr. Iyer",
    held: 28,
    attended: 22,
    nextClass: "Mon, 11:00 AM",
  },
  {
    code: "CN",
    name: "Computer Networks",
    faculty: "Prof. Rao",
    held: 24,
    attended: 21,
    nextClass: "Tue, 10:00 AM",
  },
  {
    code: "AI",
    name: "Artificial Intelligence",
    faculty: "Dr. Sen",
    held: 18,
    attended: 16,
    nextClass: "Wed, 2:00 PM",
  },
];

const assignments = [
  {
    title: "OS deadlock case study",
    course: "Operating Systems",
    due: "Today, 11:59 PM",
    state: "Pending",
    source: "Google Classroom",
  },
  {
    title: "CN subnetting worksheet",
    course: "Computer Networks",
    due: "Tomorrow, 5:00 PM",
    state: "Submitted",
    source: "Google Classroom",
  },
  {
    title: "DBMS ER diagram revision",
    course: "Database Management Systems",
    due: "Jun 16, 9:00 AM",
    state: "Unknown",
    source: "Manual entry",
  },
];

const exams = [];

const updates = [
  "Placement prep session moved to 4:30 PM in Seminar Hall 2.",
  "Central library will stay open until midnight this week.",
  "Hostel dinner menu changed to chole rice and curd.",
];

function mapOverviewSubject(subject) {
  return {
    code: subject.code,
    name: subject.name,
    faculty: subject.faculty,
    held: subject.held_classes,
    attended: subject.attended_classes,
    nextClass: subject.next_class,
    percent: subject.attendance_percent,
    bunkBudget: subject.bunk_budget,
    classesNeeded: subject.classes_needed,
    state: subject.status.charAt(0).toUpperCase() + subject.status.slice(1),
  };
}

function getAttendance(subject, threshold) {
  const percent = Number(((subject.attended / subject.held) * 100).toFixed(1));
  const maxTotalClasses = Math.floor(subject.attended / (threshold / 100));
  const bunkBudget = Math.max(0, maxTotalClasses - subject.held);
  let classesNeeded = 0;

  while (
    ((subject.attended + classesNeeded) / (subject.held + classesNeeded)) * 100 <
    threshold
  ) {
    classesNeeded += 1;
  }

  let state = "Safe";
  if (percent < threshold) state = "Critical";
  else if (Math.abs(percent - threshold) <= 10) state = "Danger";
  else if (percent < 85) state = "Watch";

  return { percent, bunkBudget, classesNeeded, state };
}

function statusClass(value) {
  return value.toLowerCase();
}

export default function Home() {
  const threshold = 75;
  const [selectedSubject, setSelectedSubject] = useState(subjects[0].code);
  const [feedback, setFeedback] = useState("held-attended");
  const [integrationStatus, setIntegrationStatus] = useState(null);
  const [integrationMessage, setIntegrationMessage] = useState(
    "Connect Google Classroom and Discord when credentials are configured.",
  );
  const [overview, setOverview] = useState(null);
  const [overviewMessage, setOverviewMessage] = useState("Loading live CampusFlow data.");
  const [attendanceEvents, setAttendanceEvents] = useState([]);
  const [examUploadMessage, setExamUploadMessage] = useState(
    "Upload a text-based PDF exam schedule, then extract reminders.",
  );
  const [examPdfFile, setExamPdfFile] = useState(null);

  const attendance = useMemo(
    () => {
      if (overview?.attendance?.length) {
        return overview.attendance.map(mapOverviewSubject);
      }
      return subjects.map((subject) => ({
        ...subject,
        ...getAttendance(subject, threshold),
      }));
    },
    [overview],
  );

  const activeSubject = attendance.find((item) => item.code === selectedSubject);
  const liveAssignments = overview?.assignments?.length
    ? overview.assignments.map((assignment) => ({
        title: assignment.title,
        course: assignment.course,
        due: assignment.due_at,
        state: assignment.status.charAt(0).toUpperCase() + assignment.status.slice(1),
        source: assignment.source,
      }))
    : assignments;
  const liveExams = overview?.exams?.length
    ? overview.exams.map((exam) => ({
        subject: exam.subject,
        date: exam.exam_date,
        time: exam.time,
        venue: exam.venue,
        verified: exam.verified_by_user,
      }))
    : exams;
  const dangerCount = attendance.filter((item) =>
    ["Critical", "Danger"].includes(item.state),
  ).length;
  const pendingAssignments = liveAssignments.filter(
    (assignment) => assignment.state !== "Submitted",
  ).length;

  async function refreshCampusFlowData() {
    await fetch(`${API_BASE}/campusflow/overview`)
      .then((response) => response.json())
      .then((data) => {
        setOverview(data);
        setOverviewMessage(`Live data loaded. Last verified: ${data.last_verified}`);
      })
      .catch(() => {
        setOverviewMessage("Using demo data because backend overview is not reachable.");
      });

    await fetch(`${API_BASE}/campusflow/attendance/events`)
      .then((response) => response.json())
      .then(setAttendanceEvents)
      .catch(() => setAttendanceEvents([]));
  }

  useEffect(() => {
    refreshCampusFlowData();
    fetch(`${API_BASE}/integrations/status`)
      .then((response) => response.json())
      .then(setIntegrationStatus)
      .catch(() => {
        setIntegrationMessage("Backend integration status is not reachable yet.");
      });
  }, []);

  async function openGoogleClassroomAuth() {
    const response = await fetch(`${API_BASE}/integrations/google/auth-url`);
    const data = await response.json();
    if (!response.ok) {
      setIntegrationMessage(data.detail || "Google Classroom is not configured.");
      return;
    }
    window.open(data.auth_url, "_blank", "noopener,noreferrer");
    setIntegrationMessage("Google OAuth opened. Complete consent, then sync assignments.");
  }

  async function syncGoogleClassroom() {
    const response = await fetch(`${API_BASE}/integrations/google/classroom/sync`, {
      method: "POST",
    });
    const data = await response.json();
    if (!response.ok) {
      setIntegrationMessage(data.detail || "Google Classroom sync failed.");
      return;
    }
    setIntegrationMessage(data.message);
    refreshCampusFlowData();
  }

  async function sendDiscordPrompt() {
    const response = await fetch(`${API_BASE}/integrations/discord/daily-feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subject_code: selectedSubject }),
    });
    const data = await response.json();
    if (!response.ok) {
      setIntegrationMessage(data.detail || "Discord prompt failed.");
      return;
    }
    setIntegrationMessage(data.message);
    refreshCampusFlowData();
  }

  async function uploadExamPdf() {
    if (!examPdfFile) {
      setExamUploadMessage("Choose a PDF exam schedule first.");
      return;
    }

    const formData = new FormData();
    formData.append("file", examPdfFile);
    formData.append("confirm_as_latest", "true");

    const response = await fetch(`${API_BASE}/campusflow/exams/upload-pdf`, {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    if (!response.ok) {
      setExamUploadMessage(data.detail || "PDF exam schedule upload failed.");
      return;
    }
    setExamUploadMessage(data.message);
    if (data.outdated_items?.length) {
      setExamUploadMessage(`${data.message} Outdated: ${data.outdated_items.join(", ")}`);
    }
    refreshCampusFlowData();
  }

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="CampusFlow navigation">
        <div>
          <p className="eyebrow">CampusFlow</p>
          <h1>Student Life OS</h1>
        </div>
        <nav>
          <a href="#attendance">Attendance</a>
          <a href="#exams">Exams</a>
          <a href="#assignments">Assignments</a>
          <a href="#briefing">Briefing</a>
        </nav>
        <div className="sidebar-note">
          <span>Verified</span>
          <strong>13 Jun, 9:00 IST</strong>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Semester 5 dashboard</p>
            <h2>Tonight&apos;s briefing is ready for Discord</h2>
          </div>
          <button type="button" className="primary-button">
            Send briefing
          </button>
        </header>

        <section className="metrics" aria-label="CampusFlow summary">
          <div className="metric">
            <span>Attendance risk</span>
            <strong>{dangerCount}</strong>
            <p>subjects near or below 75%</p>
          </div>
          <div className="metric">
            <span>Pending work</span>
            <strong>{pendingAssignments}</strong>
            <p>assignments need attention</p>
          </div>
          <div className="metric">
            <span>Next exam</span>
            <strong>{liveExams[0]?.date || "None"}</strong>
            <p>{liveExams[0]?.subject || "Upload schedule PDF"}</p>
          </div>
          <div className="metric">
            <span>Daily nudges</span>
            <strong>8 PM</strong>
            <p>Discord private channel</p>
          </div>
        </section>

        <section className="grid-main">
          <section className="panel attendance-panel" id="attendance">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Human feedback loop</p>
                <h3>Attendance tracker</h3>
              </div>
              <span className="threshold">Threshold {threshold}%</span>
            </div>

            <div className="attendance-list">
              <p className="live-note">{overviewMessage}</p>
              {attendance.map((subject) => (
                <article className="subject-row" key={subject.code}>
                  <div>
                    <strong>{subject.code}</strong>
                    <span>{subject.name}</span>
                  </div>
                  <div className="progress-wrap" aria-label={`${subject.code} attendance`}>
                    <span
                      className={`progress ${statusClass(subject.state)}`}
                      style={{ width: `${subject.percent}%` }}
                    />
                  </div>
                  <div className="subject-stats">
                    <strong>{subject.percent}%</strong>
                    <span>{subject.attended}/{subject.held}</span>
                  </div>
                  <span className={`pill ${statusClass(subject.state)}`}>
                    {subject.state}
                  </span>
                  <div className="bunk">
                    <strong>{subject.bunkBudget}</strong>
                    <span>bunks left</span>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="panel feedback-panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Class reality check</p>
                <h3>Submit feedback</h3>
              </div>
            </div>
            <label>
              Subject
              <select
                value={selectedSubject}
                onChange={(event) => setSelectedSubject(event.target.value)}
              >
                {attendance.map((subject) => (
                  <option key={subject.code} value={subject.code}>
                    {subject.code} - {subject.nextClass}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Class status
              <select
                value={feedback}
                onChange={(event) => setFeedback(event.target.value)}
              >
                <option value="held-attended">Held and attended</option>
                <option value="held-missed">Held but missed</option>
                <option value="cancelled">Cancelled</option>
                <option value="holiday">Holiday</option>
                <option value="teacher-absent">Teacher absent</option>
              </select>
            </label>
            <div className="feedback-result">
              <span>Preview</span>
              <strong>
                {activeSubject.code} stays at {activeSubject.percent}% today
              </strong>
              <p>
                If class was cancelled, it will not affect the attendance denominator.
              </p>
            </div>
          </section>
        </section>

        <section className="panel integrations-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Real integrations</p>
              <h3>Google Classroom + Discord</h3>
            </div>
            <div className="integration-status">
              <span
                className={`dot ${
                  integrationStatus?.google_classroom_connected ? "on" : "off"
                }`}
              />
              <span>Classroom</span>
              <span
                className={`dot ${integrationStatus?.discord_configured ? "on" : "off"}`}
              />
              <span>Discord</span>
              <span
                className={`dot ${
                  integrationStatus?.discord_bot_configured ? "on" : "off"
                }`}
              />
              <span>Bot buttons</span>
            </div>
          </div>
          <div className="integration-actions">
            <button type="button" onClick={openGoogleClassroomAuth}>
              Connect Classroom
            </button>
            <button type="button" onClick={syncGoogleClassroom}>
              Sync assignments
            </button>
            <button type="button" onClick={sendDiscordPrompt}>
              Send button prompt
            </button>
          </div>
          <p className="integration-message">{integrationMessage}</p>
        </section>

        <section className="three-column">
          <section className="panel" id="exams">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Freshness check</p>
                <h3>Exam reminders</h3>
              </div>
            </div>
            <div className="stack">
              {liveExams.length === 0 ? (
                <p className="empty-state">
                  No upcoming exams uploaded. Add a schedule PDF to activate reminders.
                </p>
              ) : (
                liveExams.map((exam) => (
                  <article className="list-item" key={exam.subject}>
                    <div>
                      <strong>{exam.subject}</strong>
                      <span>{exam.date} at {exam.time}</span>
                      <small>{exam.venue}</small>
                    </div>
                    <span className={`pill ${exam.verified ? "safe" : "watch"}`}>
                      {exam.verified ? "Verified" : "Confirm"}
                    </span>
                  </article>
                ))
              )}
            </div>
          </section>

          <section className="panel" id="assignments">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Google Classroom</p>
                <h3>Assignments</h3>
              </div>
            </div>
            <div className="stack">
              {liveAssignments.map((assignment) => (
                <article className="list-item" key={assignment.title}>
                  <div>
                    <strong>{assignment.title}</strong>
                    <span>{assignment.course}</span>
                    <small>{assignment.due} · {assignment.source}</small>
                  </div>
                  <span className={`pill ${statusClass(assignment.state)}`}>
                    {assignment.state}
                  </span>
                </article>
              ))}
            </div>
          </section>

          <section className="panel" id="briefing">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Discord digest</p>
                <h3>Daily briefing</h3>
              </div>
            </div>
            <div className="briefing">
              <p>Attend DBMS next. It is closest to the 75% threshold.</p>
              <p>Finish the OS case study before dinner to avoid a late-night rush.</p>
              <p>Confirm the CN exam schedule because the source is not verified.</p>
            </div>
          </section>
        </section>

        <section className="panel exam-upload-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Latest schedule check</p>
              <h3>Upload exam schedule</h3>
            </div>
          </div>
          <div className="file-upload-row">
            <label>
              PDF schedule
              <input
                type="file"
                accept="application/pdf"
                onChange={(event) => setExamPdfFile(event.target.files?.[0] || null)}
              />
            </label>
            <button type="button" onClick={uploadExamPdf}>
              Extract from PDF
            </button>
          </div>
          <p className="upload-message">{examUploadMessage}</p>
        </section>

        <section className="bottom-grid">
          <section className="panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Campus updates</p>
                <h3>Important summaries</h3>
              </div>
            </div>
            <div className="update-list">
              {updates.map((update) => (
                <p key={update}>{update}</p>
              ))}
            </div>
          </section>

          <section className="panel ask-panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Grounded AI answer</p>
                <h3>Ask CampusFlow</h3>
              </div>
            </div>
            <div className="question-box">
              <span>Question</span>
              <strong>Can I skip tomorrow&apos;s DBMS class?</strong>
            </div>
            <p className="answer">
              You should attend. DBMS is at 76.9%, which leaves only 0 safe bunks
              before falling below 75%. Source: attendance tracker and confirmed
              timetable.
            </p>
          </section>
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Audit trail</p>
              <h3>Human feedback events</h3>
            </div>
            <span className="threshold">{attendanceEvents.length} saved</span>
          </div>
          <div className="event-list">
            {attendanceEvents.length === 0 ? (
              <p className="empty-state">
                No feedback events yet. Send a Discord prompt and click a button to
                create the first saved event.
              </p>
            ) : (
              attendanceEvents.slice(0, 8).map((event) => (
                <article className="event-row" key={event.event_id}>
                  <div>
                    <strong>{event.subject_code}</strong>
                    <span>
                      {event.class_status.replace("_", " ")}
                      {event.class_status === "held"
                        ? event.attended
                          ? " · attended"
                          : " · missed"
                        : ""}
                    </span>
                  </div>
                  <span className="event-source">{event.source.replace("_", " ")}</span>
                  <time>{new Date(event.created_at).toLocaleString()}</time>
                </article>
              ))
            )}
          </div>
        </section>
      </section>
    </main>
  );
}
