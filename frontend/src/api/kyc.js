// src/api/kyc.js — all backend calls live here.

const API_BASE = "https://sagging-dorsal-hull.ngrok-free.dev";

const HEADERS = { "ngrok-skip-browser-warning": "true" };

export async function checkHealth() {
  const res = await fetch(`${API_BASE}/api/health`, { headers: HEADERS });
  if (!res.ok) throw new Error(`Backend responded with status ${res.status}`);
  return res.json();
}

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
  if (behaviorMetrics) {
    data.append("behavior_metrics", JSON.stringify(behaviorMetrics));
  }

  const res = await fetch(`${API_BASE}/api/submit-kyc`, {
    method: "POST",
    body: data,
    headers: HEADERS,
  });

  if (!res.ok) {
    throw new Error(`Submission failed (status ${res.status})`);
  }
  return res.json();
}

export async function listSubmissions() {
  const res = await fetch(`${API_BASE}/api/submissions`, { headers: HEADERS });
  if (!res.ok) throw new Error(`Failed to load submissions (${res.status})`);
  return res.json();
}