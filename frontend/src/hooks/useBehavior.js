// useBehavior.js — behavioral biometrics tracker for form filling.
// Monitors typing patterns to detect automated/bulk-paste form filling
// consistent with organized identity theft operations.
//
// Collects: paste events, typing speed, field timing, total form time.
// Sends raw metrics to the backend — scoring happens server-side.

import { useRef, useCallback } from "react";

export default function useBehavior() {
  const metrics = useRef({
    paste_count: 0,             // how many fields were pasted into
    keystrokes: 0,              // total keystrokes across all fields
    first_input_at: null,       // timestamp of very first interaction
    last_input_at: null,        // timestamp of most recent interaction
    field_times: {},            // { field_name: { start, end, pastes, keys } }
  });

  // Call this on every keystroke (onChange fires per character in React).
  const trackKeystroke = useCallback((fieldName) => {
    const m = metrics.current;
    const now = Date.now();
    if (!m.first_input_at) m.first_input_at = now;
    m.last_input_at = now;
    m.keystrokes++;

    if (!m.field_times[fieldName]) {
      m.field_times[fieldName] = { start: now, end: now, pastes: 0, keys: 0 };
    }
    m.field_times[fieldName].end = now;
    m.field_times[fieldName].keys++;
  }, []);

  // Call this when a paste event fires on any field.
  const trackPaste = useCallback((fieldName) => {
    const m = metrics.current;
    m.paste_count++;
    if (!m.field_times[fieldName]) {
      m.field_times[fieldName] = { start: Date.now(), end: Date.now(), pastes: 0, keys: 0 };
    }
    m.field_times[fieldName].pastes++;
  }, []);

  // Get the final metrics object to send with the submission.
  const getMetrics = useCallback(() => {
    const m = metrics.current;
    const total_time_ms = (m.first_input_at && m.last_input_at)
      ? m.last_input_at - m.first_input_at
      : 0;

    // Typing speed: characters per second across the whole form.
    const typing_speed = total_time_ms > 0
      ? Math.round((m.keystrokes / (total_time_ms / 1000)) * 100) / 100
      : 0;

    // Count fields that were pasted into vs typed.
    const fields = Object.entries(m.field_times);
    const pasted_fields = fields.filter(([_, f]) => f.pastes > 0).length;
    const total_fields = fields.length;

    return {
      paste_count: m.paste_count,
      pasted_fields: pasted_fields,
      total_fields: total_fields,
      keystrokes: m.keystrokes,
      total_time_ms: total_time_ms,
      typing_speed_cps: typing_speed,   // characters per second
      field_details: m.field_times,
    };
  }, []);

  return { trackKeystroke, trackPaste, getMetrics };
}