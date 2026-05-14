# Apple Watch ECG Analyzer

Extract and analyze Apple Watch ECG PDF exports. Two-stage pipeline: **PDF waveform extraction** → **QRS detection & premature beat screening**.

> **Not a medical device.** This tool is for informational and research purposes only. Always consult a licensed physician for diagnosis and treatment decisions.

## Features

- **PDF Waveform Extraction** — Parse Apple Watch ECG PDFs and extract raw time/voltage data (512 Hz, Lead I)
- **QRS Detection** — Pure Python implementation of Pan-Tompkins-style algorithm (no numpy/scipy)
- **Heart Rate & RR Intervals** — Compute mean HR, RR statistics, basic HRV (SDNN equivalent)
- **Premature Beat Screening** — Detect and classify APC/PVC candidates with confidence grading
- **Quality Assessment** — Data completeness check, row offset detection, artifact flagging guidance
- **Multiple Output Formats** — JSON (structured) or CSV (raw waveform)

## Installation

```bash
pip install pdfplumber
```

Or:

```bash
pip install -r requirements.txt
```

Requires Python 3.8+.

## Usage

### Step 1: Extract waveform from PDF

```bash
python3 scripts/ecg_extract.py <input.pdf> -o output.json --pretty
python3 scripts/ecg_extract.py <input.pdf> --csv -o waveform.csv
```

**Output JSON structure:**
- `metadata` — patient name, DOB, record time, HR, rhythm, device info
- `waveform.time_voltage` — array of `{t, v, row}` (time in seconds, voltage in mV)
- `quality` — data completeness, Row 0 offset info

**Key notes:**
- Apple Watch PDFs use a 3-row layout (10 seconds each)
- Row 0 has a ~0.36s offset due to the ECG icon
- Each row baseline is computed independently to avoid cross-row jumps

### Step 2: QRS detection & analysis

```bash
python3 scripts/ecg_qrs_detect.py output.json --pretty -o analysis.json
```

**Output JSON structure:**
- `peaks` — detected R-peaks with time, voltage, index
- `rr_intervals` — consecutive RR intervals in ms
- `summary` — total beats, mean HR, RR statistics
- `summary.potential_ectopic` — premature beat candidates with confidence & classification

**Example summary output:**
```
Beats: 42, HR: 84.0 bpm
RR: 714.3ms (std: 45.2ms)
Potential ectopic: 2
  t=12.34s, RR=280ms (39%) [PVC, high]
  t=18.56s, RR=420ms (59%) [APC, medium]
```

## Algorithm Overview

See [`references/analysis_guide.md`](references/analysis_guide.md) for detailed documentation.

**High-level pipeline:**

1. **Bandpass filter** — 0.5 Hz highpass (remove baseline drift) + 40 Hz lowpass (remove noise)
2. **Differentiation + squaring + integration** — 150ms moving window to create energy envelope
3. **Adaptive threshold peak detection** — Dynamic threshold based on signal/noise levels, 200ms refractory period
4. **Back-search for R-peak** — Map energy peak to true maximum voltage point in filtered signal
5. **RR analysis & ectopic screening** — Coupling interval < 80% of median RR flags premature beat

**Sensitivity adjustment:** Edit the threshold coefficient in `ecg_qrs_detect.py` line:
```python
threshold1 = noise_level + 0.25 * (signal_level - noise_level)
```
Increase (e.g., 0.35) for stricter detection, decrease (e.g., 0.15) for more sensitive.

## AI Agent Compatibility

These scripts are standalone Python CLI tools. They can be invoked by any AI agent or coding assistant:

| Agent | Usage |
|-------|-------|
| **Claude Code** | Direct script execution via Bash tool |
| **Codex** | Direct script execution via Bash tool |
| **OpenClaw** | Native Skill support (wraps scripts with `SKILL.md`) |

The scripts read local PDF/JSON files and write local output — no network calls, no API keys, no external dependencies beyond `pdfplumber`.

## Limitations

- **Single-lead only** — Apple Watch Lead I; cannot distinguish all morphologies
- **No P-wave detection** — APC vs PVC classification is probabilistic based on timing only
- **30-second snapshot** — Captures episodic events but may miss intermittent patterns
- **Chinese PDFs only** — Metadata parsing targets Apple Watch ECG PDFs in Chinese locale
- **Threshold-based** — Struggles with very low-amplitude QRS or significant motion artifact

## Artifact Verification

When the algorithm flags a PVC or very short RR (< 300 ms), verify against the original PDF:

- Normal R-peaks: 0.3–0.8 mV. Values > 1.5 mV suggest artifact.
- Normal QRS: sharp, narrow (< 120 ms). Wide arcs or plateaus → artifact.
- Single bizarre beat among normal beats → more likely artifact than pathology.
- See `docs/analysis_guide.md` for full verification protocol.

## License

MIT License — see [LICENSE](LICENSE).

## Acknowledgments

- Pan & Tompkins, 1985 — original real-time QRS detection algorithm
- Apple Watch ECG: 512 Hz, Lead I, 10 mm/mV, 25 mm/s
