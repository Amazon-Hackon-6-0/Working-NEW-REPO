import { useEffect, useState } from "react";
import CampusBuddyHeader from "../components/CampusBuddyHeader.jsx";
import { campusbuddyApi } from "../services/campusbuddyApi.js";

export default function Groups({ currentUser }) {
  const [groups, setGroups] = useState([]);
  const [invites, setInvites] = useState([]);
  const [statusMessage, setStatusMessage] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [actingGroupId, setActingGroupId] = useState("");
  const currentUserId = currentUser.userId;

  async function loadGroups(studentId = currentUserId) {
    if (!studentId) return;
    setError("");
    setIsLoading(true);

    try {
      const response = await campusbuddyApi.groups(studentId);
      setGroups(response.groups || []);
    } catch (requestError) {
      setError("Could not load campus groups right now.");
    } finally {
      setIsLoading(false);
    }
  }

  async function loadInvites(studentId) {
    if (!studentId) return;
    setError("");

    try {
      const response = await campusbuddyApi.groupInvites(studentId);
      setInvites(response.invites || []);
    } catch (requestError) {
      setError("Could not load group invites right now.");
    }
  }

  useEffect(() => {
    let isActive = true;

    if (!currentUserId) return undefined;

    campusbuddyApi
      .groups(currentUserId)
      .then((response) => {
        if (!isActive) return;
        setGroups(response.groups || []);
        setError("");
      })
      .catch(() => {
        if (!isActive) return;
        setError("Could not load campus groups right now.");
      })
      .finally(() => {
        if (!isActive) return;
        setIsLoading(false);
      });

    return () => {
      isActive = false;
    };
  }, [currentUserId]);

  useEffect(() => {
    let isActive = true;

    if (!currentUserId) return undefined;

    campusbuddyApi
      .groupInvites(currentUserId)
      .then((response) => {
        if (!isActive) return;
        setInvites(response.invites || []);
        setError("");
      })
      .catch(() => {
        if (!isActive) return;
        setError("Could not load group invites right now.");
      });

    return () => {
      isActive = false;
    };
  }, [currentUserId]);

  async function joinGroup(groupId) {
    setStatusMessage("");
    setError("");
    setActingGroupId(groupId);

    try {
      const response = await campusbuddyApi.joinGroup(groupId, currentUserId);
      await loadInvites(currentUserId);
      await loadGroups(currentUserId);
      setStatusMessage(response.message || "Joined group.");
    } catch (requestError) {
      setError("Could not join this group right now.");
    } finally {
      setActingGroupId("");
    }
  }

  async function ignoreGroup(groupId) {
    setStatusMessage("");
    setError("");
    setActingGroupId(groupId);

    try {
      const response = await campusbuddyApi.ignoreGroup(groupId, currentUserId);
      await loadInvites(currentUserId);
      await loadGroups(currentUserId);
      setStatusMessage(response.message || "Invite ignored.");
    } catch (requestError) {
      setError("Could not ignore this invite right now.");
    } finally {
      setActingGroupId("");
    }
  }

  function formatSource(source) {
    if (!source) return "Not available";
    return source === "gemini" ? "Gemini" : "Fallback";
  }

  return (
    <div>
      <CampusBuddyHeader eyebrow="Interest-Based Group Formation" title="CampusBuddy Groups">
        Groups are formed from Trust Dashboard interests when enough students opt in for group suggestions. Students choose whether to join.
      </CampusBuddyHeader>

      <section className="cb-note">
        <strong>Privacy-first groups.</strong>
        <span>CampusBuddy shows group opportunities without exposing who added which interest. Joining is consent-based.</span>
      </section>

      <section className="cb-form">
        <p className="cb-small-note">
          Private group invites for {currentUser.name || "the current user"} are created from consented Trust Dashboard interests.
        </p>
      </section>

      {error ? <div className="cb-success cb-alert">{error}</div> : null}
      {statusMessage ? <div className="cb-success">{statusMessage}</div> : null}

      <section className="cb-section">
        <div className="cb-inbox-header">
          <div>
            <span className="cb-eyebrow">All Campus Groups</span>
            <h2>Available Opportunities</h2>
            <p className="cb-small-note">Only group-level information is shown here.</p>
          </div>
          <button className="cb-secondary" disabled={isLoading} onClick={() => loadGroups(currentUserId)} type="button">
            {isLoading ? "Loading..." : "Refresh groups"}
          </button>
        </div>

        {groups.length ? (
          <div className="cb-grid">
            {groups.map((group) => {
              const isActing = actingGroupId === group.group_id;
              const hasJoined = group.current_student_status === "joined";

              return (
                <article className="cb-card" key={group.group_id}>
                  <div className="cb-result-meta">
                    <span className="cb-pill">{group.hobby_label}</span>
                    <span className="cb-pill">{group.status}</span>
                    <span className="cb-pill">{hasJoined ? "joined" : "not joined"}</span>
                  </div>
                  <h3>{group.group_name}</h3>
                  <dl className="cb-detail-list">
                    <div>
                      <dt>Interest count</dt>
                      <dd>{group.consensus_interest_count ?? group.member_interest_count} / {group.threshold}</dd>
                    </div>
                    <div>
                      <dt>Destination</dt>
                      <dd>{group.destination}</dd>
                    </div>
                    <div>
                      <dt>Discord privacy</dt>
                      <dd>{group.discord_private ? "Private channel" : "Invite-based channel"}</dd>
                    </div>
                    <div>
                      <dt>Invite mode</dt>
                      <dd>{group.invite_mode}</dd>
                    </div>
                    <div>
                      <dt>Summary source</dt>
                      <dd>{formatSource(group.summary_source)}</dd>
                    </div>
                  </dl>
                  <div className="cb-consent">
                    <strong>Group summary</strong>
                    <span>{group.group_summary}</span>
                    {group.discord_invite_url ? (
                      <a href={group.discord_invite_url} rel="noreferrer" target="_blank">
                        Open Discord invite
                      </a>
                    ) : null}
                    {group.discord_announcement_channel_id ? (
                      <span>Invite announced in Discord channel {group.discord_announcement_channel_id}</span>
                    ) : null}
                    {group.summary_fallback_reason ? (
                      <span>Fallback reason: {group.summary_fallback_reason}</span>
                    ) : null}
                  </div>
                  {hasJoined ? (
                    <div className="cb-success">Joined. Discord joining is handled by the campus integration.</div>
                  ) : (
                    <div className="cb-actions">
                      <button
                        className="cb-primary"
                        disabled={isActing}
                        onClick={() => joinGroup(group.group_id)}
                        type="button"
                      >
                        {isActing ? "Joining..." : "Join Group"}
                      </button>
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        ) : (
          <article className="cb-card cb-inbox-empty">
            <h3>No campus groups are ready yet</h3>
            <p>Add interests in Trust Dashboard with group suggestions enabled.</p>
          </article>
        )}
      </section>

      <section className="cb-section">
        <div className="cb-inbox-header">
          <div>
            <span className="cb-eyebrow">My Group Invites</span>
            <h2>Private Invites</h2>
            <p className="cb-small-note">Only invites for the selected student appear here.</p>
          </div>
          <button className="cb-secondary" onClick={() => loadInvites(currentUserId)} type="button">
            Refresh invites
          </button>
        </div>

        {invites.length ? (
          <div className="cb-grid">
            {invites.map((invite) => {
              const isActing = actingGroupId === invite.group_id;
              const canJoin = invite.invite_status === "ready_to_join";
              const canIgnore = invite.invite_status === "ready_to_join";

              return (
                <article className="cb-card" key={invite.invite_id}>
                  <div className="cb-result-meta">
                    <span className="cb-pill">{invite.invite_status}</span>
                    <span className="cb-pill">{invite.hobby_label}</span>
                  </div>
                  <h3>{invite.group_name}</h3>
                  <dl className="cb-detail-list">
                    <div>
                      <dt>Destination</dt>
                      <dd>{invite.destination}</dd>
                    </div>
                    <div>
                      <dt>Invite mode</dt>
                      <dd>{invite.invite_mode}</dd>
                    </div>
                    <div>
                      <dt>Summary source</dt>
                      <dd>{formatSource(invite.summary_source)}</dd>
                    </div>
                  </dl>
                  <div className="cb-consent">
                    <strong>Invite message</strong>
                    <span>{invite.message}</span>
                    {invite.group_summary ? <span>{invite.group_summary}</span> : null}
                  </div>
                  {invite.invite_status === "joined" ? (
                    <div className="cb-success">Status joined. Discord joining is handled by the campus integration.</div>
                  ) : null}
                  <div className="cb-actions">
                    {canJoin ? (
                      <button
                        className="cb-primary"
                        disabled={isActing}
                        onClick={() => joinGroup(invite.group_id)}
                        type="button"
                      >
                        {isActing ? "Updating..." : "Join Group"}
                      </button>
                    ) : null}
                    {canIgnore ? (
                      <button
                        className="cb-secondary"
                        disabled={isActing}
                        onClick={() => ignoreGroup(invite.group_id)}
                        type="button"
                      >
                        Ignore
                      </button>
                    ) : null}
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <article className="cb-card cb-inbox-empty">
            <h3>No group invites for this student yet</h3>
            <p>Invites appear when this student&apos;s Trust Dashboard interests match a ready group.</p>
          </article>
        )}
      </section>
    </div>
  );
}
