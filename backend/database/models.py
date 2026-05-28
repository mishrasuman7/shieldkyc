# database/models.py — defines the "submissions" table structure.
# Each row = one completed KYC check and its risk verdict.

from sqlalchemy import Column, Integer, String, DateTime, JSON
from datetime import datetime, timezone
from .db import Base   # relative import: the Base from db.py in this same package

class Submission(Base):
    __tablename__ = "submissions"   # the actual table name in SQLite

    # Internal auto-incrementing row id (1, 2, 3...). Primary key.
    id = Column(Integer, primary_key=True, index=True)

    # The public-facing id we show users/admins, e.g. "KYC-a1b2c3d4".
    # unique=True stops duplicates; index=True makes lookups by it fast.
    submission_id = Column(String, unique=True, index=True)

    # --- Personal info collected in Step 1 of the wizard ---
    full_name = Column(String)
    dob = Column(String)
    citizenship_number = Column(String, index=True)  # indexed: we'll search by it
    phone = Column(String, index=True)               # indexed: duplicate checks

    # --- Final output from the risk engine (Module 4) ---
    risk_score = Column(Integer)   # 0-100
    risk_level = Column(String)    # "LOW" / "MEDIUM" / "HIGH"
    decision = Column(String)      # "AUTO_APPROVED" / "FLAGGED_FOR_REVIEW"

    # --- Rich detail stored as JSON (SQLite holds these as text) ---
    # JSON columns let us store lists/dicts directly without extra tables.
    # Perfect for the variable-length explanation list and nested module output.
    explanation = Column(JSON)        # ["Name does not match document", ...]
    signal_breakdown = Column(JSON)   # {"name_mismatch": 20, "face_mismatch": 40}
    module_results = Column(JSON)     # full per-module results for the evidence panel

    # When the submission was processed. Stored in UTC to avoid timezone bugs.
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))