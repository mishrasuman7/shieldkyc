# modules/fingerprint.py — Module 5: Fingerprint Biometrics (MOCK-FIRST)
# Inputs:  reference fingerprint (the print on the citizenship card),
#          probe fingerprint (the user's uploaded fingerprint photo),
#          mode: "photo" | "sensor" | "skip"
# Output:  dict with risk points, plain-English reason, raw numbers
#
# WHY MOCK-FIRST (your spec's call): real SourceAFIS minutiae matching against
# a PHOTOGRAPHED thumbprint is hard and finicky — the riskiest module to get
# reliable under time pressure. So we build a working mock NOW that always
# returns a sensible score, get the whole pipeline running on it, and slot real
# SourceAFIS into _real_match() LATER if there's time. Nothing else changes.
#
# THE THREE MODES (your spec):
#   "photo"  — Option A: match uploaded fingerprint photo against card print -> +15 on mismatch
#   "sensor" — Option B: WebAuthn phone sensor. Returns a crypto TOKEN, not an
#              image, so it CANNOT match the card — treated as a liveness/
#              consistency check only. Passes (+0).
#   "skip"   — user skipped the optional step -> no signal (+0).
#
# SAFETY RULE: in photo mode, if matching crashes or an image can't be read,
# we ADD the mismatch points (fail closed) — never silently clear.

import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

import cv2
import numpy as np

RISK_WEIGHTS = {"fingerprint_mismatch": 15}

# A fingerprint "matches" the card if its score is >= this (0-100).
# This is a MOCK heuristic threshold — calibrate when you have real prints,
# or it becomes irrelevant once real SourceAFIS is wired into _real_match().
FINGERPRINT_MATCH_MIN = 40.0


def _real_match(ref_img, probe_img):
    """REAL SourceAFIS minutiae matching goes here later. For now it raises,
    so analyze_fingerprint() falls back to the mock automatically. When you're
    ready: install sourceafis, implement this to return a 0-100 score, and the
    rest of the pipeline needs ZERO changes."""
    raise NotImplementedError("SourceAFIS not wired yet — using mock")


def _mock_score(ref_img, probe_img):
    """Mock match score (0-100). NOT real minutiae matching — it's an image-
    similarity proxy so the demo behaves sensibly: the same print scores high,
    a different one scores low. Deterministic, so results are reproducible."""
    size = (256, 256)
    a = cv2.equalizeHist(cv2.resize(ref_img, size))    # normalize contrast
    b = cv2.equalizeHist(cv2.resize(probe_img, size))
    af, bf = a.flatten().astype(np.float64), b.flatten().astype(np.float64)
    if af.std() == 0 or bf.std() == 0:
        corr = 0.0
    else:
        corr = float(np.corrcoef(af, bf)[0, 1])   # -1..1
    return round(max(0.0, corr) * 100, 1)          # negatives -> 0


def analyze_fingerprint(reference_path=None, probe_path=None, mode="photo"):
    """Run the fingerprint check. Returns the standard module shape."""
    weight = RISK_WEIGHTS["fingerprint_mismatch"]

    # Mode: WebAuthn sensor — a token, not an image. Liveness/consistency only.
    if mode == "sensor":
        return _result(False, 0, None,
                       "Fingerprint sensor verified (liveness check)",
                       {"mode": "sensor",
                        "note": "WebAuthn token verified; cannot be matched to card print"})

    # Mode: skipped optional step, or images simply not provided.
    if mode == "skip" or reference_path is None or probe_path is None:
        return _result(False, 0, None,
                       "Fingerprint not provided (optional step)",
                       {"mode": "skip"})

    # Mode: photo — match the uploaded fingerprint against the card print.
    try:
        ref = cv2.imread(reference_path, cv2.IMREAD_GRAYSCALE)
        probe = cv2.imread(probe_path, cv2.IMREAD_GRAYSCALE)
        if ref is None or probe is None:
            raise ValueError("Could not read one or both fingerprint images")

        # Try real matching; fall back to mock if SourceAFIS isn't wired.
        try:
            score = _real_match(ref, probe)
            engine = "sourceafis"
        except Exception:
            score = _mock_score(ref, probe)
            engine = "mock"

        triggered = score < FINGERPRINT_MATCH_MIN   # low score = mismatch = risk
        return _result(
            triggered, weight if triggered else 0,
            f"Fingerprint does not match citizenship card (score: {score:.0f}/100)" if triggered else None,
            None if triggered else f"Fingerprint matches citizenship card (score: {score:.0f}/100)",
            {"mode": "photo", "match_score": score,
             "threshold": FINGERPRINT_MATCH_MIN, "engine": engine},
        )
    except Exception as e:
        # FAIL CLOSED: unreadable / crash -> treat as a mismatch.
        return _result(True, weight,
                       "Fingerprint could not be verified — treated as a mismatch",
                       None, {"error": str(e), "mode": mode})


def _result(triggered, points, reason, pass_note, detail):
    """Pack into the standard shape every module returns."""
    return {
        "module": "fingerprint",
        "risk_added": points,
        "signals": {"fingerprint_mismatch": points} if triggered else {},
        "reasons": [reason] if (triggered and reason) else [],
        "passed": [pass_note] if (not triggered and pass_note) else [],
        "details": {"fingerprint": detail},
    }


# --- Standalone test ---
# From backend/:  python -m modules.fingerprint selftest <imgA> <imgB>
# (For the MOCK, any two images work — same image = match, different = mismatch.
#  Real fingerprint prints come at demo prep.)
if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 4 and sys.argv[1] == "selftest":
        a, b = sys.argv[2], sys.argv[3]

        def show(label, r):
            note = (r["reasons"] or r["passed"] or ["(none)"])[0]
            print(f"  {label:<28} -> +{r['risk_added']:<3} | {note}")
            if "match_score" in r["details"]["fingerprint"]:
                d = r["details"]["fingerprint"]
                print(f"  {'':<28}    score={d['match_score']} engine={d['engine']}")

        print("\n" + "=" * 60)
        print("  FINGERPRINT MODULE — mock-first selftest")
        print("=" * 60)
        show("same print (expect match)",    analyze_fingerprint(a, a, mode="photo"))
        show("different print (mismatch)",   analyze_fingerprint(a, b, mode="photo"))
        show("WebAuthn sensor (pass +0)",    analyze_fingerprint(mode="sensor"))
        show("skipped (pass +0)",            analyze_fingerprint(mode="skip"))
        show("missing file (fail closed)",   analyze_fingerprint("nope.jpg", "nope.jpg", mode="photo"))
        print()
    else:
        print('Usage: python -m modules.fingerprint selftest <imgA> <imgB>')