from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


OFFICIAL_FIELDS = [
    "TEAM_ID", "MISSION_TIME", "PACKET_COUNT", "MODE", "STATE", "ALTITUDE",
    "TEMPERATURE", "PRESSURE", "VOLTAGE", "CURRENT", "GYRO_R", "GYRO_P", "GYRO_Y",
    "ACCEL_R", "ACCEL_P", "ACCEL_Y", "GPS_TIME", "GPS_ALTITUDE", "GPS_LATITUDE",
    "GPS_LONGITUDE", "GPS_SATS", "CMD_ECHO", "YAW", "TOF",
]

CANONICAL_ORDER = [
    "TEAM_ID", "MISSION_TIME", "PACKET_COUNT", "MODE", "STATE", "ALTITUDE",
    "TEMPERATURE", "PRESSURE", "VOLTAGE", "CURRENT", "GYRO_R", "GYRO_P", "GYRO_Y",
    "ACCEL_R", "ACCEL_P", "ACCEL_Y", "GPS_TIME", "GPS_ALTITUDE", "GPS_LAT", "GPS_LON",
    "GPS_SATS", "CMD_ECHO", "YAW", "TOF",
    "GPS_LATITUDE", "GPS_LONGITUDE", "GPS_ALT", "SOURCE_FILE", "SOURCE_SHEET", "SOURCE_ROW",
    "T_FROM_LAUNCH_S",
]

STATE_MAP_NUMERIC = {
    "0": "LAUNCH_PAD",
    "1": "ASCENT",
    "2": "APOGEE",
    "3": "DESCENT",
    "4": "PAYLOAD_RELEASE",
    "5": "LANDED",
    "6": "PROBE_RELEASE",
}

COLUMN_ALIASES = {
    "TEAM_ID": ["TEAM_ID", "TEAM ID", "TEAM"],
    "MISSION_TIME": ["MISSION_TIME", "MISSION TIME", "TIME"],
    "PACKET_COUNT": ["PACKET_COUNT", "PACKET", "PACKETCOUNT", "PKT", "COUNT"],
    "MODE": ["MODE", "FLIGHT_MODE"],
    "STATE": ["STATE", "FLIGHT_STATE", "FLIGHT STATE", "STATUS"],
    "ALTITUDE": ["ALTITUDE", "ALT", "ALTITUDE_M", "BARO_ALTITUDE", "BMP_ALTITUDE"],
    "TEMPERATURE": ["TEMPERATURE", "TEMP", "TEMP_C", "TEMPERATURE_C", "ALT0_TEMPERATURE", "ALT0 TEMP", "ALT0_TEMP", "ALT1_TEMPERATURE"],
    "PRESSURE": ["PRESSURE", "PRES", "PRESSURE_KPA"],
    "VOLTAGE": ["VOLTAGE", "VOLT", "VBAT", "BATTERY_VOLTAGE"],
    "CURRENT": ["CURRENT", "CURR", "CURRENT_A", "CURRENT_MA"],
    "GYRO_R": ["GYRO_R", "GYRO R", "GYRO_ROLL", "ROLL_RATE", "GYRO_X"],
    "GYRO_P": ["GYRO_P", "GYRO P", "GYRO_PITCH", "PITCH_RATE", "GYRO_Y"],
    "GYRO_Y": ["GYRO_Y", "GYRO Y", "GYRO_YAW", "YAW_RATE", "GYRO_Z"],
    "ACCEL_R": ["ACCEL_R", "ACCEL R", "ACCEL_ROLL", "ACCEL_X", "ACC_X"],
    "ACCEL_P": ["ACCEL_P", "ACCEL P", "ACCEL_PITCH", "ACCEL_Y", "ACC_Y"],
    "ACCEL_Y": ["ACCEL_Y", "ACCEL Y", "ACCEL_YAW", "ACCEL_Z", "ACC_Z"],
    "GPS_TIME": ["GPS_TIME", "GPS TIME"],
    "GPS_ALTITUDE": ["GPS_ALTITUDE", "GPS ALTITUDE", "GPS_ALT", "GPS ALT"],
    "GPS_LATITUDE": ["GPS_LATITUDE", "GPS LATITUDE", "GPS_LAT", "GPS LAT", "LATITUDE", "LAT"],
    "GPS_LONGITUDE": ["GPS_LONGITUDE", "GPS LONGITUDE", "GPS_LON", "GPS LON", "LONGITUDE", "LON"],
    "GPS_SATS": ["GPS_SATS", "GPS SATS", "SATS", "SATELLITES"],
    "CMD_ECHO": ["CMD_ECHO", "CMD ECHO", "COMMAND"],
    "YAW": ["YAW"],
    "TOF": ["TOF", "TIME_OF_FLIGHT"],
}


def _norm_key(x: object) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", str(x).strip().upper()).strip("_")


def _clean_col(x: object) -> str:
    return re.sub(r"\s+", " ", str(x).strip().replace("\n", " ").replace("\r", " "))


def normalize_state(value: object) -> str:
    if pd.isna(value):
        return ""
    s = str(value).strip().upper()
    s = s.replace("REALEASE", "RELEASE")
    s = s.replace("LAUNCHPAD", "LAUNCH_PAD")
    s = re.sub(r"[^A-Z0-9]+", "_", s).strip("_")
    if s in STATE_MAP_NUMERIC:
        return STATE_MAP_NUMERIC[s]
    if s in {"LAUNCH_PAD", "ASCENT", "APOGEE", "DESCENT", "PROBE_RELEASE", "PAYLOAD_RELEASE", "LANDED"}:
        return s
    if "LAUNCH" in s and "PAD" in s:
        return "LAUNCH_PAD"
    if "ASCENT" in s or "ASCENDING" in s:
        return "ASCENT"
    if "APOGEE" in s or "PEAK" in s:
        return "APOGEE"
    if "DESCENT" in s or "DESCENDING" in s:
        return "DESCENT"
    if "PROBE" in s:
        return "PROBE_RELEASE"
    if "PAYLOAD" in s:
        return "PAYLOAD_RELEASE"
    if "LAND" in s:
        return "LANDED"
    return s


def _rename_columns(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, str]]:
    df = df.copy()
    df.columns = [_clean_col(c) for c in df.columns]
    lookup = {_norm_key(c): c for c in df.columns}
    rename = {}
    for target, aliases in COLUMN_ALIASES.items():
        if target in df.columns:
            continue
        for alias in [target] + aliases:
            k = _norm_key(alias)
            if k in lookup:
                rename[lookup[k]] = target
                break
    df = df.rename(columns=rename)
    return df, {str(k): str(v) for k, v in rename.items()}


def _read_csv_trim_extra(path: Path) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """Read CanSat CSV while trimming extra appended fields instead of skipping valid rows."""
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        header = [_clean_col(h) for h in header]
        official_like = all(x in [_norm_key(h) for h in header] for x in ["PACKET_COUNT", "STATE", "ALTITUDE"])
        expected = len(header)

        # Many raw CanSat rows have extra telemetry fields appended after the official header.
        # If the official 24 columns are present, keep only those first official fields.
        if expected >= 24 and official_like:
            expected = 24
            header = header[:24]

        rows = []
        extra = 0
        short = 0
        for i, row in enumerate(reader, start=2):
            if len(row) >= expected:
                if len(row) > expected:
                    extra += 1
                rows.append(row[:expected])
            else:
                short += 1

    return pd.DataFrame(rows, columns=header), {
        "rows_read": len(rows),
        "extra_rows_trimmed": extra,
        "short_rows_skipped": short,
        "field_count_used": expected,
    }


def _read_excel_all_sheets(path: Path) -> Tuple[pd.DataFrame, Dict[str, object]]:
    """Read Excel flight logs safely.

    Default behavior is single-sheet selection, not concatenation.
    Mixed workbooks often contain a public flight sheet plus an SD/raw sheet with
    different row rates/timebases. Concatenating them can fake a landing or extend
    the mission beyond the last sample of the sheet the user is checking.

    Overrides:
    - CFDS_EXCEL_SHEET=<sheet name> forces one sheet.
    - CFDS_EXCEL_CONCAT_SHEETS=1 restores old concatenate-all behavior.
    """
    sheets = pd.read_excel(path, sheet_name=None)
    valid_frames = []
    sheet_reports = {}
    forced_sheet = os.environ.get("CFDS_EXCEL_SHEET", "").strip()
    concat_mode = os.environ.get("CFDS_EXCEL_CONCAT_SHEETS", "0").strip().lower() in {"1", "true", "yes", "on"}

    for order, (name, sdf) in enumerate(sheets.items()):
        if sdf is None or sdf.empty:
            sheet_reports[name] = {"rows_raw": 0, "used": False, "reason": "empty sheet"}
            continue
        sdf = sdf.dropna(how="all").copy()
        sdf, rename = _rename_columns(sdf)
        has_core = {"PACKET_COUNT", "STATE", "ALTITUDE"}.issubset(set(sdf.columns))
        alt = pd.to_numeric(sdf["ALTITUDE"], errors="coerce") if "ALTITUDE" in sdf.columns else pd.Series(dtype=float)
        states = sdf["STATE"].astype(str).str.upper() if "STATE" in sdf.columns else pd.Series(dtype=str)
        max_alt = float(alt.max()) if alt.notna().any() else np.nan
        last_alt = float(alt.dropna().iloc[-1]) if alt.notna().any() else np.nan
        row_count = int(len(sdf))
        state_good = int(states.isin(["LAUNCH_PAD", "ASCENT", "APOGEE", "DESCENT", "PROBE_RELEASE", "PAYLOAD_RELEASE", "LANDED"]).sum()) if len(states) else 0
        name_u = str(name).upper()
        name_bonus = 35 if any(k in name_u for k in ["FLIGHT", "MISSION"]) else 0
        sd_penalty = -35 if any(k in name_u for k in ["SD_LOG", "RAW", "DEBUG"]) else 0
        score = (
            (100 if has_core else -999)
            + min(row_count, 2000) / 40.0
            + min(max(max_alt if np.isfinite(max_alt) else 0.0, 0.0), 1000.0) / 20.0
            + min(state_good, 1000) / 35.0
            + name_bonus
            + sd_penalty
            - order * 2.0
        )
        sdf["SOURCE_SHEET"] = str(name)
        sheet_reports[name] = {
            "rows_raw": row_count,
            "columns": [str(c) for c in sdf.columns],
            "rename_map": rename,
            "has_core": bool(has_core),
            "score": float(score),
            "max_altitude_m": max_alt,
            "last_altitude_m": last_alt,
            "used": False,
        }
        if has_core:
            valid_frames.append((score, order, name, sdf))

    if forced_sheet:
        if forced_sheet not in sheets:
            raise ValueError(f"CFDS_EXCEL_SHEET={forced_sheet!r} not found. Available sheets: {list(sheets.keys())}")
        out = sheets[forced_sheet].dropna(how="all").copy()
        out, _ = _rename_columns(out)
        out["SOURCE_SHEET"] = forced_sheet
        if forced_sheet in sheet_reports:
            sheet_reports[forced_sheet]["used"] = True
            sheet_reports[forced_sheet]["selection_reason"] = "forced_by_CFDS_EXCEL_SHEET"
        out = out.copy(deep=True)
        return out, {"sheet_reports": sheet_reports, "sheets_found": list(sheets.keys()), "excel_sheet_policy": "forced_single_sheet", "selected_sheet": forced_sheet}

    if concat_mode and valid_frames:
        frames = []
        for _score, _order, name, sdf in valid_frames:
            sheet_reports[name]["used"] = True
            sheet_reports[name]["selection_reason"] = "concat_mode"
            frames.append(sdf)
        out = pd.concat(frames, ignore_index=True, sort=False).copy(deep=True)
        return out, {"sheet_reports": sheet_reports, "sheets_found": list(sheets.keys()), "excel_sheet_policy": "concat_all_valid_sheets"}

    if valid_frames:
        score, order, selected_name, selected = sorted(valid_frames, key=lambda item: (-item[0], item[1]))[0]
        sheet_reports[selected_name]["used"] = True
        sheet_reports[selected_name]["selection_reason"] = "selected_best_single_flight_sheet"
        selected = selected.copy(deep=True)
        return selected, {"sheet_reports": sheet_reports, "sheets_found": list(sheets.keys()), "excel_sheet_policy": "single_best_flight_sheet", "selected_sheet": str(selected_name)}

    first_name = next(iter(sheets.keys())) if sheets else "Sheet1"
    out = sheets[first_name] if sheets else pd.DataFrame()
    out, _ = _rename_columns(out)
    out["SOURCE_SHEET"] = first_name
    out = out.copy(deep=True)
    return out, {"sheet_reports": sheet_reports, "sheets_found": list(sheets.keys()), "excel_sheet_policy": "fallback_first_sheet", "selected_sheet": first_name}


def infer_state_from_altitude(df: pd.DataFrame) -> pd.Series:
    if "ALTITUDE" not in df.columns or len(df) == 0:
        return pd.Series(["ASCENT"] * len(df), index=df.index, dtype=object)
    alt = pd.to_numeric(df["ALTITUDE"], errors="coerce").interpolate(limit_direction="both").bfill().ffill()
    n = len(alt)
    if n == 0:
        return pd.Series([], dtype=object)
    arr = alt.to_numpy(dtype=float, copy=True)
    finite = arr[np.isfinite(arr)]
    if len(finite) == 0:
        return pd.Series(["ASCENT"] * n, index=df.index, dtype=object)
    max_pos = int(np.nanargmax(arr))
    max_alt = float(np.nanmax(arr))
    baseline = float(np.nanmedian(arr[:max(3, min(20, n))]))
    threshold = baseline + max(2.0, abs(max_alt - baseline) * 0.02)
    above = np.where(arr > threshold)[0]
    launch_pos = int(above[0]) if len(above) else 0
    states = pd.Series(["DESCENT"] * n, index=df.index, dtype=object)
    states.iloc[:launch_pos] = "LAUNCH_PAD"
    states.iloc[launch_pos:max_pos] = "ASCENT"
    states.iloc[max_pos] = "APOGEE"
    pr_alt = max_alt * 0.80
    pr_positions = np.where((np.arange(n) >= max_pos) & (arr <= pr_alt))[0]
    if len(pr_positions):
        states.iloc[int(pr_positions[0]):] = "PAYLOAD_RELEASE"
    land_positions = np.where((np.arange(n) >= max_pos) & (arr <= max(baseline + 3.0, 5.0)))[0]
    if len(land_positions):
        states.iloc[int(land_positions[0]):] = "LANDED"
    if not (states == "ASCENT").any():
        states.iloc[max(0, min(launch_pos, n - 1))] = "ASCENT"
    return states



def detect_altitude_launch_trigger(df: pd.DataFrame, fs_hz: float = 5.0) -> Dict[str, object]:
    """Find a physical launch trigger so altitude rise begins at x=0."""
    if df.empty or "PACKET_COUNT" not in df.columns or "ALTITUDE" not in df.columns:
        return {"launch_packet": np.nan, "method": "unavailable", "baseline_m": np.nan, "threshold_m": np.nan}

    work = df.dropna(subset=["PACKET_COUNT", "ALTITUDE"]).sort_values("PACKET_COUNT").reset_index(drop=True).copy()
    if work.empty:
        return {"launch_packet": np.nan, "method": "unavailable", "baseline_m": np.nan, "threshold_m": np.nan}

    alt = pd.to_numeric(work["ALTITUDE"], errors="coerce").interpolate(limit_direction="both").bfill().ffill().to_numpy(dtype=float)
    pkt = pd.to_numeric(work["PACKET_COUNT"], errors="coerce").to_numpy(dtype=float, copy=True)
    state = work["STATE"].astype(str) if "STATE" in work.columns else pd.Series([""] * len(work))
    ascent_pos = np.where(state.eq("ASCENT").to_numpy(copy=True))[0]
    first_ascent_pos = int(ascent_pos[0]) if len(ascent_pos) else None

    if first_ascent_pos is not None and first_ascent_pos > 3:
        base_slice = alt[max(0, first_ascent_pos - 40):first_ascent_pos]
    else:
        base_slice = alt[:max(5, min(50, len(alt)))]

    finite_base = base_slice[np.isfinite(base_slice)]
    baseline = float(np.nanmedian(finite_base)) if len(finite_base) else float(np.nanmedian(alt[:max(3, min(20, len(alt)))]))
    noise = float(np.nanmedian(np.abs(finite_base - baseline))) if len(finite_base) else 0.0
    max_alt = float(np.nanmax(alt))
    threshold = baseline + max(2.0, 6.0 * noise, 0.015 * abs(max_alt - baseline))

    rise_candidates = np.where(np.isfinite(alt) & (alt > threshold))[0]
    rise_pos = int(rise_candidates[0]) if len(rise_candidates) else None

    if first_ascent_pos is not None and rise_pos is not None:
        dt_s = abs(float(pkt[first_ascent_pos] - pkt[rise_pos])) / fs_hz
        if dt_s <= 2.0:
            return {
                "launch_packet": float(pkt[first_ascent_pos]),
                "method": "STATE_ASCENT_close_to_altitude_rise",
                "baseline_m": baseline,
                "threshold_m": threshold,
                "state_ascent_packet": float(pkt[first_ascent_pos]),
                "altitude_rise_packet": float(pkt[rise_pos]),
                "state_altitude_difference_s": dt_s,
            }
        return {
            "launch_packet": float(pkt[rise_pos]),
            "method": "ALTITUDE_RISE_overrode_STATE_ASCENT",
            "baseline_m": baseline,
            "threshold_m": threshold,
            "state_ascent_packet": float(pkt[first_ascent_pos]),
            "altitude_rise_packet": float(pkt[rise_pos]),
            "state_altitude_difference_s": dt_s,
        }

    if rise_pos is not None:
        return {
            "launch_packet": float(pkt[rise_pos]),
            "method": "ALTITUDE_RISE",
            "baseline_m": baseline,
            "threshold_m": threshold,
            "state_ascent_packet": None,
            "altitude_rise_packet": float(pkt[rise_pos]),
        }

    if first_ascent_pos is not None:
        return {
            "launch_packet": float(pkt[first_ascent_pos]),
            "method": "STATE_ASCENT_fallback",
            "baseline_m": baseline,
            "threshold_m": threshold,
            "state_ascent_packet": float(pkt[first_ascent_pos]),
            "altitude_rise_packet": None,
        }

    return {
        "launch_packet": float(pkt[0]),
        "method": "FIRST_PACKET_fallback",
        "baseline_m": baseline,
        "threshold_m": threshold,
        "state_ascent_packet": None,
        "altitude_rise_packet": None,
    }



def _mission_time_seconds(values: pd.Series) -> Tuple[pd.Series, Dict[str, object]]:
    """
    Parse MISSION_TIME/GPS_TIME into seconds.

    Handles:
    - HH:MM:SS / HH:MM:SS.sss strings
    - numeric seconds
    - datetime-like values
    - midnight wrap
    """
    vals = values.copy()
    report: Dict[str, object] = {"method": "none", "usable": False}
    # numeric seconds first, but reject stuck columns
    numeric = pd.to_numeric(vals, errors="coerce")
    if numeric.notna().sum() >= 3:
        arr = numeric.to_numpy(dtype=float, copy=True)
        finite = np.isfinite(arr)
        if finite.sum() >= 3:
            rng = float(np.nanmax(arr[finite]) - np.nanmin(arr[finite]))
            unique = int(len(np.unique(np.round(arr[finite], 6))))
            if rng > 0 and unique >= 3:
                report.update({"method": "numeric_seconds", "usable": True, "range_s": rng, "unique": unique})
                return pd.Series(arr, index=values.index), report

    # HH:MM:SS parser; safest for USCANSAT-style mission time
    out = []
    ok = []
    for v in vals:
        s = str(v).strip()
        m = re.match(r"^(\d{1,2}):(\d{2}):(\d{2})(?:\.(\d+))?$", s)
        if m:
            h = int(m.group(1)); mi = int(m.group(2)); sec = int(m.group(3))
            frac = float("0." + m.group(4)) if m.group(4) else 0.0
            out.append(h*3600.0 + mi*60.0 + sec + frac)
            ok.append(True)
        else:
            out.append(np.nan)
            ok.append(False)
    ser = pd.Series(out, index=values.index, dtype=float)
    if ser.notna().sum() >= 3:
        arr = ser.to_numpy(dtype=float, copy=True)
        # unwrap midnight if needed
        add = 0.0
        prev = np.nan
        for i, val in enumerate(arr):
            if not np.isfinite(val):
                continue
            if np.isfinite(prev) and val + add < prev - 12*3600:
                add += 24*3600
            arr[i] = val + add
            prev = arr[i]
        finite = np.isfinite(arr)
        rng = float(np.nanmax(arr[finite]) - np.nanmin(arr[finite]))
        unique = int(len(np.unique(np.round(arr[finite], 6))))
        if rng > 0 and unique >= 3:
            report.update({"method": "clock_hms", "usable": True, "range_s": rng, "unique": unique})
            return pd.Series(arr, index=values.index), report

    # fallback datetime parser
    dt = pd.to_datetime(vals.astype(str), errors="coerce")
    if dt.notna().sum() >= 3:
        base = dt.dropna().iloc[0]
        sec = (dt - base).dt.total_seconds()
        rng = float(sec.max() - sec.min())
        unique = int(sec.round(6).nunique(dropna=True))
        if rng > 0 and unique >= 3:
            report.update({"method": "pandas_datetime", "usable": True, "range_s": rng, "unique": unique})
            return sec.astype(float), report

    return pd.Series(np.nan, index=values.index, dtype=float), report


def _build_time_from_launch(raw: pd.DataFrame, launch_packet: float, fs_hz: float = 5.0) -> Tuple[pd.Series, Dict[str, object]]:
    """Prefer real MISSION_TIME; use packet/fs only when real time is not usable."""
    packet = pd.to_numeric(raw["PACKET_COUNT"], errors="coerce")
    launch_idx = int((packet - launch_packet).abs().idxmin()) if packet.notna().any() else int(raw.index[0])

    if "MISSION_TIME" in raw.columns:
        sec, rep = _mission_time_seconds(raw["MISSION_TIME"])
        if rep.get("usable") and sec.notna().sum() >= 3:
            t0 = float(sec.loc[launch_idx]) if pd.notna(sec.loc[launch_idx]) else float(sec.dropna().iloc[0])
            t = sec - t0
            # Validate monotonic and positive duration
            finite = t.dropna()
            if len(finite) >= 3 and float(finite.max() - finite.min()) > 0:
                rep.update({"source": "MISSION_TIME", "launch_index": launch_idx, "launch_packet": launch_packet})
                return t.astype(float), rep

    # Packet fallback only if mission time is absent/unusable
    t = (packet - launch_packet) / float(fs_hz)
    return t.astype(float), {
        "source": "PACKET_COUNT_FALLBACK",
        "method": f"packet_count/{fs_hz:g}Hz",
        "usable": True,
        "launch_index": launch_idx,
        "launch_packet": launch_packet,
    }

def normalize_log_file(source_path: Path, out_dir: Path) -> Path:
    source_path = Path(source_path)
    out_dir = Path(out_dir)
    diag = out_dir / "00_diagnostics"
    diag.mkdir(parents=True, exist_ok=True)

    suffix = source_path.suffix.lower()
    loader_report: Dict[str, object] = {"source_file": str(source_path), "suffix": suffix}

    if suffix in {".csv", ".txt"}:
        raw, rep = _read_csv_trim_extra(source_path)
        loader_report.update(rep)
        raw, rename = _rename_columns(raw)
        loader_report["rename_map"] = rename
        raw["SOURCE_SHEET"] = ""
    elif suffix in {".xlsx", ".xlsm", ".xls"}:
        raw, rep = _read_excel_all_sheets(source_path)
        loader_report.update(rep)
        raw, rename = _rename_columns(raw)
        loader_report["rename_map_after_concat"] = rename
    else:
        raise ValueError(f"Unsupported log type: {suffix}")

    raw = raw.dropna(how="all").copy()
    raw["SOURCE_FILE"] = source_path.name
    raw["SOURCE_ROW"] = np.arange(len(raw)) + 2

    missing = [c for c in ["PACKET_COUNT", "ALTITUDE"] if c not in raw.columns]
    if missing:
        (diag / "normalization_error.json").write_text(json.dumps({
            **loader_report,
            "error": f"missing required columns: {missing}",
            "columns_found": [str(c) for c in raw.columns],
        }, indent=2), encoding="utf-8")
        raise ValueError(f"Cannot normalize log: missing required columns {missing}. Found columns: {list(raw.columns)[:40]}")

    if "STATE" not in raw.columns:
        raw["STATE"] = ""

    # canonical numeric conversion
    for col in raw.columns:
        if col not in {"STATE", "MISSION_TIME", "MODE", "GPS_TIME", "CMD_ECHO", "SOURCE_FILE", "SOURCE_SHEET"}:
            raw[col] = pd.to_numeric(raw[col], errors="coerce")

    raw = raw.dropna(subset=["PACKET_COUNT", "ALTITUDE"]).copy()
    raw = raw.sort_values(["SOURCE_SHEET", "PACKET_COUNT", "SOURCE_ROW"]).reset_index(drop=True)
    raw["STATE_RAW"] = raw["STATE"]
    raw["STATE"] = raw["STATE"].map(normalize_state)

    valid_states = {"LAUNCH_PAD", "ASCENT", "APOGEE", "DESCENT", "PROBE_RELEASE", "PAYLOAD_RELEASE", "LANDED"}
    if (raw["STATE"].isin(valid_states)).sum() < max(3, int(len(raw) * 0.05)) or not raw["STATE"].eq("ASCENT").any():
        raw["STATE"] = infer_state_from_altitude(raw)

    # engine aliases
    if "GPS_LAT" not in raw.columns and "GPS_LATITUDE" in raw.columns:
        raw["GPS_LAT"] = raw["GPS_LATITUDE"]
    if "GPS_LON" not in raw.columns and "GPS_LONGITUDE" in raw.columns:
        raw["GPS_LON"] = raw["GPS_LONGITUDE"]
    if "GPS_ALT" not in raw.columns and "GPS_ALTITUDE" in raw.columns:
        raw["GPS_ALT"] = raw["GPS_ALTITUDE"]

    launch_trigger = detect_altitude_launch_trigger(raw, fs_hz=5.0)
    launch_packet = float(launch_trigger["launch_packet"]) if pd.notna(launch_trigger.get("launch_packet")) else float(raw["PACKET_COUNT"].iloc[0])
    raw["LAUNCH_TRIGGER_METHOD"] = launch_trigger.get("method", "unknown")
    raw["LAUNCH_BASELINE_M"] = launch_trigger.get("baseline_m", np.nan)
    raw["LAUNCH_THRESHOLD_M"] = launch_trigger.get("threshold_m", np.nan)

    # Canonical timebase: altitude rise / accepted launch trigger is x=0.
    # v0.5.11 fix: prefer real MISSION_TIME when available. Do NOT force packet_count/5
    # on 1 Hz flight logs such as USCANSAT FLIGHT.xlsx.
    raw["T_FROM_LAUNCH_S"], timebase_report = _build_time_from_launch(raw, launch_packet, fs_hz=5.0)
    raw["TIMEBASE_SOURCE"] = timebase_report.get("source", "")
    raw["TIMEBASE_METHOD"] = timebase_report.get("method", "")

    # X0 rule: pre-launch altitude is held at the launchpad baseline.
    baseline_m = float(launch_trigger.get("baseline_m", np.nan)) if pd.notna(launch_trigger.get("baseline_m", np.nan)) else 0.0
    raw["ALTITUDE_RAW"] = raw["ALTITUDE"]
    raw.loc[raw["T_FROM_LAUNCH_S"] < 0, "ALTITUDE"] = baseline_m

    optional_defaults = {
        "VOLTAGE": np.nan, "TEMPERATURE": np.nan, "PRESSURE": np.nan, "CURRENT": np.nan,
        "GPS_LAT": np.nan, "GPS_LON": np.nan, "GPS_ALT": np.nan,
        "GYRO_R": np.nan, "GYRO_P": np.nan, "GYRO_Y": np.nan,
        "ACCEL_R": np.nan, "ACCEL_P": np.nan, "ACCEL_Y": np.nan,
        "TOF": np.nan, "YAW": np.nan, "GPS_SATS": np.nan,
        "TILT_ROLL_DERIVED": np.nan, "TILT_PITCH_DERIVED": np.nan,
        "SERVO_CURRENT_1": np.nan, "SERVO_CURRENT_2": np.nan, "SERVO_CURRENT_3": np.nan,
        "SERVO_TARGET_1": np.nan, "SERVO_TARGET_2": np.nan, "SERVO_TARGET_3": np.nan,
    }
    for col, val in optional_defaults.items():
        if col not in raw.columns:
            raw[col] = val

    # v0.5.16: Temperature fallback for logs that store sensor temperature as ALT0_TEMPERATURE.
    # Do not let an empty canonical TEMPERATURE column make the graph family unavailable
    # when the source log has a valid temperature sensor column.
    if "TEMPERATURE" in raw.columns and pd.to_numeric(raw["TEMPERATURE"], errors="coerce").notna().sum() < 2:
        for temp_src in ["ALT0_TEMPERATURE", "ALT1_TEMPERATURE", "CPU_TEMP"]:
            if temp_src in raw.columns and pd.to_numeric(raw[temp_src], errors="coerce").notna().sum() >= 2:
                raw["TEMPERATURE"] = pd.to_numeric(raw[temp_src], errors="coerce")
                break

    # Keep any extra columns too, but put canonical columns first.
    front = [c for c in CANONICAL_ORDER if c in raw.columns]
    rest = [c for c in raw.columns if c not in front]
    normalized = raw[front + rest].copy()

    normalized_path = diag / "normalized_log.csv"
    normalized.to_csv(normalized_path, index=False)

    # also write root-level copy for engine compatibility and quick inspection
    root_copy = out_dir / "normalized_input_for_engine.csv"
    normalized.to_csv(root_copy, index=False)

    # event diagnostics
    flight = normalized[normalized["T_FROM_LAUNCH_S"] >= 0].copy()
    apogee = flight.loc[flight["ALTITUDE"].idxmax()] if not flight.empty else normalized.loc[normalized["ALTITUDE"].idxmax()]
    target80 = float(apogee["ALTITUDE"]) * 0.8 if pd.notna(apogee["ALTITUDE"]) else np.nan
    after_apogee = normalized[normalized["T_FROM_LAUNCH_S"] > float(apogee["T_FROM_LAUNCH_S"])]
    release_state = after_apogee[after_apogee["STATE"].eq("PAYLOAD_RELEASE")]
    release80 = after_apogee[after_apogee["ALTITUDE"] <= target80] if pd.notna(target80) else pd.DataFrame()
    phys_after = normalized[normalized["T_FROM_LAUNCH_S"] >= (float(release_state["T_FROM_LAUNCH_S"].iloc[0]) if not release_state.empty else float(apogee["T_FROM_LAUNCH_S"]))]
    landing_phys = phys_after[phys_after["ALTITUDE"] <= 2.0]
    landing_state = after_apogee[after_apogee["STATE"].eq("LANDED")]

    def row_info(row):
        if row is None or isinstance(row, float):
            return None
        return {
            "time_s": float(row["T_FROM_LAUNCH_S"]),
            "packet": float(row["PACKET_COUNT"]),
            "altitude_m": float(row["ALTITUDE"]),
            "state": str(row["STATE"]),
        }

    event_report = {
        "launch_packet": launch_packet,
        "launch_trigger": launch_trigger,
        "timebase": timebase_report,
        "apogee_by_max_altitude": row_info(apogee),
        "target_80_altitude_m": target80,
        "payload_release_by_state": row_info(release_state.iloc[0]) if not release_state.empty else None,
        "payload_release_by_80_percent_crossing": row_info(release80.iloc[0]) if not release80.empty else None,
        "landing_by_physical_altitude_le_2m": row_info(landing_phys.iloc[0]) if not landing_phys.empty else None,
        "landing_by_state": row_info(landing_state.iloc[0]) if not landing_state.empty else None,
        "state_counts": normalized["STATE"].value_counts(dropna=False).to_dict(),
    }

    report = {
        **loader_report,
        "rows_normalized": int(len(normalized)),
        "columns_normalized": [str(c) for c in normalized.columns],
        "normalized_csv": str(normalized_path),
        "root_engine_csv": str(root_copy),
        "events": event_report,
    }
    (diag / "normalization_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (diag / "state_counts.csv").write_text(normalized["STATE"].value_counts(dropna=False).to_csv(), encoding="utf-8")
    return root_copy
