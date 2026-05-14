#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ECG QRS Detection for Apple Watch extracted data."""

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path


def bandpass_filter(samples, fs=512, lowcut=0.5, highcut=40.0):
    n = len(samples)
    hp_window = int(fs / lowcut)
    hp = []
    for i in range(n):
        start = max(0, i - hp_window)
        end = min(n, i + 1)
        ma = sum(samples[j]["v"] for j in range(start, end)) / (end - start)
        hp.append({"t": samples[i]["t"], "v": samples[i]["v"] - ma,
                   "row": samples[i].get("row", 0)})

    lp_window = max(2, int(fs / highcut / 2))
    filtered = []
    for i in range(n):
        start = max(0, i - lp_window // 2)
        end = min(n, i + lp_window // 2 + 1)
        ma = sum(hp[j]["v"] for j in range(start, end)) / (end - start)
        filtered.append({"t": hp[i]["t"], "v": ma, "row": hp[i]["row"]})
    return filtered


def detect_qrs(filtered, fs=512):
    n = len(filtered)
    diff = [0.0] * n
    for i in range(2, n - 2):
        diff[i] = (2 * filtered[i + 1]["v"] + filtered[i + 2]["v"]
                   - 2 * filtered[i - 1]["v"] - filtered[i - 2]["v"]) / 8.0

    squared = [d * d for d in diff]
    win_size = max(5, int(0.15 * fs))
    integrated = []
    for i in range(n):
        start = max(0, i - win_size // 2)
        end = min(n, i + win_size // 2 + 1)
        integrated.append(sum(squared[j] for j in range(start, end)) / (end - start))

    init_samples = min(int(2.0 * fs), n // 10)
    noise_level = sum(integrated[:init_samples]) / init_samples
    signal_level = max(integrated) * 0.5
    threshold1 = noise_level + 0.25 * (signal_level - noise_level)

    peaks = []
    min_rr = int(0.25 * fs)
    refractory = int(0.20 * fs)
    last_peak_idx = -min_rr

    i = win_size
    while i < n - win_size:
        if integrated[i] > threshold1 and (i - last_peak_idx) >= min_rr:
            peak_idx = i
            for j in range(i, min(n, i + win_size)):
                if integrated[j] > integrated[peak_idx]:
                    peak_idx = j
            search_start = max(0, peak_idx - win_size // 2)
            search_end = min(n, peak_idx + win_size // 2 + 1)
            r_idx = search_start
            for j in range(search_start, search_end):
                if filtered[j]["v"] > filtered[r_idx]["v"]:
                    r_idx = j
            if filtered[r_idx]["v"] > 0.05:
                peaks.append({"idx": r_idx, "t": filtered[r_idx]["t"],
                              "v": filtered[r_idx]["v"],
                              "row": filtered[r_idx]["row"]})
                last_peak_idx = r_idx
                i = peak_idx + refractory
                continue
        i += 1
    return peaks


def compute_rr(peaks):
    rr = []
    for i in range(1, len(peaks)):
        rr_ms = (peaks[i]["t"] - peaks[i - 1]["t"]) * 1000
        rr.append({"start_t": peaks[i - 1]["t"], "end_t": peaks[i]["t"],
                   "rr_ms": round(rr_ms, 1)})
    return rr


def screen_ectopic(peaks, rr):
    if len(rr) < 3:
        return []
    rr_values = [r["rr_ms"] for r in rr]
    sorted_rr = sorted(rr_values)
    median_rr = sorted_rr[len(sorted_rr) // 2]

    ectopic = []
    for i, r in enumerate(rr):
        coupling = r["rr_ms"] / median_rr * 100
        if coupling < 80:
            if r["rr_ms"] < 350:
                confidence = "high"
            elif r["rr_ms"] < 450:
                confidence = "medium"
            else:
                confidence = "low"
            next_rr = rr[i + 1]["rr_ms"] if i + 1 < len(rr) else None
            compensatory = next_rr is not None and next_rr > median_rr * 1.3
            ectopic.append({
                "t": peaks[i + 1]["t"],
                "rr_ms": round(r["rr_ms"], 1),
                "coupling_percent": round(coupling, 1),
                "confidence": confidence,
                "compensatory_pause": compensatory,
                "type": "PVC" if r["rr_ms"] < 350 and confidence == "high" else "APC",
            })
    return ectopic


def analyze(data_path):
    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)
    samples = data["waveform"]["time_voltage"]
    fs = data["waveform"].get("sample_rate_hz", 512)
    filtered = bandpass_filter(samples, fs)
    peaks = detect_qrs(filtered, fs)
    rr = compute_rr(peaks)
    ectopic = screen_ectopic(peaks, rr)

    if len(rr) >= 2:
        rr_values = [r["rr_ms"] for r in rr]
        mean_rr = sum(rr_values) / len(rr_values)
        std_rr = math.sqrt(sum((r - mean_rr) ** 2 for r in rr_values) / len(rr_values))
        hr = 60000 / mean_rr
    else:
        mean_rr = std_rr = hr = None

    return {
        "source": data.get("metadata", {}).get("source_file", Path(data_path).name),
        "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
        "detection_params": {
            "sample_rate_hz": fs,
            "highpass_cutoff_hz": 0.5,
            "lowpass_cutoff_hz": 40.0,
            "qrs_window_ms": 150,
            "min_rr_ms": 250,
            "refractory_ms": 200,
        },
        "peaks": [{"idx": p["idx"], "t": round(p["t"], 3),
                   "v": round(p["v"], 4), "type": "R"} for p in peaks],
        "rr_intervals": rr,
        "summary": {
            "total_beats": len(peaks),
            "mean_hr_bpm": round(hr, 1) if hr else None,
            "mean_rr_ms": round(mean_rr, 1) if mean_rr else None,
            "rr_std_ms": round(std_rr, 1) if std_rr else None,
            "potential_ectopic": ectopic,
            "ectopic_count": len(ectopic),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="QRS detection for Apple Watch ECG")
    parser.add_argument("json", help="Input JSON from ecg_extract.py")
    parser.add_argument("-o", "--output", help="Output file")
    parser.add_argument("--csv", action="store_true", help="Output CSV")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = parser.parse_args()

    result = analyze(args.json)

    if args.csv:
        out_path = args.output or Path(args.json).with_suffix(".peaks.csv")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("time_s,voltage_mV,type\n")
            for p in result["peaks"]:
                f.write(f"{p['t']:.3f},{p['v']:.4f},{p['type']}\n")
        print(f"CSV saved: {out_path}")
    else:
        out_path = args.output or Path(args.json).with_suffix(".qrs.json")
        indent = 2 if args.pretty else None
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=indent)
        print(f"JSON saved: {out_path}")
        s = result["summary"]
        print(f"  Beats: {s['total_beats']}, HR: {s['mean_hr_bpm']} bpm")
        print(f"  RR: {s['mean_rr_ms']}ms (std: {s['rr_std_ms']}ms)")
        print(f"  Potential ectopic: {s['ectopic_count']}")
        for e in s["potential_ectopic"][:5]:
            print(f"    t={e['t']:.2f}s, RR={e['rr_ms']:.0f}ms"
                  f" ({e['coupling_percent']:.0f}%)"
                  f" [{e['type']}, {e['confidence']}]")


if __name__ == "__main__":
    main()
