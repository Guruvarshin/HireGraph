const EMAIL_KEY      = "hiregraph_user_email";
const FALLBACK_KEY   = "hiregraph_fallback_id";

function generateUUID() {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

/** Set the authenticated email — called after Google OAuth */
export function setRecruiterEmail(email) {
  if (typeof window !== "undefined" && email) {
    localStorage.setItem(EMAIL_KEY, email.toLowerCase().trim());
  }
}

/** Get the stored email, or fall back to a stable UUID for unauthenticated use */
export function getRecruiterId() {
  if (typeof window === "undefined") return "";

  const email = localStorage.getItem(EMAIL_KEY);
  if (email) return email;

  // Pre-login fallback — replaced by email once authenticated
  let id = localStorage.getItem(FALLBACK_KEY);
  if (!id) {
    id = generateUUID();
    localStorage.setItem(FALLBACK_KEY, id);
  }
  return id;
}

export function getApiHeaders() {
  return {
    "X-Recruiter-ID":  getRecruiterId(),
    "Content-Type":    "application/json",
  };
}

/** Called on sign-out — clears auth email but keeps fallback UUID intact */
export function clearRecruiterEmail() {
  if (typeof window !== "undefined") {
    localStorage.removeItem(EMAIL_KEY);
  }
}
