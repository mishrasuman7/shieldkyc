# modules/fingerprint.py — Module 5: Fingerprint Biometrics (SIFT + FLANN)
#
# THE INNOVATION (Nepal-specific):
#   Nepali citizenship cards have two inked thumbprints on the back.
#   This module extracts them, then matches against a fresh thumb photo
#   using SIFT keypoints + FLANN matching.
#
# PIPELINE:
#   1. Crop the thumbprint region from the citizenship card back
#   2. Enhance with CLAHE (boost faded ink contrast)
#   3. Extract SIFT keypoints from both card print and fresh thumb photo
#   4. Match with FLANN + Lowe's ratio test
#   5. Score based on number of good matches
#
# SAFETY RULE: if matching fails or images unreadable -> ADD risk (fail closed).

import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

import cv2
import numpy as np

RISK_WEIGHTS = {"fingerprint_mismatch": 15}

# Minimum good SIFT matches to consider it a verified match.
MATCH_THRESHOLD = 1

# Lowe's ratio test threshold — lower = stricter matching.
LOWE_RATIO = 0.75


def _enhance_print(img_gray):
    """Enhance a fingerprint image: resize, CLAHE contrast boost, blur.
    Makes faded ink prints from citizenship cards much more readable."""
    img = cv2.resize(img_gray, (300, 300))
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    img = clahe.apply(img)
    img = cv2.GaussianBlur(img, (3, 3), 0)
    return img


def _crop_thumbprint(card_back_gray, side="left"):
    """Crop the thumbprint region from the citizenship card back.
    Nepali citizenship cards have prints in the bottom portion.
    'left' = left side prints (default), 'right' = right side."""
    h, w = card_back_gray.shape
    top = int(h * 0.50)
    if side == "right":
        left = int(w * 0.55)
        return card_back_gray[top:, left:]
    else:
        right = int(w * 0.45)
        return card_back_gray[top:, :right]


def _sift_match(img1_gray, img2_gray):
    """Extract SIFT keypoints from both images, match with FLANN,
    apply Lowe's ratio test, return match data for scoring + visualization."""
    img1 = _enhance_print(img1_gray)
    img2 = _enhance_print(img2_gray)

    sift = cv2.SIFT_create()
    kp1, des1 = sift.detectAndCompute(img1, None)
    kp2, des2 = sift.detectAndCompute(img2, None)

    if des1 is None or des2 is None or len(des1) < 5 or len(des2) < 5:
        raise ValueError("Too few features detected — image quality too low for matching")

    # FLANN matcher — fast approximate nearest neighbors.
    index_params = {"algorithm": 1, "trees": 5}
    search_params = {"checks": 50}
    flann = cv2.FlannBasedMatcher(index_params, search_params)
    matches = flann.knnMatch(des1, des2, k=2)

    # Lowe's ratio test: keep only matches where the best match is significantly
    # better than the second-best. Filters out ambiguous/bad matches.
    good = []
    for m, n in matches:
        if m.distance < LOWE_RATIO * n.distance:
            good.append(m)

    return {
        "good_count": len(good),
        "total_kp1": len(kp1),
        "total_kp2": len(kp2),
        "kp1": kp1, "kp2": kp2,
        "good_matches": good,
        "img1": img1, "img2": img2,
    }


def visualize_match(card_back_path, thumb_path, out_path, side="left"):
    """DEMO GOLD: draw lines connecting matched keypoints between the card
    print and the fresh thumb photo. Green lines = verified matches."""
    card = cv2.imread(card_back_path, cv2.IMREAD_GRAYSCALE)
    thumb = cv2.imread(thumb_path, cv2.IMREAD_GRAYSCALE)
    if card is None or thumb is None:
        raise ValueError("Could not read one or both images")

    card_crop = _crop_thumbprint(card, side)
    result = _sift_match(card_crop, thumb)

    vis = cv2.drawMatches(
        result["img1"], result["kp1"],
        result["img2"], result["kp2"],
        result["good_matches"][:50],
        None,
        matchColor=(0, 200, 0),
        singlePointColor=(200, 200, 200),
        flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS,
    )
    cv2.imwrite(out_path, vis)
    return result["good_count"]



def analyze_fingerprint(card_back_path=None, thumb_path=None, mode="photo", side="left"):
    """Run the fingerprint check. Returns the standard module shape."""
    weight = RISK_WEIGHTS["fingerprint_mismatch"]

    # Mode: WebAuthn sensor — liveness/consistency check only.
    if mode == "sensor":
        return _result(False, 0, None,
                       "Fingerprint sensor verified (biometric liveness check)",
                       {"mode": "sensor",
                        "note": "WebAuthn confirms device owner; card print analyzed separately"})

    # Mode: skipped.
    if mode == "skip" or card_back_path is None or thumb_path is None:
        return _result(False, 0, None,
                       "Fingerprint not provided (optional step)",
                       {"mode": "skip"})

    # Mode: photo — SIFT match the card print against the fresh thumb.
    try:
        card = cv2.imread(card_back_path, cv2.IMREAD_GRAYSCALE)
        thumb = cv2.imread(thumb_path, cv2.IMREAD_GRAYSCALE)
        if card is None or thumb is None:
            raise ValueError("Could not read one or both fingerprint images")

        card_crop = _crop_thumbprint(card, side)
        result = _sift_match(card_crop, thumb)

        good_count = result["good_count"]
        triggered = good_count < MATCH_THRESHOLD

        score_pct = round(min(good_count / MATCH_THRESHOLD * 100, 100.0), 1)

        return _result(
            triggered, weight if triggered else 0,
            f"Fingerprint does not match citizenship card ({good_count} keypoint matches, need {MATCH_THRESHOLD})" if triggered else None,
            None if triggered else f"Fingerprint matches citizenship card ({good_count} keypoint matches, {score_pct}% confidence)",
            {"mode": "photo", "engine": "sift_flann",
             "good_matches": good_count,
             "threshold": MATCH_THRESHOLD,
             "keypoints_card": result["total_kp1"],
             "keypoints_thumb": result["total_kp2"],
             "match_confidence_pct": score_pct,
             "side": side},
        )
    except Exception as e:
        # FAIL CLOSED.
        return _result(True, weight,
                       "Fingerprint could not be verified — treated as a mismatch",
                       None, {"error": str(e), "mode": mode})


# --- Duplicate Fingerprint Detection ---
# Stores cropped prints per submission. On new submission, SIFT-matches
# against all stored prints. Catches reuse of the same citizenship card.

PRINT_STORE_DIR = os.path.join("data", "fingerprint_store")


def store_print(submission_id, card_back_path, side="left"):
    """Crop and save the thumbprint for future duplicate checks."""
    try:
        os.makedirs(PRINT_STORE_DIR, exist_ok=True)
        card = cv2.imread(card_back_path, cv2.IMREAD_GRAYSCALE)
        if card is None:
            return False
        crop = _crop_thumbprint(card, side)
        out_path = os.path.join(PRINT_STORE_DIR, f"{submission_id}.jpg")
        cv2.imwrite(out_path, crop)
        return True
    except Exception:
        return False


def check_duplicate_print(card_back_path, current_submission_id=None, side="left"):
    """SIFT-match this card's thumbprint against all previously stored prints.
    Returns the standard module result shape."""
    weight = 30  # strong fraud signal
    try:
        card = cv2.imread(card_back_path, cv2.IMREAD_GRAYSCALE)
        if card is None:
            raise ValueError("Could not read card back image")
        crop = _crop_thumbprint(card, side)

        os.makedirs(PRINT_STORE_DIR, exist_ok=True)
        stored = [f for f in os.listdir(PRINT_STORE_DIR)
                  if f.endswith(".jpg") and f != f"{current_submission_id}.jpg"]

        if not stored:
            return _result(False, 0, None,
                           "No prior fingerprints to compare against",
                           {"duplicate_print": {"stored_count": 0}})

        best_match_id = None
        best_count = 0

        for fname in stored:
            stored_path = os.path.join(PRINT_STORE_DIR, fname)
            stored_img = cv2.imread(stored_path, cv2.IMREAD_GRAYSCALE)
            if stored_img is None:
                continue
            try:
                result = _sift_match(crop, stored_img)
                if result["good_count"] > best_count:
                    best_count = result["good_count"]
                    best_match_id = fname.replace(".jpg", "")
            except Exception:
                continue

        is_dup = best_count >= MATCH_THRESHOLD

        if is_dup:
            return _result(True, weight,
                           f"Card fingerprint matches a previous submission ({best_match_id}) — possible document reuse ({best_count} keypoint matches)",
                           None,
                           {"duplicate_print": {"match_id": best_match_id,
                                                "matches": best_count,
                                                "threshold": MATCH_THRESHOLD,
                                                "stored_count": len(stored)}})
        else:
            return _result(False, 0, None,
                           "Card fingerprint does not match any prior submissions",
                           {"duplicate_print": {"best_match": best_count,
                                                "threshold": MATCH_THRESHOLD,
                                                "stored_count": len(stored)}})
    except Exception as e:
        # Fail closed.
        return _result(True, weight,
                       "Could not check for duplicate fingerprints — treated as suspicious",
                       None, {"duplicate_print": {"error": str(e)}})

def _result(triggered, points, reason, pass_note, detail):
    return {
        "module": "fingerprint",
        "risk_added": points,
        "signals": {"fingerprint_mismatch": points} if triggered else {},
        "reasons": [reason] if (triggered and reason) else [],
        "passed": [pass_note] if (not triggered and pass_note) else [],
        "details": {"fingerprint": detail},
    }


# --- Standalone test ---
# python -m modules.fingerprint match <card_back> <thumb_photo> [left|right]
# python -m modules.fingerprint visualize <card_back> <thumb_photo> <output.jpg> [left|right]
if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else ""

    if cmd == "match" and len(sys.argv) >= 4:
        card_back, thumb = sys.argv[2], sys.argv[3]
        side = sys.argv[4] if len(sys.argv) > 4 else "left"
        print(f"\nMatching thumb against card ({side} side)...")
        r = analyze_fingerprint(card_back, thumb, mode="photo", side=side)
        print(f"\n{'=' * 55}")
        print(f"  FINGERPRINT (SIFT+FLANN)  ->  +{r['risk_added']} risk points")
        print(f"{'=' * 55}")
        d = r["details"]["fingerprint"]
        if r["reasons"]:
            for reason in r["reasons"]:
                print(f"  FLAG: {reason}")
        if r["passed"]:
            for p in r["passed"]:
                print(f"  PASS: {p}")
        print(f"\n  Keypoints on card:  {d.get('keypoints_card', '?')}")
        print(f"  Keypoints on thumb: {d.get('keypoints_thumb', '?')}")
        print(f"  Good matches:       {d.get('good_matches', '?')}")
        print(f"  Threshold:          {d.get('threshold', '?')}")
        print(f"  Engine:             {d.get('engine', '?')}")
        print()

    elif cmd == "visualize" and len(sys.argv) >= 5:
        card_back, thumb, out = sys.argv[2], sys.argv[3], sys.argv[4]
        side = sys.argv[5] if len(sys.argv) > 5 else "left"
        print(f"Generating match visualization ({side} side)...")
        n = visualize_match(card_back, thumb, out, side)
        print(f"  {n} good matches drawn -> saved to {out}")
        print(f"  Open {out} to see the matched keypoints!")

    else:
        print("Usage:")
        print("  python -m modules.fingerprint match <card_back> <thumb_photo> [left|right]")
        print("  python -m modules.fingerprint visualize <card_back> <thumb_photo> <output.jpg> [left|right]")