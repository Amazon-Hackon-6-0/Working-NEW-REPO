import { useState } from "react";
import { LockKeyhole, LogIn, UserPlus } from "lucide-react";

import { logIn, logOut, readAuthSession, signUp } from "./authSession.js";

export default function AuthGate({ children }) {
  const [authUser, setAuthUser] = useState(() => readAuthSession());
  const [mode, setMode] = useState("login");
  const [message, setMessage] = useState("");

  function handleSubmit(event) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const payload = {
      name: String(formData.get("name") || ""),
      email: String(formData.get("email") || ""),
      password: String(formData.get("password") || ""),
      accessCode: String(formData.get("accessCode") || ""),
    };
    const result = mode === "signup" ? signUp(payload) : logIn(payload);
    if (!result.ok) {
      setMessage(result.message);
      return;
    }
    setMessage("");
    setAuthUser(result.user);
  }

  function handleLogout() {
    logOut();
    setAuthUser(null);
    setMode("login");
    setMessage("");
  }

  if (authUser) {
    return children({ authUser, onLogout: handleLogout });
  }

  const isSignUp = mode === "signup";

  return (
    <main className="auth-shell">
      <section className="auth-panel">
        <div className="auth-brand">
          <span className="auth-mark">
            <LockKeyhole size={24} />
          </span>
          <div>
            <p className="eyebrow">CampusFlow Authorization</p>
            <h1>{isSignUp ? "Create your campus account" : "Log in to CampusFlow"}</h1>
          </div>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          {isSignUp ? (
            <label>
              Full name
              <input name="name" autoComplete="name" placeholder="Pranjay Singh" />
            </label>
          ) : null}
          <label>
            Email
            <input name="email" autoComplete="email" placeholder="you@college.edu" type="email" />
          </label>
          <label>
            Password
            <input name="password" autoComplete={isSignUp ? "new-password" : "current-password"} type="password" />
          </label>
          {isSignUp ? (
            <label>
              Campus access code
              <input name="accessCode" placeholder="Ask admin for access code" />
            </label>
          ) : null}

          {message ? <div className="auth-message">{message}</div> : null}

          <button className="primary-button auth-submit" type="submit">
            {isSignUp ? <UserPlus size={18} /> : <LogIn size={18} />}
            {isSignUp ? "Sign up" : "Log in"}
          </button>
        </form>

        <div className="auth-switch">
          <span>{isSignUp ? "Already authorized?" : "New to this campus workspace?"}</span>
          <button type="button" onClick={() => setMode(isSignUp ? "login" : "signup")}>
            {isSignUp ? "Log in" : "Create account"}
          </button>
        </div>
      </section>
    </main>
  );
}
