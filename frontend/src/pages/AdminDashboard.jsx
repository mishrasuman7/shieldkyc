import { useState, useEffect } from "react";
import { listSubmissions } from "../api/kyc";

export default function AdminDashboard() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedId, setExpandedId] = useState(null);  // which row's explanation is open

  // Load the list once on mount.
  useEffect(() => {
    listSubmissions()
      .then(setRows)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  // Colors per risk level — same palette as the user-facing result screen.
  const badge = (level) => ({
    LOW:    "bg-emerald-50 text-emerald-700 ring-emerald-200",
    MEDIUM: "bg-amber-50 text-amber-700 ring-amber-200",
    HIGH:   "bg-rose-50 text-rose-700 ring-rose-200",
  }[level] || "bg-slate-100 text-slate-700 ring-slate-200");

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-shield-50 to-slate-100 px-4 py-8">
      <div className="max-w-5xl mx-auto">

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="grid place-items-center h-10 w-10 rounded-xl bg-shield-600 text-white font-bold">S</div>
            <div>
              <h1 className="text-xl font-semibold text-slate-900 leading-tight">ShieldKYC · Reviewer</h1>
              <p className="text-xs text-slate-500">Submission queue</p>
            </div>
          </div>
          <a href="/" className="text-sm font-medium text-shield-600 hover:underline">
            ← Back to submission portal
          </a>
        </div>

        {/* Body */}
        <div className="bg-white rounded-3xl ring-1 ring-slate-900/5 shadow-xl shadow-shield-500/5 overflow-hidden">

          {loading && (
            <div className="p-12 text-center text-slate-400 text-sm">Loading submissions…</div>
          )}

          {error && (
            <div className="p-12 text-center text-rose-600 text-sm">{error}</div>
          )}

          {!loading && !error && rows.length === 0 && (
            <div className="p-12 text-center text-slate-400 text-sm">
              No submissions yet. Submit one through the portal to see it here.
            </div>
          )}

          {!loading && !error && rows.length > 0 && (
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="text-left font-semibold px-6 py-3">Submission</th>
                  <th className="text-left font-semibold px-6 py-3">Name</th>
                  <th className="text-left font-semibold px-6 py-3">Risk</th>
                  <th className="text-left font-semibold px-6 py-3">Decision</th>
                  <th className="text-right font-semibold px-6 py-3">Submitted</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((r) => {
                  const open = expandedId === r.submission_id;
                  return (
                    <Row
                      key={r.submission_id}
                      r={r}
                      open={open}
                      onToggle={() => setExpandedId(open ? null : r.submission_id)}
                      badge={badge}
                    />
                  );
                })}
              </tbody>
            </table>
          )}

        </div>

        <p className="text-xs text-slate-400 text-center mt-4">
          {rows.length} {rows.length === 1 ? "submission" : "submissions"} · auto-loads on open
        </p>

      </div>
    </div>
  );
}

// A row + its expandable explanation panel underneath.
function Row({ r, open, onToggle, badge }) {
  const when = r.created_at ? new Date(r.created_at).toLocaleString() : "—";
  const niceDecision = r.decision === "AUTO_APPROVED" ? "Verified" : "Review";

  return (
    <>
      <tr onClick={onToggle} className="cursor-pointer hover:bg-slate-50 transition">
        <td className="px-6 py-3 font-mono text-xs text-slate-600">{r.submission_id}</td>
        <td className="px-6 py-3 text-slate-900">{r.full_name || "—"}</td>
        <td className="px-6 py-3">
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium ring-1 ring-inset ${badge(r.risk_level)}`}>
            {r.risk_level} · {r.risk_score}/100
          </span>
        </td>
        <td className="px-6 py-3 text-slate-700">{niceDecision}</td>
        <td className="px-6 py-3 text-right text-xs text-slate-500">{when}</td>
      </tr>
      {open && (
        <tr className="bg-slate-50/60">
          <td colSpan={5} className="px-6 py-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">
              {(r.explanation || []).length} finding{(r.explanation || []).length !== 1 ? "s" : ""}
            </p>
            <ul className="space-y-1.5">
              {(r.explanation || []).map((reason, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-slate-700">
                  <span className="text-slate-400 mt-1">•</span>
                  <span>{reason}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-slate-400">
              Citizenship no. <span className="font-mono">{r.citizenship_number || "—"}</span>
            </p>
          </td>
        </tr>
      )}
    </>
  );
}