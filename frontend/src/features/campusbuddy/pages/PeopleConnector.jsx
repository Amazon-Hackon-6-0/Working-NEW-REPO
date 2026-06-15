import { useEffect, useState } from "react";
import CampusBuddyHeader from "../components/CampusBuddyHeader.jsx";
import { campusbuddyApi } from "../services/campusbuddyApi.js";

export default function PeopleConnector({ currentUser }) {
  const [query, setQuery] = useState("I need help in DSA graphs but I feel awkward asking in the group.");
  const [data, setData] = useState(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sendingConnectionId, setSendingConnectionId] = useState("");
  const [inbox, setInbox] = useState(null);
  const [inboxError, setInboxError] = useState("");
  const [inboxStatusMessage, setInboxStatusMessage] = useState("");
  const [respondingRequestId, setRespondingRequestId] = useState("");
  const [revealingRequestId, setRevealingRequestId] = useState("");
  const [revealStatuses, setRevealStatuses] = useState({});

  const currentUserId = currentUser.userId;

  useEffect(() => {
    if (currentUserId) fetchIncomingRequests(currentUserId);
  }, [currentUserId]);

  async function fetchIncomingRequests(userId) {
    setInboxError("");

    try {
      setInbox(await campusbuddyApi.connectionRequests(userId));
    } catch (requestError) {
      setInboxError("Could not load incoming requests right now.");
    }
  }

  async function respondToRequest(requestId, action) {
    setInboxStatusMessage("");
    setInboxError("");
    setRespondingRequestId(requestId);

    try {
      const updatedRequest = await campusbuddyApi.respondConnectionRequest(requestId, currentUserId, action);
      setInboxStatusMessage(`Request ${updatedRequest.status}. Identity is still hidden.`);
      await fetchIncomingRequests(currentUserId);
    } catch (requestError) {
      setInboxError("Could not update this request right now. Please try again.");
    } finally {
      setRespondingRequestId("");
    }
  }

  async function requestIdentityReveal(requestId) {
    setInboxStatusMessage("");
    setInboxError("");
    setRevealingRequestId(requestId);

    try {
      const revealStatus = await campusbuddyApi.giveRevealConsent(requestId, currentUserId);
      setRevealStatuses((currentStatuses) => ({
        ...currentStatuses,
        [requestId]: revealStatus,
      }));
      setInboxStatusMessage(
        revealStatus.identity_revealed
          ? "Identity revealed by mutual consent."
          : "Reveal consent recorded. Identities stay anonymous until both students agree."
      );
      await fetchIncomingRequests(currentUserId);
    } catch (requestError) {
      setInboxError("Could not update reveal consent right now. Please try again.");
    } finally {
      setRevealingRequestId("");
    }
  }

  async function findMatches(event) {
    event.preventDefault();
    if (!query.trim() || !currentUserId) return;

    setIsLoading(true);
    setStatusMessage("");
    setError("");

    try {
      setData(await campusbuddyApi.connect(query.trim(), currentUserId));
    } catch (connectError) {
      setError("Could not find anonymous matches right now. Please try again.");
    } finally {
      setIsLoading(false);
    }
  }

  async function sendAnonymousRequest(match) {
    setStatusMessage("");
    setError("");
    setSendingConnectionId(match.connection_id);

    try {
      const request = await campusbuddyApi.createConnectionRequest({
        connectionId: match.connection_id,
        requestMessage: data.suggested_request_message,
        topic: data.extracted_topic,
        category: data.category,
        requesterUserId: currentUserId,
      });
      setStatusMessage(request.message || "Anonymous request sent. The helper can accept or deny from their inbox.");
      fetchIncomingRequests(currentUserId);
    } catch (requestError) {
      setError("Could not send the anonymous request right now. Please try again.");
    } finally {
      setSendingConnectionId("");
    }
  }

  function getRequestDisplay(request) {
    const revealStatus = revealStatuses[request.request_id];
    const identityRevealed = revealStatus?.identity_revealed || request.identity_revealed;
    const revealedDetails = revealStatus?.identity_revealed ? revealStatus : request;
    const requesterName = identityRevealed
      ? revealedDetails.visible_requester_name || request.requester_alias
      : request.requester_alias;
    const helperName = identityRevealed
      ? revealedDetails.visible_helper_name || request.helper_alias
      : request.helper_alias;

    return { helperName, identityRevealed, requesterName };
  }

  function getIncomingStatusNote(status) {
    if (status === "accepted") {
      return "Request accepted. You can now continue anonymously or request identity reveal.";
    }
    if (status === "denied") {
      return "Request denied.";
    }
    return "";
  }

  const matches = data?.matches || [];

  return (
    <div>
      <CampusBuddyHeader eyebrow="Mutual Anonymous Connector" title="Find safe help">
        Requester and helper both control anonymity before any identity reveal.
      </CampusBuddyHeader>
      <section className="cb-form">
        <p className="cb-small-note">
          {currentUser.name || "The current user"} is the requester for new help requests and the viewer for incoming or sent requests.
        </p>
      </section>
      <form className="cb-input-row" onSubmit={findMatches}>
        <input
          placeholder="Ask for help with any doubt, skill, campus issue, or interest..."
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <button className="cb-primary" disabled={isLoading} type="submit">
          {isLoading ? "Finding..." : "Find matches"}
        </button>
      </form>
      {error ? <div className="cb-success cb-alert">{error}</div> : null}
      {data ? (
        <section className="cb-grid cb-connector-results">
          <article className="cb-card cb-wide">
            <div className="cb-result-meta">
              <span className="cb-pill">CampusBuddy AI-assisted match</span>
              <span className="cb-pill">{data.category || "general_help"}</span>
            </div>
            <h3>What CampusBuddy understood</h3>
            <dl className="cb-detail-list">
              <div>
                <dt>Extracted topic</dt>
                <dd>{data.extracted_topic || "General support"}</dd>
              </div>
              <div>
                <dt>Helper type needed</dt>
                <dd>{data.helper_type_needed || "A consent-approved anonymous helper"}</dd>
              </div>
              <div>
                <dt>Suggested anonymous request</dt>
                <dd>{data.suggested_request_message || "Can someone help me anonymously first?"}</dd>
              </div>
            </dl>
            <p className="cb-small-note">{data.privacy_note}</p>
          </article>

          {matches.length > 0 ? (
            matches.map((match) => (
              <article className="cb-card" key={match.connection_id || match.anonymous_name}>
                <h3>{match.anonymous_name}</h3>
                <span className="cb-pill">{match.matched_memory_label}</span>
                <p>{match.match_reason}</p>
                <div className="cb-usage">
                  <span className="on">Contact: {match.contact_mode}</span>
                  <span className="on">Consent: {match.consent_status}</span>
                  <span className="on">Reveal: {match.reveal_policy}</span>
                </div>
                <div className="cb-actions">
                  <button
                    className="cb-secondary"
                    disabled={sendingConnectionId === match.connection_id}
                    onClick={() => sendAnonymousRequest(match)}
                    type="button"
                  >
                    {sendingConnectionId === match.connection_id ? "Sending..." : "Send anonymous request"}
                  </button>
                  <button
                    className="cb-secondary"
                    onClick={() =>
                      setStatusMessage("Reveal request sent. Identity will be shared only if both students agree.")
                    }
                    type="button"
                  >
                    Request identity reveal
                  </button>
                </div>
              </article>
            ))
          ) : (
            <article className="cb-card cb-wide">
              <h3>No direct anonymous match yet</h3>
              <p>{data.no_match_message || "No consent-approved matching student was found for this request."}</p>
              <div className="cb-consent">
                <strong>Anonymous opt-in request</strong>
                <span>{data.suggested_request_message || "Can someone help me anonymously first?"}</span>
              </div>
            </article>
          )}
        </section>
      ) : null}
      {statusMessage ? <div className="cb-success">{statusMessage}</div> : null}

      <section className="cb-section">
        <div className="cb-inbox-header">
          <div>
            <span className="cb-eyebrow">Helper Inbox</span>
            <h2>Incoming Requests</h2>
            <p className="cb-small-note">View only anonymous incoming requests for the selected student.</p>
          </div>
        </div>

        {inboxError ? <div className="cb-success cb-alert">{inboxError}</div> : null}
        {inboxStatusMessage ? <div className="cb-success">{inboxStatusMessage}</div> : null}

        {inbox?.incoming_requests?.length ? (
          <div className="cb-grid">
            {inbox.incoming_requests.map((request) => {
              const isPending = request.status === "pending";
              const isResponding = respondingRequestId === request.request_id;
              const isRevealing = revealingRequestId === request.request_id;
              const { helperName, identityRevealed, requesterName } = getRequestDisplay(request);
              const statusNote = getIncomingStatusNote(request.status);

              return (
                <article className="cb-card" key={request.request_id}>
                  <div className="cb-result-meta">
                    <span className="cb-pill">{request.status}</span>
                    <span className="cb-pill">{request.category}</span>
                  </div>
                  <h3>{requesterName}</h3>
                  <p>{request.request_message}</p>
                  <dl className="cb-detail-list">
                    <div>
                      <dt>Topic</dt>
                      <dd>{request.topic}</dd>
                    </div>
                    <div>
                      <dt>Requester reveal consent</dt>
                      <dd>{request.requester_reveal_consent ? "Given" : "Not given"}</dd>
                    </div>
                    <div>
                      <dt>Helper reveal consent</dt>
                      <dd>{request.helper_reveal_consent ? "Given" : "Not given"}</dd>
                    </div>
                    <div>
                      <dt>Identity revealed</dt>
                      <dd>{identityRevealed ? "Yes" : "No"}</dd>
                    </div>
                    {identityRevealed ? (
                      <>
                        <div>
                          <dt>Visible requester name</dt>
                          <dd>{requesterName}</dd>
                        </div>
                        <div>
                          <dt>Visible helper name</dt>
                          <dd>{helperName}</dd>
                        </div>
                      </>
                    ) : null}
                  </dl>
                  {identityRevealed ? (
                    <div className="cb-success">Identity revealed by mutual consent.</div>
                  ) : null}
                  {statusNote && !identityRevealed ? <div className="cb-consent">{statusNote}</div> : null}
                  {!identityRevealed ? (
                    <div className="cb-actions">
                      {isPending ? (
                        <>
                          <button
                            className="cb-secondary"
                            disabled={isResponding}
                            onClick={() => respondToRequest(request.request_id, "accepted")}
                            type="button"
                          >
                            {isResponding ? "Updating..." : "Accept"}
                          </button>
                          <button
                            className="cb-secondary"
                            disabled={isResponding}
                            onClick={() => respondToRequest(request.request_id, "denied")}
                            type="button"
                          >
                            Deny
                          </button>
                        </>
                      ) : null}
                      {request.status !== "denied" ? (
                        <button
                          className="cb-secondary"
                          disabled={isRevealing}
                          onClick={() => requestIdentityReveal(request.request_id)}
                          type="button"
                        >
                          {isRevealing ? "Requesting..." : "Request identity reveal"}
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        ) : (
          <article className="cb-card cb-inbox-empty">
            <h3>No incoming requests yet</h3>
            <p>Send an anonymous request to a matched helper, then view as that helper to see it here.</p>
          </article>
        )}

        <div className="cb-inbox-header cb-sent-header">
          <div>
            <span className="cb-eyebrow">Requester View</span>
            <h2>Sent Requests</h2>
            <p className="cb-small-note">View anonymous requests sent by the selected student.</p>
          </div>
        </div>

        {inbox?.outgoing_requests?.length ? (
          <div className="cb-grid">
            {inbox.outgoing_requests.map((request) => {
              const isRevealing = revealingRequestId === request.request_id;
              const { helperName, identityRevealed, requesterName } = getRequestDisplay(request);

              return (
                <article className="cb-card" key={request.request_id}>
                  <div className="cb-result-meta">
                    <span className="cb-pill">{request.status}</span>
                    <span className="cb-pill">{request.category}</span>
                  </div>
                  <h3>{helperName}</h3>
                  <p>{request.request_message}</p>
                  <dl className="cb-detail-list">
                    <div>
                      <dt>Topic</dt>
                      <dd>{request.topic}</dd>
                    </div>
                    <div>
                      <dt>Requester reveal consent</dt>
                      <dd>{request.requester_reveal_consent ? "Given" : "Not given"}</dd>
                    </div>
                    <div>
                      <dt>Helper reveal consent</dt>
                      <dd>{request.helper_reveal_consent ? "Given" : "Not given"}</dd>
                    </div>
                    <div>
                      <dt>Identity revealed</dt>
                      <dd>{identityRevealed ? "Yes" : "No"}</dd>
                    </div>
                    {identityRevealed ? (
                      <>
                        <div>
                          <dt>Visible requester name</dt>
                          <dd>{requesterName}</dd>
                        </div>
                        <div>
                          <dt>Visible helper name</dt>
                          <dd>{helperName}</dd>
                        </div>
                      </>
                    ) : null}
                  </dl>
                  {identityRevealed ? (
                    <div className="cb-success">Identity revealed by mutual consent.</div>
                  ) : null}
                  {!identityRevealed ? (
                    <div className="cb-actions">
                      <button
                        className="cb-secondary"
                        disabled={isRevealing}
                        onClick={() => requestIdentityReveal(request.request_id)}
                        type="button"
                      >
                        {isRevealing ? "Requesting..." : "Request identity reveal"}
                      </button>
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        ) : (
          <article className="cb-card cb-inbox-empty">
            <h3>No sent requests yet</h3>
            <p>Send an anonymous request to a matched helper to see it here.</p>
          </article>
        )}
      </section>
    </div>
  );
}
