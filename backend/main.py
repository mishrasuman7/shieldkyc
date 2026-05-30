# main.py — ShieldKYC backend + /api/submit-kyc pipeline (five-image version).
#
# FIVE IMAGES, each with a clear job:
#   citizenship_front — Nepali (Devanagari). Document forensics + stored.
#   citizenship_back  — English. OCR name match + forensics + fingerprint source.
#   photo             — PP-size portrait. Face-matched against the selfie.
#   thumb             — Fresh thumb photo. SIFT-matched against card back print.
#   selfie            — Live capture. Face-matched against photo + liveness.

import os
import uuid
import shutil

from fastapi import FastAPI, Depends, Form, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database.db import engine, get_db
from database import models

from modules.document_forensics import analyze_document
from modules.face_match import analyze_face
from modules.ocr_engine import analyze_name
from modules.duplicate_detection import check_duplicate, add_face
from modules.fingerprint import analyze_fingerprint, check_duplicate_print, store_print
from modules.risk_engine import fuse

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="ShieldKYC API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # allow all origins (mobile IP, localhost, etc.)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.path.join("data", "uploads")


def _save_upload(upload: UploadFile, submission_id: str, kind: str) -> str:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(upload.filename or "")[1] or ".jpg"
    path = os.path.join(UPLOAD_DIR, f"{submission_id}_{kind}{ext}")
    with open(path, "wb") as f:
        shutil.copyfileobj(upload.file, f)
    return path


def _shrink_saved_image(path: str, max_dim: int = 1400):
    """Downscale a saved image in place if its longest side exceeds max_dim."""
    import cv2
    img = cv2.imread(path)
    if img is None:
        return
    h, w = img.shape[:2]
    scale = max_dim / max(h, w)
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)),
                         interpolation=cv2.INTER_AREA)
        cv2.imwrite(path, img)


@app.get("/")
def root():
    return {"message": "ShieldKYC backend is running"}

@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "shieldkyc-backend"}

@app.get("/api/db-check")
def db_check(db: Session = Depends(get_db)):
    count = db.query(models.Submission).count()
    return {"database": "connected", "submissions_stored": count}

@app.get("/api/submissions")
def list_submissions(db: Session = Depends(get_db)):
    rows = db.query(models.Submission).order_by(models.Submission.id.desc()).all()
    return [
        {
            "submission_id": r.submission_id,
            "full_name": r.full_name,
            "citizenship_number": r.citizenship_number,
            "risk_score": r.risk_score,
            "risk_level": r.risk_level,
            "decision": r.decision,
            "explanation": r.explanation,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@app.post("/api/submit-kyc")
def submit_kyc(
    # Wizard Step 1: personal info
    full_name: str = Form(...),
    dob: str = Form(...),
    citizenship_number: str = Form(...),
    phone: str = Form(...),
    # Images — front, back, photo required; thumb and selfie optional
    citizenship_front: UploadFile = File(...),
    citizenship_back: UploadFile = File(...),
    photo: UploadFile = File(...),
    thumb: UploadFile = File(None),
    selfie: UploadFile = File(None),
    behavior_metrics: str = Form("{}"),   # JSON string of typing/paste metrics
    db: Session = Depends(get_db),
):
    submission_id = "KYC-" + uuid.uuid4().hex[:8]

    # Save uploads to disk.
    front_path = _save_upload(citizenship_front, submission_id, "front")
    back_path = _save_upload(citizenship_back, submission_id, "back")
    photo_path = _save_upload(photo, submission_id, "photo")
    thumb_path = _save_upload(thumb, submission_id, "thumb") if thumb else None
    selfie_path = _save_upload(selfie, submission_id, "selfie") if selfie else None

    # Shrink all images to cap memory usage.
    _shrink_saved_image(front_path)
    _shrink_saved_image(back_path)
    _shrink_saved_image(photo_path)
    if thumb_path:
        _shrink_saved_image(thumb_path)
    if selfie_path:
        _shrink_saved_image(selfie_path)

    # --- Run modules, each on the RIGHT image ---

    # Module 1: Document forensics on the FRONT.
    doc_result = analyze_document(front_path)

    # Module 2: Face match — PP PHOTO vs SELFIE.
    if selfie_path:
        face_result = analyze_face(photo_path, selfie_path)
    else:
        face_result = {
            "module": "face_match", "risk_added": 60,
            "signals": {"face_mismatch": 40, "liveness_failed": 20},
            "reasons": ["No selfie provided — face could not be verified against the photo"],
            "passed": [],
            "details": {"face_mismatch": {"error": "selfie skipped"}},
        }

    # Module 6: OCR name on the ENGLISH BACK side.
    ocr_result = analyze_name(back_path, full_name)

    # Module 3: Duplicate detection on the SELFIE.
    if selfie_path:
        dup_result = check_duplicate(selfie_path)
    else:
        dup_result = {
            "module": "duplicate_detection", "risk_added": 25,
            "signals": {"duplicate_face": 25},
            "reasons": ["No selfie provided — duplicate-account check could not run"],
            "passed": [],
            "details": {"duplicate_face": {"error": "selfie skipped"}},
        }

    # Module 5: Fingerprint — SIFT match thumb against card BACK.
    if thumb_path and back_path:
        fp_result = analyze_fingerprint(back_path, thumb_path, mode="photo")
    else:
        fp_result = {
            "module": "fingerprint", "risk_added": 0,
            "signals": {}, "reasons": [],
            "passed": ["Fingerprint not provided (optional step)"],
            "details": {"fingerprint": {"mode": "skip"}},
        }

    # --- Behavioral biometrics: detect automated/bulk-paste form filling ---
    import json as _json
    try:
        bm = _json.loads(behavior_metrics)
        behavior_risk = 0
        behavior_reasons = []
        behavior_passed = []

        paste_count = bm.get("paste_count", 0)
        pasted_fields = bm.get("pasted_fields", 0)
        total_time_ms = bm.get("total_time_ms", 999999)
        typing_speed = bm.get("typing_speed_cps", 0)

        # Flag 1: Most fields were pasted (bulk paste operation).
        if pasted_fields >= 3:
            behavior_risk += 10
            behavior_reasons.append(
                f"Suspicious paste behavior — {pasted_fields} of {bm.get('total_fields', 4)} fields were pasted, not typed"
            )

        # Flag 2: Form completed inhumanly fast (< 3 seconds for all fields).
        if total_time_ms < 3000 and total_time_ms > 0:
            behavior_risk += 10
            behavior_reasons.append(
                f"Form completed in {total_time_ms / 1000:.1f}s — too fast for manual entry"
            )

        # Flag 3: Typing speed is inhuman (> 15 chars/second sustained).
        if typing_speed > 15:
            behavior_risk += 5
            behavior_reasons.append(
                f"Typing speed ({typing_speed:.1f} chars/sec) exceeds human norms"
            )

        if not behavior_reasons:
            behavior_passed.append("Form filling behavior appears natural")

        behavior_result = {
            "module": "behavior",
            "risk_added": behavior_risk,
            "signals": {"suspicious_behavior": behavior_risk} if behavior_risk > 0 else {},
            "reasons": behavior_reasons,
            "passed": behavior_passed,
            "details": {"behavior": bm},
        }
    except Exception:
        behavior_result = {
            "module": "behavior", "risk_added": 0,
            "signals": {}, "reasons": [],
            "passed": ["Behavior metrics unavailable"],
            "details": {"behavior": {"error": "could not parse metrics"}},
        }

    # Duplicate fingerprint: check if this card's print was seen before.
    if back_path:
        dup_print_result = check_duplicate_print(back_path, submission_id)
    else:
        dup_print_result = {
            "module": "duplicate_print", "risk_added": 0,
            "signals": {}, "reasons": [],
            "passed": ["No card back provided for fingerprint duplicate check"],
            "details": {},
        }
    # Module 4: Fuse everything into one verdict.
    # verdict = fuse([doc_result, face_result, ocr_result, dup_result, fp_result, behavior_result])
    verdict = fuse([doc_result, face_result, ocr_result, dup_result, fp_result, dup_print_result, behavior_result])
    # Persist to SQLite.
    submission = models.Submission(
        submission_id=submission_id,
        full_name=full_name,
        dob=dob,
        citizenship_number=citizenship_number,
        phone=phone,
        risk_score=verdict["risk_score"],
        risk_level=verdict["risk_level"],
        decision=verdict["decision"],
        explanation=verdict["explanation"],
        signal_breakdown=verdict["signal_breakdown"],
        module_results=verdict["module_results"],
    )
    db.add(submission)
    db.commit()

    # Add selfie to FAISS AFTER duplicate check + save.
    if selfie_path:
        add_face(submission_id, selfie_path)
    
    if back_path:
        store_print(submission_id, back_path)

    return {
        "submission_id": submission_id,
        "risk_score": verdict["risk_score"],
        "risk_level": verdict["risk_level"],
        "decision": verdict["decision"],
        "explanation": verdict["explanation"],
        "signal_breakdown": verdict["signal_breakdown"],
        "module_results": verdict["module_results"],
    }