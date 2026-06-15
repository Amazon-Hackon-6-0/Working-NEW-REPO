import { writeCampusBuddyProfile } from "../campusbuddy/services/campusbuddyProfile.js";

const ACCOUNTS_KEY = "campusflow.accounts";
const SESSION_KEY = "campusflow.session";
const ACCESS_CODE = process.env.NEXT_PUBLIC_CAMPUSFLOW_ACCESS_CODE || "CAMPUSFLOW";

function readJson(key, fallback) {
  if (typeof window === "undefined") return fallback;
  try {
    return JSON.parse(window.localStorage.getItem(key) || "null") || fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key, value) {
  if (typeof window === "undefined") return value;
  window.localStorage.setItem(key, JSON.stringify(value));
  return value;
}

function normalizeEmail(email) {
  return email.trim().toLowerCase();
}

function userIdFromEmail(email) {
  return `user_${normalizeEmail(email).replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "")}`;
}

function publicUser(account) {
  return {
    userId: account.userId,
    name: account.name,
    email: account.email,
  };
}

export function readAuthSession() {
  const session = readJson(SESSION_KEY, null);
  if (!session?.email) return null;

  const account = readJson(ACCOUNTS_KEY, []).find(
    (item) => item.email === normalizeEmail(session.email),
  );
  if (!account) return null;

  const user = publicUser(account);
  writeCampusBuddyProfile(user);
  return user;
}

export function signUp({ name, email, password, accessCode }) {
  const cleanName = name.trim();
  const cleanEmail = normalizeEmail(email);
  const cleanPassword = password.trim();
  const cleanAccessCode = accessCode.trim();

  if (!cleanName || !cleanEmail || !cleanPassword || !cleanAccessCode) {
    return { ok: false, message: "Enter name, email, password, and access code." };
  }
  if (cleanAccessCode !== ACCESS_CODE) {
    return { ok: false, message: "Access code is not authorized for this campus." };
  }

  const accounts = readJson(ACCOUNTS_KEY, []);
  if (accounts.some((account) => account.email === cleanEmail)) {
    return { ok: false, message: "An account already exists for this email. Log in instead." };
  }

  const account = {
    userId: userIdFromEmail(cleanEmail),
    name: cleanName,
    email: cleanEmail,
    password: cleanPassword,
    createdAt: new Date().toISOString(),
  };
  writeJson(ACCOUNTS_KEY, [...accounts, account]);
  writeJson(SESSION_KEY, { email: cleanEmail });
  const user = publicUser(account);
  writeCampusBuddyProfile(user);
  return { ok: true, user };
}

export function logIn({ email, password }) {
  const cleanEmail = normalizeEmail(email);
  const cleanPassword = password.trim();
  const account = readJson(ACCOUNTS_KEY, []).find(
    (item) => item.email === cleanEmail && item.password === cleanPassword,
  );

  if (!account) {
    return { ok: false, message: "Email or password is incorrect." };
  }

  writeJson(SESSION_KEY, { email: cleanEmail });
  const user = publicUser(account);
  writeCampusBuddyProfile(user);
  return { ok: true, user };
}

export function logOut() {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(SESSION_KEY);
  }
}
