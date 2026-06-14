"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

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

function formatExamMetric(exam) {
  if (!exam) return "Upload exam schedule PDF";
  const date = new Date(`${exam.date}T00:00:00`);
  const dateLabel = Number.isNaN(date.getTime())
    ? exam.date
    : date.toLocaleDateString("en-IN", {
        weekday: "short",
        month: "short",
        day: "numeric",
      });
  const venue = exam.venue ? ` · ${exam.venue}` : "";
  return `${dateLabel} · ${exam.time}${venue}`;
}

function compactSubjectCode(subjectName, attendance = []) {
  if (!subjectName) return "None";
  const normalized = subjectName.toLowerCase();
  const liveMatch = attendance.find((subject) => {
    const subjectLabel = subject.name?.toLowerCase();
    return subjectLabel && (subjectLabel === normalized || normalized.includes(subjectLabel));
  });
  if (liveMatch?.code) return liveMatch.code;

  const fallbackMatch = subjects.find(
    (subject) =>
      subject.name.toLowerCase() === normalized ||
      normalized.includes(subject.name.toLowerCase())
  );
  if (fallbackMatch?.code) return fallbackMatch.code;

  return subjectName
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => word[0])
    .join("")
    .slice(0, 6)
    .toUpperCase();
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
  const [briefingMessage, setBriefingMessage] = useState(
    "Ready to send attendance, work, classes, next exam, and next class to Discord.",
  );
  const [isBriefingSending, setIsBriefingSending] = useState(false);
  const [processCollegeId, setProcessCollegeId] = useState("default");
  const [policyPdfFile, setPolicyPdfFile] = useState(null);
  const [policyUploadMessage, setPolicyUploadMessage] = useState(
    "Upload a campus policy PDF before asking process questions.",
  );
  const [policyUploadStatus, setPolicyUploadStatus] = useState("idle");
  const [isPolicyUploading, setIsPolicyUploading] = useState(false);
  const [relayStudentName, setRelayStudentName] = useState("");
  const [relayStudentEmail, setRelayStudentEmail] = useState("");
  const [relaySubject, setRelaySubject] = useState("");
  const [relayAttachedDocs, setRelayAttachedDocs] = useState("");
  const [relayIssue, setRelayIssue] = useState(
    "I missed my DBMS exam because I was sick.",
  );
  const [relayCase, setRelayCase] = useState(null);
  const [relayCases, setRelayCases] = useState([]);
  const [relayMessage, setRelayMessage] = useState("");
  const [relayStatus, setRelayStatus] = useState("idle");
  const [isCreatingCase, setIsCreatingCase] = useState(false);
  const [isSendingCase, setIsSendingCase] = useState(false);
  const [replyMessage, setReplyMessage] = useState("");
  const [isAddingReply, setIsAddingReply] = useState(false);
  const [isSendingFollowUp, setIsSendingFollowUp] = useState(false);
  const [updatingTaskId, setUpdatingTaskId] = useState(null);
  const [campusQuestion, setCampusQuestion] = useState(
    "Can I participate in a college event tomorrow?",
  );
  const [campusAnswer, setCampusAnswer] = useState(null);
  const [isAskingCampusFlow, setIsAskingCampusFlow] = useState(false);

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
  const nextExam = liveExams[0];
  const nextExamCode = compactSubjectCode(nextExam?.subject, attendance);
  const nextExamLabel = formatExamMetric(nextExam);
  const briefing = overview?.briefing;
  const briefingItems = briefing
    ? [
        ...briefing.alerts,
        ...briefing.schedule,
        ...briefing.suggestions,
      ].slice(0, 6)
    : [
        "Attendance, assignments, classes, and exam reminders will appear after live data loads.",
      ];

  const loadProcessCases = useCallback(async () => {
    const query = new URLSearchParams({
      college_id: processCollegeId || "default",
    });
    try {
      const response = await fetch(
        `${API_BASE}/campusflow/process-copilot/cases?${query.toString()}`,
      );
      if (!response.ok) {
        setRelayCases([]);
        return;
      }
      const data = await response.json();
      setRelayCases(Array.isArray(data) ? data : []);
    } catch {
      setRelayCases([]);
    }
  }, [processCollegeId]);

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

  useEffect(() => {
    const query = new URLSearchParams({
      college_id: processCollegeId || "default",
    });
    fetch(`${API_BASE}/campusflow/process-copilot/cases?${query.toString()}`)
      .then((response) => {
        if (!response.ok) return [];
        return response.json();
      })
      .then((data) => {
        setRelayCases(Array.isArray(data) ? data : []);
      })
      .catch(() => setRelayCases([]));
  }, [processCollegeId]);

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

  async function sendBriefing() {
    setIsBriefingSending(true);
    setBriefingMessage("Sending briefing to Discord...");
    try {
      const response = await fetch(`${API_BASE}/integrations/discord/briefing`, {
        method: "POST",
      });
      const data = await response.json();
      if (!response.ok) {
        setBriefingMessage(data.detail || "Discord briefing failed.");
        return;
      }
      setBriefingMessage(data.message);
    } catch {
      setBriefingMessage("Could not reach the backend while sending the briefing.");
    } finally {
      setIsBriefingSending(false);
    }
  }

  async function askCampusFlow() {
    if (!campusQuestion.trim()) {
      setCampusAnswer({
        answer: "Ask a question first.",
        sources: [],
        confidence: "low",
      });
      return;
    }

    setIsAskingCampusFlow(true);
    try {
      const response = await fetch(`${API_BASE}/campusflow/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: campusQuestion }),
      });
      const data = await response.json();
      if (!response.ok) {
        setCampusAnswer({
          answer: data.detail || "CampusFlow could not answer that question.",
          sources: [],
          confidence: "low",
        });
        return;
      }
      setCampusAnswer(data);
    } catch {
      setCampusAnswer({
        answer: "Could not reach the backend while asking CampusFlow.",
        sources: [],
        confidence: "low",
      });
    } finally {
      setIsAskingCampusFlow(false);
    }
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

  async function uploadPolicyPdf() {
    if (!policyPdfFile) {
      setPolicyUploadStatus("error");
      setPolicyUploadMessage("Choose a campus policy PDF first.");
      return;
    }

    setIsPolicyUploading(true);
    setPolicyUploadStatus("loading");
    setPolicyUploadMessage("Extracting campus policy text...");
    const formData = new FormData();
    formData.append("file", policyPdfFile);
    formData.append("college_id", processCollegeId || "default");

    try {
      const response = await fetch(`${API_BASE}/campusflow/process-copilot/upload-policy`, {
        method: "POST",
        body: formData,
      });
      const data = await response.json();
      if (!response.ok) {
        setPolicyUploadStatus("error");
        setPolicyUploadMessage(data.detail || "Campus policy upload failed.");
        return;
      }
      setPolicyUploadStatus("success");
      setPolicyUploadMessage(data.message);
    } catch {
      setPolicyUploadStatus("error");
      setPolicyUploadMessage("Could not reach the backend while uploading the policy PDF.");
    } finally {
      setIsPolicyUploading(false);
    }
  }

  function attachedDocumentNames() {
    return relayAttachedDocs
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }

  async function createRelayCase() {
    if (!relayIssue.trim()) {
      setRelayStatus("error");
      setRelayMessage("Enter the student issue before creating a case.");
      return;
    }

    setIsCreatingCase(true);
    setRelayStatus("loading");
    setRelayMessage("Creating campus request draft...");
    try {
      const response = await fetch(`${API_BASE}/campusflow/process-copilot/cases`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          college_id: processCollegeId || "default",
          student_name: relayStudentName || null,
          student_email: relayStudentEmail || null,
          student_issue: relayIssue,
          course_or_subject: relaySubject || null,
          attached_document_names: attachedDocumentNames(),
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        setRelayStatus("error");
        setRelayMessage(data.detail || "Could not create process case.");
        return;
      }
      setRelayCase(data);
      setRelayStatus("success");
      setRelayMessage(data.action_message || "Draft case created.");
      await loadProcessCases();
    } catch {
      setRelayStatus("error");
      setRelayMessage("Could not reach the backend while creating the case.");
    } finally {
      setIsCreatingCase(false);
    }
  }

  async function sendRelayCase() {
    if (!relayCase?.case_id) return;
    setIsSendingCase(true);
    setRelayStatus("loading");
    setRelayMessage(
      relayCase.delivery_mode === "email"
        ? "Sending request to routed office..."
        : "Queueing request locally...",
    );
    try {
      const response = await fetch(
        `${API_BASE}/campusflow/process-copilot/cases/${relayCase.case_id}/send`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ student_approved: true }),
        },
      );
      const data = await response.json();
      if (!response.ok) {
        setRelayStatus("error");
        setRelayMessage(data.detail || "Could not queue request.");
        return;
      }
      setRelayCase(data);
      setRelayStatus("success");
      setRelayMessage(data.action_message || "Request updated.");
      await loadProcessCases();
    } catch {
      setRelayStatus("error");
      setRelayMessage("Could not reach the backend while sending the request.");
    } finally {
      setIsSendingCase(false);
    }
  }

  async function addRelayReply() {
    if (!relayCase?.case_id || !replyMessage.trim()) {
      setRelayStatus("error");
      setRelayMessage("Open a case and enter an office reply first.");
      return;
    }

    setIsAddingReply(true);
    setRelayStatus("loading");
    setRelayMessage("Adding simulated office reply...");
    try {
      const response = await fetch(
        `${API_BASE}/campusflow/process-copilot/cases/${relayCase.case_id}/reply`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            reply_from: relayCase.routed_to_office,
            reply_message: replyMessage,
          }),
        },
      );
      const data = await response.json();
      if (!response.ok) {
        setRelayStatus("error");
        setRelayMessage(data.detail || "Could not add office reply.");
        return;
      }
      setRelayCase(data);
      setReplyMessage("");
      setRelayStatus("success");
      setRelayMessage(data.action_message || "Office reply added.");
      await loadProcessCases();
    } catch {
      setRelayStatus("error");
      setRelayMessage("Could not reach the backend while adding the reply.");
    } finally {
      setIsAddingReply(false);
    }
  }

  async function sendRelayFollowUp() {
    if (!relayCase?.case_id) return;
    setIsSendingFollowUp(true);
    setRelayStatus("loading");
    setRelayMessage("Preparing follow-up...");
    try {
      const response = await fetch(
        `${API_BASE}/campusflow/process-copilot/cases/${relayCase.case_id}/follow-up`,
        { method: "POST" },
      );
      const data = await response.json();
      if (!response.ok) {
        setRelayStatus("error");
        setRelayMessage(data.detail || "Could not send follow-up.");
        return;
      }
      setRelayCase(data);
      setRelayStatus("success");
      setRelayMessage(data.action_message || "Follow-up updated.");
      await loadProcessCases();
    } catch {
      setRelayStatus("error");
      setRelayMessage("Could not reach the backend while sending follow-up.");
    } finally {
      setIsSendingFollowUp(false);
    }
  }

  async function updateRelayTask(taskId, done) {
    if (!relayCase?.case_id) return;
    setUpdatingTaskId(taskId);
    setRelayStatus("loading");
    setRelayMessage("Updating checklist...");
    try {
      const response = await fetch(
        `${API_BASE}/campusflow/process-copilot/cases/${relayCase.case_id}/tasks/${taskId}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ done }),
        },
      );
      const data = await response.json();
      if (!response.ok) {
        setRelayStatus("error");
        setRelayMessage(data.detail || "Could not update task.");
        return;
      }
      setRelayCase(data);
      setRelayStatus("success");
      setRelayMessage(data.action_message || "Task updated.");
      await loadProcessCases();
    } catch {
      setRelayStatus("error");
      setRelayMessage("Could not reach the backend while updating the task.");
    } finally {
      setUpdatingTaskId(null);
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
          <a href="#process-copilot">Process Relay</a>
          <a href="#exams">Exams</a>
          <a href="#assignments">Assignments</a>
          <a href="#briefing">Briefing</a>
          <button type="button" onClick={() => window.location.assign("/campusbuddy")}>
            CampusBuddy AI
          </button>
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
          <button
            type="button"
            className="primary-button"
            onClick={sendBriefing}
            disabled={isBriefingSending}
          >
            {isBriefingSending ? "Sending..." : "Send briefing"}
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
          <div className="metric">
            <span>Next exam</span>
            <strong>{nextExamCode}</strong>
            <p>{nextExamLabel}</p>
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

        <section className="panel process-copilot-panel" id="process-copilot">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Campus helpdesk AI</p>
              <h3>Campus Process Relay</h3>
            </div>
            <span className="threshold">{processCollegeId || "default"}</span>
          </div>
          <p className="relay-feature-note">
            Campus Process Relay turns a student issue into a routed campus case,
            drafts the official request, tracks office replies, and updates the
            student&apos;s next action.
          </p>
          <div className="relay-workspace">
            <div className="relay-create-card">
              <h4>Create process case</h4>
              <label>
                College ID
                <input
                  type="text"
                  value={processCollegeId}
                  onChange={(event) => setProcessCollegeId(event.target.value)}
                  placeholder="default"
                />
              </label>
              <div className="file-upload-row">
                <label>
                  Campus policy PDF
                  <input
                    type="file"
                    accept="application/pdf"
                    onChange={(event) => setPolicyPdfFile(event.target.files?.[0] || null)}
                  />
                </label>
                <button
                  type="button"
                  onClick={uploadPolicyPdf}
                  disabled={isPolicyUploading}
                >
                  {isPolicyUploading ? "Uploading..." : "Upload policy PDF"}
                </button>
              </div>
              <p className={`upload-message ${policyUploadStatus}`}>
                {policyUploadMessage}
              </p>
              <label>
                Describe your campus problem
                <textarea
                  value={relayIssue}
                  onChange={(event) => setRelayIssue(event.target.value)}
                  placeholder="I missed my DBMS exam because I was sick."
                  rows={5}
                />
              </label>
              <div className="relay-inline-fields">
                <label>
                  Student name
                  <input
                    type="text"
                    value={relayStudentName}
                    onChange={(event) => setRelayStudentName(event.target.value)}
                    placeholder="Optional"
                  />
                </label>
                <label>
                  Student email
                  <input
                    type="email"
                    value={relayStudentEmail}
                    onChange={(event) => setRelayStudentEmail(event.target.value)}
                    placeholder="Optional"
                  />
                </label>
                <label>
                  Subject/course
                  <input
                    type="text"
                    value={relaySubject}
                    onChange={(event) => setRelaySubject(event.target.value)}
                    placeholder="DBMS, attendance, hostel"
                  />
                </label>
              </div>
              <label>
                Attached document names
                <input
                  type="text"
                  value={relayAttachedDocs}
                  onChange={(event) => setRelayAttachedDocs(event.target.value)}
                  placeholder="medical_certificate.pdf, exam_form.pdf"
                />
              </label>
              <button
                type="button"
                className="primary-button process-ask-button"
                onClick={createRelayCase}
                disabled={isCreatingCase}
              >
                {isCreatingCase ? "Creating..." : "Create Process Case"}
              </button>
              {relayMessage ? (
                <p className={`upload-message ${relayStatus}`}>{relayMessage}</p>
              ) : null}
            </div>

            <div className="relay-case-card">
              {relayCase ? (
                <>
                  <div className="relay-case-title">
                    <div>
                      <p className="eyebrow">{relayCase.issue_type}</p>
                      <h4>{relayCase.summary}</h4>
                    </div>
                    <span className={`case-status ${statusClass(relayCase.status)}`}>
                      {relayCase.status}
                    </span>
                  </div>
                  <div className="process-mode-row">
                    <span
                      className={`mode-note ${
                        relayCase.llm_used && relayCase.llm_provider === "gemini"
                          ? "gemini"
                          : "fallback"
                      }`}
                    >
                      {relayCase.llm_used && relayCase.llm_provider === "gemini"
                        ? "Gemini relay"
                        : "Fallback relay"}
                    </span>
                    <span className="process-college">
                      Confidence {relayCase.confidence}
                    </span>
                  </div>
                  {relayCase.fallback_mode && relayCase.llm_error ? (
                    <p className="llm-error">{relayCase.llm_error}</p>
                  ) : null}

                  <div className="process-meta">
                    <div>
                      <span>Routed office</span>
                      <strong>{relayCase.routed_to_office}</strong>
                      {relayCase.routed_to_email ? (
                        <small>{relayCase.routed_to_email}</small>
                      ) : null}
                    </div>
                    <div>
                      <span>Delivery mode</span>
                      <strong>
                        {relayCase.delivery_mode === "email" ? "Email enabled" : "Queue mode"}
                      </strong>
                      <small>
                        {relayCase.delivery_mode === "email"
                          ? `Email enabled: this request will be sent to ${relayCase.routed_to_email || "the routed office email"}.`
                          : "Email disabled: request will be queued locally. In production, SMTP sends this to the routed office."}
                      </small>
                    </div>
                    <div>
                      <span>Deadline/timeline</span>
                      <strong>{relayCase.deadline_or_timeline || "Not found in policy"}</strong>
                    </div>
                  </div>

                  {relayCase.required_documents?.length ? (
                    <div className="process-block">
                      <span>Required documents</span>
                      <div className="document-chip-list">
                        {relayCase.required_documents.map((document, index) => (
                          <span className="document-chip" key={`relay-doc-${index}`}>
                            {document}
                          </span>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  <div className="process-block">
                    <span>Request sent to office</span>
                    <p className="relay-note">
                      This is the message sent to the routed office, not to the student.
                    </p>
                    <strong>{relayCase.generated_message_subject}</strong>
                    <pre>{relayCase.generated_message_body}</pre>
                  </div>

                  {relayCase.student_next_action ? (
                    <div className="process-block">
                      <span>Student next action</span>
                      <p className="relay-next-action">{relayCase.student_next_action}</p>
                    </div>
                  ) : null}

                  {relayCase.tasks?.length ? (
                    <div className="process-block">
                      <span>Checklist</span>
                      <div className="relay-task-list">
                        {relayCase.tasks.map((task, index) => (
                          <label key={`relay-task-${index}`}>
                            <input
                              type="checkbox"
                              checked={Boolean(task.done)}
                              disabled={updatingTaskId === task.task_id}
                              onChange={(event) =>
                                updateRelayTask(task.task_id, event.target.checked)
                              }
                            />
                            {task.title}
                          </label>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {relayCase.timeline?.length ? (
                    <div className="process-block">
                      <span>Case timeline</span>
                      <div className="relay-timeline">
                        {relayCase.timeline.map((event, index) => (
                          <div className="relay-timeline-item" key={`relay-event-${index}`}>
                            <strong>{event.title}</strong>
                            {event.message ? <small>{event.message}</small> : null}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  <div className="relay-action-row">
                    <button
                      type="button"
                      className="primary-button process-ask-button"
                      onClick={sendRelayCase}
                      disabled={isSendingCase || relayCase.status !== "draft"}
                    >
                      {isSendingCase
                        ? relayCase.delivery_mode === "email"
                          ? "Sending..."
                          : "Queueing..."
                        : relayCase.delivery_mode === "email"
                          ? "Send Request to Office"
                          : "Queue Request"}
                    </button>
                    <button
                      type="button"
                      onClick={sendRelayFollowUp}
                      disabled={isSendingFollowUp}
                    >
                      {isSendingFollowUp ? "Sending..." : "Send Follow-up"}
                    </button>
                  </div>
                  {relayCase.last_student_notification ? (
                    <p className="relay-next-action">{relayCase.last_student_notification}</p>
                  ) : null}

                  <div className="process-block">
                    <span>Simulate / Add Office Reply</span>
                    <p className="relay-note">
                      Production replies can be matched from email by case ID; use this box
                      to simulate an office reply during testing.
                    </p>
                    <textarea
                      value={replyMessage}
                      onChange={(event) => setReplyMessage(event.target.value)}
                      placeholder="Paste office reply"
                      rows={3}
                    />
                    <button
                      type="button"
                      onClick={addRelayReply}
                      disabled={isAddingReply}
                    >
                      {isAddingReply ? "Adding..." : "Add Office Reply"}
                    </button>
                    {relayCase.office_reply ? (
                      <p className="answer">{relayCase.office_reply}</p>
                    ) : null}
                    {relayCase.reply_outcome ? (
                      <small>Outcome: {relayCase.reply_outcome}</small>
                    ) : null}
                  </div>

                  {relayCase.sources_used?.length ? (
                    <details className="process-block source-details">
                      <summary>Sources used</summary>
                      <ul>
                        {relayCase.sources_used.map((source, index) => (
                          <li key={`relay-source-${index}`}>{source}</li>
                        ))}
                      </ul>
                    </details>
                  ) : null}
                </>
              ) : (
                <p className="empty-state">
                  Create a case to draft, queue, and track a campus request.
                </p>
              )}
            </div>

            <div className="relay-case-list">
              <div className="relay-case-list-header">
                <h4>My cases</h4>
                <button type="button" onClick={loadProcessCases}>
                  Refresh
                </button>
              </div>
              {relayCases.length ? (
                relayCases.map((item, index) => (
                  <button
                    type="button"
                    className="case-list-item"
                    key={`policy-case-${index}`}
                    onClick={() => {
                      setRelayCase(item);
                      setReplyMessage("");
                      setRelayStatus("success");
                      setRelayMessage("Case opened.");
                    }}
                  >
                    <span>{item.issue_type}</span>
                    <strong>{item.routed_to_office}</strong>
                    <small>{item.status}</small>
                  </button>
                ))
              ) : (
                <p className="empty-state">No process cases yet.</p>
              )}
            </div>
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
              <p className="live-note">{briefingMessage}</p>
              {briefingItems.map((item) => (
                <p key={item}>{item}</p>
              ))}
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

        <section className="panel ask-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Grounded AI answer</p>
              <h3>Ask CampusFlow</h3>
            </div>
            <span className="threshold">
              {campusAnswer ? campusAnswer.confidence : "Context aware"}
            </span>
          </div>
          <label>
            Question
            <textarea
              value={campusQuestion}
              onChange={(event) => setCampusQuestion(event.target.value)}
              rows={3}
              placeholder="Ask about exams, next classes, attendance, assignments, or whether you can attend an event."
            />
          </label>
          <button
            type="button"
            className="primary-button ask-button"
            onClick={askCampusFlow}
            disabled={isAskingCampusFlow}
          >
            {isAskingCampusFlow ? "Thinking..." : "Ask CampusFlow"}
          </button>
          {campusAnswer ? (
            <div className="question-box">
              <span>Answer</span>
              <strong>{campusAnswer.answer}</strong>
              {campusAnswer.sources?.length ? (
                <small>Sources: {campusAnswer.sources.join(", ")}</small>
              ) : null}
            </div>
          ) : (
            <p className="answer">
              Ask whether you can attend a college event, skip a class, prepare for an exam,
              or prioritize pending work. CampusFlow will answer using your live attendance,
              timetable, exams, and assignments.
            </p>
          )}
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
