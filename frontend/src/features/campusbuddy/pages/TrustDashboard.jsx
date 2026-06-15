import { useEffect, useState } from "react";
import CampusBuddyHeader from "../components/CampusBuddyHeader.jsx";
import { campusbuddyApi } from "../services/campusbuddyApi.js";

const defaultUsedFor = {
  personalization: true,
  peer_matching: false,
  group_suggestions: true,
  anonymous_campus_insight: false,
};

export default function TrustDashboard({ currentUser }) {
  const [data, setData] = useState(null);
  const [memoryLabel, setMemoryLabel] = useState("I like badminton");
  const [memoryType, setMemoryType] = useState("Interest");
  const [usedFor, setUsedFor] = useState(defaultUsedFor);
  const [statusMessage, setStatusMessage] = useState("");
  const [error, setError] = useState("");

  const currentUserId = currentUser.userId;

  async function load(studentId = currentUserId) {
    if (!studentId) return;
    setError("");

    try {
      setData(await campusbuddyApi.trustDashboard(studentId));
    } catch (requestError) {
      setError("Could not load Trust Dashboard right now.");
    }
  }

  useEffect(() => {
    let isActive = true;

    if (!currentUserId) return undefined;

    campusbuddyApi
      .trustDashboard(currentUserId)
      .then((nextData) => {
        if (!isActive) return;
        setData(nextData);
        setError("");
      })
      .catch(() => {
        if (!isActive) return;
        setError("Could not load Trust Dashboard right now.");
      });

    return () => {
      isActive = false;
    };
  }, [currentUserId]);

  async function addMemory(event) {
    event.preventDefault();
    const trimmedLabel = memoryLabel.trim();
    if (!trimmedLabel) return;

    setStatusMessage("");
    setError("");

    try {
      const saved = await campusbuddyApi.remember(trimmedLabel, memoryType, usedFor, currentUserId);
      setStatusMessage(`Remembered for ${currentUser.name || currentUserId}: ${saved.label}`);
      setMemoryLabel("");
      await load(currentUserId);
    } catch (requestError) {
      setError("Could not save this memory right now.");
    }
  }

  async function remove(id) {
    setStatusMessage("");
    setError("");

    try {
      const result = await campusbuddyApi.deleteMemory(id, currentUserId);
      setStatusMessage(result.deleted ? "Memory deleted." : "Memory was not found for this student.");
      await load(currentUserId);
    } catch (requestError) {
      setError("Could not delete this memory right now.");
    }
  }

  function toggleUse(key) {
    setUsedFor((current) => ({
      ...current,
      [key]: !current[key],
    }));
  }

  return (
    <div>
      <CampusBuddyHeader eyebrow="Consent-Based Memory" title="Trust Dashboard">
        See what CampusBuddy remembers, what can be edited or deleted, and how each memory is used.
      </CampusBuddyHeader>

      <section className="cb-form">
        <p className="cb-small-note">
          Private Trust Dashboard for {currentUser.name || "the current user"}.
        </p>
      </section>

      <form className="cb-form cb-section" onSubmit={addMemory}>
        <div className="cb-inbox-header">
          <div>
            <span className="cb-eyebrow">Add Consent Memory</span>
            <h2>Remember only with permission</h2>
            <p className="cb-small-note">Use this to seed interests for group suggestions or personalize different students.</p>
          </div>
        </div>
        <input
          placeholder="Add an interest, preference, or goal..."
          value={memoryLabel}
          onChange={(event) => setMemoryLabel(event.target.value)}
        />
        <label className="cb-select-label cb-student-select">
          Memory type
          <select value={memoryType} onChange={(event) => setMemoryType(event.target.value)}>
            <option value="Interest">Interest</option>
            <option value="Student-approved memory">Student-approved memory</option>
            <option value="Privacy preference">Privacy preference</option>
          </select>
        </label>
        <div className="cb-usage">
          {Object.entries(usedFor).map(([key, value]) => (
            <button
              className={value ? "on" : "off"}
              key={key}
              onClick={() => toggleUse(key)}
              type="button"
            >
              {key.replaceAll("_", " ")}
            </button>
          ))}
        </div>
        <div className="cb-actions">
          <button className="cb-primary" type="submit">Remember for selected student</button>
        </div>
      </form>

      {error ? <div className="cb-success cb-alert">{error}</div> : null}
      {statusMessage ? <div className="cb-success">{statusMessage}</div> : null}

      {data ? (
        <section className="cb-grid">
          <article className="cb-card cb-wide">
            <h2>{data.student_alias}</h2>
            <p>{data.privacy_mode}</p>
            <p>Student must click Remember before data is saved.</p>
          </article>
          {data.memories.length ? (
            data.memories.map((memory) => (
              <article className="cb-card" key={memory.id}>
                <span className="cb-pill">{memory.type}</span>
                <h3>{memory.label}</h3>
                <div className="cb-usage">
                  {Object.entries(memory.used_for).map(([key, value]) => (
                    <span className={value ? "on" : "off"} key={key}>{key.replaceAll("_", " ")}</span>
                  ))}
                </div>
                <div className="cb-actions">
                  <button className="cb-secondary">Edit</button>
                  <button className="cb-secondary" onClick={() => remove(memory.id)} type="button">Delete</button>
                </div>
              </article>
            ))
          ) : (
            <article className="cb-card cb-wide">
              <h3>No memories for this student yet</h3>
              <p>Add a consent memory above to personalize CampusBuddy for this student.</p>
            </article>
          )}
        </section>
      ) : <div className="cb-card">Loading trust dashboard...</div>}
    </div>
  );
}
