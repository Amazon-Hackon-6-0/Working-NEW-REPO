const API_BASE_URL =
  process.env.NEXT_PUBLIC_CAMPUSBUDDY_API_BASE_URL || "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const { userId, ...fetchOptions } = options;
  const response = await fetch(`${API_BASE_URL}/api/campusbuddy${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(userId ? { "X-CampusBuddy-User-Id": userId } : {}),
      ...fetchOptions.headers,
    },
    ...fetchOptions,
  });

  if (!response.ok) {
    throw new Error(`CampusBuddy request failed: ${response.status}`);
  }

  return response.json();
}

export const campusbuddyApi = {
  chat: (message, studentId) =>
    request("/chat", {
      method: "POST",
      userId: studentId,
      body: JSON.stringify({ message, student_id: studentId }),
    }),
  trustDashboard: (studentId) =>
    request(`/trust-dashboard?student_id=${encodeURIComponent(studentId)}`, { userId: studentId }),
  remember: (label, memoryType = "Student-approved memory", usedFor = {}, studentId) =>
    request("/memory", {
      method: "POST",
      userId: studentId,
      body: JSON.stringify({ label, memory_type: memoryType, used_for: usedFor, student_id: studentId }),
    }),
  deleteMemory: (id, studentId) =>
    request(`/memory/${id}?student_id=${encodeURIComponent(studentId)}`, {
      method: "DELETE",
      userId: studentId,
    }),
  connect: (query, studentId) =>
    request("/connect", {
      method: "POST",
      userId: studentId,
      body: JSON.stringify({ query, student_id: studentId }),
    }),
  createConnectionRequest: ({ connectionId, requestMessage, topic, category, requesterUserId }) =>
    request("/connection-requests", {
      method: "POST",
      userId: requesterUserId,
      body: JSON.stringify({
        connection_id: connectionId,
        request_message: requestMessage,
        topic,
        category,
        requester_user_id: requesterUserId,
      }),
    }),
  connectionRequests: (userId) => request(`/connection-requests?user_id=${encodeURIComponent(userId)}`, { userId }),
  respondConnectionRequest: (requestId, userId, action) =>
    request(`/connection-requests/${requestId}/respond`, {
      method: "POST",
      userId,
      body: JSON.stringify({ user_id: userId, action }),
    }),
  giveRevealConsent: (requestId, userId) =>
    request(`/connection-requests/${requestId}/reveal-consent`, {
      method: "POST",
      userId,
      body: JSON.stringify({ user_id: userId }),
    }),
  groups: (studentId) =>
    request(studentId ? `/groups?student_id=${encodeURIComponent(studentId)}` : "/groups", { userId: studentId }),
  groupInvites: (studentId) => request(`/groups/invites?student_id=${encodeURIComponent(studentId)}`, { userId: studentId }),
  joinGroup: (groupId, studentId) =>
    request(`/groups/${groupId}/join`, {
      method: "POST",
      userId: studentId,
      body: JSON.stringify({ student_id: studentId }),
    }),
  ignoreGroup: (groupId, studentId) =>
    request(`/groups/${groupId}/ignore`, {
      method: "POST",
      userId: studentId,
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
      userId: studentId,
      body: JSON.stringify({ student_id: studentId, complaint_text: complaintText }),
    }),
  complaintEscalations: () => request("/complaints/escalations"),
  committeeDashboard: () => request("/committee-dashboard"),
};
