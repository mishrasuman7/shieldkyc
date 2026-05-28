# modules/duplicate_detection.py — Module 3: Duplicate Face Detection
# Input:  a face image (selfie)
# Output: dict with risk points, plain-English reason, raw numbers
#
# WHAT IT DOES:
#   Converts the face to a 512-D ArcFace vector and searches a stored index of
#   all previously-seen faces. If a near-identical face already exists under a
#   different submission, it's the same person on multiple accounts -> +25.
#
# FAISS with a NUMPY FALLBACK: if faiss-cpu isn't installed, we search with
# numpy instead. Same math (cosine similarity), identical results, fast enough
# for hackathon scale. The module never blocks on a FAISS install problem.
#
# SAFETY RULE: if the face can't be read/analyzed, we ADD the duplicate points
# (fail closed) — an unanalyzable face is never silently cleared.
#
# SELF-CONTAMINATION TRAP (your spec's warning): the order is SEARCH first,
# ADD later. A new submission is checked against PAST faces, then added only
# after it's processed — so it can never match itself. For clean tests, always
# clear_index() first, or your own test face flags as its own duplicate.

import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

import json
import numpy as np
from modules.face_match import get_embedding   # reuse Module 2's ArcFace

# Optional FAISS — degrade gracefully to numpy if unavailable.
try:
    import faiss
    _HAS_FAISS = True
except Exception:
    _HAS_FAISS = False

RISK_WEIGHTS = {"duplicate_face": 25}

# A stored face counts as the SAME person if cosine distance <= this.
# Expressed in the same distance terms as Module 2's face match (0=identical),
# and set to match it for consistency. Calibrate alongside FACE_MATCH_THRESHOLD.
DUPLICATE_DISTANCE_THRESHOLD = 0.55

EMBED_DIM = 512
INDEX_DIR = os.path.join("data", "faiss_index")
EMB_PATH = os.path.join(INDEX_DIR, "embeddings.npy")
IDS_PATH = os.path.join(INDEX_DIR, "ids.json")


def _normalize(vec):
    """Unit-normalize so a dot product equals cosine similarity."""
    v = np.asarray(vec, dtype=np.float32)
    norm = np.linalg.norm(v)
    return v / norm if norm > 0 else v


def _load_store():
    """Load stored (embeddings, ids). Returns empty arrays if nothing saved yet."""
    if os.path.exists(EMB_PATH) and os.path.exists(IDS_PATH):
        embeddings = np.load(EMB_PATH)
        with open(IDS_PATH) as f:
            ids = json.load(f)
        return embeddings, ids
    return np.zeros((0, EMBED_DIM), dtype=np.float32), []


def _save_store(embeddings, ids):
    os.makedirs(INDEX_DIR, exist_ok=True)
    np.save(EMB_PATH, embeddings)
    with open(IDS_PATH, "w") as f:
        json.dump(ids, f)


def clear_index():
    """Wipe the index. Run before clean tests to avoid self-contamination."""
    for p in (EMB_PATH, IDS_PATH):
        if os.path.exists(p):
            os.remove(p)
    print("Duplicate index cleared.")


def add_face(submission_id, image_path):
    """Store a face AFTER its submission is processed. Called by the pipeline,
    never before the duplicate check (see self-contamination note)."""
    try:
        emb = _normalize(get_embedding(image_path))
    except Exception as e:
        print(f"  [add_face] skipped — could not read face: {e}")
        return False
    embeddings, ids = _load_store()
    embeddings = np.vstack([embeddings, emb[None, :]])
    ids.append(submission_id)
    _save_store(embeddings, ids)
    return True


def _search(query_emb, embeddings):
    """Return (best_similarity, best_row_index) using FAISS if available,
    else numpy. Both expect normalized vectors -> dot product = cosine sim."""
    if _HAS_FAISS:
        index = faiss.IndexFlatIP(EMBED_DIM)   # inner product on unit vectors
        index.add(embeddings)
        sims, idxs = index.search(query_emb[None, :], 1)
        return float(sims[0][0]), int(idxs[0][0])
    sims = embeddings @ query_emb              # numpy fallback
    best_i = int(np.argmax(sims))
    return float(sims[best_i]), best_i


def check_duplicate(image_path):
    """Search the stored index for a face matching this one. Does NOT add."""
    weight = RISK_WEIGHTS["duplicate_face"]
    try:
        query = _normalize(get_embedding(image_path))
        embeddings, ids = _load_store()

        if len(ids) == 0:
            # Nothing stored yet -> cannot be a duplicate.
            return _result(False, 0, None,
                           "No matching face found in prior submissions",
                           {"stored_faces": 0, "engine": "faiss" if _HAS_FAISS else "numpy"})

        best_sim, best_i = _search(query, embeddings)
        distance = 1.0 - best_sim
        is_dup = distance <= DUPLICATE_DISTANCE_THRESHOLD
        match_id = ids[best_i] if is_dup else None

        return _result(
            is_dup, weight if is_dup else 0,
            f"This face matches an existing submission ({match_id}) — possible duplicate account" if is_dup else None,
            None if is_dup else "No matching face found in prior submissions",
            {"stored_faces": len(ids), "best_match_id": ids[best_i],
             "distance": round(distance, 4), "threshold": DUPLICATE_DISTANCE_THRESHOLD,
             "engine": "faiss" if _HAS_FAISS else "numpy"},
        )
    except Exception as e:
        # FAIL CLOSED: unreadable face -> treat as suspicious.
        return _result(True, weight,
                       "Could not check for duplicate faces — treated as suspicious",
                       None, {"error": str(e)})


def _result(triggered, points, reason, pass_note, detail):
    """Pack into the standard module shape every other module returns."""
    return {
        "module": "duplicate_detection",
        "risk_added": points,
        "signals": {"duplicate_face": points} if triggered else {},
        "reasons": [reason] if (triggered and reason) else [],
        "passed": [pass_note] if (not triggered and pass_note) else [],
        "details": {"duplicate_face": detail},
    }


# --- Standalone test / self-contamination demo ---
# From backend/:
#   python -m modules.duplicate_detection clear
#   python -m modules.duplicate_detection selftest <faceA_img> <faceB_img>
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""

    if cmd == "clear":
        clear_index()

    elif cmd == "selftest" and len(sys.argv) >= 4:
        face_a, face_b = sys.argv[2], sys.argv[3]
        print(f"\nEngine: {'FAISS' if _HAS_FAISS else 'numpy fallback'}")
        print("\n[1] Clearing index for a clean test...")
        clear_index()

        print("\n[2] Checking face A against an EMPTY index (expect: no duplicate, +0)")
        r = check_duplicate(face_a)
        print(f"    -> +{r['risk_added']}  | {(r['reasons'] or r['passed'])[0]}")

        print("\n[3] Adding face A to the index as submission TEST-A...")
        add_face("TEST-A", face_a)

        print("\n[4] Checking face A AGAIN (expect: DUPLICATE of TEST-A, +25)")
        r = check_duplicate(face_a)
        print(f"    -> +{r['risk_added']}  | {(r['reasons'] or r['passed'])[0]}")
        print(f"       distance={r['details']['duplicate_face'].get('distance')}")

        print("\n[5] Checking face B, a DIFFERENT person (expect: no duplicate, +0)")
        r = check_duplicate(face_b)
        print(f"    -> +{r['risk_added']}  | {(r['reasons'] or r['passed'])[0]}")
        print(f"       distance={r['details']['duplicate_face'].get('distance')}")

        print("\n[6] Cleaning up (clearing test index)...")
        clear_index()
        print("\nSelftest done.\n")

    else:
        print("Usage:")
        print("  python -m modules.duplicate_detection clear")
        print("  python -m modules.duplicate_detection selftest <faceA_img> <faceB_img>")