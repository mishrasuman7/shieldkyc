import { useState, useRef, useEffect } from "react";
import { submitKYC } from "../api/kyc";

// The four steps. The progress bar and navigation read from this array.
const STEPS = [
  { id: 1, label: "Personal info" },
  { id: 2, label: "Citizenship card" },
  { id: 3, label: "Your photo" },
  { id: 4, label: "Selfie" },
];

export default function SubmissionPortal() {
  const [step, setStep] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [submitError, setSubmitError] = useState(null);

  const [form, setForm] = useState({
    full_name: "",
    dob: "",
    citizenship_number: "",
    phone: "",
    citizenship_front: null,
    citizenship_back: null,
    photo: null,
    selfie: null,
  });

  const update = (field) => (e) =>
    setForm((f) => ({ ...f, [field]: e.target.value }));

  const setFile = (field) => (file) =>
    setForm((f) => ({ ...f, [field]: file }));

  // --- Per-step validation gates ---
  const step1Valid =
    form.full_name.trim() &&
    form.dob.trim() &&
    form.citizenship_number.trim() &&
    form.phone.trim();
  const step2Valid = form.citizenship_front && form.citizenship_back;
  const step3Valid = form.photo;
  const step4Valid = form.selfie;

  const canAdvance =
    step === 1 ? step1Valid :
    step === 2 ? step2Valid :
    step === 3 ? step3Valid :
    step === 4 ? step4Valid :
    true;

  const next = async () => {
    if (!canAdvance) return;
    // On the last step, "Next" becomes "Submit".
    if (step === STEPS.length) {
      setSubmitting(true);
      setSubmitError(null);
      try {
        const verdict = await submitKYC(form);
        setResult(verdict);
      } catch (err) {
        setSubmitError(err.message || "Something went wrong. Please try again.");
      } finally {
        setSubmitting(false);
      }
      return;
    }
    setStep((s) => Math.min(s + 1, STEPS.length));
  };

  const back = () => setStep((s) => Math.max(s - 1, 1));

  const progress = Math.round((step / STEPS.length) * 100);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 via-shield-50 to-slate-100 px-4 py-8">
      <div className="w-full max-w-lg rounded-3xl bg-white ring-1 ring-slate-900/5 shadow-xl shadow-shield-500/5 p-6 sm:p-8">

        {result ? (
          <ResultScreen result={result} onReset={() => { setResult(null); setStep(1); }} />
        ) : (
        <>

        {/* --- Header: brand + secure badge --- */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="grid place-items-center h-9 w-9 rounded-xl bg-shield-600 text-white font-bold">S</div>
            <div>
              <h1 className="text-base font-semibold text-slate-900 leading-tight">ShieldKYC</h1>
              <p className="text-xs text-slate-500">Identity verification</p>
            </div>
          </div>
          <span className="inline-flex items-center gap-1.5 text-xs text-slate-500 bg-slate-50 px-2.5 py-1 rounded-full">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
            Secure
          </span>
        </div>

        {/* --- Progress bar --- */}
        <div className="mb-6">
          <div className="flex justify-between text-xs text-slate-500 mb-2">
            <span>Step {step} of {STEPS.length} · {STEPS[step - 1].label}</span>
            <span>{progress}%</span>
          </div>
          <div className="flex gap-1.5">
            {STEPS.map((s) => (
              <div
                key={s.id}
                className={`flex-1 h-1.5 rounded-full transition-colors ${
                  s.id <= step ? "bg-shield-600" : "bg-slate-200"
                }`}
              />
            ))}
          </div>
        </div>

        {/* --- Step body --- */}
        <div className="min-h-[280px]">

          {step === 1 && (
            <div>
              <h2 className="text-lg font-semibold text-slate-900 mb-1">Your details</h2>
              <p className="text-sm text-slate-500 mb-5">
                Enter your information exactly as it appears on your citizenship card.
              </p>
              <div className="space-y-4">
                <Field label="Full name" value={form.full_name} onChange={update("full_name")} placeholder="Suman Mishra" />
                <Field label="Date of birth" type="date" value={form.dob} onChange={update("dob")} />
                <Field label="Citizenship number" value={form.citizenship_number} onChange={update("citizenship_number")} placeholder="72-01-80-00667" />
                <Field label="Phone number" type="tel" value={form.phone} onChange={update("phone")} placeholder="98XXXXXXXX" />
              </div>
            </div>
          )}

          {step === 2 && (
            <div>
              <h2 className="text-lg font-semibold text-slate-900 mb-1">Upload your citizenship card</h2>
              <p className="text-sm text-slate-500 mb-5">
                Both sides required. We read the English back side for your name and details.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <UploadZone label="Front side" hint="Nepali side (with photo)" file={form.citizenship_front} onFile={setFile("citizenship_front")} />
                <UploadZone label="Back side" hint="English side (with details)" file={form.citizenship_back} onFile={setFile("citizenship_back")} />
              </div>
            </div>
          )}

          {step === 3 && (
            <div>
              <h2 className="text-lg font-semibold text-slate-900 mb-1">Upload a recent photo</h2>
              <p className="text-sm text-slate-500 mb-5">
                A clear, recent passport-size photo of your face. We match this against your selfie — not your citizenship photo, which is often old.
              </p>
              <div className="max-w-[240px] mx-auto">
                <UploadZone label="Your photo" hint="Recent, front-facing" file={form.photo} onFile={setFile("photo")} />
              </div>
            </div>
          )}

          {step === 4 && (
            <div>
              <h2 className="text-lg font-semibold text-slate-900 mb-1">Take a selfie</h2>
              <p className="text-sm text-slate-500 mb-5">
                Look straight at the camera in good lighting. This confirms a live person matching your photo.
              </p>
              <SelfieCapture file={form.selfie} onCapture={setFile("selfie")} />
            </div>
          )}

        </div>

        {/* --- Navigation --- */}
        <div className="flex items-center justify-between pt-5 border-t border-slate-100">
          <button
            onClick={back}
            disabled={step === 1 || submitting}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 px-4 py-2 rounded-xl hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            ← Back
          </button>
          <button
            onClick={next}
            disabled={!canAdvance || submitting}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-white bg-shield-600 px-5 py-2 rounded-xl hover:bg-shield-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? "Verifying…" : step === STEPS.length ? "Submit" : "Next →"}
          </button>
        </div>

        {submitError && (
          <p className="text-sm text-rose-600 mt-3 text-center">{submitError}</p>
        )}

        </>
        )}

      </div>
    </div>
  );
}

// A reusable labeled input.
function Field({ label, type = "text", ...props }) {
  return (
    <label className="block">
      <span className="block text-sm font-medium text-slate-700 mb-1.5">{label}</span>
      <input
        type={type}
        {...props}
        className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-shield-500 focus:ring-2 focus:ring-shield-500/20 outline-none transition"
      />
    </label>
  );
}

// A reusable upload zone — empty state or filled state with thumbnail preview.
function UploadZone({ label, hint, file, onFile }) {
  const inputId = `upload-${label.replace(/\s+/g, "-").toLowerCase()}`;
  const previewUrl = file ? URL.createObjectURL(file) : null;

  const handleChange = (e) => {
    const f = e.target.files?.[0];
    if (f) onFile(f);
  };

  return (
    <div>
      <input id={inputId} type="file" accept="image/*" onChange={handleChange} className="hidden" />
      <label
        htmlFor={inputId}
        className={`block cursor-pointer rounded-xl border p-4 text-center transition ${
          file
            ? "border-emerald-300 bg-emerald-50"
            : "border-dashed border-slate-300 hover:border-shield-400 hover:bg-slate-50"
        }`}
      >
        {file ? (
          <div>
            <img src={previewUrl} alt={`${label} preview`} className="mx-auto h-20 w-full max-w-[140px] object-cover rounded-lg mb-2" />
            <div className="flex items-center justify-center gap-1.5 text-emerald-700">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M20 6 9 17l-5-5"/></svg>
              <span className="text-sm font-medium">{label}</span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5 truncate">{file.name}</p>
            <p className="text-xs text-shield-600 mt-1">Tap to replace</p>
          </div>
        ) : (
          <div className="py-3">
            <svg className="mx-auto text-slate-400 mb-2" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            <p className="text-sm font-medium text-slate-700">{label}</p>
            <p className="text-xs text-slate-400 mt-0.5">{hint}</p>
            <p className="text-xs text-slate-400 mt-1">Tap to upload</p>
          </div>
        )}
      </label>
    </div>
  );
}

// Webcam selfie capture, with an upload fallback if the camera is unavailable.
function SelfieCapture({ file, onCapture }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [camError, setCamError] = useState(false);
  const [previewUrl, setPreviewUrl] = useState(null);

  useEffect(() => {
    let active = true;
    async function startCamera() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user" },
          audio: false,
        });
        if (!active) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
      } catch (err) {
        setCamError(true);
      }
    }
    startCamera();
    return () => {
      active = false;
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
      }
    };
  }, []);

  const capture = () => {
    const video = videoRef.current;
    if (!video) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    canvas.toBlob((blob) => {
      if (!blob) return;
      const selfieFile = new File([blob], "selfie.jpg", { type: "image/jpeg" });
      onCapture(selfieFile);
      setPreviewUrl(URL.createObjectURL(selfieFile));
    }, "image/jpeg", 0.92);
  };

  const retake = () => {
    onCapture(null);
    setPreviewUrl(null);
  };

  if (file && previewUrl) {
    return (
      <div className="text-center">
        <img src={previewUrl} alt="Captured selfie" className="mx-auto rounded-2xl max-h-56 object-cover" />
        <div className="mt-3 inline-flex items-center gap-1.5 text-emerald-700 text-sm font-medium">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M20 6 9 17l-5-5"/></svg>
          Selfie captured
        </div>
        <button onClick={retake} className="block mx-auto mt-2 text-sm text-shield-600 hover:underline">
          Retake
        </button>
      </div>
    );
  }

  if (camError) {
    return (
      <div>
        <div className="rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-xs p-3 mb-3">
          Camera unavailable. You can upload a selfie photo instead.
        </div>
        <UploadZone label="Selfie" hint="Upload a clear selfie" file={file} onFile={onCapture} />
      </div>
    );
  }

  return (
    <div className="text-center">
      <video ref={videoRef} autoPlay playsInline muted className="mx-auto rounded-2xl max-h-56 bg-slate-900 object-cover" />
      <button
        onClick={capture}
        className="mt-4 inline-flex items-center gap-2 text-sm font-medium text-white bg-shield-600 px-5 py-2.5 rounded-xl hover:bg-shield-700 transition-colors"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>
        Capture
      </button>
    </div>
  );
}

// The verdict screen — the demo centerpiece.
function ResultScreen({ result, onReset }) {
  const { risk_score, risk_level, decision, explanation } = result;

  const theme = {
    LOW:    { ring: "text-emerald-500", chip: "bg-emerald-50 text-emerald-700", label: "Verified" },
    MEDIUM: { ring: "text-amber-500",   chip: "bg-amber-50 text-amber-700",     label: "Flagged for review" },
    HIGH:   { ring: "text-rose-500",    chip: "bg-rose-50 text-rose-700",       label: "Flagged for review" },
  }[risk_level] || { ring: "text-slate-500", chip: "bg-slate-100 text-slate-700", label: decision };

  const R = 52;
  const C = 2 * Math.PI * R;
  const filled = (risk_score / 100) * C;

  return (
    <div className="text-center">
      <h2 className="text-lg font-semibold text-slate-900 mb-1">Verification result</h2>
      <p className="text-sm text-slate-500 mb-6">Risk assessment complete</p>

      <div className="relative inline-grid place-items-center mb-4">
        <svg width="130" height="130" className="-rotate-90">
          <circle cx="65" cy="65" r={R} fill="none" stroke="currentColor" strokeWidth="10" className="text-slate-100" />
          <circle
            cx="65" cy="65" r={R} fill="none" strokeWidth="10" strokeLinecap="round"
            className={theme.ring}
            stroke="currentColor"
            strokeDasharray={C}
            strokeDashoffset={C - filled}
          />
        </svg>
        <div className="absolute text-center">
          <div className="text-3xl font-bold text-slate-900">{risk_score}</div>
          <div className="text-xs text-slate-400">/ 100</div>
        </div>
      </div>

      <div className="mb-2">
        <span className={`inline-flex items-center gap-1.5 text-sm font-medium px-3 py-1 rounded-full ${theme.chip}`}>
          {risk_level} risk · {theme.label}
        </span>
      </div>

      <div className="text-left mt-6 border-t border-slate-100 pt-5">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-3">
          {explanation.length} finding{explanation.length !== 1 ? "s" : ""}
        </p>
        <ul className="space-y-2.5">
          {explanation.map((reason, i) => (
            <li key={i} className="flex items-start gap-2.5 text-sm text-slate-700">
              <span className={`mt-0.5 shrink-0 ${risk_level === "LOW" ? "text-emerald-500" : "text-amber-500"}`}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  {risk_level === "LOW"
                    ? <path d="M20 6 9 17l-5-5"/>
                    : <><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></>}
                </svg>
              </span>
              <span>{reason}</span>
            </li>
          ))}
        </ul>
      </div>

      <button onClick={onReset} className="mt-6 text-sm font-medium text-shield-600 hover:underline">
        Submit another
      </button>
    </div>
  );
}