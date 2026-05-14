# ECG Analysis Guide for Apple Watch Data

## QRS Detection Algorithm (`ecg_qrs_detect.py`)

### Architecture

Pure Python implementation — no scipy/numpy dependency. Uses moving-average filters and finite-difference derivative, suitable for Apple Watch 512Hz single-lead data.

### Stage 1: Bandpass Filter

**Highpass (0.5Hz) — remove baseline drift**
- Moving average over `fs/lowcut = 1024` samples (~2s window)
- Subtract MA from original: `hp[i] = raw[i] - MA(raw[i-1024:i])`
- Handles slow baseline wander from respiration / electrode motion

**Lowpass (40Hz) — remove high-frequency noise**
- Moving average over `fs/highcut/2 = 6` samples (~12ms window)
- Smooths muscle tremor / electrical interference above QRS bandwidth

### Stage 2: Differentiation + Squaring + Integration

1. **Five-point derivative**: `(2*v[i+1] + v[i+2] - 2*v[i-1] - v[i-2]) / 8`
   - Emphasizes QRS slope, suppresses P/T waves
2. **Squaring**: `diff²` — all positive, amplifies large deflections
3. **Moving window integration**: 150ms window (~77 samples at 512Hz)
   - Produces smooth "energy envelope" where QRS complexes stand out as peaks

### Stage 3: Adaptive Threshold Peak Detection

```python
threshold1 = noise_level + 0.25 * (signal_level - noise_level)
```

- `noise_level`: average of first 2 seconds of integrated signal
- `signal_level`: 50% of maximum integrated value
- **Coefficient 0.25** controls sensitivity (see below)
- **Refractory**: 200ms after each detection — prevents double-counting
- **Min RR**: 250ms (max 240bpm) — physiologic floor

**Back-search for true R-peak**: After finding a peak in the integrated signal, search ±75ms in the *filtered* signal for the maximum voltage point. This maps the "energy peak" back to the actual R-wave apex.

### Sensitivity Adjustment

| Coefficient | Effect | Use case |
|-------------|--------|----------|
| 0.15 | Very sensitive, more detections | Low-amplitude QRS, possible misses |
| 0.25 | **Default** | Balanced |
| 0.35 | Stricter, fewer detections | Noisy signal, reduce false positives |
| 0.50 | Conservative | High noise, only strong QRS |

Edit line: `threshold1 = noise_level + 0.25 * (signal_level - noise_level)`

### Stage 4: RR Interval Computation

Simple consecutive differences: `RR[i] = (peak[i+1].t - peak[i].t) × 1000` (ms)

### Stage 5: Premature Beat Screening

**Criterion**: Coupling interval < 80% of median RR

**Confidence grading** (based on coupling interval):

| RR (ms) | Confidence | Typical interpretation |
|---------|-----------|------------------------|
| < 350 | **high** | Very early, likely true ectopic |
| 350–450 | **medium** | Early, probable ectopic |
| > 450 | **low** | Mildly early, may be normal variation or artifact |

**Type classification**:
- **PVC**: RR < 350ms AND high confidence
- **APC**: All other premature intervals

**Compensatory pause check**: Next RR > 130% of median RR → suggests full compensatory pause (more typical of PVC). APCs usually have *non-compensatory* pause (total cycle ≈ 2× normal).

### Limitations

- Single-lead (Lead I) — cannot distinguish all morphologies
- No P-wave detection — APC vs PVC classification is probabilistic, not definitive
- 30-second snapshot — captures episodic events but misses intermittent patterns
- Threshold-based detection struggles with very low-amplitude QRS or significant artifact

## HRV Metrics

The script reports basic statistics:
- **Mean RR** — average interval
- **RR STD** — standard deviation (SDNN equivalent for 30s)
- **Mean HR** — derived from mean RR

For full HRV (pNN50, RMSSD, frequency domain), export RR intervals to specialized tools.

## Common Artifacts

| Artifact | Cause | Detection hint |
|----------|-------|---------------|
| Baseline drift | Respiration, motion | Low-frequency wander in raw signal |
| Muscle tremor | Arm tension | High-frequency noise, reduced after 40Hz lowpass |
| Row boundary jump | Improper baseline handling | 3.7mV step at 10s/20s (extract script prevents this) |
| Missed beat | Low amplitude QRS | Unexpected long RR, check threshold sensitivity |
| Double detection | T-wave counted as R | Usually within refractory window, rare with 200ms |

### ⚠️ Motion Artifact — Critical Verification

**When algorithm flags PVC or very short RR (<300ms), verify against raw data:**

1. **Voltage check** — Normal R-peak: 0.3–0.8mV. >1.5mV or sudden 2× jump → suspect artifact.
2. **Morphology check** — Normal QRS: sharp, narrow (<120ms). Wide arc / plateau / gradual ramp → artifact.
3. **Baseline context** — Preceding 2s drift >0.2mV → measurement condition changed.
4. **Temporal isolation** — Single bizarre beat among normal beats → more likely artifact than consistent pathology.

**Artifact signature:**
- Sudden large swing (>2× normal amplitude)
- Gradual drift 0.5–2s (arm movement)
- "Double peak" from noise splitting one QRS
- RR exactly 2× or 0.5× adjacent intervals

**Action:** Flag as "存疑 — possible artifact", do not report as definitive finding. Consider re-recording.

## APC vs PVC Differentiation

| Feature | APC | PVC |
|---------|-----|-----|
| Origin | Atrial | Ventricular |
| Coupling interval | Usually longer (350–550ms) | Often shorter (< 350ms) |
| Compensatory pause | Non-compensatory (total ≈ 2× RR) | Full compensatory |
| QRS morphology | Usually narrow (supraventricular) | Wide, bizarre (if visible in Lead I) |
| Premature P wave | May be visible before QRS | No preceding P |

**Important**: Apple Watch single-lead cannot reliably assess QRS width or P-wave presence. The script's APC/PVC labels are **probabilistic** based on timing patterns only. Clinical confirmation requires 12-lead ECG or physician review.

## Reference

- Pan & Tompkins, 1985 — original real-time QRS detection algorithm
- Apple Watch ECG: 512Hz, Lead I, 10mm/mV, 25mm/s
