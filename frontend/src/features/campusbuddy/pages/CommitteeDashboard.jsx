import { useEffect, useState } from "react";
import CampusBuddyHeader from "../components/CampusBuddyHeader.jsx";
import { campusbuddyApi } from "../services/campusbuddyApi.js";

export default function CommitteeDashboard() {
  const [data, setData] = useState(null);

  useEffect(() => {
    campusbuddyApi.committeeDashboard().then(setData);
  }, []);

  return (
    <div>
      <CampusBuddyHeader eyebrow="Committee View" title="Anonymous campus signals">
        Committees see summarized issues, not raw student chats.
      </CampusBuddyHeader>
      {data ? (
        <section className="cb-grid">
          {data.issues.map((issue) => (
            <article className="cb-card" key={issue.id}>
              <span className="cb-pill">{issue.category}</span>
              <h3>{issue.committee}</h3>
              <p>{issue.summary}</p>
              <strong>{issue.count} report(s)</strong>
              <p>{issue.status}</p>
            </article>
          ))}
        </section>
      ) : <div className="cb-card">Loading committee dashboard...</div>}
    </div>
  );
}
