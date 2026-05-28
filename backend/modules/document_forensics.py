# modules/document_forensics.py — Module 1: Document Forensics
# Input:  path to an ID document image
# Output: a dict with risk points, plain-English reasons, and raw numbers
#
# THREE CHECKS:
#   1. ELA (Error Level Analysis) -> detects edited/pasted regions  -> "tamper"
#   2. EXIF metadata             -> missing = screenshot signature  -> "missing_exif"
#                                -> editing-software tag (Photoshop) -> "editing_software"
#   3. FFT / Moiré               -> photo-of-a-screen detection      -> "screen_replay"
#
# SAFETY RULE (non-negotiable): if any check crashes or can't analyze the
# image, it ADDS its risk points. An unanalyzable document is treated as
# suspicious, never waved through. This is why every check is wrapped in
# try/except that fails *closed*.

import io
import cv2
import numpy as np
from PIL import Image, ImageChops
from PIL.ExifTags import TAGS

# --- Risk weights (from your spec). Keep them here so they're easy to tune. ---
RISK_WEIGHTS = {
    "tamper": 30,
    "editing_software": 25,
    "missing_exif": 12,
    "screen_replay": 20,
}

# --- Thresholds you will CALIBRATE on your own images (see test block) ---
ELA_MAX_THRESHOLD = 95.0     # higher ELA peak = more likely edited
SCREEN_REPLAY_RATIO = 4.5    # higher FFT peak ratio = more likely a screen photo


def _check_ela(image_path):
    """Recompress the image and measure where it 'breaks'. Freshly edited or
    pasted regions compress differently from the rest, showing up as bright
    spots in the difference. We flag on the brightest difference (the peak)."""
    weight = RISK_WEIGHTS["tamper"]
    try:
        original = Image.open(image_path).convert("RGB")

        # Re-save as JPEG at a known quality, then reopen. This is the trick:
        # an untouched image compresses uniformly; edited areas don't.
        buf = io.BytesIO()
        original.save(buf, "JPEG", quality=90)
        buf.seek(0)
        recompressed = Image.open(buf)

        # Pixel-by-pixel difference between original and recompressed.
        diff = ImageChops.difference(original, recompressed)
        ela = np.asarray(diff, dtype=np.float32)

        max_diff = float(ela.max())    # brightest single point (the tell)
        mean_diff = float(ela.mean())  # overall noise level (for context)

        triggered = max_diff >= ELA_MAX_THRESHOLD
        return {
            "name": "tamper",
            "triggered": triggered,
            "points": weight if triggered else 0,
            "reason": "Document shows signs of digital editing (error-level analysis)" if triggered else None,
            "pass_note": None if triggered else "No editing artifacts detected in the document",
            "detail": {"ela_max": round(max_diff, 1), "ela_mean": round(mean_diff, 2),
                       "threshold": ELA_MAX_THRESHOLD},
        }
    except Exception as e:
        # FAIL CLOSED: could not analyze -> treat as tampered.
        return {
            "name": "tamper", "triggered": True, "points": weight,
            "reason": "Document could not be analyzed for editing — treated as suspicious",
            "pass_note": None, "detail": {"error": str(e)},
        }


def _check_metadata(image_path):
    """Camera photos carry EXIF metadata (camera model, timestamp, etc.).
    Screenshots and downloads usually have NONE. Edited files sometimes carry
    a 'Software' tag like 'Adobe Photoshop'. Returns a LIST because it can
    raise two separate signals."""
    results = []
    try:
        img = Image.open(image_path)
        exif = img.getexif()

        if not exif or len(exif) == 0:
            # No metadata at all — classic screenshot/download signature.
            results.append({
                "name": "missing_exif", "triggered": True,
                "points": RISK_WEIGHTS["missing_exif"],
                "reason": "Document has no camera metadata — likely a screenshot or download",
                "pass_note": None, "detail": {"exif_tags": 0},
            })
            return results

        # Metadata exists — look for an editing-software fingerprint.
        software = ""
        for tag_id, value in exif.items():
            if TAGS.get(tag_id) == "Software":
                software = str(value)

        editing_tools = ["photoshop", "gimp", "paint", "lightroom", "pixelmator", "affinity"]
        is_edited = any(tool in software.lower() for tool in editing_tools)

        results.append({
            "name": "editing_software",
            "triggered": is_edited,
            "points": RISK_WEIGHTS["editing_software"] if is_edited else 0,
            "reason": f"Document was processed by editing software ({software})" if is_edited else None,
            "pass_note": None if is_edited else "Document metadata is intact with no editing-software trace",
            "detail": {"software": software or "none", "exif_tags": len(exif)},
        })
        return results
    except Exception as e:
        # FAIL CLOSED: unreadable metadata -> treat as missing EXIF.
        return [{
            "name": "missing_exif", "triggered": True,
            "points": RISK_WEIGHTS["missing_exif"],
            "reason": "Document metadata could not be read — treated as suspicious",
            "pass_note": None, "detail": {"error": str(e)},
        }]


def _check_screen_replay(image_path):
    """Photographing a screen introduces a faint regular grid (Moiré pattern)
    from the screen's pixels. In the frequency domain (FFT) that grid shows up
    as sharp peaks away from the center. We measure how 'peaky' the spectrum
    is relative to its baseline."""
    weight = RISK_WEIGHTS["screen_replay"]
    try:
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError("OpenCV could not read the image")

        # Downscale large images for speed and consistent thresholds.
        h, w = img.shape
        scale = 512.0 / max(h, w)
        if scale < 1.0:
            img = cv2.resize(img, (int(w * scale), int(h * scale)))

        # 2D FFT, shifted so low frequencies sit in the center.
        f = np.fft.fftshift(np.fft.fft2(img))
        logmag = np.log1p(np.abs(f))

        # Zero out the central low-frequency blob — that's normal image content,
        # not the screen grid we're hunting for.
        cy, cx = np.array(logmag.shape) // 2
        logmag[cy - 20:cy + 20, cx - 20:cx + 20] = 0

        periphery = logmag[logmag > 0]
        peak = float(np.percentile(periphery, 99.9))   # strongest outer peaks
        median = float(np.median(periphery)) or 1e-6   # baseline
        ratio = peak / median

        triggered = ratio >= SCREEN_REPLAY_RATIO
        return {
            "name": "screen_replay",
            "triggered": triggered,
            "points": weight if triggered else 0,
            "reason": "Document appears to be a photo of a screen (Moiré pattern detected)" if triggered else None,
            "pass_note": None if triggered else "No screen-replay (Moiré) pattern detected",
            "detail": {"fft_peak_ratio": round(ratio, 2), "threshold": SCREEN_REPLAY_RATIO},
        }
    except Exception as e:
        # FAIL CLOSED: could not run FFT -> treat as screen replay.
        return {
            "name": "screen_replay", "triggered": True, "points": weight,
            "reason": "Document could not be checked for screen-replay — treated as suspicious",
            "pass_note": None, "detail": {"error": str(e)},
        }


def analyze_document(image_path):
    """Run all three checks and fuse them into one module result.
    This is the function the pipeline (and main.py) will call."""
    # Gather every signal. _check_metadata returns a list; the others single dicts.
    signals = [_check_ela(image_path)]
    signals += _check_metadata(image_path)
    signals.append(_check_screen_replay(image_path))

    risk_added = 0
    breakdown = {}
    reasons = []
    passed = []
    details = {}

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
        "module": "document_forensics",
        "risk_added": risk_added,
        "signals": breakdown,    # only triggered signals, feeds signal_breakdown
        "reasons": reasons,      # plain-English flags, feeds explanation[]
        "passed": passed,        # clean-signal notes
        "details": details,      # raw numbers for the admin evidence panel
    }


# --- Standalone test / calibration tool ---
# Run from the backend/ folder:  python -m modules.document_forensics <image_path>
if __name__ == "__main__":
    import sys, json
    if len(sys.argv) < 2:
        print("Usage: python -m modules.document_forensics <path-to-image>")
        sys.exit(1)

    result = analyze_document(sys.argv[1])
    print("\n" + "=" * 55)
    print(f"  DOCUMENT FORENSICS  ->  +{result['risk_added']} risk points")
    print("=" * 55)
    if result["reasons"]:
        print("  FLAGS:")
        for r in result["reasons"]:
            print(f"    - {r}")
    if result["passed"]:
        print("  PASSED:")
        for p in result["passed"]:
            print(f"    - {p}")
    print("\n  RAW NUMBERS (use these to calibrate thresholds):")
    print(json.dumps(result["details"], indent=4))
    print()