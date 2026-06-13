"use client";

import { useEffect, useMemo, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000/api/v1";

const weekdays = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

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
  const percent = Number.isFinite(Number(subject.attendance_percent))
    ? Number(subject.attendance_percent)
    : 100;
  const held = Number(subject.held_classes ?? 0);
  const attended = Number(subject.attended_classes ?? 0);
  const classHours = Number(subject.class_hours ?? 1) || 1;
  const plannedHours = Number(subject.planned_hours ?? 100) || 100;
  const providedPlannedClasses = Number(subject.planned_classes);
  const plannedClasses =
    Number.isFinite(providedPlannedClasses) && providedPlannedClasses > 0
      ? providedPlannedClasses
      : Math.max(1, Math.floor(plannedHours / classHours));
  const missedClasses = Number(subject.missed_classes ?? Math.max(0, held - attended));
  const missedHours = Number(subject.missed_hours ?? missedClasses * classHours);
  const providedBunkBudget = Number(subject.bunk_budget);
  const bunkBudget =
    Number.isFinite(providedBunkBudget)
      ? providedBunkBudget
      : Math.max(0, Math.floor((plannedHours * 0.25 - missedHours) / classHours));
  const status = subject.status || "safe";

  return {
    code: subject.code,
    name: subject.name,
    faculty: subject.faculty,
    held,
    attended,
    nextClass: subject.next_class,
    percent,
    bunkBudget,
    classesNeeded: Number(subject.classes_needed ?? 0),
    heldClasses: held,
    missedClasses,
    plannedClasses,
    classHours,
    plannedHours,
    missedHours,
    state: status.charAt(0).toUpperCase() + status.slice(1),
  };
}

function getAttendance(subject, threshold) {
  const percent = subject.held
    ? Number(((subject.attended / subject.held) * 100).toFixed(1))
    : 100;
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

  return {
    percent,
    bunkBudget,
    classesNeeded,
    heldClasses: subject.held,
    missedClasses: Math.max(0, subject.held - subject.attended),
    plannedClasses: 100,
    classHours: 1,
    plannedHours: 100,
    missedHours: Math.max(0, subject.held - subject.attended),
    state,
  };
}

function statusClass(value) {
  return String(value || "safe").toLowerCase();
}

function formatNextTimetableClass(entry, startsAt) {
  if (!entry) return "No upcoming class";
  const room = entry.room ? ` · ${entry.room}` : "";
  const dateLabel = startsAt
    ? new Date(startsAt).toLocaleDateString("en-IN", {
        weekday: "short",
        month: "short",
        day: "numeric",
      })
    : entry.weekday;
  return `${entry.subject_code} · ${dateLabel} · ${entry.start_time}-${entry.end_time}${room}`;
}

export default function Home() {
  const threshold = 75;
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
  const [timetable, setTimetable] = useState(null);
  const [timetablePdfFile, setTimetablePdfFile] = useState(null);
  const [timetableUploadMessage, setTimetableUploadMessage] = useState(
    "Upload your semester timetable PDF to replace demo attendance subjects.",
  );
  const [timetableUploadStatus, setTimetableUploadStatus] = useState("idle");
  const [isTimetableUploading, setIsTimetableUploading] = useState(false);

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

  const timetableByDay = useMemo(() => {
    const grouped = new Map(weekdays.map((weekday) => [weekday, []]));
    (timetable?.entries || []).forEach((entry) => {
      grouped.get(entry.weekday)?.push(entry);
    });
    return weekdays
      .map((weekday) => ({
        weekday,
        classes: grouped.get(weekday) || [],
      }))
      .filter((item) => item.classes.length);
  }, [timetable]);

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
  const todayClassCount = timetable?.today_count ?? 0;
  const nextClassLabel = formatNextTimetableClass(
    timetable?.next_class,
    timetable?.next_class_starts_at,
  );

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

    await fetch(`${API_BASE}/campusflow/timetable`)
      .then((response) => response.json())
      .then(setTimetable)
      .catch(() => setTimetable(null));
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

  async function runScheduledDiscordPrompts() {
    const response = await fetch(
      `${API_BASE}/integrations/discord/scheduled-feedback/run-today`,
      { method: "POST" },
    );
    const data = await response.json();
    if (!response.ok) {
      setIntegrationMessage(data.detail || "Discord scheduled prompt run failed.");
      return;
    }
    setIntegrationMessage(
      `${data.sent} daily Discord message sent for ${data.attempted} class${data.attempted === 1 ? "" : "es"}. ${data.messages.join(" ")}`,
    );
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

  async function uploadTimetablePdf() {
    if (!timetablePdfFile) {
      setTimetableUploadMessage("Choose a semester timetable PDF first.");
      setTimetableUploadStatus("error");
      return;
    }

    setIsTimetableUploading(true);
    setTimetableUploadStatus("loading");
    setTimetableUploadMessage("Extracting classes from timetable PDF...");
    const formData = new FormData();
    formData.append("file", timetablePdfFile);

    try {
      const response = await fetch(`${API_BASE}/campusflow/timetable/upload-pdf`, {
        method: "POST",
        body: formData,
      });
      const data = await response.json();
      if (!response.ok) {
        setTimetableUploadStatus("error");
        setTimetableUploadMessage(data.detail || "Semester timetable upload failed.");
        return;
      }
      if (!data.entries?.length) {
        setTimetableUploadStatus("error");
        setTimetableUploadMessage(
          data.message || "Could not find class rows in this timetable PDF.",
        );
        return;
      }
      setTimetableUploadStatus("success");
      setTimetableUploadMessage(data.message);
      refreshCampusFlowData();
    } catch {
      setTimetableUploadStatus("error");
      setTimetableUploadMessage(
        "Could not reach the backend while uploading the timetable PDF.",
      );
    } finally {
      setIsTimetableUploading(false);
    }
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
          <a href="#timetable">Timetable</a>
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
            <span>Today&apos;s classes</span>
            <strong>{todayClassCount}</strong>
            <p>{timetable?.has_uploaded_timetable ? "from uploaded timetable" : "demo timetable fallback"}</p>
          </div>
          <div className="metric">
            <span>Next class</span>
            <strong>{timetable?.next_class?.subject_code || "None"}</strong>
            <p>{nextClassLabel}</p>
          </div>
        </section>

        <section className="panel timetable-panel" id="timetable">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Semester timetable</p>
              <h3>PDF upload and weekly classes</h3>
            </div>
            <span className="threshold">
              {timetable?.has_uploaded_timetable ? "Uploaded" : "Demo fallback"}
            </span>
          </div>
          <div className="file-upload-row">
            <label>
              Semester timetable PDF
              <input
                type="file"
                accept="application/pdf"
                onChange={(event) => setTimetablePdfFile(event.target.files?.[0] || null)}
              />
            </label>
            <button
              type="button"
              onClick={uploadTimetablePdf}
              disabled={isTimetableUploading}
            >
              {isTimetableUploading ? "Extracting..." : "Extract timetable"}
            </button>
          </div>
          <p className={`upload-message ${timetableUploadStatus}`}>
            {timetableUploadMessage}
          </p>
          <div className="timetable-summary">
            <div>
              <span>Today</span>
              <strong>{todayClassCount} class{todayClassCount === 1 ? "" : "es"}</strong>
            </div>
            <div>
              <span>Next</span>
              <strong>{nextClassLabel}</strong>
            </div>
          </div>
          <div className="weekly-timetable">
            {timetableByDay.length === 0 ? (
              <p className="empty-state">
                No timetable classes loaded yet.
              </p>
            ) : (
              timetableByDay.map((day) => (
                <article className="day-column" key={day.weekday}>
                  <div className="day-header">
                    <strong>{day.weekday}</strong>
                    <span>{day.classes.length}</span>
                  </div>
                  {day.classes.map((entry, index) => (
                    <div
                      className="class-slot"
                      key={`${entry.weekday}-${entry.start_time}-${entry.end_time}-${entry.subject_code}-${entry.room || "room"}-${index}`}
                    >
                      <strong>{entry.subject_code}</strong>
                      <span>{entry.start_time}-{entry.end_time}</span>
                      <small>{entry.subject_name}</small>
                      <small>{entry.faculty || "Faculty TBA"}{entry.room ? ` · ${entry.room}` : ""}</small>
                    </div>
                  ))}
                </article>
              ))
            )}
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
              {attendance.map((subject) => {
                const progressWidth = Math.max(
                  0,
                  Math.min(100, Number(subject.percent) || 0)
                );

                return (
                  <article className="subject-row" key={subject.code}>
                    <div>
                      <strong>{subject.code}</strong>
                      <span>{subject.name}</span>
                    </div>
                    <div className="progress-wrap" aria-label={`${subject.code} attendance`}>
                      <span
                        className={`progress ${statusClass(subject.state)}`}
                        style={{ width: `${progressWidth}%` }}
                      />
                    </div>
                    <div className="subject-stats">
                      <strong>{subject.percent}%</strong>
                      <span>
                        {subject.heldClasses} / {subject.plannedClasses} classes
                      </span>
                    </div>
                    <span className={`pill ${statusClass(subject.state)}`}>
                      {subject.state}
                    </span>
                    <div className="bunk">
                      <strong>{subject.bunkBudget}</strong>
                      <span>bunks left</span>
                    </div>
                  </article>
                );
              })}
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
            <button type="button" onClick={runScheduledDiscordPrompts}>
              Run today&apos;s prompt
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
                No feedback events yet. Run today&apos;s prompt and click a Discord button to
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
