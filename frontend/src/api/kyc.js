// src/api/kyc.js — all backend calls live here, so the rest of the app
// never hardcodes URLs. When we deploy later, we change ONE line.

// const API_BASE = "http://localhost:8000";   // e.g. http://192.168.1.105:8000
// const API_BASE = "http://192.168.15.140:8000";
const API_BASE = "https://sagging-dorsal-hull.ngrok-free.dev";

// Pings the backend's health endpoint we built earlier.
// Returns the JSON on success; throws on any failure so the UI can react.
export async function checkHealth() {
  const res = await fetch(`${API_BASE}/api/health`);
  if (!res.ok) throw new Error(`Backend responded with status ${res.status}`);
  return res.json();
}

// Sends all four images + personal info to the backend pipeline.
// Uses FormData because we're uploading files (multipart/form-data) — the
// browser sets the right headers automatically when you pass a FormData body.
export async function submitKYC(form, behaviorMetrics) {
  const data = new FormData();
  data.append("full_name", form.full_name);
  data.append("dob", form.dob);
  data.append("citizenship_number", form.citizenship_number);
  data.append("phone", form.phone);
  data.append("citizenship_front", form.citizenship_front);
  data.append("citizenship_back", form.citizenship_back);
  data.append("photo", form.photo);
  if (form.thumb) {
    data.append("thumb", form.thumb);
  }
  if (form.selfie) {
    data.append("selfie", form.selfie);
  }
  // Behavioral biometrics — JSON string of typing/paste metrics.
  if (behaviorMetrics) {
    data.append("behavior_metrics", JSON.stringify(behaviorMetrics));
  }

  const res = await fetch(`${API_BASE}/api/submit-kyc`, {
    method: "POST",
    body: data,
  });

  if (!res.ok) {
    throw new Error(`Submission failed (status ${res.status})`);
  }
  return res.json();
}

// Fetch all stored submissions for the admin dashboard.
export async function listSubmissions() {
  const res = await fetch(`${API_BASE}/api/submissions`);
  if (!res.ok) throw new Error(`Failed to load submissions (${res.status})`);
  return res.json();
}