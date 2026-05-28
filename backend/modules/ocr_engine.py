# modules/ocr_engine.py — Module 6: OCR Name Verification
# Inputs:  path to ID document image, the name the user TYPED into the form
# Output:  dict with risk points, plain-English reason, raw numbers
#
# ONE CHECK:
#   name_mismatch (+20) — the typed name does not appear on the document.
#   Uses FUZZY matching so small OCR errors don't cause false flags.
#
# SAFETY RULE: if OCR crashes or reads NO text, we cannot confirm the name
# matches -> we ADD the mismatch points. We never assume a match we couldn't
# verify. Fails CLOSED, like every other module.

import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

import cv2  # for image loading (not strictly needed for OCR, but common in image processing)

from difflib import SequenceMatcher   # built into Python — no extra install
import easyocr

RISK_WEIGHTS = {"name_mismatch": 20}

# How similar a name part must be to OCR text to count as "found" (0.0-1.0).
# 0.80 tolerates small OCR errors (1-2 wrong letters in a normal-length word)
# while still rejecting a genuinely different name. Tunable.
NAME_MATCH_RATIO = 0.80

# Cap the longest image side before OCR. Big images make EasyOCR's neural net
# allocate huge tensors (the "not enough memory" error). 1600px is plenty to
# read a name off an ID card, and it keeps memory + speed sane.
OCR_MAX_DIM = 1000

# EasyOCR's Reader is expensive to create (loads models), so we build it ONCE
# and reuse it. gpu=False because your laptop has no NVIDIA GPU — this avoids
# CUDA warnings and forces clean CPU mode.
_reader = None
def _get_reader():
    global _reader
    if _reader is None:
        # ['en'] = English. For Devanagari (Nepali script) names you could use
        # ['en', 'ne'], but romanized English names are far more reliable for OCR,
        # and Demo names are in English — so we keep it to 'en'.
        _reader = easyocr.Reader(["en"], gpu=False)
    return _reader


def _similarity(a, b):
    """0.0-1.0 similarity between two lowercase strings."""
    return SequenceMatcher(None, a, b).ratio()

def _load_resized(image_path):
    """Read the image and shrink it if it's larger than OCR_MAX_DIM on its
    longest side. Returns a numpy array EasyOCR can read directly."""
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError("Could not read the document image")
    h, w = img.shape[:2]
    scale = OCR_MAX_DIM / max(h, w)
    if scale < 1.0:   # only ever shrink, never enlarge
        img = cv2.resize(img, (int(w * scale), int(h * scale)),
                         interpolation=cv2.INTER_AREA)  # INTER_AREA = best for downscaling
    return img


def _check_name(image_path, submitted_name):
    weight = RISK_WEIGHTS["name_mismatch"]
    try:
        reader = _get_reader()
        # detail=0 -> return just the text strings, not bounding boxes.
        detected = reader.readtext(_load_resized(image_path), detail=0, canvas_size=1000)
        detected_text = " ".join(detected).lower()
        detected_tokens = detected_text.split()

        if not detected_tokens:
            raise ValueError("OCR found no readable text on the document")

        # Break the submitted name into parts, ignore tiny tokens (initials).
        name_parts = [p for p in submitted_name.lower().split() if len(p) >= 2]
        if not name_parts:
            raise ValueError("Submitted name is empty or too short to verify")

        # For each name part, find its best fuzzy match among the OCR tokens.
        part_scores = {}
        for part in name_parts:
            best = max((_similarity(part, tok) for tok in detected_tokens), default=0.0)
            part_scores[part] = round(best, 2)

        # A part is "found" if its best match clears the ratio threshold.
        found = {p: s >= NAME_MATCH_RATIO for p, s in part_scores.items()}
        all_found = all(found.values())

        triggered = not all_found   # ANY missing part = mismatch = risk
        missing = [p for p, ok in found.items() if not ok]

        return {
            "name": "name_mismatch",
            "triggered": triggered,
            "points": weight if triggered else 0,
            "reason": (f"Submitted name '{submitted_name}' does not match the name on the "
                       f"document (missing: {', '.join(missing)})") if triggered else None,
            "pass_note": None if triggered else f"Submitted name '{submitted_name}' matches the document",
            "detail": {"submitted_name": submitted_name,
                       "part_match_scores": part_scores,
                       "match_ratio_threshold": NAME_MATCH_RATIO,
                       # Trim stored OCR text so the evidence panel isn't huge.
                       "detected_text_sample": detected_text[:200]},
        }
    except Exception as e:
        # FAIL CLOSED: can't read or verify -> treat as a name mismatch.
        return {
            "name": "name_mismatch", "triggered": True, "points": weight,
            "reason": "Could not read the name from the document — treated as a mismatch",
            "pass_note": None, "detail": {"error": str(e), "submitted_name": submitted_name},
        }


def analyze_name(image_path, submitted_name):
    """Run the name check and fuse into one module result (same shape as others)."""
    s = _check_name(image_path, submitted_name)

    risk_added = s["points"] if s["triggered"] else 0
    breakdown = {s["name"]: s["points"]} if s["triggered"] else {}
    reasons = [s["reason"]] if (s["triggered"] and s["reason"]) else []
    passed = [s["pass_note"]] if (not s["triggered"] and s.get("pass_note")) else []

    return {
        "module": "ocr_name",
        "risk_added": risk_added,
        "signals": breakdown,
        "reasons": reasons,
        "passed": passed,
        "details": {s["name"]: s["detail"]},
    }


# --- Standalone test ---
# Run from backend/:  python -m modules.ocr_engine <document_image> "<submitted name>"
if __name__ == "__main__":
    import sys, json
    if len(sys.argv) < 3:
        print('Usage: python -m modules.ocr_engine <document_image> "<submitted name>"')
        sys.exit(1)

    result = analyze_name(sys.argv[1], sys.argv[2])
    print("\n" + "=" * 55)
    print(f"  OCR NAME VERIFICATION  ->  +{result['risk_added']} risk points")
    print("=" * 55)
    if result["reasons"]:
        print("  FLAGS:")
        for r in result["reasons"]:
            print(f"    - {r}")
    if result["passed"]:
        print("  PASSED:")
        for p in result["passed"]:
            print(f"    - {p}")
    print("\n  RAW NUMBERS:")
    print(json.dumps(result["details"], indent=4))
    print()