# 🛡️ ShieldKYC

**AI-Powered KYC Fraud Detection for Esewa**

Seven independent fraud signals fuse into one explainable risk score — AI screens, humans decide.

> Built for the **eSewa × WWF Hackathon 2026** by Suman Mishra.

---

## The Problem

Organized crime rings use stolen Nepali citizenship cards to open hundreds of fraudulent accounts. Each submission looks legitimate, and manual KYC review can't keep up. ShieldKYC catches the fraud **before the account is created** — not after the money is gone.

---

## How It Works

A submission runs through **7 independent fraud checks**, each adding to a 0–100 risk score:

| # | Module | What it catches |
|---|--------|----------------|
| 1 | **Document Forensics** | Tampered/edited images, screenshots, screen-replay (ELA, EXIF, FFT) |
| 2 | **Face Match + Liveness** | Selfie doesn't match the photo on file |
| 3 | **Duplicate Face Detection** | Same face used across multiple accounts |
| 4 | **OCR Name Verification** | Name on card doesn't match submitted name |
| 5 | **Fingerprint Matching** | Thumbprint on citizenship card vs. live thumb photo |
| 6 | **Duplicate Fingerprint** | Same citizenship card reused across accounts |
| 7 | **Behavioral Biometrics** | Copy-paste / bot-like form filling (crime-ring operators) |

All signals fuse in a **risk engine** with **fail-closed safety** — if any check crashes, it *adds* risk and routes to human review. It never silently approves.

**Verdict:** `0–40` Low → Auto-approve · `41–70` Medium → Review · `71–100` High → Urgent review

---

## What Makes It Unique

- 🇳🇵 **Nepal's first** fingerprint matching on citizenship cards — extract the inked thumbprint and match it against a live thumb photo.
- 🤖 **Behavioral detection** — a real person types their name; a fraud operator pastes stolen data. We catch the difference.
- 🔗 **Multi-signal fusion** — no single check is enough, but seven together produce a verdict you can trust *and explain*.

---

## Tech Stack

**Backend:** Python 3.12 · FastAPI · SQLAlchemy · SQLite
**AI/ML:** DeepFace (ArcFace) · EasyOCR · OpenCV SIFT + FLANN · FAISS
**Frontend:** React 18 · Vite · Tailwind CSS v4 · WebRTC
**Deployment:** Google Colab · ngrok HTTPS tunnel

---

## Getting Started

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
python -m uvicorn main:app --port 8000 --host 0.0.0.0
```

### Frontend

```bash
cd frontend
npm install
npm run dev -- --host
```

Update `frontend/src/api/kyc.js` with your backend URL:

```js
const API_BASE = "http://localhost:8000";
```

Open `http://localhost:5173` for the submission wizard, `http://localhost:5173/admin` for the reviewer dashboard.

---

## API

`POST /api/submit-kyc` — submit a KYC application (multipart form)

| Field | Type | Required |
|-------|------|----------|
| `full_name`, `dob`, `citizenship_number`, `phone` | text | ✓ |
| `citizenship_front`, `citizenship_back`, `photo` | image | ✓ |
| `thumb`, `selfie` | image | optional |
| `behavior_metrics` | JSON string | optional |

Returns: `risk_score`, `risk_level`, `decision`, `explanation[]`, `signal_breakdown{}`.

Other endpoints: `GET /api/health` · `GET /api/submissions` · `GET /api/db-check`

---

## Roadmap

- **30 days:** Signature matching · enhanced admin panel · approve/reject workflow + audit trail
- **3 months:** Devanagari ↔ English cross-check · Postgres · eSewa pilot
- **6 months:** Cross-submission network graph (fraud rings as clusters) · fraud velocity alerts · document age estimation
- **12 months:** Mobile SDK · regulatory dashboard for Nepal Rastra Bank

> *ShieldKYC today catches the fraudster. ShieldKYC tomorrow catches the fraud RING.*

---

## License

Built for the eSewa × WWF Hackathon 2026. Contact for usage.

**Suman Mishra** · [github.com/mishrasuman7](https://github.com/mishrasuman7)
