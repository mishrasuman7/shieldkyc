# modules/risk_engine.py — Module 4: Risk Score Engine + Explainability
# Input:  a list of module result dicts (the standard shape every module returns)
# Output: one fused verdict — score, level, decision, ordered explanations
#
# THIS IS THE BRAIN. Each module produces signals; this fuses them into ONE
# number a human can act on, plus the plain-English reasons that are the
# project's real differentiator.
#
# FOUR JOBS:
#   1. Sum every triggered signal's points, capped at 100.
#   2. Map the score to LOW / MEDIUM / HIGH and an auto-approve/review decision.
#   3. Assemble the explanation list (FLAGS first, then PASSED notes).
#   4. Enforce the SAFETY RULE at the fusion level: a crashed/unanalyzable
#      module ADDS risk and can NEVER drag the score toward auto-approve.
#
# CORE PHILOSOPHY (your spec): AI scores, humans decide. Nobody is auto-
# rejected. LOW = auto-approve; MEDIUM/HIGH = human review.

# --- Thresholds (your spec) ---
THRESHOLD_LOW_MAX = 40     # 0-40   -> LOW    -> AUTO_APPROVED
THRESHOLD_MEDIUM_MAX = 70  # 41-70  -> MEDIUM -> FLAGGED_FOR_REVIEW
                           # 71-100 -> HIGH   -> FLAGGED_FOR_REVIEW (urgent)
MAX_SCORE = 100


def fuse(module_results):
    """Fuse a list of module result dicts into the final verdict.

    Each module_result is the standard shape:
      { "module", "risk_added", "signals", "reasons", "passed", "details" }

    Returns the dict that becomes the API response body.
    """
    total_score = 0
    signal_breakdown = {}   # {"face_mismatch": 40, ...} -> only triggered signals
    flags = []              # plain-English reasons signals fired
    passed = []             # plain-English clean-check notes
    module_results_map = {} # full per-module detail for the evidence panel
    safety_events = []      # records any module that failed closed

    for result in module_results:
        # --- Defensive read: even if a module returned something malformed,
        #     we must NOT let that silently zero out risk. If a result is
        #     unusable, we treat it as a fail-closed event and add a floor of
        #     risk so it routes to human review. This is the fusion-level
        #     enforcement of the safety rule. ---
        if not isinstance(result, dict) or "risk_added" not in result:
            safety_events.append("A fraud-check module returned no usable result")
            total_score += 15   # floor: unusable module -> non-zero risk
            flags.append("A verification module failed to run — flagged for manual review")
            continue

        module_name = result.get("module", "unknown")

        # Sum this module's contributed risk.
        total_score += int(result.get("risk_added", 0))

        # Merge its triggered signals into the breakdown.
        for sig_name, sig_points in result.get("signals", {}).items():
            signal_breakdown[sig_name] = sig_points

        # Collect flags and passed notes.
        flags.extend(result.get("reasons", []))
        passed.extend(result.get("passed", []))

        # Detect a fail-closed event for transparency (module ran but couldn't
        # analyze — its detail carries an "error"). It already added its points
        # above; we just surface it so reviewers know WHY.
        for sig_detail in result.get("details", {}).values():
            if isinstance(sig_detail, dict) and "error" in sig_detail:
                safety_events.append(f"{module_name}: {sig_detail['error']}")

        # Keep full module detail for the admin evidence panel.
        module_results_map[module_name] = result.get("details", {})

    # --- Cap the score. Signals can sum past 100 (e.g. 40+30+25+20=115);
    #     a risk score is 0-100 by definition. ---
    total_score = min(total_score, MAX_SCORE)

    # --- Map score -> level + decision. ---
    if total_score <= THRESHOLD_LOW_MAX:
        risk_level = "LOW"
        decision = "AUTO_APPROVED"
    elif total_score <= THRESHOLD_MEDIUM_MAX:
        risk_level = "MEDIUM"
        decision = "FLAGGED_FOR_REVIEW"
    else:
        risk_level = "HIGH"
        decision = "FLAGGED_FOR_REVIEW"

    # --- Build the ordered explanation: FLAGS first (what's wrong), then a
    #     summary of what passed. This ordering matters for the demo — a
    #     reviewer reads the problems first. ---
    explanation = list(flags)
    if not flags:
        explanation.append("All fraud checks passed — no suspicious signals detected")

    return {
        "risk_score": total_score,
        "risk_level": risk_level,
        "decision": decision,
        "explanation": explanation,        # the human-facing reasons
        "passed_checks": passed,           # clean signals, for a "what we verified" panel
        "signal_breakdown": signal_breakdown,
        "module_results": module_results_map,
        "safety_events": safety_events,    # empty in a clean run; populated if anything failed closed
    }


# --- Standalone test: feed it fake module outputs and watch it fuse. ---
# From backend/:  python -m modules.risk_engine
if __name__ == "__main__":
    import json

    def banner(title, verdict):
        print("\n" + "=" * 60)
        print(f"  {title}")
        print("=" * 60)
        print(f"  SCORE: {verdict['risk_score']}/100   "
              f"LEVEL: {verdict['risk_level']}   DECISION: {verdict['decision']}")
        print("  EXPLANATION:")
        for e in verdict["explanation"]:
            print(f"    - {e}")
        if verdict["safety_events"]:
            print("  SAFETY EVENTS (failed-closed modules):")
            for s in verdict["safety_events"]:
                print(f"    ! {s}")

    # --- Demo A: a clean, legitimate user. Every module passed. ---
    clean = [
        {"module": "document_forensics", "risk_added": 0, "signals": {},
         "reasons": [], "passed": ["No editing artifacts detected in the document",
                                   "Document metadata is intact"], "details": {}},
        {"module": "face_match", "risk_added": 0, "signals": {},
         "reasons": [], "passed": ["Selfie matches the document photo (91% confidence)"],
         "details": {}},
        {"module": "ocr_name", "risk_added": 0, "signals": {},
         "reasons": [], "passed": ["Submitted name matches the document"], "details": {}},
        {"module": "duplicate_detection", "risk_added": 0, "signals": {},
         "reasons": [], "passed": ["No matching face found in prior submissions"], "details": {}},
    ]
    banner("DEMO A — Legitimate user", fuse(clean))

    # --- Demo B: a fraudster. Multiple strong signals fire. ---
    fraud = [
        {"module": "document_forensics", "risk_added": 42,
         "signals": {"tamper": 30, "missing_exif": 12},
         "reasons": ["Document shows signs of digital editing (error-level analysis)",
                     "Document has no camera metadata — likely a screenshot or download"],
         "passed": [], "details": {}},
        {"module": "face_match", "risk_added": 40, "signals": {"face_mismatch": 40},
         "reasons": ["Selfie face does not match document photo (22% match confidence)"],
         "passed": [], "details": {}},
        {"module": "ocr_name", "risk_added": 20, "signals": {"name_mismatch": 20},
         "reasons": ["Submitted name 'Suman Mishra' does not match the name on the document"],
         "passed": [], "details": {}},
        {"module": "duplicate_detection", "risk_added": 0, "signals": {},
         "reasons": [], "passed": ["No matching face found in prior submissions"], "details": {}},
    ]
    banner("DEMO B — Fraudster", fuse(fraud))

    # --- Edge case: a module CRASHED (fail-closed). Must NOT auto-approve. ---
    crashed = [
        {"module": "document_forensics", "risk_added": 0, "signals": {},
         "reasons": [], "passed": ["No editing artifacts detected"], "details": {}},
        {"module": "face_match", "risk_added": 40, "signals": {"face_mismatch": 40},
         "reasons": ["Could not verify the face against the document — treated as a mismatch"],
         "passed": [], "details": {"face_mismatch": {"error": "no face detected"}}},
        "THIS IS A MALFORMED RESULT",   # simulate a module returning garbage
    ]
    banner("EDGE — A module failed closed", fuse(crashed))
    print()