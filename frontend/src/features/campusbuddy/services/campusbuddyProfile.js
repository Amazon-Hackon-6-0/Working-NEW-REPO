const PROFILE_STORAGE_KEY = "campusbuddy.currentUser";

function createUserId(email = "") {
  const normalizedEmail = email.trim().toLowerCase();
  if (normalizedEmail) {
    return `user_${normalizedEmail.replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "")}`;
  }
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return `user_${crypto.randomUUID()}`;
  }
  return `user_${Date.now()}`;
}

export function defaultCampusBuddyProfile() {
  return {
    userId: createUserId(),
    name: "",
    email: "",
  };
}

export function readCampusBuddyProfile() {
  if (typeof window === "undefined") return defaultCampusBuddyProfile();

  try {
    const storedProfile = JSON.parse(window.localStorage.getItem(PROFILE_STORAGE_KEY) || "null");
    if (storedProfile?.userId) {
      return {
        userId: storedProfile.userId,
        name: storedProfile.name || "",
        email: storedProfile.email || "",
      };
    }
  } catch {
    // Ignore malformed local data and create a fresh local identity.
  }

  const profile = defaultCampusBuddyProfile();
  writeCampusBuddyProfile(profile);
  return profile;
}

export function writeCampusBuddyProfile(profile) {
  if (typeof window === "undefined") return profile;

  const normalizedProfile = {
    userId: profile.userId || createUserId(profile.email),
    name: profile.name || "",
    email: profile.email || "",
  };
  window.localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(normalizedProfile));
  return normalizedProfile;
}

export function profileFromForm(previousProfile, formData) {
  const email = (formData.get("email") || "").toString().trim();
  return {
    userId: previousProfile.userId || createUserId(email),
    name: (formData.get("name") || "").toString().trim(),
    email,
  };
}
