#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Apple Watch ECG PDF Extractor

Extracts vector waveform data and metadata from Apple Watch ECG PDF exports.
Outputs standardized JSON for downstream analysis.

Usage:
    python ecg_extract.py input.pdf [-o output.json]
    python ecg_extract.py input.pdf --csv [-o output.csv]
"""

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("Error: pdfplumber not installed. Run: pip install pdfplumber")
    sys.exit(1)


MM_PER_PT = 1 / 2.835
S_PER_MM = 1 / 25
MV_PER_MM = 1 / 10
FS = 512
ROW_DURATION = 10.0
GRID_LEFT_X = 40.0


def extract_metadata(page):
    text = unicodedata.normalize("NFKC", page.extract_text() or "")
    meta = {
        "source_file": None,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "patient_name": None,
        "birth_date": None,
        "record_time": None,
        "average_hr_bpm": None,
        "rhythm": None,
        "afib_detected": None,
        "parameters": {},
        "raw_text": text,
    }

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if lines:
        meta["patient_name"] = lines[0]

    m = re.search(r"出生日期%\s*(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    if m:
        meta["birth_date"] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    m = re.search(r"记录时间%\s*(\d{4})年(\d{1,2})月(\d{1,2})日(\d{1,2}):(\d{2})", text)
    if m:
        meta["record_time"] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}T{m.group(4)}:{m.group(5)}:00"

    m = re.search(r"平均(\d+)次/分", text)
    if m:
        meta["average_hr_bpm"] = int(m.group(1))

    m = re.search(r"(窦性心律|心房颤动|心律不齐|其他)", text)
    if m:
        meta["rhythm"] = m.group(1)

    # Fixed: handle negation - "未显示房颤" means NO afib
    if "未显示房颤" in text or "未显示心房颤动" in text:
        meta["afib_detected"] = False
    elif "显示房颤" in text or "显示心房颤动" in text:
        meta["afib_detected"] = True
    else:
        meta["afib_detected"] = "房颤" in text and "未" not in text

    m = re.search(r"(\d+)\s*mm/s.*?(\d+)\s*mm/mV.*?导联(.)\s*,\s*(\d+)Hz", text, re.DOTALL)
    if m:
        meta["parameters"] = {
            "speed_mm_s": int(m.group(1)),
            "gain_mm_mv": int(m.group(2)),
            "lead": m.group(3),
            "sample_rate_hz": int(m.group(4)),
        }
    else:
        meta["parameters"] = {
            "speed_mm_s": 25,
            "gain_mm_mv": 10,
            "lead": "I",
            "sample_rate_hz": 512,
        }

    m = re.search(r"iOS\s+([\d.]+).*?watchOS\s+([\d.]+)", text)
    if m:
        meta["parameters"]["ios_version"] = m.group(1)
        meta["parameters"]["watchos_version"] = m.group(2)

    m = re.search(r"(Watch[\d,]+)", text)
    if m:
        meta["parameters"]["device"] = m.group(1)

    m = re.search(r"算法版本\s+([\d—\-]+)", text)
    if m:
        meta["parameters"]["algorithm_version"] = m.group(1).replace("—", "-")

    return meta


def extract_waveform(page):
    curves = page.objects.get("curve", [])
    if not curves:
        return []

    # First curve is usually the calibration/grid, skip it
    wave_curves = curves[1:]

    # Classify curves into rows by y-coordinate range
    row1 = [c for c in wave_curves if c.get("pts") and 250 < max(p[1] for p in c["pts"]) < 290]
    row2 = [c for c in wave_curves if c.get("pts") and 350 < max(p[1] for p in c["pts"]) < 390]
    row3 = [c for c in wave_curves if c.get("pts") and 450 < max(p[1] for p in c["pts"]) < 500]

    rows_raw = [
        sorted(row1, key=lambda c: min(p[0] for p in c["pts"])),
        sorted(row2, key=lambda c: min(p[0] for p in c["pts"])),
        sorted(row3, key=lambda c: min(p[0] for p in c["pts"])),
    ]

    all_samples = []
    for row_idx, row_curves in enumerate(rows_raw):
        if not row_curves:
            continue

        # Merge curves into continuous point list
        points = []
        for i, c in enumerate(row_curves):
            pts = c["pts"]
            if i == 0:
                points.extend(pts)
            else:
                # Deduplicate overlapping endpoints
                prev_end = row_curves[i - 1]["pts"][-1]
                curr_start = pts[0]
                if abs(prev_end[0] - curr_start[0]) < 0.1 and abs(prev_end[1] - curr_start[1]) < 0.1:
                    points.extend(pts[1:])
                else:
                    points.extend(pts)

        # Per-row baseline: median of y-values (baseline ≈ isoelectric line)
        ys = [p[1] for p in points]
        ys_sorted = sorted(ys)
        baseline = ys_sorted[len(ys_sorted) // 2]

        for p in points:
            t = (p[0] - GRID_LEFT_X) * MM_PER_PT * S_PER_MM
            v = (baseline - p[1]) * MM_PER_PT * MV_PER_MM  # inverted: lower y = higher voltage
            all_samples.append({
                "t": t + row_idx * ROW_DURATION,
                "v": v,
                "row": row_idx,
            })

    return all_samples


def compute_quality(samples, meta):
    total = len(samples)
    expected = int(meta["parameters"].get("sample_rate_hz", FS) * 30)
    row0_samples = [s for s in samples if s["row"] == 0]
    row0_offset = row0_samples[0]["t"] if row0_samples else 0.0
    missing_samples = int(row0_offset * FS)

    return {
        "row_0_start_offset_s": round(row0_offset, 3),
        "row_0_missing_samples": missing_samples,
        "total_samples": total,
        "expected_samples": expected,
        "data_completeness": round(total / expected, 4) if expected else None,
        "notes": [
            "Row 0 has a fixed ~0.36s offset due to ECG icon occupying space.",
            "Each row baseline is computed independently to avoid cross-row jumps.",
        ],
    }


def extract(pdf_path):
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        meta = extract_metadata(page)
        meta["source_file"] = pdf_path.name
        samples = extract_waveform(page)

    if not samples:
        raise ValueError("No waveform data found in PDF.")

    quality = compute_quality(samples, meta)

    return {
        "metadata": meta,
        "waveform": {
            "sample_rate_hz": meta["parameters"].get("sample_rate_hz", FS),
            "duration_s": 30,
            "lead": meta["parameters"].get("lead", "I"),
            "unit": "mV",
            "time_voltage": samples,
        },
        "quality": quality,
    }


def to_csv(data, out_path):
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("time_s,voltage_mV,row\n")
        for s in data["waveform"]["time_voltage"]:
            f.write(f"{s['t']:.6f},{s['v']:.6f},{s['row']}\n")


def main():
    parser = argparse.ArgumentParser(description="Extract ECG from Apple Watch PDF")
    parser.add_argument("pdf", help="Input PDF file")
    parser.add_argument("-o", "--output", help="Output file")
    parser.add_argument("--csv", action="store_true", help="Output CSV")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = parser.parse_args()

    data = extract(args.pdf)

    if args.csv:
        out_path = args.output or Path(args.pdf).with_suffix(".csv")
        to_csv(data, out_path)
        print(f"CSV saved: {out_path}")
    else:
        out_path = args.output or Path(args.pdf).with_suffix(".json")
        indent = 2 if args.pretty else None
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
        print(f"JSON saved: {out_path}")
        print(f"  Samples: {data['quality']['total_samples']} / {data['quality']['expected_samples']} expected")
        print(f"  HR: {data['metadata'].get('average_hr_bpm', '?')} bpm")
        print(f"  Rhythm: {data['metadata'].get('rhythm', '?')}")
        if data["quality"]["row_0_start_offset_s"] > 0:
            print(f"  Note: Row 0 offset {data['quality']['row_0_start_offset_s']}s ({data['quality']['row_0_missing_samples']} samples)")


if __name__ == "__main__":
    main()
