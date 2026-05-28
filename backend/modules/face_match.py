# modules/face_match.py — Module 2: Face Match + Liveness
# Inputs:  path to ID document image, path to selfie image
# Output:  dict with risk points, plain-English reasons, raw numbers
#
# TWO CHECKS:
#   1. Face match  -> DeepFace.verify(ID, selfie) with ArcFace 512D embeddings
#                     -> "face_mismatch" (+40), the single strongest signal
#   2. Liveness    -> sharpness + color analysis of the selfie
#                     -> "liveness_failed" (+20) for printed/screen re-captures
#
# SAFETY RULE: your spec is explicit — "An unanalyzable face = treat as
# mismatch." If DeepFace can't find or compare a face (bad image, no face,
# crash), we ADD the mismatch points. A fraudster cannot dodge the check by
# submitting an image that breaks it. Every check fails CLOSED.

# Quiet TensorFlow's startup noise — must be set BEFORE importing deepface.
import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

import cv2
import numpy as np
from deepface import DeepFace

RISK_WEIGHTS = {
    "face_mismatch": 40,
    "liveness_failed": 20,
}

# KYC face-match threshold. STRICTER than DeepFace's default 0.68 because, for
# fraud detection, a false "match" (letting an impostor through) is far worse
# than a false "mismatch" (which only routes to human review — nobody is
# auto-rejected). Calibrate this BETWEEN your real-match distance and your
# impostor distance (see test below).
FACE_MATCH_THRESHOLD = 0.55

# Cap image size before face processing — keeps peak RAM low on 8GB machines.
FACE_MAX_DIM = 1000

# Detector backend. "retinaface" is far more reliable at actually FINDING the
# face than the old "opencv" Haar cascade — important so a real selfie in
# Demo A doesn't get a false "no face -> mismatch". It downloads a small model
# on the very first verify call (one-time), then caches it.
DETECTOR = "opencv"

def get_embedding(image_path):
    """Return ONE 512-D ArcFace embedding for the face in image_path.
    Module 3 imports this so duplicate detection uses the EXACT same model
    and vector space as face matching — they must match to compare correctly.
    Raises on no-face/error so the caller can fail closed."""
    reps = DeepFace.represent(
        img_path=image_path,
        model_name="ArcFace",          # same model as verify()
        detector_backend=DETECTOR,     # same detector
        enforce_detection=True,        # no face -> raises -> caller fails closed
    )
    # represent() returns a list (one entry per detected face); take the first.
    return reps[0]["embedding"]

# --- Liveness thresholds you will CALIBRATE on real selfies (lenient defaults
#     so genuine webcam selfies pass cleanly) ---
BLUR_MIN_SHARPNESS = 40.0    # below this = suspiciously blurry (re-photo)
SATURATION_MIN = 18.0        # below this = washed-out (grayscale print/screen)


def _shrink_in_place(image_path):
    """Downscale an image on disk if it's larger than FACE_MAX_DIM on its
    longest side, overwriting it with the smaller version. Keeps DeepFace's
    memory footprint low. Returns the path (unchanged) for convenience.
    Safe to call repeatedly — only ever shrinks."""
    import cv2
    img = cv2.imread(image_path)
    if img is None:
        return image_path  # let the downstream check fail closed normally
    h, w = img.shape[:2]
    scale = FACE_MAX_DIM / max(h, w)
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)),
                         interpolation=cv2.INTER_AREA)
        cv2.imwrite(image_path, img)
    return image_path


def _check_face_match(id_image_path, selfie_image_path):
    """Compare the two faces with ArcFace. verified=True means same person."""
    weight = RISK_WEIGHTS["face_mismatch"]
    try:
        _shrink_in_place(id_image_path)
        _shrink_in_place(selfie_image_path)
        result = DeepFace.verify(
            img1_path=id_image_path,
            img2_path=selfie_image_path,
            model_name="ArcFace",          # 512D embeddings, per spec
            detector_backend=DETECTOR,
            enforce_detection=True,        # raise if no face -> we fail closed
        )
        # verified = bool(result["verified"])
        # distance = float(result["distance"])

        distance = float(result["distance"])
        default_threshold = float(result["threshold"])   # DeepFace's own (~0.68)
        # We override with OUR stricter threshold — decision is ours, not DeepFace's.
        verified = distance <= FACE_MATCH_THRESHOLD
        # Rough human-friendly confidence: closer distance = higher % match.
        confidence = round(max(0.0, 1.0 - distance) * 100, 1)

        triggered = not verified   # a MISMATCH is what adds risk
        return {
            "name": "face_mismatch",
            "triggered": triggered,
            "points": weight if triggered else 0,
            "reason": f"Selfie face does not match document photo ({confidence}% match confidence)" if triggered else None,
            "pass_note": None if triggered else f"Selfie matches the document photo ({confidence}% confidence)",
            "detail": {"verified": verified, "distance": round(distance, 4),
                       "match_confidence_pct": confidence,
                       "threshold": FACE_MATCH_THRESHOLD,
                       "deepface_default": round(default_threshold, 4)},
        }
    except Exception as e:
        # FAIL CLOSED: no face found / unreadable / crash -> treat as mismatch.
        return {
            "name": "face_mismatch", "triggered": True, "points": weight,
            "reason": "Could not verify the face against the document — treated as a mismatch",
            "pass_note": None, "detail": {"error": str(e)},
        }


def _check_liveness(selfie_image_path):
    """Cheap heuristic for printed/screen re-captures. A live webcam selfie is
    reasonably sharp and color-rich; flat printouts and screen photos tend to
    be blurry or washed out. This is a HEURISTIC, not a guarantee — tune the
    two thresholds on real selfies."""
    weight = RISK_WEIGHTS["liveness_failed"]
    try:
        img = cv2.imread(selfie_image_path)
        if img is None:
            raise ValueError("OpenCV could not read the selfie")

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Laplacian variance = sharpness. Low = blurry.
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        # Mean saturation in HSV. Low = grayscale-ish (print/screen tell).
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        saturation = float(hsv[:, :, 1].mean())

        # Conservative: flag only if clearly blurry OR clearly washed out.
        too_blurry = sharpness < BLUR_MIN_SHARPNESS
        too_flat = saturation < SATURATION_MIN
        triggered = too_blurry or too_flat

        return {
            "name": "liveness_failed",
            "triggered": triggered,
            "points": weight if triggered else 0,
            "reason": "Selfie may be a printed photo or screen capture, not a live capture" if triggered else None,
            "pass_note": None if triggered else "Selfie appears to be a live capture",
            "detail": {"sharpness": round(sharpness, 1), "saturation": round(saturation, 1),
                       "blur_threshold": BLUR_MIN_SHARPNESS, "saturation_threshold": SATURATION_MIN},
        }
    except Exception as e:
        # FAIL CLOSED: can't assess liveness -> treat as failed.
        return {
            "name": "liveness_failed", "triggered": True, "points": weight,
            "reason": "Selfie liveness could not be assessed — treated as suspicious",
            "pass_note": None, "detail": {"error": str(e)},
        }


def analyze_face(id_image_path, selfie_image_path):
    """Run both checks and fuse into one module result, same shape as Module 1."""
    signals = [
        _check_face_match(id_image_path, selfie_image_path),
        _check_liveness(selfie_image_path),
    ]

    risk_added = 0
    breakdown, reasons, passed, details = {}, [], [], {}
    for s in signals:
        if s["triggered"]:
            risk_added += s["points"]
            breakdown[s["name"]] = s["points"]
            if s["reason"]:
                reasons.append(s["reason"])
        elif s.get("pass_note"):
            passed.append(s["pass_note"])
        details[s["name"]] = s["detail"]

    return {
        "module": "face_match",
        "risk_added": risk_added,
        "signals": breakdown,
        "reasons": reasons,
        "passed": passed,
        "details": details,
    }


# --- Standalone test ---
# Run from backend/:  python -m modules.face_match <id_image> <selfie_image>
if __name__ == "__main__":
    import sys, json
    if len(sys.argv) < 3:
        print("Usage: python -m modules.face_match <id_image> <selfie_image>")
        sys.exit(1)

    result = analyze_face(sys.argv[1], sys.argv[2])
    print("\n" + "=" * 55)
    print(f"  FACE MATCH + LIVENESS  ->  +{result['risk_added']} risk points")
    print("=" * 55)
    if result["reasons"]:
        print("  FLAGS:")
        for r in result["reasons"]:
            print(f"    - {r}")
    if result["passed"]:
        print("  PASSED:")
        for p in result["passed"]:
            print(f"    - {p}")
    print("\n  RAW NUMBERS (use these to calibrate liveness thresholds):")
    print(json.dumps(result["details"], indent=4))
    print()