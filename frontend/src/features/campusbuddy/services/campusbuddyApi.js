const API_BASE_URL =
  process.env.NEXT_PUBLIC_CAMPUSBUDDY_API_BASE_URL || "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}/api/campusbuddy${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    throw new Error(`CampusBuddy request failed: ${response.status}`);
  }

  return response.json();
}

export const campusbuddyApi = {
  chat: (message, studentId = "student_001") =>
    request("/chat", {
      method: "POST",
      body: JSON.stringify({ message, student_id: studentId }),
    }),
  trustDashboard: (studentId = "student_001") =>
    request(`/trust-dashboard?student_id=${encodeURIComponent(studentId)}`),
  remember: (label, memoryType = "Student-approved memory", usedFor = {}, studentId = "student_001") =>
    request("/memory", {
      method: "POST",
      body: JSON.stringify({ label, memory_type: memoryType, used_for: usedFor, student_id: studentId }),
    }),
  deleteMemory: (id, studentId = "student_001") =>
    request(`/memory/${id}?student_id=${encodeURIComponent(studentId)}`, {
      method: "DELETE",
    }),
  connect: (query, studentId = "student_001") =>
    request("/connect", {
      method: "POST",
      body: JSON.stringify({ query, student_id: studentId }),
    }),
  createConnectionRequest: ({ connectionId, requestMessage, topic, category, requesterUserId }) =>
    request("/connection-requests", {
      method: "POST",
      body: JSON.stringify({
        connection_id: connectionId,
        request_message: requestMessage,
        topic,
        category,
        requester_user_id: requesterUserId,
      }),
    }),
  connectionRequests: (userId) => request(`/connection-requests?user_id=${encodeURIComponent(userId)}`),
  respondConnectionRequest: (requestId, userId, action) =>
    request(`/connection-requests/${requestId}/respond`, {
      method: "POST",
      body: JSON.stringify({ user_id: userId, action }),
    }),
  giveRevealConsent: (requestId, userId) =>
    request(`/connection-requests/${requestId}/reveal-consent`, {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    }),
  groups: (studentId) =>
    request(studentId ? `/groups?student_id=${encodeURIComponent(studentId)}` : "/groups"),
  groupInvites: (studentId) => request(`/groups/invites?student_id=${encodeURIComponent(studentId)}`),
  joinGroup: (groupId, studentId) =>
    request(`/groups/${groupId}/join`, {
      method: "POST",
      body: JSON.stringify({ student_id: studentId }),
    }),
  ignoreGroup: (groupId, studentId) =>
    request(`/groups/${groupId}/ignore`, {
      method: "POST",
      body: JSON.stringify({ student_id: studentId }),
    }),
  committeeEscalation: (category, description) =>
    request("/committee-escalation", {
      method: "POST",
      body: JSON.stringify({ category, description }),
    }),
  submitComplaint: ({ studentId, complaintText }) =>
    request("/complaints", {
      method: "POST",
      body: JSON.stringify({ student_id: studentId, complaint_text: complaintText }),
    }),
  complaintEscalations: () => request("/complaints/escalations"),
  committeeDashboard: () => request("/committee-dashboard"),
};
