# main.py — ShieldKYC backend + /api/submit-kyc pipeline (four-image version).
#
# FOUR IMAGES, each with a clear job:
#   citizenship_front — Nepali (Devanagari). Document forensics + stored.
#                       NOT used for OCR (Nepali script is unreliable to read).
#   citizenship_back  — English. THE TEXT SOURCE: OCR name match + forensics.
#   photo             — PP-size portrait. Face-matched against the selfie.
#                       (NOT the card photo — those are often old/B&W and would
#                        falsely reject legitimate senior citizens.)
#   selfie            — live capture. Face-matched against photo + liveness.
#
# Fingerprint (Module 5) stays parked (Path C). Back side is reserved for it later.

import os
import uuid
import shutil

from fastapi import FastAPI, Depends, Form, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database.db import engine, get_db
from database import models

from modules.document_forensics import analyze_document       # Module 1
from modules.face_match import analyze_face                   # Module 2
from modules.ocr_engine import analyze_name                   # Module 6
from modules.duplicate_detection import check_duplicate, add_face  # Module 3
from modules.risk_engine import fuse                          # Module 4 (brain)

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="ShieldKYC API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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
    """Return all submissions, newest first, for the admin dashboard."""
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
    # Four images
    citizenship_front: UploadFile = File(...),
    citizenship_back: UploadFile = File(...),
    photo: UploadFile = File(...),
    selfie: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    submission_id = "KYC-" + uuid.uuid4().hex[:8]

    # Save all four uploads to disk.
    front_path = _save_upload(citizenship_front, submission_id, "front")
    back_path = _save_upload(citizenship_back, submission_id, "back")
    photo_path = _save_upload(photo, submission_id, "photo")
    selfie_path = _save_upload(selfie, submission_id, "selfie")

    # --- Run the four active modules, each on the RIGHT image ---

    # Document forensics: check the FRONT (the official card face) for tampering.
    doc_result = analyze_document(front_path)

    # Face match: PP PHOTO vs SELFIE (two current, comparable portraits).
    face_result = analyze_face(photo_path, selfie_path)

    # OCR name: read the ENGLISH BACK side and match the submitted name.
    ocr_result = analyze_name(back_path, full_name)

    # Duplicate: search the selfie against past faces (BEFORE adding it).
    dup_result = check_duplicate(selfie_path)

    # Fuse into one verdict.
    verdict = fuse([doc_result, face_result, ocr_result, dup_result])

    # Persist.
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

    # Add this selfie to FAISS AFTER the duplicate check + save.
    add_face(submission_id, selfie_path)

    return {
        "submission_id": submission_id,
        "risk_score": verdict["risk_score"],
        "risk_level": verdict["risk_level"],
        "decision": verdict["decision"],
        "explanation": verdict["explanation"],
        "signal_breakdown": verdict["signal_breakdown"],
        "module_results": verdict["module_results"],
    }