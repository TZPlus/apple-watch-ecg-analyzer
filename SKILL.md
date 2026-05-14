---
name: apple-watch-ecg-analyzer
description: >
  Extract and analyze Apple Watch ECG PDF data. This skill should be used when the user sends an Apple Watch
  ECG PDF for waveform extraction, heart rate analysis, premature beat detection, or rhythm assessment.
  Supports extracting raw waveform data from Apple Watch ECG PDFs, QRS detection and RR interval analysis,
  premature beat APC/PVC screening with confidence grading, and basic heart rate variability metrics.
  Do not use for 12-lead ECG interpretation, non-Apple Watch ECG formats, or real-time monitoring.
  Triggers on Apple Watch ECG PDF, ECG waveform analysis, RR interval, premature beat detection, or cardiac rhythm queries.
license: MIT
---

# Apple Watch ECG Analyzer

Two-stage pipeline: extract raw waveform data from PDF, then analyze for clinical findings.

## Stage 1: Data Extraction

Run the extraction script on any Apple Watch ECG PDF:

```bash
python3 scripts/ecg_extract.py <pdf_path> -o <output.json> --pretty
python3 scripts/ecg_extract.py <pdf_path> --csv -o <output.csv>
```

**Output JSON structure:**
- `metadata` — patient name, DOB, record time, HR, rhythm, device info
- `waveform.time_voltage` — array of `{t, v, row}` (time in seconds, voltage in mV, row 0/1/2)
- `quality` — data completeness, Row 0 offset info

**Key technical notes:**
- 3-row layout, each row = 10 seconds, Row 0 has ~0.36s offset (ECG icon space)
- Each row baseline computed independently (median) — no cross-row jumps
- `t` is global time in seconds; `v` is voltage in mV (positive = upward deflection)
- To get continuous signal: sort by `t` (already baseline-corrected)

## Stage 2: Clinical Analysis

After extraction, run the QRS detection script on the JSON output:

```bash
python3 scripts/ecg_qrs_detect.py <extracted.json> --pretty -o <output.json>
```

**Output JSON structure:**
- `peaks` — detected R-peaks with time, voltage, index
- `rr_intervals` — consecutive RR intervals in ms
- `summary` — total beats, mean HR, RR statistics
- `summary.potential_ectopic` — premature beat candidates with confidence and classification

**Key algorithm features:**
- Pure Python, no scipy/numpy dependency
- Bandpass filter: 0.5Hz highpass + 40Hz lowpass
- Adaptive threshold + refractory constraint (200ms)
- Premature beat grading: PVC/APC + high/medium/low confidence + compensatory pause check

**Sensitivity adjustment:**
Edit `scripts/ecg_qrs_detect.py` line `threshold1 = noise_level + 0.25 * (signal_level - noise_level)` — increase coefficient (e.g., 0.35) for stricter detection, decrease (e.g., 0.15) for more sensitive.

## Artifact Detection and Verification

When the algorithm flags a key finding (PVC, couplet, very short RR under 300ms), verify against the original PDF:

1. Check voltage amplitude — Normal R-peaks in Apple Watch ECG are typically 0.3–0.8mV. Values over 1.5mV or sudden baseline shifts suggest motion artifact or poor contact.
2. Check waveform morphology — Look for smooth, physiologic QRS shape. Sharp spikes, rectangular waves, or gradual ramps are likely artifact.
3. Check temporal context — A single bizarre beat surrounded by normal beats is more suspicious for artifact than a consistent pattern.
4. Cross-reference with adjacent rows — If artifact occurs near row boundary (t approximately 10s, 20s), check if it is a baseline transition artifact.

If uncertain:
- Export raw `time_voltage` data around the suspect timepoint
- Ask user to confirm measurement conditions (arm position, movement, device contact)
- Flag as "possible artifact" rather than definitive diagnosis
- Consider re-recording if artifact suspected

**Motion artifact signature:**
- Sudden large voltage swing (over 2x normal amplitude)
- Gradual drift over 0.5–2s (baseline wander from arm movement)
- "Double peak" where one QRS is split by noise
- RR interval that is exactly 2x or 0.5x adjacent intervals (missed/double detection)

For detailed algorithm documentation, see `references/analysis_guide.md`.

## Workflow

1. Receive Apple Watch ECG PDF from user
2. Run `scripts/ecg_extract.py` to get JSON
3. Read JSON, extract `waveform.time_voltage`
4. Run QRS detection to get R-peak locations
5. Compute RR intervals, detect premature beats
6. Classify premature beats (APC vs PVC)
7. Report findings to user with time positions in the 30-second recording

## Important

- Do not skip extraction — never analyze raw PDF content streams directly (they contain cross-row artifacts)
- Row 0 offset — when reporting time positions, account for the ~0.36s Row 0 start offset
- PDF time axis — the PDF displays 3 rows of 10 seconds each; Row 0 starts at ~0.36s due to ECG icon
- afib_detected — the script handles negation ("no afib shown" = no afib); previous versions had a bug here
