from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
import hashlib
import json
import time
from pathlib import Path
from io import BytesIO

import streamlit as st
import streamlit.components.v1 as components

# Make matplotlib safe on headless web hosts.
os.environ.setdefault("MPLBACKEND", "Agg")

APP_TITLE = "CanSat Flight Data Studio"
SUPPORTED_TYPES = ["csv", "txt", "xlsx", "xlsm", "xls"]

GRAPH_FAMILIES = {
    "altitude": {"label": "Altitude", "hint": "main launch/apogee altitude previews", "folder_prefix": "01_alt"},
    "velocity": {"label": "Velocity", "hint": "descent-rate and rule trend graphs", "folder_prefix": "02_vel"},
    "conops": {"label": "CONOPS", "hint": "actual vs planned mission profile", "folder_prefix": "06_conops"},
    "voltage_temperature": {"label": "Voltage + Temperature", "hint": "sensor health scalar graphs", "folder_prefix": "03_vt"},
    "gps": {"label": "GPS", "hint": "3D path, ground track, GPS checks", "folder_prefix": "04_gps"},
    "multi_axis": {"label": "Motion / Multi-axis", "hint": "accel, gyro, tilt focus + compared graphs", "folder_prefix": "05_multi"},
}

PRESETS = {
    "Quick Check": ["altitude", "velocity", "conops"],
    "Sensor Health": ["voltage_temperature"],
    "GPS Pack": ["gps"],
    "Motion Pack": ["multi_axis"],
    "Report Pack": ["altitude", "velocity", "voltage_temperature", "gps", "conops"],
    "Full Export": list(GRAPH_FAMILIES.keys()),
    "Custom": ["altitude", "velocity", "conops"],
}


st.set_page_config(
    page_title="CFDS Web",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 0.75rem; padding-bottom: 1.5rem; max-width: 1180px; }
    div[data-testid="stSidebar"] { min-width: 250px; }
    .cfds-hero {
        padding: 0.95rem 1rem;
        border-radius: 20px;
        border: 1px solid rgba(148, 163, 184, 0.25);
        background: linear-gradient(135deg, rgba(15,23,42,0.96), rgba(30,64,175,0.88));
        color: white;
        margin-bottom: 0.75rem;
    }
    .cfds-hero h1 { margin: 0; font-size: clamp(1.45rem, 4vw, 2.1rem); }
    .cfds-hero p { opacity: 0.86; margin: 0.3rem 0 0 0; }
    .cfds-card {
        padding: 0.8rem 0.9rem;
        border-radius: 16px;
        border: 1px solid rgba(148, 163, 184, 0.25);
        background: rgba(248, 250, 252, 0.72);
    }
    .stButton button, .stDownloadButton button { min-height: 3rem; border-radius: 14px; font-weight: 700; }
    .metric-card { padding: 0.65rem 0.8rem; border-radius: 14px; background: rgba(241,245,249,0.78); border: 1px solid rgba(148,163,184,0.25); }
    .replay-card { padding: 0.8rem 0.9rem; border-radius: 18px; border: 1px solid rgba(248,113,113,0.35); background: rgba(255,247,247,0.72); margin: 0.4rem 0 0.8rem 0; }
    @media (max-width: 760px) {
        .block-container { padding-left: 0.55rem; padding-right: 0.55rem; }
        .cfds-hero { border-radius: 16px; padding: 0.85rem; }
        .cfds-hero p { font-size: 0.88rem; }
    
    /* ---------- Visibility fix for mission input / upload / generation panels ---------- */
    .cfds-panel,
    .cfds-panel * {
        color: var(--cfds-text) !important;
    }
    .cfds-panel-title {
        color: var(--cfds-cyan) !important;
        text-shadow: 0 0 12px rgba(56, 213, 255, .22);
    }
    div[data-testid="stFileUploader"] {
        background: rgba(7,24,39,.72) !important;
        border: 1px solid rgba(56,213,255,.24) !important;
        border-radius: 14px !important;
        padding: .35rem .55rem !important;
    }
    div[data-testid="stFileUploader"] label,
    div[data-testid="stFileUploader"] label p,
    div[data-testid="stFileUploader"] small,
    div[data-testid="stFileUploader"] span,
    div[data-testid="stFileUploader"] div,
    div[data-testid="stFileUploader"] section,
    div[data-testid="stFileUploader"] [data-testid="stWidgetLabel"] p {
        color: #DDF8FF !important;
        opacity: 1 !important;
    }
    div[data-testid="stFileUploader"] section {
        background: rgba(14,43,69,.78) !important;
        border: 1px dashed rgba(56,213,255,.42) !important;
    }
    div[data-testid="stFileUploader"] button,
    div[data-testid="stFileUploaderDropzone"] button {
        background: linear-gradient(180deg, #0B84FF, #0067C8) !important;
        color: #FFFFFF !important;
        border: 1px solid rgba(221,248,255,.65) !important;
        font-weight: 800 !important;
    }
    div[data-testid="stFileUploaderDropzone"] svg,
    div[data-testid="stFileUploader"] svg {
        color: #38D5FF !important;
        fill: #38D5FF !important;
        opacity: 1 !important;
    }
    .stCheckbox label, .stRadio label, .stSlider label,
    .stSelectbox label, .stMultiSelect label {
        color: #DDF8FF !important;
        opacity: 1 !important;
    }
    .stCheckbox p, .stRadio p, .stSlider p,
    .stSelectbox p, .stMultiSelect p {
        color: #DDF8FF !important;
        opacity: 1 !important;
    }

    div[data-testid="stImage"] img { border-radius: 10px; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# V12.56-adapted mobile console skin. This keeps Streamlit's simple layout,
# but gives the web app the same control-studio language as the desktop UI.
st.markdown(
    """
    <style>
    :root {
        --cfds-bg: #050b12;
        --cfds-panel: #071827;
        --cfds-panel-2: #0b2136;
        --cfds-card: #0e2b45;
        --cfds-border: rgba(56, 213, 255, .28);
        --cfds-border-soft: rgba(148, 163, 184, .20);
        --cfds-text: #eaffff;
        --cfds-muted: #99b4c9;
        --cfds-cyan: #38d5ff;
        --cfds-blue: #0b84ff;
        --cfds-green: #22c55e;
        --cfds-red: #ff4b55;
        --cfds-yellow: #f59e0b;
    }
    html, body, [data-testid="stAppViewContainer"] {
        background:
          radial-gradient(circle at 15% 0%, rgba(56, 213, 255, .12), transparent 28%),
          linear-gradient(180deg, #081122 0%, #050b12 42%, #04080f 100%) !important;
        color: var(--cfds-text) !important;
    }
    [data-testid="stHeader"] { background: rgba(5, 11, 18, .72) !important; backdrop-filter: blur(12px); }
    .block-container { max-width: 1320px !important; padding-top: .8rem !important; }
    .cfds-hero { display:none !important; }
    .cfds-v12-top {
        border: 1px solid var(--cfds-border);
        background: linear-gradient(180deg, rgba(7,24,39,.96), rgba(5,11,18,.96));
        border-radius: 18px;
        box-shadow: 0 0 30px rgba(56, 213, 255, .10), inset 0 1px 0 rgba(255,255,255,.06);
        margin: 0 0 .8rem 0;
        overflow: hidden;
    }
    .cfds-v12-brand {
        display: grid; grid-template-columns: 1.1fr 1fr; gap: .8rem; align-items: center;
        padding: .95rem 1rem .75rem 1rem; border-bottom: 1px solid rgba(56,213,255,.16);
    }
    .cfds-logo { display:flex; align-items:center; gap:.8rem; }
    .cfds-mark { width:42px; height:42px; border-radius:12px; display:grid; place-items:center; color:#06111f; background:linear-gradient(135deg,#38d5ff,#0b84ff); font-weight:900; box-shadow:0 0 18px rgba(56,213,255,.35); }
    .cfds-title { font-size: clamp(1.55rem, 4.8vw, 2.6rem); letter-spacing:.08em; font-weight:900; line-height:1; color:var(--cfds-text); }
    .cfds-sub { margin-top:.25rem; color:var(--cfds-muted); font-size:.82rem; letter-spacing:.12em; text-transform:uppercase; }
    .cfds-metrics { display:grid; grid-template-columns: repeat(4,1fr); gap:.45rem; }
    .cfds-chip { border-left:1px solid rgba(56,213,255,.18); padding:.25rem .65rem; min-height:46px; }
    .cfds-chip b { display:block; color:var(--cfds-cyan); font-size:.7rem; letter-spacing:.14em; text-transform:uppercase; }
    .cfds-chip span { color:var(--cfds-text); font-size:.92rem; }
    .cfds-dock { display:grid; grid-template-columns:repeat(5,1fr); }
    .cfds-dock a { text-align:center; padding:.8rem .25rem; text-decoration:none; color:#b9cce0; border-right:1px solid rgba(56,213,255,.11); letter-spacing:.12em; font-size:.82rem; text-transform:uppercase; }
    .cfds-dock a:hover, .cfds-dock .active { color:var(--cfds-cyan); background:rgba(56,213,255,.08); box-shadow:inset 0 -3px 0 var(--cfds-cyan); }
    .cfds-panel {
        border:1px solid var(--cfds-border);
        background:linear-gradient(180deg, rgba(7,24,39,.92), rgba(5,11,18,.90));
        border-radius:18px; padding:1rem; margin:.8rem 0;
        box-shadow: inset 0 1px 0 rgba(255,255,255,.04);
    }
    .cfds-panel-title { color:var(--cfds-cyan); letter-spacing:.12em; text-transform:uppercase; font-weight:800; margin-bottom:.55rem; }
    .cfds-card, .metric-card, .replay-card {
        background: rgba(7,24,39,.72) !important;
        color: var(--cfds-text) !important;
        border: 1px solid var(--cfds-border-soft) !important;
        border-radius: 16px !important;
    }
    h1, h2, h3, h4, p, label, span, div, .stMarkdown, .stCaptionContainer, [data-testid="stMarkdownContainer"] { color: inherit; }
    .stCaptionContainer, small { color: var(--cfds-muted) !important; }
    .stButton button, .stDownloadButton button {
        background: linear-gradient(180deg, rgba(14,43,69,.96), rgba(7,24,39,.96)) !important;
        color: var(--cfds-text) !important;
        border: 1px solid rgba(56,213,255,.32) !important;
        border-radius: 12px !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,.05);
    }
    .stButton button[kind="primary"], .stButton button:hover, .stDownloadButton button:hover {
        background: linear-gradient(180deg, #0b84ff, #0067c8) !important;
        border-color: rgba(56,213,255,.85) !important;
        color: white !important;
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(7,24,39,.98), rgba(5,11,18,.98)) !important;
        border-right: 1px solid var(--cfds-border) !important;
    }
    [data-testid="stFileUploader"] section, [data-testid="stExpander"], [data-testid="stMetric"], [data-testid="stTabs"] {
        background: rgba(7,24,39,.55) !important;
        border-color: rgba(56,213,255,.16) !important;
    }

    /* ---------- Visibility fix for mission input / upload / generation panels ---------- */
    .cfds-panel,
    .cfds-panel * {
        color: var(--cfds-text) !important;
    }
    .cfds-panel-title {
        color: var(--cfds-cyan) !important;
        text-shadow: 0 0 12px rgba(56, 213, 255, .22);
    }
    div[data-testid="stFileUploader"] {
        background: rgba(7,24,39,.72) !important;
        border: 1px solid rgba(56,213,255,.24) !important;
        border-radius: 14px !important;
        padding: .35rem .55rem !important;
    }
    div[data-testid="stFileUploader"] label,
    div[data-testid="stFileUploader"] label p,
    div[data-testid="stFileUploader"] small,
    div[data-testid="stFileUploader"] span,
    div[data-testid="stFileUploader"] div,
    div[data-testid="stFileUploader"] section,
    div[data-testid="stFileUploader"] [data-testid="stWidgetLabel"] p {
        color: #DDF8FF !important;
        opacity: 1 !important;
    }
    div[data-testid="stFileUploader"] section {
        background: rgba(14,43,69,.78) !important;
        border: 1px dashed rgba(56,213,255,.42) !important;
    }
    div[data-testid="stFileUploader"] button,
    div[data-testid="stFileUploaderDropzone"] button {
        background: linear-gradient(180deg, #0B84FF, #0067C8) !important;
        color: #FFFFFF !important;
        border: 1px solid rgba(221,248,255,.65) !important;
        font-weight: 800 !important;
    }
    div[data-testid="stFileUploaderDropzone"] svg,
    div[data-testid="stFileUploader"] svg {
        color: #38D5FF !important;
        fill: #38D5FF !important;
        opacity: 1 !important;
    }
    .stCheckbox label, .stRadio label, .stSlider label,
    .stSelectbox label, .stMultiSelect label {
        color: #DDF8FF !important;
        opacity: 1 !important;
    }
    .stCheckbox p, .stRadio p, .stSlider p,
    .stSelectbox p, .stMultiSelect p {
        color: #DDF8FF !important;
        opacity: 1 !important;
    }

    div[data-testid="stImage"] img {
        border-radius: 12px !important;
        border: 1px solid rgba(56,213,255,.22);
        background: #f7fcff;
    }
    .cfds-mobile-note { color:var(--cfds-muted); font-size:.86rem; margin-top:.4rem; }
    @media (max-width: 760px) {
        .cfds-v12-brand { grid-template-columns: 1fr; }
        .cfds-metrics { grid-template-columns: repeat(2,1fr); }
        .cfds-dock { grid-template-columns: repeat(5, minmax(54px,1fr)); overflow-x:auto; }
        .cfds-dock a { font-size:.68rem; letter-spacing:.04em; padding:.7rem .15rem; }
        .cfds-chip { padding:.25rem .45rem; }
        .cfds-chip span { font-size:.82rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)



# --- V12.56 Replay Dashboard CSS upgrade (mobile-first, dark HUD graph workspace) ---
st.markdown(
    """
    <style>
    .cfds-replay-shell { border: 1px solid rgba(56,213,255,.30); background: radial-gradient(circle at 18% 0%, rgba(56,213,255,.10), transparent 30%), linear-gradient(180deg, rgba(7,24,39,.96), rgba(4,8,15,.96)); border-radius: 20px; padding: 1rem; margin: .9rem 0; box-shadow: 0 0 28px rgba(56,213,255,.08), inset 0 1px 0 rgba(255,255,255,.05); }
    .cfds-replay-head { display:flex; justify-content:space-between; gap:.75rem; align-items:flex-start; border-bottom:1px solid rgba(56,213,255,.16); padding-bottom:.7rem; margin-bottom:.8rem; }
    .cfds-replay-kicker { color:#38d5ff; letter-spacing:.14em; text-transform:uppercase; font-weight:800; font-size:.78rem; }
    .cfds-replay-title { color:#eaffff; font-size:clamp(1.3rem,4vw,2.0rem); font-weight:900; letter-spacing:.04em; margin:.1rem 0 0 0; }
    .cfds-replay-sub { color:#99b4c9; font-size:.88rem; margin-top:.2rem; }
    .cfds-replay-badges { display:flex; flex-wrap:wrap; gap:.45rem; justify-content:flex-end; }
    .cfds-badge { border:1px solid rgba(56,213,255,.28); border-radius:999px; padding:.32rem .62rem; color:#dbeafe; background:rgba(14,43,69,.74); font-size:.78rem; white-space:nowrap; }
    .cfds-badge b { color:#38d5ff; }
    .cfds-control-block { border:1px solid rgba(56,213,255,.18); background:rgba(5,11,18,.35); border-radius:16px; padding:.8rem; margin-bottom:.7rem; }
    .cfds-control-title { color:#38d5ff; font-size:.78rem; font-weight:800; letter-spacing:.12em; text-transform:uppercase; margin-bottom:.45rem; }
    .cfds-status-grid { display:grid; grid-template-columns:1fr 1fr; gap:.45rem; }
    .cfds-status-cell { border:1px solid rgba(148,163,184,.14); border-radius:12px; padding:.55rem; background:rgba(7,24,39,.48); }
    .cfds-status-cell span { display:block; color:#99b4c9; font-size:.68rem; letter-spacing:.09em; text-transform:uppercase; }
    .cfds-status-cell b { display:block; color:#eaffff; margin-top:.14rem; font-size:.95rem; }
    .cfds-state-pill { display:inline-block; border-radius:999px; padding:.22rem .65rem; color:#EAFBFF !important; background:rgba(14,43,69,.82) !important; border:1px solid rgba(56,213,255,.72) !important; font-weight:900; font-size:.72rem; letter-spacing:.05em; box-shadow:0 0 0 1px rgba(0,0,0,.25) inset; }
    .cfds-graph-card { border:1px solid rgba(56,213,255,.18); background:linear-gradient(180deg, rgba(7,24,39,.74), rgba(5,11,18,.52)); border-radius:18px; padding:.75rem; }
    .cfds-graph-titlebar { display:flex; justify-content:space-between; align-items:center; gap:.7rem; padding:.2rem .25rem .6rem .25rem; }
    .cfds-graph-titlebar h3 { color:#38d5ff; margin:0; letter-spacing:.08em; text-transform:uppercase; font-size:1rem; }
    .cfds-graph-titlebar span { color:#99b4c9; font-size:.78rem; }
    .cfds-mini-help { color:#99b4c9; font-size:.78rem; padding:.55rem .25rem 0 .25rem; }
    .cfds-event-strip { display:grid; grid-template-columns:repeat(auto-fit,minmax(132px,1fr)); gap:.45rem; margin:.70rem .15rem .1rem .15rem; }
    .cfds-event-chip { border:1px solid rgba(56,213,255,.20); background:rgba(7,24,39,.68); border-radius:12px; padding:.48rem .55rem; }
    .cfds-event-chip span { display:block; color:#99b4c9; font-size:.62rem; letter-spacing:.09em; text-transform:uppercase; }
    .cfds-event-chip b { display:block; color:#eaffff; font-size:.82rem; margin-top:.12rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .cfds-state-strip { display:grid; grid-template-columns:repeat(7,minmax(0,1fr)); gap:.46rem; align-items:stretch; border:1px solid rgba(56,213,255,.18); background:rgba(7,24,39,.48); border-radius:12px; margin:1.05rem .15rem .55rem .15rem; padding:.72rem .72rem .68rem .72rem; position:relative; }
    .cfds-state-strip-title { position:absolute; top:-.72rem; left:.72rem; background:#071827; color:#9db7c9; font-size:.64rem; letter-spacing:.12em; text-transform:uppercase; font-weight:900; padding:0 .42rem; }
    .cfds-state-chip { display:flex; align-items:center; justify-content:center; gap:.36rem; min-height:2.15rem; padding:.35rem .44rem; color:#eafaff; font-size:.68rem; font-weight:800; letter-spacing:.055em; white-space:nowrap; border:1px solid rgba(234,251,255,.16); border-radius:10px; background:rgba(14,43,69,.50); overflow:hidden; text-overflow:ellipsis; }
    .cfds-state-dot { width:.72rem; height:.72rem; min-width:.72rem; border-radius:999px; border:1px solid rgba(255,255,255,.78); box-shadow:0 0 0 1px rgba(0,0,0,.45); }
    .cfds-replay-tipbar { border-top:1px solid rgba(56,213,255,.14); color:#99b4c9; margin-top:.55rem; padding:.55rem .2rem .05rem .2rem; font-size:.78rem; }
    @media (max-width: 760px) { .cfds-replay-shell { padding:.68rem; border-radius:16px; } .cfds-replay-head { display:block; } .cfds-replay-badges { justify-content:flex-start; margin-top:.6rem; } .cfds-status-grid { grid-template-columns:1fr; } .cfds-graph-card { padding:.35rem; } .cfds-event-strip { grid-template-columns:1fr 1fr; gap:.35rem; } .cfds-state-strip { grid-template-columns:repeat(2,minmax(0,1fr)); gap:.38rem; padding:.68rem .50rem .55rem .50rem; } .cfds-state-chip { justify-content:flex-start; font-size:.62rem; min-height:2.05rem; } }
    </style>
    """,
    unsafe_allow_html=True,
)


def safe_filename(name: str) -> str:
    keep = []
    for ch in name:
        if ch.isalnum() or ch in {".", "_", "-", " ", "(", ")"}:
            keep.append(ch)
        else:
            keep.append("_")
    clean = "".join(keep).strip()
    return clean or "uploaded_log.csv"


def make_zip_bytes(folder: Path) -> bytes:
    """Fast ZIP creation. compresslevel=1 is much quicker on small cloud CPUs."""
    return make_filtered_zip_bytes(folder, "CFDS_graph_exports.zip", include_suffixes=None)


def make_filtered_zip_bytes(folder: Path, archive_name: str, include_suffixes: set[str] | None = None) -> bytes:
    """Create an export ZIP from a folder, optionally filtered by file suffix."""
    archive_path = folder.parent / archive_name
    if archive_path.exists():
        archive_path.unlink()
    try:
        zf_ctx = zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=1)
    except TypeError:
        zf_ctx = zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED)
    with zf_ctx as zf:
        for file in sorted(folder.rglob("*")):
            if not file.is_file():
                continue
            if include_suffixes is not None and file.suffix.lower() not in include_suffixes:
                continue
            # Mobile thumbnail cache should never go into official exports.
            if "_mobile_previews" in file.parts:
                continue
            zf.write(file, file.relative_to(folder))
    return archive_path.read_bytes()


def collect_export_payload(output_dir: Path, code: int, logs: str) -> dict:
    """Store export data in session_state so buttons keep working after Streamlit reruns."""
    png_files = sorted(output_dir.rglob("*.png"), key=_score_preview)
    report_md = output_dir / "00_diagnostics" / "flight_report.md"
    normalized_csv = output_dir / "00_diagnostics" / "normalized_log.csv"

    individual_pngs = []
    for png in png_files[:80]:
        try:
            individual_pngs.append((str(png.relative_to(output_dir)), png.read_bytes()))
        except Exception:
            pass

    payload = {
        "status_code": code,
        "logs": logs[-20000:],
        "png_count": len(png_files),
        "full_zip": make_zip_bytes(output_dir),
        "png_zip": make_filtered_zip_bytes(output_dir, "CFDS_png_only_export.zip", {".png"}),
        "diagnostics_zip": make_filtered_zip_bytes(output_dir, "CFDS_diagnostics_export.zip", {".json", ".csv", ".md", ".txt"}),
        "individual_pngs": individual_pngs,
        "folder_zips": make_folder_zips(output_dir),
        "report_text": report_md.read_text(encoding="utf-8", errors="replace") if report_md.exists() else "",
        "normalized_csv": normalized_csv.read_bytes() if normalized_csv.exists() else b"",
    }
    return payload


def _download_kwargs(key: str) -> dict:
    """Keep download buttons from rerunning the whole Streamlit page.

    Streamlit's default download_button behavior is to rerun the app after a
    click. On iPhone this makes expanders/folder sections look like they
    suddenly disappeared. on_click="ignore" keeps the UI stable.
    """
    return {"key": key, "on_click": "ignore"}




def _safe_radio_choice(label: str, options: list[str], key: str, index: int = 0, help_text: str | None = None) -> str | None:
    """iPhone-safe selector.

    Streamlit selectbox is searchable and on iPhone it can leave typed filter text
    in the field with a red/invalid border. Radio buttons are less compact but
    they are tap-only, so the value cannot desync from the visible label.
    """
    if not options:
        return None
    index = max(0, min(index, len(options) - 1))
    return st.radio(
        label,
        options,
        index=index,
        key=key,
        horizontal=False,
        help=help_text,
    )

def show_export_center(payload: dict) -> None:
    st.markdown('<a id="export"></a><div class="cfds-panel"><div class="cfds-panel-title">Export control deck</div>', unsafe_allow_html=True)
    st.subheader("Export center")
    st.caption("Use these buttons directly in the web app. On iPhone, downloaded files go to Files/Downloads.")

    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "⬇️ Export full CFDS ZIP",
            data=payload.get("full_zip", b""),
            file_name="CFDS_graph_exports.zip",
            mime="application/zip",
            use_container_width=True,
            disabled=not payload.get("full_zip"),
            **_download_kwargs("dl_full_cfds_zip"),
        )
        st.download_button(
            "🖼️ Export PNG graphs only",
            data=payload.get("png_zip", b""),
            file_name="CFDS_png_only_export.zip",
            mime="application/zip",
            use_container_width=True,
            disabled=not payload.get("png_zip"),
            **_download_kwargs("dl_png_graphs_only"),
        )
    with c2:
        st.download_button(
            "🧪 Export diagnostics",
            data=payload.get("diagnostics_zip", b""),
            file_name="CFDS_diagnostics_export.zip",
            mime="application/zip",
            use_container_width=True,
            disabled=not payload.get("diagnostics_zip"),
            **_download_kwargs("dl_diagnostics_zip"),
        )
        st.download_button(
            "📄 Export flight report",
            data=payload.get("report_text", ""),
            file_name="flight_report.md",
            mime="text/markdown",
            use_container_width=True,
            disabled=not payload.get("report_text"),
            **_download_kwargs("dl_flight_report_md"),
        )

    if payload.get("normalized_csv"):
        st.download_button(
            "📊 Export normalized CSV",
            data=payload["normalized_csv"],
            file_name="normalized_log.csv",
            mime="text/csv",
            use_container_width=True,
            **_download_kwargs("dl_normalized_csv"),
        )

    folder_zips = payload.get("folder_zips", {})
    individual_pngs = payload.get("individual_pngs", [])

    # Export browser: one folder selector controls both folder ZIP and PNG list.
    # This is more stable on iPhone than two independent widgets, and it prevents
    # the PNG selector from showing stale files after the selected folder changes.
    if folder_zips or individual_pngs:
        st.markdown("### Graph export browser")
        st.caption("Choose one graph folder, then download that folder ZIP or one PNG from that same folder.")

        png_by_folder: dict[str, list[tuple[str, bytes]]] = {}
        for rel_name, data in individual_pngs:
            folder_name = str(Path(rel_name).parent).replace("\\", "/")
            if folder_name in ["", "."]:
                folder_name = "root"
            png_by_folder.setdefault(folder_name, []).append((rel_name, data))

        folder_names = sorted(set(folder_zips.keys()) | set(png_by_folder.keys()))
        if folder_names:
            previous = st.session_state.get("export_graph_folder", folder_names[0])
            if previous not in folder_names:
                previous = folder_names[0]
            selected_folder = _safe_radio_choice(
                "Choose graph folder",
                folder_names,
                key="export_graph_folder_radio",
                index=folder_names.index(previous),
                help_text="Tap one folder. This avoids the searchable selectbox state bug on iPhone.",
            )
            st.session_state["export_graph_folder"] = selected_folder

            if selected_folder in folder_zips:
                folder_file_name = "CFDS_" + selected_folder.replace("/", "_").replace("\\", "_") + "_png.zip"
                st.download_button(
                    f"⬇️ Download selected folder ZIP: {selected_folder}",
                    data=folder_zips[selected_folder],
                    file_name=folder_file_name,
                    mime="application/zip",
                    use_container_width=True,
                    **_download_kwargs(f"dl_folder_zip_{hashlib.sha1(selected_folder.encode('utf-8')).hexdigest()[:10]}"),
                )
            else:
                st.info("This folder has PNG files, but no folder ZIP was packed for it.")

            folder_pngs = sorted(png_by_folder.get(selected_folder, []), key=lambda item: item[0])
            st.markdown("### Individual PNG download")
            if not folder_pngs:
                st.info("No individual PNG found in this folder.")
            elif len(folder_pngs) == 1:
                rel_name, data = folder_pngs[0]
                st.caption(f"1 PNG available in {selected_folder}")
                st.download_button(
                    f"⬇️ Download PNG: {Path(rel_name).name}",
                    data=data,
                    file_name=Path(rel_name).name,
                    mime="image/png",
                    use_container_width=True,
                    **_download_kwargs(f"dl_png_single_{hashlib.sha1(rel_name.encode('utf-8')).hexdigest()[:10]}"),
                )
            else:
                png_labels = [rel_name for rel_name, _ in folder_pngs]
                png_key = "export_individual_png_selector_" + hashlib.sha1(selected_folder.encode("utf-8")).hexdigest()[:10]
                selected_png = _safe_radio_choice(
                    f"Choose PNG ({len(folder_pngs)} in this folder)",
                    png_labels,
                    index=0,
                    key=png_key + "_radio",
                    help_text="Tap one PNG from the selected folder.",
                )
                png_lookup = dict(folder_pngs)
                st.download_button(
                    f"⬇️ Download PNG: {Path(selected_png).name}",
                    data=png_lookup[selected_png],
                    file_name=Path(selected_png).name,
                    mime="image/png",
                    use_container_width=True,
                    **_download_kwargs(f"dl_png_{hashlib.sha1(selected_png.encode('utf-8')).hexdigest()[:10]}"),
                )

    st.markdown('</div>', unsafe_allow_html=True)

def run_worker(input_path: Path, output_dir: Path, mode: str, speed: str, families: list[str]) -> tuple[int, str]:
    env = os.environ.copy()
    env.setdefault("MPLBACKEND", "Agg")
    cmd = [
        sys.executable,
        str(Path(__file__).with_name("run_worker.py")),
        "--csv",
        str(input_path),
        "--out",
        str(output_dir),
        "--mode",
        mode,
        "--speed",
        speed,
        "--families",
        ",".join(families),
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(Path(__file__).parent),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return proc.returncode, proc.stdout


def show_report(output_dir: Path) -> None:
    report_md = output_dir / "00_diagnostics" / "flight_report.md"
    if report_md.exists():
        with st.expander("Flight report", expanded=False):
            st.markdown(report_md.read_text(encoding="utf-8", errors="replace"))

    manifest = output_dir / "studio_manifest.json"
    if manifest.exists():
        with st.expander("Studio manifest / diagnostics", expanded=False):
            st.code(manifest.read_text(encoding="utf-8", errors="replace"), language="json")


def _thumbnail_path(src: Path, cache_dir: Path, max_width: int = 900) -> Path:
    """Create a lightweight mobile preview image without changing export files."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"{src.stem}_preview.jpg"
    if out.exists():
        return out
    try:
        from PIL import Image
        img = Image.open(src)
        img.thumbnail((max_width, max_width * 3))
        if img.mode in ("RGBA", "LA"):
            bg = Image.new("RGB", img.size, "white")
            bg.paste(img, mask=img.getchannel("A"))
            img = bg
        else:
            img = img.convert("RGB")
        img.save(out, "JPEG", quality=72, optimize=True)
        return out
    except Exception:
        return src


def _score_preview(png: Path) -> tuple[int, str]:
    name = png.name.lower()
    rel = str(png).lower()
    # Put the most useful checks first on mobile.
    if "altitude" in name or "01_alt" in rel:
        return (0, name)
    if "velocity" in name or "02_vel" in rel:
        return (1, name)
    if "conops" in name or "06_conops" in rel:
        return (2, name)
    if "voltage" in name or "temperature" in name or "03_vt" in rel:
        return (3, name)
    if "gps" in name or "04_gps" in rel:
        return (4, name)
    return (5, name)


def _folder_label(folder: Path, output_dir: Path, count: int) -> str:
    rel = folder.relative_to(output_dir)
    name = "All folders" if str(rel) == "." else str(rel)
    return f"{name}  ({count})"


def show_previews(output_dir: Path, max_images: int, show_full_png: bool, show_all_folders: bool) -> None:
    png_files = sorted(output_dir.rglob("*.png"), key=_score_preview)
    if not png_files:
        st.warning("No PNG previews were generated. Check diagnostics or error log in the ZIP.")
        return

    thumb_dir = output_dir / "00_diagnostics" / "_mobile_previews"

    folders = sorted({p.parent for p in png_files}, key=lambda x: str(x.relative_to(output_dir)))
    folder_counts = {folder: sum(1 for p in png_files if p.parent == folder) for folder in folders}

    st.markdown('<a id="preview"></a><div class="cfds-panel"><div class="cfds-panel-title">Graph preview browser</div>', unsafe_allow_html=True)
    st.subheader("Preview browser")
    st.caption(
        f"Generated {len(png_files)} PNG files. Choose a folder to browse, or use Fast preview for the first {max_images}. "
        "Phone previews are compressed; ZIP exports keep the selected quality profile."
    )

    tab_fast, tab_folder = st.tabs(["⚡ Fast preview", "📁 Folder browser"])

    with tab_fast:
        visible = png_files[:max_images]
        st.caption(f"Showing {len(visible)} of {len(png_files)} PNG files.")
        for png in visible:
            preview_img = png if show_full_png else _thumbnail_path(png, thumb_dir)
            st.image(str(preview_img), caption=str(png.relative_to(output_dir)), use_container_width=True)

    with tab_folder:
        labels = [_folder_label(folder, output_dir, folder_counts[folder]) for folder in folders]
        selected_label = _safe_radio_choice(
            "Choose graph folder",
            labels,
            index=0,
            key="preview_graph_folder_radio",
            help_text="Tap-only folder picker for iPhone stability.",
        )
        selected_folder = folders[labels.index(selected_label)]
        folder_files = sorted([p for p in png_files if p.parent == selected_folder], key=lambda p: p.name)

        # Streamlit sliders require min_value < max_value.
        # Some selected folders contain only one image, so render that image directly
        # instead of creating a 1..1 slider that crashes the app.
        if len(folder_files) <= 1:
            folder_limit = len(folder_files)
            st.caption(
                f"Showing {folder_limit} of {len(folder_files)} image in {selected_folder.relative_to(output_dir)}"
            )
        else:
            default_limit = min(len(folder_files), 12)
            safe_folder_key = hashlib.sha1(str(selected_folder.relative_to(output_dir)).encode("utf-8")).hexdigest()[:10]
            folder_limit = st.slider(
                "Images from this folder",
                min_value=1,
                max_value=len(folder_files),
                value=default_limit,
                step=1,
                key=f"folder_preview_limit_{safe_folder_key}",
            )
            st.caption(
                f"Showing {min(folder_limit, len(folder_files))} of {len(folder_files)} images in {selected_folder.relative_to(output_dir)}"
            )

        for png in folder_files[:folder_limit]:
            preview_img = png if show_full_png else _thumbnail_path(png, thumb_dir)
            st.image(str(preview_img), caption=png.name, use_container_width=True)

    if show_all_folders:
        with st.expander("Folder summary", expanded=False):
            for folder in folders:
                st.markdown(f"**{folder.relative_to(output_dir)}** — {folder_counts[folder]} images")




def _score_preview_name(rel_name: str) -> tuple[int, str]:
    name = Path(rel_name).name.lower()
    rel = rel_name.lower()
    if "altitude" in name or "01_alt" in rel:
        return (0, name)
    if "velocity" in name or "02_vel" in rel:
        return (1, name)
    if "conops" in name or "06_conops" in rel:
        return (2, name)
    if "voltage" in name or "temperature" in name or "03_vt" in rel:
        return (3, name)
    if "gps" in name or "04_gps" in rel:
        return (4, name)
    return (5, name)


def _preview_image_bytes(png_bytes: bytes, show_full_png: bool, max_width: int = 900) -> bytes:
    """Return stable in-memory bytes for Streamlit image rendering.

    Important: Streamlit reruns the script after widget changes. The graph files are
    generated in a TemporaryDirectory that disappears after the generation run, so
    preview images must come from session-state bytes, not from local temp paths.
    """
    if show_full_png:
        return png_bytes
    try:
        from PIL import Image
        img = Image.open(BytesIO(png_bytes))
        img.thumbnail((max_width, max_width * 3))
        if img.mode in ("RGBA", "LA"):
            bg = Image.new("RGB", img.size, "white")
            bg.paste(img, mask=img.getchannel("A"))
            img = bg
        else:
            img = img.convert("RGB")
        out = BytesIO()
        img.save(out, "JPEG", quality=72, optimize=True)
        return out.getvalue()
    except Exception:
        return png_bytes


def _set_preview_folder(folder: str) -> None:
    """Persist selected preview folder through Streamlit reruns."""
    st.session_state["preview_selected_folder"] = folder


def show_previews_from_payload(payload: dict, max_images: int, show_full_png: bool, show_all_folders: bool) -> None:
    """Render preview images from cached bytes using an iPhone-safe single view.

    Earlier builds used Streamlit tabs plus a folder radio. On iPhone this felt like
    the image did not change because any widget interaction reruns the script and
    tabs/scroll position can visually reset. This version removes the tab dependency:
    the selected folder preview is always rendered directly below the folder picker.
    """
    png_items = payload.get("individual_pngs", []) or []
    if not png_items:
        st.warning("No PNG previews are available in the cached export. Try generating graphs again.")
        return

    png_items = sorted(png_items, key=lambda item: _score_preview_name(item[0]))
    by_folder: dict[str, list[tuple[str, bytes]]] = {}
    for rel_name, data in png_items:
        folder_name = str(Path(rel_name).parent).replace("\\", "/")
        if folder_name in ["", "."]:
            folder_name = "root"
        by_folder.setdefault(folder_name, []).append((rel_name, data))

    st.subheader("Preview browser")
    st.caption(
        f"Generated {len(png_items)} PNG files. Folder preview is loaded from session memory, "
        "so switching folders does not depend on deleted temp files."
    )

    folders = sorted(by_folder.keys())
    if not folders:
        st.warning("No preview folders found.")
        return

    current_folder = st.session_state.get("preview_selected_folder", folders[0])
    if current_folder not in folders:
        current_folder = folders[0]
        st.session_state["preview_selected_folder"] = current_folder

    folder_labels = [f"{folder}  ({len(by_folder[folder])})" for folder in folders]
    current_index = folders.index(current_folder)
    selected_label = st.radio(
        "Choose graph folder",
        folder_labels,
        index=current_index,
        key="preview_graph_folder_radio_single_view",
        horizontal=False,
        help="Tap a folder. The selected folder preview appears immediately below this list.",
    )
    selected_folder = folders[folder_labels.index(selected_label)]
    if selected_folder != st.session_state.get("preview_selected_folder"):
        st.session_state["preview_selected_folder"] = selected_folder

    folder_files = sorted(by_folder[selected_folder], key=lambda item: item[0])
    st.markdown(f"### {selected_folder} preview")

    if len(folder_files) <= 1:
        folder_limit = len(folder_files)
    else:
        safe_key = hashlib.sha1(selected_folder.encode("utf-8")).hexdigest()[:10]
        existing_key = f"folder_preview_limit_memory_{safe_key}"
        default_limit = min(len(folder_files), max(1, min(max_images, 12)))
        # If the number of files changes, clamp the remembered slider value.
        if existing_key in st.session_state:
            st.session_state[existing_key] = min(max(1, int(st.session_state[existing_key])), len(folder_files))
        folder_limit = st.slider(
            "Images from this folder",
            min_value=1,
            max_value=len(folder_files),
            value=st.session_state.get(existing_key, default_limit),
            step=1,
            key=existing_key,
        )

    st.caption(f"Showing {folder_limit} of {len(folder_files)} images in {selected_folder}")
    for rel_name, data in folder_files[:folder_limit]:
        st.image(BytesIO(_preview_image_bytes(data, show_full_png)), caption=Path(rel_name).name, use_container_width=True)

    with st.expander(f"⚡ Quick preview — first {min(max_images, len(png_items))} PNGs", expanded=False):
        visible = png_items[:max_images]
        st.caption("This is only a fast mixed preview. Use the folder picker above for reliable folder browsing on iPhone.")
        for rel_name, data in visible:
            st.image(BytesIO(_preview_image_bytes(data, show_full_png)), caption=rel_name, use_container_width=True)

    if show_all_folders:
        with st.expander("Folder summary", expanded=False):
            for folder in folders:
                st.markdown(f"**{folder}** — {len(by_folder[folder])} images")

    st.markdown('</div>', unsafe_allow_html=True)

def make_file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def make_cache_key(file_hash: str, selected: list[str], speed: str) -> str:
    return json.dumps({"file": file_hash, "families": sorted(selected), "speed": speed}, sort_keys=True)


def make_folder_zips(output_dir: Path) -> dict[str, bytes]:
    png_files = sorted(output_dir.rglob("*.png"))
    folders = sorted({p.parent for p in png_files}, key=lambda x: str(x.relative_to(output_dir)))
    result = {}
    for folder in folders:
        rel = str(folder.relative_to(output_dir))
        archive_name = "CFDS_" + rel.replace("/", "_").replace("\\", "_") + "_png.zip"
        result[rel] = make_filtered_zip_bytes(folder, archive_name, {".png"})
    return result



def _numeric_series(df, names: list[str]):
    """Return the first numeric column found from a list of candidate names."""
    for name in names:
        if name in df.columns:
            try:
                return name, __import__("pandas").to_numeric(df[name], errors="coerce")
            except Exception:
                continue
    return None, None


def _replay_dataframe_from_payload(payload: dict):
    """Load the normalized CSV stored in the export payload for Flight Replay."""
    csv_bytes = payload.get("normalized_csv") or b""
    if not csv_bytes:
        return None, "No normalized CSV found. Generate graphs first, then open Flight Replay."
    try:
        import pandas as pd
        df = pd.read_csv(BytesIO(csv_bytes))
    except Exception as exc:
        return None, f"Could not read normalized CSV for replay: {exc}"

    if df.empty:
        return None, "Normalized CSV is empty."

    # Stable mission-time axis for replay.
    # IMPORTANT: exported graphs use T_FROM_LAUNCH_S when available, with x=0 at launch.
    # PACKET_COUNT/5 from the beginning of the raw log can include minutes of launch-pad data,
    # which makes the replay look flat until ~300 s. Prefer the normalized launch-relative axis.
    if "T_FROM_LAUNCH_S" in df.columns:
        t = pd.to_numeric(df["T_FROM_LAUNCH_S"], errors="coerce")
    elif "T_REL" in df.columns:
        t = pd.to_numeric(df["T_REL"], errors="coerce")
    elif "PACKET_COUNT" in df.columns:
        t = pd.to_numeric(df["PACKET_COUNT"], errors="coerce") / 5.0
        # Best-effort launch alignment: if state/altitude can identify launch, subtract that time.
        try:
            launch_mask = pd.Series(False, index=df.index)
            if "STATE" in df.columns:
                s = df["STATE"].astype(str).str.upper()
                launch_mask = s.str.contains("ASCENT|LAUNCH", regex=True, na=False) & ~s.str.contains("PAD", na=False)
            alt_col, alt = _numeric_series(df, ["ALTITUDE", "ALT", "ALTITUDE_M"])
            if alt_col is not None:
                alt0 = float(alt.dropna().iloc[0]) if alt.dropna().size else 0.0
                launch_mask = launch_mask | (alt > alt0 + 5.0)
            if launch_mask.any():
                t = t - float(t.loc[launch_mask].iloc[0])
            else:
                t = t - t.min(skipna=True)
        except Exception:
            t = t - t.min(skipna=True)
    else:
        t = pd.Series(range(len(df)), dtype="float")

    t = t.ffill().fillna(0.0)
    df = df.copy()
    df["__REPLAY_TIME_S"] = t

    # Keep only the same visible launch window style as CFDS graphs: a little pad time before launch,
    # then the flight. This removes long flat pre-launch periods from replay.
    try:
        df = df[df["__REPLAY_TIME_S"] >= -3.0].copy()
    except Exception:
        pass
    if df.empty:
        return None, "No replay data inside the launch-relative window."
    return df.reset_index(drop=True), ""


def _downsample_for_replay(df, max_points: int):
    """Create a uniformly timed replay dataframe.

    Earlier versions downsampled by row index. That made the Plotly player feel jerky
    because mission-time spacing between frames was uneven. For replay we instead
    resample onto an even time grid, interpolate numeric telemetry, and forward-fill
    categorical fields such as STATE. The export graph engine is untouched.
    """
    import numpy as np
    import pandas as pd

    if df is None or df.empty or "__REPLAY_TIME_S" not in df.columns:
        return df.reset_index(drop=True) if df is not None else df

    try:
        max_points = int(max(20, max_points))
    except Exception:
        max_points = 300

    d = df.copy()
    d["__REPLAY_TIME_S"] = pd.to_numeric(d["__REPLAY_TIME_S"], errors="coerce")
    d = d.dropna(subset=["__REPLAY_TIME_S"]).sort_values("__REPLAY_TIME_S")
    d = d.drop_duplicates(subset=["__REPLAY_TIME_S"], keep="last").reset_index(drop=True)
    if d.empty or len(d) < 2:
        return d.reset_index(drop=True)

    t = d["__REPLAY_TIME_S"].to_numpy(dtype=float)
    if len(d) <= max_points:
        # Still normalize order/index; don't add frames unless requested.
        return d.reset_index(drop=True)

    new_t = np.linspace(float(t[0]), float(t[-1]), max_points)
    out = pd.DataFrame({"__REPLAY_TIME_S": new_t})

    for col in d.columns:
        if col == "__REPLAY_TIME_S":
            continue
        ser_num = pd.to_numeric(d[col], errors="coerce")
        numeric_ratio = float(ser_num.notna().mean()) if len(ser_num) else 0.0
        if numeric_ratio >= 0.70:
            valid = ser_num.notna().to_numpy()
            if valid.sum() >= 2:
                out[col] = np.interp(new_t, t[valid], ser_num.to_numpy(dtype=float)[valid])
            elif valid.sum() == 1:
                out[col] = float(ser_num[valid].iloc[0])
            else:
                out[col] = np.nan
        else:
            # Forward-fill text/category values onto the new time grid.
            left = pd.DataFrame({"__REPLAY_TIME_S": new_t})
            right = d[["__REPLAY_TIME_S", col]].copy().sort_values("__REPLAY_TIME_S")
            merged = pd.merge_asof(left, right, on="__REPLAY_TIME_S", direction="backward")
            if merged[col].isna().any():
                merged[col] = merged[col].bfill().ffill()
            out[col] = merged[col].to_numpy()

    # Keep time columns aligned when present.
    if "T_FROM_LAUNCH_S" in out.columns:
        out["T_FROM_LAUNCH_S"] = out["__REPLAY_TIME_S"]
    return out.reset_index(drop=True)

def _replay_plot_data(df, graph_type: str):
    """Choose columns and display labels for the selected replay graph.

    Velocity/descent-rate is now resilient: if the log does not include an explicit
    velocity column, replay derives descent rate from altitude and mission time.
    Motion has split options instead of one generic "Motion magnitude" bucket.
    """
    import pandas as pd
    import numpy as np

    graph_map = {
        "Altitude": (["ALTITUDE", "ALT", "ALTITUDE_M", "BARO_ALTITUDE", "ALTITUDE_FT_M"], "Altitude (m)"),
        "Voltage": (["VOLTAGE", "VBATT", "BATTERY_VOLTAGE", "VOLTAGE_V"], "Voltage (V)"),
        "Temperature": (["TEMPERATURE", "TEMP", "TEMP_C", "TEMPERATURE_C"], "Temperature (°C)"),
        "Pressure": (["PRESSURE", "PRES", "BARO_PRESSURE", "PRESSURE_PA", "PRESSURE_HPA"], "Pressure"),
        "Current": (["CURRENT", "CURR", "BATTERY_CURRENT", "CURRENT_A"], "Current (A)"),
        "GPS altitude": (["GPS_ALT", "GNSS_ALT", "GPS_ALTITUDE", "GPS_ALTITUDE_M", "ALT_GPS"], "GPS altitude (m)"),
    }

    # Descent rate: prefer explicit columns, otherwise derive from altitude.
    if graph_type == "Velocity / Descent rate":
        col, ser = _numeric_series(df, [
            "DESCENT_RATE", "DESCENT_RATE_DERIVED", "DESCENT_RATE_MPS",
            "VELOCITY_DERIVED", "VELOCITY", "VERTICAL_VELOCITY", "VERTICAL_SPEED", "VZ",
        ])
        if col is not None and ser.notna().sum() >= 2:
            label = "Velocity / descent rate"
            return pd.DataFrame({"Mission time (s)": df["__REPLAY_TIME_S"], label: ser}), label

        alt_col, alt = _numeric_series(df, ["ALTITUDE", "ALT", "ALTITUDE_M", "BARO_ALTITUDE", "GPS_ALT", "GPS_ALTITUDE", "GPS_ALTITUDE_M"])
        if alt_col is not None and alt.notna().sum() >= 3:
            t = pd.to_numeric(df["__REPLAY_TIME_S"], errors="coerce")
            d = pd.DataFrame({"t": t, "alt": alt}).dropna().sort_values("t")
            d = d.drop_duplicates(subset=["t"], keep="last")
            if len(d) >= 3:
                tt = d["t"].to_numpy(dtype=float)
                aa = d["alt"].to_numpy(dtype=float)
                # Positive value = descending. Smooth lightly to avoid noisy derivative spikes.
                with np.errstate(divide="ignore", invalid="ignore"):
                    rate = -np.gradient(aa, tt)
                rate = pd.Series(rate).replace([np.inf, -np.inf], np.nan).rolling(7, center=True, min_periods=1).median().to_numpy()
                out = pd.DataFrame({"Mission time (s)": tt, "Descent rate (m/s)": rate})
                return out, "Descent rate (m/s)"
        return None, "No usable velocity column and could not derive descent rate from altitude."

    motion_mag_map = {
        "Acceleration magnitude": (["ACCEL_R", "ACCEL_X", "AX", "ACC_X"], ["ACCEL_P", "ACCEL_Y", "AY", "ACC_Y"], ["ACCEL_Y", "ACCEL_Z", "AZ", "ACC_Z"], "Acceleration magnitude"),
        "Gyro magnitude": (["GYRO_R", "GYRO_X", "GX", "GYRO_ROLL", "ANGULAR_VELOCITY_X", "OMEGA_X"], ["GYRO_P", "GYRO_Y", "GY", "GYRO_PITCH", "ANGULAR_VELOCITY_Y", "OMEGA_Y"], ["GYRO_YAW", "GYRO_Z", "GZ", "ANGULAR_VELOCITY_Z", "OMEGA_Z"], "Gyro magnitude (deg/s)"),
        "Angular velocity magnitude": (["ANGULAR_VELOCITY_X", "OMEGA_X", "GYRO_X", "GX", "GYRO_R"], ["ANGULAR_VELOCITY_Y", "OMEGA_Y", "GYRO_Y", "GY", "GYRO_P"], ["ANGULAR_VELOCITY_Z", "OMEGA_Z", "GYRO_Z", "GZ", "GYRO_YAW"], "Angular velocity magnitude (deg/s)"),
        "Tilt magnitude": (["TILT_ROLL_DERIVED", "TILT_ROLL", "ROLL_DEG", "ROLL", "TILT_R", "TILT_X"], ["TILT_PITCH_DERIVED", "TILT_PITCH", "PITCH_DEG", "PITCH", "TILT_P", "TILT_Y"], ["TILT_YAW_DERIVED", "TILT_YAW", "YAW_DEG", "YAW", "TILT_Z"], "Tilt magnitude (deg)"),
        # Backward compatibility.
        "Motion magnitude": (["ACCEL_R", "ACCEL_X", "AX", "ACC_X"], ["ACCEL_P", "ACCEL_Y", "AY", "ACC_Y"], ["ACCEL_Y", "ACCEL_Z", "AZ", "ACC_Z"], "Motion magnitude"),
    }
    if graph_type in motion_mag_map:
        xs, ys, zs, label = motion_mag_map[graph_type]
        x_name, x = _numeric_series(df, xs)
        y_name, y = _numeric_series(df, ys)
        z_name, z = _numeric_series(df, zs)
        if x_name and y_name and z_name:
            mag = (pd.to_numeric(x, errors="coerce")**2 + pd.to_numeric(y, errors="coerce")**2 + pd.to_numeric(z, errors="coerce")**2) ** 0.5
            return pd.DataFrame({"Mission time (s)": df["__REPLAY_TIME_S"], label: mag}), label
        return None, f"No usable XYZ columns found for {graph_type}."

    if graph_type not in graph_map:
        return None, "Unsupported replay graph."
    col, y = _numeric_series(df, graph_map[graph_type][0])
    if col is None:
        return None, f"No usable column found for {graph_type}."
    label = graph_map[graph_type][1]
    return pd.DataFrame({"Mission time (s)": df["__REPLAY_TIME_S"], label: y}), label


def _motion_xyz_data(df, graph_type: str):
    """Return a multi-axis dataframe for acceleration/gyro/tilt replay."""
    import pandas as pd
    axis_sets = {
        "Acceleration XYZ": (["ACCEL_R", "ACCEL_X", "AX", "ACC_X"], ["ACCEL_P", "ACCEL_Y", "AY", "ACC_Y"], ["ACCEL_Y", "ACCEL_Z", "AZ", "ACC_Z"], "Acceleration"),
        "Gyro XYZ": (["GYRO_R", "GYRO_X", "GX", "GYRO_ROLL", "ANGULAR_VELOCITY_X", "OMEGA_X"], ["GYRO_P", "GYRO_Y", "GY", "GYRO_PITCH", "ANGULAR_VELOCITY_Y", "OMEGA_Y"], ["GYRO_YAW", "GYRO_Z", "GZ", "ANGULAR_VELOCITY_Z", "OMEGA_Z"], "Gyro (deg/s)"),
        "Angular velocity XYZ": (["ANGULAR_VELOCITY_X", "OMEGA_X", "GYRO_X", "GX", "GYRO_R"], ["ANGULAR_VELOCITY_Y", "OMEGA_Y", "GYRO_Y", "GY", "GYRO_P"], ["ANGULAR_VELOCITY_Z", "OMEGA_Z", "GYRO_Z", "GZ", "GYRO_YAW"], "Angular velocity (deg/s)"),
        "Tilt XYZ": (["TILT_ROLL_DERIVED", "TILT_ROLL", "ROLL_DEG", "ROLL", "TILT_R", "TILT_X"], ["TILT_PITCH_DERIVED", "TILT_PITCH", "PITCH_DEG", "PITCH", "TILT_P", "TILT_Y"], ["TILT_YAW_DERIVED", "TILT_YAW", "YAW_DEG", "YAW", "TILT_Z"], "Tilt (deg)"),
    }
    if graph_type not in axis_sets:
        return None, "Unsupported motion XYZ graph."
    xs, ys, zs, label = axis_sets[graph_type]
    x_name, x = _numeric_series(df, xs)
    y_name, y = _numeric_series(df, ys)
    z_name, z = _numeric_series(df, zs)
    if not (x_name and y_name and z_name):
        return None, f"No usable XYZ columns found for {graph_type}."
    out = pd.DataFrame({"Mission time (s)": df["__REPLAY_TIME_S"], "X": x, "Y": y, "Z": z})
    return out, label


def _gps_path_data(df):
    """Return local XY meters and XYZ data from GPS lat/lon/alt columns."""
    import pandas as pd
    import numpy as np
    lat_col, lat = _numeric_series(df, ["GPS_LAT", "GPS_LATITUDE", "GNSS_LAT", "LAT", "LATITUDE"])
    lon_col, lon = _numeric_series(df, ["GPS_LON", "GPS_LONGITUDE", "GNSS_LON", "LON", "LONGITUDE", "LONG"])
    alt_col, alt = _numeric_series(df, ["GPS_ALT", "GPS_ALTITUDE", "GPS_ALTITUDE_M", "GNSS_ALT", "ALTITUDE", "ALT", "ALTITUDE_M"])
    if lat_col is None or lon_col is None:
        return None, "No GPS latitude/longitude columns found."
    d = pd.DataFrame({"t": df["__REPLAY_TIME_S"], "lat": lat, "lon": lon})
    d["alt"] = alt if alt_col is not None else 0.0
    if "STATE" in df.columns:
        d["STATE"] = df["STATE"].astype(str).to_numpy()
    else:
        d["STATE"] = "UNKNOWN"
    d = d.dropna(subset=["t", "lat", "lon"]).copy()
    d = d[(d["lat"].abs() > 0.0001) & (d["lon"].abs() > 0.0001)]
    if len(d) < 2:
        return None, "GPS path needs at least two valid coordinates."
    lat0 = float(d["lat"].iloc[0])
    lon0 = float(d["lon"].iloc[0])
    R = 6371000.0
    lat_rad = np.deg2rad(d["lat"].to_numpy(dtype=float))
    lon_rad = np.deg2rad(d["lon"].to_numpy(dtype=float))
    lat0_rad = np.deg2rad(lat0)
    lon0_rad = np.deg2rad(lon0)
    x_east = (lon_rad - lon0_rad) * np.cos(lat0_rad) * R
    y_north = (lat_rad - lat0_rad) * R
    z_alt = pd.to_numeric(d["alt"], errors="coerce").ffill().bfill().fillna(0).to_numpy(dtype=float)
    state_vals = [_normalize_replay_state(v) for v in d.get("STATE", ["UNKNOWN"] * len(d))]
    return pd.DataFrame({"Mission time (s)": d["t"].to_numpy(dtype=float), "East (m)": x_east, "North (m)": y_north, "Altitude (m)": z_alt, "lat": d["lat"].to_numpy(dtype=float), "lon": d["lon"].to_numpy(dtype=float), "STATE": state_vals}), "GPS path"



# --- V12.56 replay graph-state helpers copied from graph engine style ---
V1256_EXPECTED_STATES = [
    "LAUNCH_PAD", "ASCENT", "APOGEE", "DESCENT", "PROBE_RELEASE", "PAYLOAD_RELEASE", "LANDED"
]
# Replay uses a dark graph workspace, so the original pastel V12.56 bands
# are remapped to separated dark-safe hues. State logic is unchanged; only
# the visual palette is adapted so adjacent bands do not collapse into gray.
V1256_STATE_COLORS = {
    # Butter/readable dark-mode palette: distinct hue per state, lower mud on dark graph.
    "LAUNCH_PAD": "#FF3B6B",      # rose / pad
    "ASCENT": "#00B8FF",          # bright blue / climb
    "BURNOUT": "#FFE66D",         # yellow / transition
    "APOGEE": "#32E875",          # green / peak
    "DESCENT": "#9B5CFF",         # violet / descent
    "PROBE_RELEASE": "#FFD23F",   # amber / probe
    "PAYLOAD_RELEASE": "#FF7A1A", # orange / payload
    "LANDED": "#A8B3C7",          # slate / landed
}
V1256_STATE_DISPLAY = {
    "LAUNCH_PAD": "LAUNCH_PAD",
    "ASCENT": "ASCENT",
    "APOGEE": "APOGEE",
    "DESCENT": "DESCENT",
    "PROBE_RELEASE": "PROBE_RELEASE",
    "PAYLOAD_RELEASE": "PAYLOAD_RELEASE",
    "LANDED": "LANDED",
}
# Short UI labels keep the legend readable on iPhone. Full state names still drive the logic.
V1256_STATE_SHORT_LABELS = {
    "LAUNCH_PAD": "PAD",
    "ASCENT": "ASCENT",
    "APOGEE": "APOGEE",
    "DESCENT": "DESCENT",
    "PROBE_RELEASE": "PROBE",
    "PAYLOAD_RELEASE": "PAYLOAD",
    "LANDED": "LANDED",
}
V1256_STATE_BORDERS = {
    "LAUNCH_PAD": "#FFB3C5",
    "ASCENT": "#8BE6FF",
    "APOGEE": "#9FFFC2",
    "DESCENT": "#D8B4FE",
    "PROBE_RELEASE": "#FFF1A6",
    "PAYLOAD_RELEASE": "#FFC08A",
    "LANDED": "#E2E8F0",
}
V1256_STAGE_ALPHA = 0.13
V1256_LINE_COLORS = {
    "Altitude": "#66E8FF",
    "Velocity / Descent rate": "#1d4ed8",
    "Voltage": "#0072B2",
    "Current": "#7c3aed",
    "Temperature": "#ea580c",
    "Pressure": "#ea580c",
    "GPS altitude": "#126FA3",
    "Motion magnitude": "#16a34a",
    "Acceleration magnitude": "#22C55E",
    "Gyro magnitude": "#60A5FA",
    "Angular velocity magnitude": "#A78BFA",
    "Tilt magnitude": "#F472B6",
}



def _normalize_replay_state(value: object) -> str:
    s = str(value).upper().strip().replace(" ", "_").replace("-", "_")
    aliases = {
        "LAUNCHPAD": "LAUNCH_PAD",
        "PAD": "LAUNCH_PAD",
        "LAUNCH": "ASCENT",
        "BOOST": "ASCENT",
        "PAYLOAD_DEPLOY": "PAYLOAD_RELEASE",
        "PAYLOAD_DEPLOYMENT": "PAYLOAD_RELEASE",
        "PROBE_DEPLOY": "PROBE_RELEASE",
        "EGG_DEPLOY": "PROBE_RELEASE",
        "EGG_DEPLOYMENT": "PROBE_RELEASE",
        "LAND": "LANDED",
        "MISSION_END": "LANDED",
    }
    return aliases.get(s, s)


def _v1256_stage_segments_for_replay(df):
    """Exact V12.56-style state segmentation: contiguous STATE rows over TIME_S.

    This intentionally copies the graph engine behavior: it does not invent Coast/Main Descent
    bands. It uses the normalized STATE column and its actual contiguous time intervals.
    """
    if df is None or df.empty or "STATE" not in df.columns or "__REPLAY_TIME_S" not in df.columns:
        return []
    try:
        import pandas as pd
        d = df[["STATE", "__REPLAY_TIME_S"]].copy()
        d["STATE"] = d["STATE"].map(_normalize_replay_state)
        d["__REPLAY_TIME_S"] = pd.to_numeric(d["__REPLAY_TIME_S"], errors="coerce")
        d = d.dropna(subset=["STATE", "__REPLAY_TIME_S"]).reset_index(drop=True)
        d = d[d["STATE"].isin(V1256_EXPECTED_STATES)].reset_index(drop=True)
        if d.empty:
            return []
        segments = []
        start_idx = 0
        for i in range(1, len(d)):
            if d.loc[i, "STATE"] != d.loc[start_idx, "STATE"]:
                state = d.loc[start_idx, "STATE"]
                start = float(d.loc[start_idx, "__REPLAY_TIME_S"])
                end = float(d.loc[i, "__REPLAY_TIME_S"])
                if end > start:
                    segments.append((state, start, end))
                start_idx = i
        state = d.loc[start_idx, "STATE"]
        start = float(d.loc[start_idx, "__REPLAY_TIME_S"])
        end = float(d.loc[len(d)-1, "__REPLAY_TIME_S"])
        if end > start:
            segments.append((state, start, end))
        return segments
    except Exception:
        return []


def _event_markers_for_replay(df):
    """Event markers copied from graph-state logic: use actual STATE first, data fallback second."""
    events = []
    if df is None or df.empty or "__REPLAY_TIME_S" not in df.columns:
        return events
    try:
        import pandas as pd
        d = df.copy()
        if "STATE" in d.columns:
            d["__STATE_NORM"] = d["STATE"].map(_normalize_replay_state)
        else:
            d["__STATE_NORM"] = ""
        t = pd.to_numeric(d["__REPLAY_TIME_S"], errors="coerce")
        # Actual state first-points, matching the export graph semantics.
        state_events = [
            ("ASCENT", "Launch", "#F43F5E"),
            ("APOGEE", "Apogee", "#22C55E"),
            ("PROBE_RELEASE", "Probe", "#FACC15"),
            ("PAYLOAD_RELEASE", "Payload", "#FB923C"),
            ("LANDED", "Landing", "#94A3B8"),
        ]
        for state, label, color in state_events:
            sub = d[d["__STATE_NORM"] == state]
            if not sub.empty:
                events.append((float(pd.to_numeric(sub["__REPLAY_TIME_S"], errors="coerce").dropna().iloc[0]), label, color))
        # Fallback only if key state labels are missing.
        if not any(name == "Apogee" for _, name, _ in events):
            alt_col, alt = _numeric_series(d, ["ALTITUDE", "ALT", "ALTITUDE_M"])
            if alt_col is not None and alt.notna().any():
                imax = int(alt.idxmax())
                events.append((float(t.loc[imax]), "Apogee", "#22C55E"))
        if not any(name == "Payload" for _, name, _ in events):
            alt_col, alt = _numeric_series(d, ["ALTITUDE", "ALT", "ALTITUDE_M"])
            if alt_col is not None and alt.notna().any():
                imax = int(alt.idxmax())
                peak = float(alt.max(skipna=True))
                below = alt.loc[imax:][alt.loc[imax:] <= peak * 0.80]
                if len(below):
                    ridx = below.index[0]
                    events.append((float(t.loc[ridx]), "Payload", "#FB923C"))
        if not any(name == "Launch" for _, name, _ in events):
            events.insert(0, (max(0.0, float(t.min(skipna=True))), "Launch", "#F43F5E"))
        if not any(name == "Landing" for _, name, _ in events):
            events.append((float(t.max(skipna=True)), "Landing", "#94A3B8"))
    except Exception:
        pass
    clean = []
    for ev in sorted(events, key=lambda x: x[0]):
        if not any(abs(ev[0] - x[0]) < 0.25 and ev[1] == x[1] for x in clean):
            clean.append(ev)
    return clean


def _v1256_stage_rects(full_df):
    """Return exact V12.56 graph-engine state bands: state, start, end, color, border, alpha."""
    rects = []
    for state, start, end in _v1256_stage_segments_for_replay(full_df):
        rects.append((start, end, state, V1256_STATE_COLORS.get(state, "#eeeeee"), V1256_STATE_BORDERS.get(state, "#e5e7eb"), V1256_STAGE_ALPHA))
    return rects


def _state_legend_strip_html(full_df) -> str:
    """Compact state legend outside the plot area so text cannot overlap the graph."""
    seen = []
    for state, _start, _end in _v1256_stage_segments_for_replay(full_df):
        if state not in seen:
            seen.append(state)
    if not seen:
        seen = V1256_EXPECTED_STATES
    parts = ['<div class="cfds-state-strip"><span class="cfds-state-strip-title">State colors</span>']
    for state in seen:
        color = V1256_STATE_COLORS.get(state, '#94A3B8')
        border = V1256_STATE_BORDERS.get(state, '#EAFBFF')
        short = V1256_STATE_SHORT_LABELS.get(state, state)
        full = V1256_STATE_DISPLAY.get(state, state).replace('_', ' ')
        parts.append(f'<span class="cfds-state-chip" title="{full}" style="border-color:{border};"><i class="cfds-state-dot" style="background:{color}; border-color:{border};"></i>{short}</span>')
    parts.append('</div>')
    return ''.join(parts)



def _display_unit_label(graph_type: str, label: str) -> str:
    """Ensure axes always show units when the source label is generic."""
    if "(" in str(label):
        return str(label)
    units = {
        "Altitude": "Altitude (m)",
        "GPS altitude": "GPS altitude (m)",
        "Velocity / Descent rate": "Descent rate (m/s)",
        "Voltage": "Voltage (V)",
        "Current": "Current (A)",
        "Temperature": "Temperature (°C)",
        "Pressure": "Pressure (Pa / hPa)",
        "Acceleration magnitude": "Acceleration magnitude (m/s²)",
        "Gyro magnitude": "Gyro magnitude (deg/s)",
        "Angular velocity magnitude": "Angular velocity magnitude (deg/s)",
        "Tilt magnitude": "Tilt magnitude (deg)",
    }
    return units.get(graph_type, str(label))


def _graph_metric_cards_html(plot_df, label: str, graph_type: str, full_df=None) -> str:
    """Small insight cards to replace empty space with useful graph-specific data."""
    try:
        import numpy as np
        import pandas as pd
        d = plot_df.dropna().copy()
        if d.empty or label not in d.columns:
            return ""
        x = pd.to_numeric(d["Mission time (s)"], errors="coerce")
        y = pd.to_numeric(d[label], errors="coerce")
        valid = x.notna() & y.notna()
        x = x[valid].to_numpy(dtype=float)
        y = y[valid].to_numpy(dtype=float)
        if len(y) < 2:
            return ""
        cards = []
        def card(k, v):
            cards.append(f'<div class="cfds-insight-card"><span>{k}</span><b>{v}</b></div>')
        if graph_type == "Voltage":
            if len(y) >= 3:
                coef = np.polyfit(x, y, 1)
                pred = np.polyval(coef, x)
                ss_res = float(np.sum((y - pred) ** 2))
                ss_tot = float(np.sum((y - np.mean(y)) ** 2)) or 1.0
                r2 = 1.0 - ss_res / ss_tot
                card("R² trend", f"{r2:.3f}")
            card("Voltage range", f"{np.nanmin(y):.2f}–{np.nanmax(y):.2f} V")
            card("Latest", f"{y[-1]:.2f} V")
        elif graph_type == "Temperature":
            card("Temp range", f"{np.nanmin(y):.1f}–{np.nanmax(y):.1f} °C")
            card("Latest", f"{y[-1]:.1f} °C")
        elif graph_type == "Velocity / Descent rate":
            good = np.sum((y >= 5) & (y <= 15))
            pct = 100.0 * good / max(1, len(y))
            card("AAS target band", "5–15 m/s")
            card("In band", f"{pct:.0f}%")
            card("Peak descent", f"{np.nanmax(y):.2f} m/s")
        elif graph_type == "Altitude":
            i = int(np.nanargmax(y))
            card("Apogee", f"{y[i]:.1f} m @ {x[i]:.1f}s")
            card("Landing est.", f"{x[-1]:.1f}s")
        elif "GPS" in graph_type:
            card("Path samples", f"{len(y)}")
            card("Time span", f"{x[0]:.1f}–{x[-1]:.1f}s")
        else:
            card("Range", f"{np.nanmin(y):.2f}–{np.nanmax(y):.2f}")
            card("Latest", f"{y[-1]:.2f}")
        return '<div class="cfds-insight-strip">' + ''.join(cards) + '</div>'
    except Exception:
        return ""

def _make_v1256_replay_fig(plot_df, label: str, full_df, graph_type: str, frame_time: float):
    import plotly.graph_objects as go
    x = plot_df["Mission time (s)"]
    y = plot_df[label]
    axis_label = _display_unit_label(graph_type, label)
    fig = go.Figure()
    if graph_type == "Velocity / Descent rate":
        # AAS 2026 descent-rate target windows. Positive values mean descending.
        # Container/parachute: 15 m/s +/- 3 => 12-18 m/s. Paraglider payload: 5 m/s +/- 3 => 2-8 m/s.
        fig.add_hrect(y0=12, y1=18, fillcolor="#38BDF8", opacity=0.12, line_width=1.2, line_color="#7DD3FC", layer="below")
        fig.add_hrect(y0=2, y1=8, fillcolor="#22C55E", opacity=0.13, line_width=1.2, line_color="#86EFAC", layer="below")
        fig.add_hline(y=12, line_dash="dot", line_color="#7DD3FC", opacity=0.85, annotation_text="12-18 m/s container", annotation_position="top right")
        fig.add_hline(y=8, line_dash="dot", line_color="#86EFAC", opacity=0.85, annotation_text="2-8 m/s payload", annotation_position="bottom right")
    events = _event_markers_for_replay(full_df)
    t_min = float(full_df["__REPLAY_TIME_S"].min())
    t_max = float(full_df["__REPLAY_TIME_S"].max())
    for x0, x1, state, color, border, alpha in _v1256_stage_rects(full_df):
        # Visible separation: each state band has a colored fill plus a brighter border.
        fig.add_vrect(x0=x0, x1=x1, fillcolor=color, opacity=max(0.10, min(float(alpha), 0.16)),
                      line_width=1.7, line_color=border)
        fig.add_vline(x=x0, line_width=1.15, line_color=border, line_dash="solid", opacity=0.95)
    # final boundary line
    rects_tmp = _v1256_stage_rects(full_df)
    if rects_tmp:
        fig.add_vline(x=rects_tmp[-1][1], line_width=1.15, line_color=rects_tmp[-1][4], line_dash="solid", opacity=0.95)
    line_color = V1256_LINE_COLORS.get(graph_type, "#126FA3")
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="lines", name=label,
        line=dict(color=line_color, width=3.4, shape="spline", smoothing=1.15),
        showlegend=False,
        fill="tozeroy" if graph_type == "Altitude" else None,
        fillcolor="rgba(0,119,167,.08)" if graph_type == "Altitude" else None,
    ))
    if len(plot_df):
        fig.add_trace(go.Scatter(
            x=[x.iloc[-1]], y=[y.iloc[-1]], mode="markers", name="Current point",
            marker=dict(size=11, color="#ef4444", line=dict(color="white", width=1.6)),
            showlegend=False,
            hovertemplate="t=%{x:.1f}s<br>value=%{y:.3g}<extra></extra>",
        ))
    fig.add_vline(x=frame_time, line_width=2, line_color="#EAFBFF", line_dash="dash")
    y_min = float(y.min()) if len(y) else 0.0
    y_max = float(y.max()) if len(y) else 1.0
    if y_min == y_max:
        y_min -= 1; y_max += 1
    for tx, name, color in events:
        if tx <= frame_time + 1e-6:
            fig.add_vline(x=tx, line_width=1.3, line_color=color, line_dash="dot")
    fig.update_layout(
        title=None,
        height=500,
        margin=dict(l=62, r=24, t=44, b=48),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#071B2A",
        font=dict(color="#DDEBFF", size=12),
        showlegend=False,
        hovermode="x unified",
    )
    fig.update_xaxes(title_text="Mission time (s)", title_standoff=28, gridcolor="rgba(203,213,225,.14)", zeroline=False, linecolor="rgba(56,213,255,.45)", mirror=True, linewidth=1.2)
    fig.update_yaxes(title_text=axis_label, title_standoff=12, gridcolor="rgba(203,213,225,.14)", zeroline=False, linecolor="rgba(56,213,255,.45)", mirror=True, linewidth=1.2)
    return fig




def _make_v1256_replay_animation_fig(plot_df, label: str, full_df, graph_type: str, trail_mode: str, frame_duration_ms: int = 40):
    """Create a light browser-side Plotly animation for iPhone.

    Performance rule: keep the graph, state bands, labels, and full telemetry line static.
    Animate only the current point and the time cursor. This avoids re-sending/re-drawing
    a long trail line every frame, which was the main source of stutter on iPhone.
    """
    import plotly.graph_objects as go
    import pandas as pd
    import numpy as np

    if plot_df is None or plot_df.empty:
        return None
    plot_df = plot_df.dropna(subset=["Mission time (s)", label]).reset_index(drop=True)
    if plot_df.empty:
        return None

    x_all = pd.to_numeric(plot_df["Mission time (s)"], errors="coerce").to_numpy(dtype=float)
    y_all = pd.to_numeric(plot_df[label], errors="coerce").to_numpy(dtype=float)
    valid = ~(np.isnan(x_all) | np.isnan(y_all))
    x_all = x_all[valid]
    y_all = y_all[valid]
    if len(x_all) < 2:
        return None

    y_min = float(np.nanmin(y_all))
    y_max = float(np.nanmax(y_all))
    if y_min == y_max:
        y_min -= 1.0
        y_max += 1.0
    pad = (y_max - y_min) * 0.08
    y0, y1 = y_min - pad, y_max + pad

    line_color = V1256_LINE_COLORS.get(graph_type, "#126FA3")

    # Static layer: state bands, full reference line, event markers.
    fig = go.Figure()
    stage_rects = _v1256_stage_rects(full_df)
    for x0, x1, state, color, border, alpha in stage_rects:
        # Keep state text out of the plot. Use border + boundary line for visibility.
        fig.add_vrect(
            x0=x0, x1=x1, fillcolor=color, opacity=max(0.10, min(float(alpha), 0.16)),
            line_width=1.7, line_color=border
        )
        fig.add_vline(x=x0, line_width=1.15, line_color=border, line_dash="solid", opacity=0.95)
    if stage_rects:
        fig.add_vline(x=stage_rects[-1][1], line_width=1.15, line_color=stage_rects[-1][4], line_dash="solid", opacity=0.95)

    # Full line stays static. This keeps motion smooth; only point/cursor animate.
    fig.add_trace(go.Scatter(
        x=x_all,
        y=y_all,
        mode="lines",
        name=label,
        line=dict(color=line_color, width=3.4, shape="spline", smoothing=1.15),
        showlegend=False,
        fill="tozeroy" if graph_type == "Altitude" else None,
        fillcolor="rgba(0,119,167,.07)" if graph_type == "Altitude" else None,
        hovertemplate="t=%{x:.1f}s<br>value=%{y:.3g}<extra></extra>",
    ))

    # Optional visible-window trail: static faint band behind current point only if selected.
    # It is intentionally not animated to prevent mobile stutter.
    if trail_mode != "Full trail":
        fig.add_trace(go.Scatter(
            x=x_all,
            y=y_all,
            mode="lines",
            name="Reference trail",
            line=dict(color="rgba(234,251,255,.22)", width=1.5),
            hoverinfo="skip",
            showlegend=False,
        ))

    # Dynamic traces: current point + time cursor. These are the only traces updated per frame.
    fig.add_trace(go.Scatter(
        x=[x_all[0]],
        y=[y_all[0]],
        mode="markers",
        name="Current point",
        showlegend=False,
        marker=dict(size=12, color="#ef4444", line=dict(color="white", width=1.6)),
        hovertemplate="t=%{x:.1f}s<br>value=%{y:.3g}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=[x_all[0], x_all[0]],
        y=[y0, y1],
        mode="lines",
        name="Time cursor",
        showlegend=False,
        line=dict(color="#EAFBFF", width=2, dash="dash"),
        hoverinfo="skip",
    ))

    events = _event_markers_for_replay(full_df)
    for tx, name, color in events:
        # Event names are shown in the Event Timeline chips under the graph.
        # Keep only a thin vertical marker in the plot so labels cannot overlap.
        fig.add_vline(x=tx, line_width=1.25, line_color=color, line_dash="dot", opacity=0.82)

    frames = []
    # Only update current point and cursor. Trace indices: static line=0, optional ref=1, current/cursor are last two.
    current_trace_index = len(fig.data) - 2
    cursor_trace_index = len(fig.data) - 1
    for i in range(len(x_all)):
        frames.append(go.Frame(
            name=str(i),
            data=[
                go.Scatter(x=[x_all[i]], y=[y_all[i]]),
                go.Scatter(x=[x_all[i], x_all[i]], y=[y0, y1]),
            ],
            traces=[current_trace_index, cursor_trace_index],
        ))
    fig.frames = frames

    # Sparse slider steps keep the JSON light while Play still uses all frames.
    steps = []
    step_stride = max(1, len(x_all) // 18)
    for i in range(0, len(x_all), step_stride):
        steps.append(dict(
            method="animate",
            args=[[str(i)], {"mode": "immediate", "frame": {"duration": 0, "redraw": False}, "transition": {"duration": 0}}],
            label=f"{x_all[i]:.0f}s",
        ))

    safe_frame_duration = int(max(20, min(1200, frame_duration_ms)))
    fig.update_layout(
        title=None,
        height=600,
        margin=dict(l=66, r=28, t=36, b=105),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#071B2A",
        font=dict(color="#DDEBFF", size=12),
        showlegend=False,
        hovermode="x unified",
        yaxis=dict(range=[y0, y1]),
        uirevision="cfds_replay_smooth_static_layers",
        updatemenus=[dict(
            type="buttons",
            direction="left",
            x=0.012,
            y=1.08,
            xanchor="left",
            yanchor="top",
            showactive=False,
            bgcolor="rgba(7,24,39,.96)",
            bordercolor="rgba(56,213,255,.48)",
            borderwidth=1,
            pad={"r": 8, "t": 4},
            buttons=[
                dict(label="▶ Play", method="animate",
                     args=[None, {"fromcurrent": True, "frame": {"duration": safe_frame_duration, "redraw": False}, "transition": {"duration": 0}, "mode": "immediate"}]),
                dict(label="⏸ Pause", method="animate",
                     args=[[None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate", "transition": {"duration": 0}}]),
            ],
        )],
        sliders=[dict(
            active=0,
            x=0.02,
            y=-0.070,
            len=0.94,
            xanchor="left",
            yanchor="top",
            pad=dict(t=8, b=0),
            currentvalue=dict(prefix="t = ", suffix=" s", font=dict(size=12, color="#DDEBFF")),
            steps=steps,
        )],
    )
    fig.update_xaxes(title_text="Mission time (s)", title_standoff=28, gridcolor="rgba(203,213,225,.14)", zeroline=False, linecolor="rgba(56,213,255,.45)", mirror=True, linewidth=1.2)
    fig.update_yaxes(title_text=label, title_standoff=12, gridcolor="rgba(203,213,225,.14)", zeroline=False, linecolor="rgba(56,213,255,.45)", mirror=True, linewidth=1.2)
    return fig


def _make_v1256_multitrace_animation_fig(plot_df, label: str, full_df, graph_type: str, frame_duration_ms: int = 40):
    """Browser-side animation for X/Y/Z motion traces.

    Static lines stay fixed; only the three current markers and one time cursor animate.
    """
    import plotly.graph_objects as go
    import pandas as pd
    import numpy as np
    if plot_df is None or plot_df.empty:
        return None
    d = plot_df.dropna(subset=["Mission time (s)"]).copy()
    if d.empty:
        return None
    x_all = pd.to_numeric(d["Mission time (s)"], errors="coerce").to_numpy(dtype=float)
    axes = ["X", "Y", "Z"]
    colors = {"X": "#38BDF8", "Y": "#F472B6", "Z": "#22C55E"}
    y_arrays = []
    for axn in axes:
        if axn not in d.columns:
            return None
        y_arrays.append(pd.to_numeric(d[axn], errors="coerce").to_numpy(dtype=float))
    valid = ~np.isnan(x_all)
    for arr in y_arrays:
        valid = valid & ~np.isnan(arr)
    x_all = x_all[valid]
    y_arrays = [arr[valid] for arr in y_arrays]
    if len(x_all) < 2:
        return None
    all_y = np.concatenate(y_arrays)
    y_min, y_max = float(np.nanmin(all_y)), float(np.nanmax(all_y))
    if y_min == y_max:
        y_min -= 1; y_max += 1
    pad = (y_max - y_min) * 0.10
    y0, y1 = y_min - pad, y_max + pad
    fig = go.Figure()
    for x0, x1, state, color, border, alpha in _v1256_stage_rects(full_df):
        fig.add_vrect(x0=x0, x1=x1, fillcolor=color, opacity=max(0.08, min(float(alpha), 0.13)), line_width=1.5, line_color=border)
        fig.add_vline(x=x0, line_width=1.0, line_color=border, line_dash="solid", opacity=0.90)
    # static full traces
    for axn, arr in zip(axes, y_arrays):
        fig.add_trace(go.Scatter(x=x_all, y=arr, mode="lines", name=f"{label} {axn}", line=dict(color=colors[axn], width=2.6, shape="spline", smoothing=1.05), showlegend=True))
    # current markers for each axis
    for axn, arr in zip(axes, y_arrays):
        fig.add_trace(go.Scatter(x=[x_all[0]], y=[arr[0]], mode="markers", name=f"Current {axn}", marker=dict(size=9, color=colors[axn], line=dict(color="white", width=1.2)), showlegend=False))
    # cursor
    fig.add_trace(go.Scatter(x=[x_all[0], x_all[0]], y=[y0, y1], mode="lines", name="Time cursor", line=dict(color="#EAFBFF", width=2, dash="dash"), showlegend=False, hoverinfo="skip"))
    current_indices = list(range(3, 6))
    cursor_index = 6
    frames=[]
    for i in range(len(x_all)):
        frame_data = [go.Scatter(x=[x_all[i]], y=[arr[i]]) for arr in y_arrays]
        frame_data.append(go.Scatter(x=[x_all[i], x_all[i]], y=[y0, y1]))
        frames.append(go.Frame(name=str(i), data=frame_data, traces=current_indices+[cursor_index]))
    fig.frames=frames
    step_stride=max(1,len(x_all)//18)
    steps=[dict(method="animate", args=[[str(i)], {"mode":"immediate", "frame":{"duration":0,"redraw":False}, "transition":{"duration":0}}], label=f"{x_all[i]:.0f}s") for i in range(0,len(x_all),step_stride)]
    safe=int(max(20,min(1200,frame_duration_ms)))
    fig.update_layout(title=None, height=600, margin=dict(l=66,r=28,t=38,b=105), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#071B2A", font=dict(color="#DDEBFF", size=12), hovermode="x unified", showlegend=True, legend=dict(orientation="h", y=1.08, x=0.40, bgcolor="rgba(7,24,39,.65)"), yaxis=dict(range=[y0,y1]), uirevision="cfds_motion_xyz",
        updatemenus=[dict(type="buttons", direction="left", x=0.012,y=1.08,xanchor="left",yanchor="top",showactive=False,bgcolor="rgba(7,24,39,.96)",bordercolor="rgba(56,213,255,.48)",borderwidth=1,buttons=[dict(label="▶ Play",method="animate",args=[None,{"fromcurrent":True,"frame":{"duration":safe,"redraw":False},"transition":{"duration":0},"mode":"immediate"}]),dict(label="⏸ Pause",method="animate",args=[[None],{"frame":{"duration":0,"redraw":False},"mode":"immediate","transition":{"duration":0}}])])],
        sliders=[dict(active=0,x=0.02,y=-0.07,len=0.94,xanchor="left",yanchor="top",pad=dict(t=8,b=0),currentvalue=dict(prefix="t = ",suffix=" s",font=dict(size=12,color="#DDEBFF")),steps=steps)])
    fig.update_xaxes(title_text="Mission time (s)", title_standoff=28, gridcolor="rgba(203,213,225,.14)", zeroline=False, linecolor="rgba(56,213,255,.45)", mirror=True, linewidth=1.2)
    fig.update_yaxes(title_text=label, title_standoff=12, gridcolor="rgba(203,213,225,.14)", zeroline=False, linecolor="rgba(56,213,255,.45)", mirror=True, linewidth=1.2)
    return fig


def _make_gps_xy_animation_fig(gps_df, full_df, frame_duration_ms: int = 40):
    import plotly.graph_objects as go
    import pandas as pd
    import numpy as np
    d = gps_df.dropna(subset=["Mission time (s)", "East (m)", "North (m)"]).reset_index(drop=True)
    if len(d) < 2:
        return None
    x = pd.to_numeric(d["East (m)"], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(d["North (m)"], errors="coerce").to_numpy(dtype=float)
    tt = pd.to_numeric(d["Mission time (s)"], errors="coerce").to_numpy(dtype=float)
    valid = ~(np.isnan(x)|np.isnan(y)|np.isnan(tt))
    x, y, tt = x[valid], y[valid], tt[valid]
    if len(x) < 2:
        return None
    pad_x = max(2, (float(np.max(x))-float(np.min(x))) * .08)
    pad_y = max(2, (float(np.max(y))-float(np.min(y))) * .08)
    fig = go.Figure()
    # State-colored GPS path segments. The path uses the same state colors as replay.
    if "STATE" in d.columns:
        states = d["STATE"].astype(str).to_numpy()[valid]
    else:
        states = np.array(["UNKNOWN"] * len(x))
    start_i = 0
    for i in range(1, len(x)+1):
        if i == len(x) or states[i] != states[start_i]:
            st_name = _normalize_replay_state(states[start_i])
            seg_color = V1256_STATE_COLORS.get(st_name, "#66E8FF")
            fig.add_trace(go.Scatter(x=x[start_i:i], y=y[start_i:i], mode="lines", name=V1256_STATE_SHORT_LABELS.get(st_name, st_name), line=dict(color=seg_color, width=4.0, shape="spline", smoothing=1.1), hovertemplate="East=%{x:.1f}m<br>North=%{y:.1f}m<extra></extra>", showlegend=True))
            start_i = i
    current_trace_index = len(fig.data)
    fig.add_trace(go.Scatter(x=[x[0]], y=[y[0]], mode="markers", name="Current", marker=dict(size=13, color="#EF4444", line=dict(color="white", width=1.5)), showlegend=False))
    frames=[go.Frame(name=str(i), data=[go.Scatter(x=[x[i]], y=[y[i]])], traces=[current_trace_index]) for i in range(len(x))]
    fig.frames=frames
    step_stride=max(1,len(x)//18)
    steps=[dict(method="animate",args=[[str(i)],{"mode":"immediate","frame":{"duration":0,"redraw":False},"transition":{"duration":0}}],label=f"{tt[i]:.0f}s") for i in range(0,len(x),step_stride)]
    safe=int(max(20,min(1200,frame_duration_ms)))
    fig.update_layout(title=None,height=620,margin=dict(l=66,r=28,t=40,b=100),paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="#071B2A",font=dict(color="#DDEBFF",size=12),showlegend=False,uirevision="cfds_gps_xy",xaxis=dict(range=[float(np.min(x))-pad_x,float(np.max(x))+pad_x],scaleanchor="y",scaleratio=1),yaxis=dict(range=[float(np.min(y))-pad_y,float(np.max(y))+pad_y]),
        updatemenus=[dict(type="buttons",direction="left",x=0.012,y=1.08,xanchor="left",yanchor="top",showactive=False,bgcolor="rgba(7,24,39,.96)",bordercolor="rgba(56,213,255,.48)",borderwidth=1,buttons=[dict(label="▶ Play",method="animate",args=[None,{"fromcurrent":True,"frame":{"duration":safe,"redraw":False},"transition":{"duration":0},"mode":"immediate"}]),dict(label="⏸ Pause",method="animate",args=[[None],{"frame":{"duration":0,"redraw":False},"mode":"immediate","transition":{"duration":0}}])])],
        sliders=[dict(active=0,x=0.02,y=-0.07,len=0.94,xanchor="left",yanchor="top",pad=dict(t=8,b=0),currentvalue=dict(prefix="t = ",suffix=" s",font=dict(size=12,color="#DDEBFF")),steps=steps)])
    fig.update_xaxes(title_text="East from launch (m)",title_standoff=24,gridcolor="rgba(203,213,225,.14)",zeroline=False,linecolor="rgba(56,213,255,.45)",mirror=True,linewidth=1.2)
    fig.update_yaxes(title_text="North from launch (m)",title_standoff=14,gridcolor="rgba(203,213,225,.14)",zeroline=False,linecolor="rgba(56,213,255,.45)",mirror=True,linewidth=1.2)
    return fig


def _make_gps_xyz_fig(gps_df):
    import plotly.graph_objects as go
    d = gps_df.dropna(subset=["East (m)", "North (m)", "Altitude (m)"]).reset_index(drop=True)
    if len(d) < 2:
        return None
    fig = go.Figure()
    if "STATE" in d.columns:
        states = d["STATE"].astype(str).to_numpy()
    else:
        states = ["UNKNOWN"] * len(d)
    start_i = 0
    for i in range(1, len(d)+1):
        if i == len(d) or states[i] != states[start_i]:
            st_name = _normalize_replay_state(states[start_i])
            seg = d.iloc[start_i:i]
            fig.add_trace(go.Scatter3d(x=seg["East (m)"], y=seg["North (m)"], z=seg["Altitude (m)"], mode="lines+markers", name=V1256_STATE_SHORT_LABELS.get(st_name, st_name), line=dict(color=V1256_STATE_COLORS.get(st_name, "#66E8FF"), width=6), marker=dict(size=2.4, color=V1256_STATE_COLORS.get(st_name, "#66E8FF"), opacity=0.78)))
            start_i = i
    fig.add_trace(go.Scatter3d(x=[d["East (m)"].iloc[0]], y=[d["North (m)"].iloc[0]], z=[d["Altitude (m)"].iloc[0]], mode="markers", name="Start", marker=dict(size=5,color="#22C55E")))
    fig.add_trace(go.Scatter3d(x=[d["East (m)"].iloc[-1]], y=[d["North (m)"].iloc[-1]], z=[d["Altitude (m)"].iloc[-1]], mode="markers", name="End", marker=dict(size=6,color="#EF4444")))
    fig.update_layout(title=None,height=680,margin=dict(l=0,r=0,t=32,b=0),paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="#071B2A",font=dict(color="#DDEBFF",size=12),scene=dict(bgcolor="#071B2A",xaxis=dict(title="East (m)",gridcolor="rgba(203,213,225,.15)",color="#DDEBFF"),yaxis=dict(title="North (m)",gridcolor="rgba(203,213,225,.15)",color="#DDEBFF"),zaxis=dict(title="Altitude (m)",gridcolor="rgba(203,213,225,.15)",color="#DDEBFF"),aspectmode="data"),legend=dict(orientation="h",y=1.02,x=0.02,bgcolor="rgba(7,24,39,.65)"),uirevision="cfds_gps_xyz")
    return fig

def _state_at_time_for_replay(df, t_now: float) -> str:
    """Return normalized STATE at/just before t_now for the replay status card."""
    try:
        import pandas as pd
        if df is None or df.empty or "STATE" not in df.columns:
            return "UNKNOWN"
        d = df[["STATE", "__REPLAY_TIME_S"]].copy()
        d["__REPLAY_TIME_S"] = pd.to_numeric(d["__REPLAY_TIME_S"], errors="coerce")
        d = d.dropna(subset=["__REPLAY_TIME_S"])
        d = d[d["__REPLAY_TIME_S"] <= float(t_now)]
        if d.empty:
            return _normalize_replay_state(df["STATE"].iloc[0])
        return _normalize_replay_state(d["STATE"].iloc[-1])
    except Exception:
        return "UNKNOWN"


def _next_event_for_replay(df, t_now: float) -> str:
    try:
        events = sorted(_event_markers_for_replay(df), key=lambda x: x[0])
        for tx, label, _color in events:
            if tx > float(t_now) + 1e-6:
                return f"{label} in {tx - float(t_now):.1f} s"
        return "Mission end"
    except Exception:
        return "—"



# --- Final rules patch: AAS 2026 velocity bands, CONOPS accuracy, multi-axis metrics ---
def _conops_planned_altitude(t_values):
    """Locked planned CONOPS profile: 681 m at 11.2 s, 80% release, 15/5 m/s descent."""
    import numpy as np
    t = np.asarray(t_values, dtype=float)
    apogee_alt = 681.0
    apogee_t = 11.2
    release_alt = apogee_alt * 0.80
    release_t = apogee_t + (apogee_alt - release_alt) / 15.0
    egg_alt = 2.0
    egg_t = release_t + (release_alt - egg_alt) / 5.0
    land_t = egg_t + egg_alt / 5.0
    out = np.zeros_like(t, dtype=float)
    # ascent
    m = t <= apogee_t
    out[m] = np.interp(t[m], [0.0, apogee_t], [0.0, apogee_alt])
    # container descent
    m = (t > apogee_t) & (t <= release_t)
    out[m] = apogee_alt - 15.0 * (t[m] - apogee_t)
    # payload paraglider descent
    m = (t > release_t) & (t <= land_t)
    out[m] = release_alt - 5.0 * (t[m] - release_t)
    out[t > land_t] = 0.0
    return np.clip(out, 0.0, None)


def _conops_actual_planned_df(df):
    """Build Actual vs Planned CONOPS dataframe from replay altitude."""
    import pandas as pd
    alt_col, alt = _numeric_series(df, ["ALTITUDE", "ALT", "ALTITUDE_M", "BARO_ALTITUDE", "GPS_ALT", "GPS_ALTITUDE", "GPS_ALTITUDE_M"])
    if alt_col is None:
        return None, "No usable altitude column found for CONOPS accuracy."
    t = pd.to_numeric(df["__REPLAY_TIME_S"], errors="coerce")
    d = pd.DataFrame({"Mission time (s)": t, "Actual altitude (m)": alt}).dropna()
    if len(d) < 3:
        return None, "CONOPS accuracy needs at least three altitude samples."
    d = d.sort_values("Mission time (s)").drop_duplicates("Mission time (s)")
    d["Planned CONOPS (m)"] = _conops_planned_altitude(d["Mission time (s)"].to_numpy(dtype=float))
    return d, "Actual altitude (m)"


_old_replay_plot_data_final = _replay_plot_data
def _replay_plot_data(df, graph_type: str):
    # Add CONOPS option, then fall back to the existing resilient replay data selector.
    if graph_type == "CONOPS accuracy":
        return _conops_actual_planned_df(df)
    return _old_replay_plot_data_final(df, graph_type)


_old_graph_metric_cards_html_final = _graph_metric_cards_html
def _graph_metric_cards_html(plot_df, label: str, graph_type: str, full_df=None) -> str:
    """Final metric cards: velocity bands per AAS 2026, CONOPS accuracy, XYZ min/max/range."""
    try:
        import numpy as np
        import pandas as pd
        d = plot_df.dropna().copy()
        if d.empty:
            return ""
        cards = []
        def card(k, v):
            cards.append(f'<div class="cfds-insight-card"><span>{k}</span><b>{v}</b></div>')

        if graph_type == "CONOPS accuracy" and {"Actual altitude (m)", "Planned CONOPS (m)", "Mission time (s)"}.issubset(d.columns):
            x = pd.to_numeric(d["Mission time (s)"], errors="coerce")
            actual = pd.to_numeric(d["Actual altitude (m)"], errors="coerce")
            planned = pd.to_numeric(d["Planned CONOPS (m)"], errors="coerce")
            valid = x.notna() & actual.notna() & planned.notna()
            actual = actual[valid].to_numpy(dtype=float)
            planned = planned[valid].to_numpy(dtype=float)
            x = x[valid].to_numpy(dtype=float)
            if len(actual) >= 3:
                diff = np.abs(actual - planned)
                scale = max(1.0, float(np.nanmax(planned)), float(np.nanmax(actual)))
                accuracy = max(0.0, 100.0 * (1.0 - float(np.nanmean(diff)) / scale))
                ia = int(np.nanargmax(actual)); ip = int(np.nanargmax(planned))
                card("CONOPS accuracy", f"{accuracy:.2f}%")
                card("Avg |Actual-Planned|", f"{float(np.nanmean(diff)):.2f} m")
                card("Apogee Δ", f"{actual[ia]-planned[ip]:+.1f} m")
                card("Actual apogee", f"{actual[ia]:.1f} m @ {x[ia]:.1f}s")
            return '<div class="cfds-insight-strip">' + ''.join(cards) + '</div>'

        # Multi-axis: X/Y/Z metrics even when label is not a dataframe column.
        if {"X", "Y", "Z", "Mission time (s)"}.issubset(d.columns):
            import numpy as np
            vals = {}
            for axis in ["X", "Y", "Z"]:
                arr = pd.to_numeric(d[axis], errors="coerce").dropna().to_numpy(dtype=float)
                if len(arr):
                    vals[axis] = (float(np.nanmin(arr)), float(np.nanmax(arr)), float(np.nanmax(arr)-np.nanmin(arr)))
            if vals:
                for axis, (mn, mx, rg) in vals.items():
                    card(f"{axis} min/max", f"{mn:.2f} / {mx:.2f}")
                mag = (pd.to_numeric(d["X"], errors="coerce")**2 + pd.to_numeric(d["Y"], errors="coerce")**2 + pd.to_numeric(d["Z"], errors="coerce")**2) ** 0.5
                card("Magnitude max", f"{float(np.nanmax(mag)):.2f}")
                return '<div class="cfds-insight-strip">' + ''.join(cards) + '</div>'

        if graph_type == "Velocity / Descent rate" and label in d.columns:
            y = pd.to_numeric(d[label], errors="coerce").dropna().to_numpy(dtype=float)
            if len(y):
                container_pct = 100.0 * float(np.sum((y >= 12) & (y <= 18))) / len(y)
                payload_pct = 100.0 * float(np.sum((y >= 2) & (y <= 8))) / len(y)
                card("AAS container band", "12–18 m/s")
                card("AAS payload band", "2–8 m/s")
                card("Container in-band", f"{container_pct:.0f}%")
                card("Payload in-band", f"{payload_pct:.0f}%")
                card("Peak descent", f"{float(np.nanmax(y)):.2f} m/s")
                return '<div class="cfds-insight-strip">' + ''.join(cards) + '</div>'

        return _old_graph_metric_cards_html_final(plot_df, label, graph_type, full_df)
    except Exception:
        try:
            return _old_graph_metric_cards_html_final(plot_df, label, graph_type, full_df)
        except Exception:
            return ""


_old_make_v1256_replay_fig_final = _make_v1256_replay_fig
def _make_v1256_replay_fig(plot_df, label: str, full_df, graph_type: str, frame_time: float):
    import plotly.graph_objects as go
    import numpy as np
    if graph_type == "CONOPS accuracy":
        d = plot_df.dropna(subset=["Mission time (s)", "Actual altitude (m)", "Planned CONOPS (m)"]).copy()
        if d.empty:
            return None
        fig = go.Figure()
        for x0, x1, state, color, border, alpha in _v1256_stage_rects(full_df):
            fig.add_vrect(x0=x0, x1=x1, fillcolor=color, opacity=max(0.10, min(float(alpha), 0.16)), line_width=1.7, line_color=border)
            fig.add_vline(x=x0, line_width=1.15, line_color=border, line_dash="solid", opacity=0.95)
        fig.add_trace(go.Scatter(x=d["Mission time (s)"], y=d["Planned CONOPS (m)"], mode="lines", name="Planned CONOPS", line=dict(color="#CBD5E1", width=2.6, dash="dash")))
        fig.add_trace(go.Scatter(x=d["Mission time (s)"], y=d["Actual altitude (m)"], mode="lines", name="Actual CONOPS", line=dict(color="#66E8FF", width=3.4, shape="spline", smoothing=1.15)))
        now_alt = np.interp(frame_time, d["Mission time (s)"], d["Actual altitude (m)"])
        fig.add_trace(go.Scatter(x=[frame_time], y=[now_alt], mode="markers", name="Current point", marker=dict(size=11, color="#EF4444", line=dict(color="white", width=1.6))))
        fig.add_vline(x=frame_time, line_width=2, line_color="#EAFBFF", line_dash="dash")
        fig.update_layout(title=None, height=500, margin=dict(l=62, r=24, t=44, b=48), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#071B2A", font=dict(color="#DDEBFF", size=12), showlegend=True, legend=dict(orientation="h", y=1.04, x=0.02, bgcolor="rgba(7,24,39,.72)"), hovermode="x unified")
        fig.update_xaxes(title_text="Mission time (s)", title_standoff=28, gridcolor="rgba(203,213,225,.14)", zeroline=False, linecolor="rgba(56,213,255,.45)", mirror=True, linewidth=1.2)
        fig.update_yaxes(title_text="Altitude (m)", title_standoff=12, gridcolor="rgba(203,213,225,.14)", zeroline=False, linecolor="rgba(56,213,255,.45)", mirror=True, linewidth=1.2)
        return fig
    fig = _old_make_v1256_replay_fig_final(plot_df, label, full_df, graph_type, frame_time)
    return fig


_old_make_v1256_replay_animation_fig_final = _make_v1256_replay_animation_fig
def _make_v1256_replay_animation_fig(plot_df, label: str, full_df, graph_type: str, trail_mode: str, frame_duration_ms: int = 40):
    import plotly.graph_objects as go
    import numpy as np
    if graph_type == "CONOPS accuracy":
        return _make_v1256_replay_fig(plot_df, label, full_df, graph_type, float(plot_df["Mission time (s)"].iloc[min(len(plot_df)-1, max(0, len(plot_df)//3))]))
    fig = _old_make_v1256_replay_animation_fig_final(plot_df, label, full_df, graph_type, trail_mode, frame_duration_ms)
    if fig is not None and graph_type == "Velocity / Descent rate":
        # Add AAS 2026 target windows to the animated descent graph too.
        fig.add_hrect(y0=12, y1=18, fillcolor="#38BDF8", opacity=0.12, line_width=1.2, line_color="#7DD3FC", layer="below")
        fig.add_hrect(y0=2, y1=8, fillcolor="#22C55E", opacity=0.13, line_width=1.2, line_color="#86EFAC", layer="below")
        fig.add_hline(y=12, line_dash="dot", line_color="#7DD3FC", opacity=0.85)
        fig.add_hline(y=18, line_dash="dot", line_color="#7DD3FC", opacity=0.85)
        fig.add_hline(y=2, line_dash="dot", line_color="#86EFAC", opacity=0.85)
        fig.add_hline(y=8, line_dash="dot", line_color="#86EFAC", opacity=0.85)
        fig.update_yaxes(title_text="Descent rate (m/s)")
    return fig

def render_flight_replay(payload: dict, mobile_fast: bool = True) -> None:
    '''Wide V12.56 replay dashboard: graph first, controls above/below, no left rail.'''
    st.markdown('<a id="replay"></a><div class="cfds-replay-shell cfds-replay-wide-shell">', unsafe_allow_html=True)

    df, err = _replay_dataframe_from_payload(payload)
    if err:
        st.markdown(
            '<div class="cfds-replay-head"><div><div class="cfds-replay-kicker">Replay deck</div><div class="cfds-replay-title">Flight Replay</div><div class="cfds-replay-sub">Generate graphs first to create a normalized mission log.</div></div></div>',
            unsafe_allow_html=True,
        )
        st.info(err)
        st.markdown('</div>', unsafe_allow_html=True)
        return

    max_points_default = 300 if mobile_fast else 650
    replay_start = float(df["__REPLAY_TIME_S"].min())
    replay_end = float(df["__REPLAY_TIME_S"].max())
    rows = len(df)
    rate_text = "5 Hz" if "PACKET_COUNT" in df.columns else "log"

    st.markdown(f'''
        <div class="cfds-replay-head cfds-replay-wide-head">
          <div>
            <div class="cfds-replay-kicker">Replay deck</div>
            <div class="cfds-replay-title">Flight Replay</div>
            <div class="cfds-replay-sub">Wide graph mode • V12.56 state bands • modebar reset-view enabled</div>
          </div>
          <div class="cfds-replay-badges">
            <div class="cfds-badge"><b>WINDOW</b> {replay_start:.1f} → {replay_end:.1f} s</div>
            <div class="cfds-badge"><b>ROWS</b> {rows}</div>
            <div class="cfds-badge"><b>RATE</b> {rate_text}</div>
          </div>
        </div>
        ''', unsafe_allow_html=True)

    graph_options = [
        "Altitude", "Velocity / Descent rate", "CONOPS accuracy", "Voltage", "Temperature", "Pressure", "Current",
        "GPS altitude", "GPS XY path", "GPS XYZ path", "GPS map path",
        "Acceleration magnitude", "Acceleration XYZ",
        "Gyro magnitude", "Gyro XYZ", "Angular velocity magnitude", "Angular velocity XYZ",
        "Tilt magnitude", "Tilt XYZ",
    ]
    speed_options = ["0.5x", "1x", "2x", "5x", "10x"]
    trail_options = ["Full trail", "Last 10 s", "Last 30 s", "Last 60 s"]
    butter_options = ["iPhone Smooth", "Butter", "Ultra Butter", "Battery Saver"]

    st.markdown('<div class="cfds-wide-controls"><div class="cfds-wide-controls-title">Replay settings</div>', unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns([1.45, 1.10, 1.20, 1.55, 1.25], gap="medium")
    with c1:
        graph_type = st.selectbox("Replay graph", graph_options, index=0, key="replay_graph_type_wide")
    with c2:
        speed = st.radio("Speed", speed_options, index=3 if mobile_fast else 2, horizontal=True, key="replay_speed_wide")
    with c3:
        trail_mode = st.radio("Trail", trail_options, index=0, horizontal=True, key="replay_trail_wide")
    with c4:
        replay_engine = st.radio(
            "Replay engine",
            ["Smooth browser animation", "Manual scrub fallback"],
            index=0,
            horizontal=False,
            key="replay_engine_mode_wide",
            help="Smooth mode uses Plotly animation controls inside the chart, not Streamlit button loops.",
        )
    with c5:
        butter_mode = st.selectbox(
            "Animation feel",
            butter_options,
            index=1 if mobile_fast else 2,
            key="replay_butter_mode_wide",
            help="Butter modes increase interpolation frames and clamp frame timing for smoother browser animation.",
        )
    preset_frames = {"Battery Saver": 240, "iPhone Smooth": 420, "Butter": 720, "Ultra Butter": 1100}.get(butter_mode, max_points_default)
    max_limit = 1400 if butter_mode == "Ultra Butter" else 1100
    max_points = st.slider(
        "Fine smoothness / frames",
        min_value=120,
        max_value=max_limit,
        value=min(max_limit, max(120, int(preset_frames))),
        step=20,
        help="More interpolated frames = smoother. If iPhone feels heavy, use iPhone Smooth or Battery Saver.",
        key="replay_max_points_wide",
    )
    st.markdown('<div class="cfds-mini-help cfds-wide-help">1x = real mission speed. 5x/10x are demo speeds. Use the Plotly modebar reset-axes button to reset view after zoom/pan.</div></div>', unsafe_allow_html=True)

    replay_df = _downsample_for_replay(df, max_points)
    if replay_df.empty:
        st.warning("No replay data after downsampling.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    speed_value = 0.5 if speed == "0.5x" else float(str(speed).replace("x", ""))
    try:
        replay_span_s = float(replay_df["__REPLAY_TIME_S"].iloc[-1] - replay_df["__REPLAY_TIME_S"].iloc[0])
        raw_frame_duration = (replay_span_s * 1000.0) / max(1, (len(replay_df) - 1) * speed_value)
        # Smooth-like-butter tuning: avoid ultra-low durations that Safari/iPhone cannot render smoothly.
        min_duration = 22 if butter_mode in ("Butter", "Ultra Butter") else 28
        if butter_mode == "Battery Saver":
            min_duration = 55
        frame_duration = int(max(min_duration, min(1400, raw_frame_duration)))
    except Exception:
        frame_duration = 80

    t_preview = float(replay_df["__REPLAY_TIME_S"].iloc[min(max(0, len(replay_df)//4), len(replay_df)-1)])
    state_preview = _state_at_time_for_replay(replay_df, t_preview)
    next_event = _next_event_for_replay(replay_df, t_preview)

    st.markdown(f'''
        <div class="cfds-wide-status-strip">
          <div class="cfds-status-cell"><span>Replay time</span><b>{t_preview:.1f} / {replay_end:.1f} s</b></div>
          <div class="cfds-status-cell"><span>Frames</span><b>{len(replay_df)}</b></div>
          <div class="cfds-status-cell"><span>State</span><b><span class="cfds-state-pill">{state_preview}</span></b></div>
          <div class="cfds-status-cell"><span>Next event</span><b>{next_event}</b></div>
          <div class="cfds-status-cell"><span>Animation</span><b>{butter_mode}</b></div>
        </div>
        ''', unsafe_allow_html=True)

    st.markdown('<div class="cfds-graph-titlebar cfds-graph-titlebar-only"><h3>'+graph_type+' vs Time</h3></div>', unsafe_allow_html=True)

    if replay_engine == "Smooth browser animation" and graph_type != "GPS map path":
        fig = None
        show_state_legend = True
        if graph_type == "GPS XY path":
            gps_df, msg = _gps_path_data(replay_df)
            if gps_df is None:
                st.info(msg)
                return
            fig = _make_gps_xy_animation_fig(gps_df, replay_df, frame_duration_ms=frame_duration)
            show_state_legend = False
        elif graph_type == "GPS XYZ path":
            gps_df, msg = _gps_path_data(replay_df)
            if gps_df is None:
                st.info(msg)
                return
            fig = _make_gps_xyz_fig(gps_df)
            show_state_legend = False
        elif graph_type in ("Acceleration XYZ", "Gyro XYZ", "Angular velocity XYZ", "Tilt XYZ"):
            plot_df, label = _motion_xyz_data(replay_df, graph_type)
            if plot_df is None:
                st.info(label)
                return
            fig = _make_v1256_multitrace_animation_fig(plot_df, label, replay_df, graph_type, frame_duration_ms=frame_duration)
        else:
            plot_df, label = _replay_plot_data(replay_df, graph_type)
            if plot_df is None:
                st.info(label)
                return
            fig = _make_v1256_replay_animation_fig(plot_df, label, replay_df, graph_type, trail_mode, frame_duration_ms=frame_duration)
        if fig is None:
            st.info("Not enough data to create this replay. Try another graph or Manual scrub fallback.")
            return
        fig.update_layout(dragmode="pan")
        st.plotly_chart(
            fig,
            use_container_width=True,
            theme=None,
            config={
                "displayModeBar": True,
                "displaylogo": False,
                "responsive": True,
                "scrollZoom": True,
                "modeBarButtonsToRemove": ["lasso2d", "select2d", "toImage"],
            },
        )
        if graph_type not in ("GPS XY path", "GPS XYZ path", "GPS map path"):
            try:
                st.markdown(_graph_metric_cards_html(plot_df, label, graph_type, replay_df), unsafe_allow_html=True)
            except Exception:
                pass
        if show_state_legend:
            st.markdown(_state_legend_strip_html(replay_df), unsafe_allow_html=True)
            chips = []
            for tx, name, _color in _event_markers_for_replay(replay_df)[:6]:
                chips.append(f'<div class="cfds-event-chip"><span>{name}</span><b>{tx:.1f} s</b></div>')
            if chips:
                st.markdown('<div class="cfds-event-strip cfds-event-strip-wide">' + ''.join(chips) + '</div>', unsafe_allow_html=True)
        st.markdown('<div class="cfds-replay-tipbar">GPS XY/XYZ and split motion graphs are now separated. Use embedded ▶ Play / ⏸ Pause for smooth replay; use Plotly reset axes after zoom/pan.</div>', unsafe_allow_html=True)
        return

    if replay_engine == "Smooth browser animation" and graph_type == "GPS map path":
        st.info("GPS map path still uses Manual scrub fallback. Use GPS XY path for smooth browser animation or GPS XYZ path for 3D view.")

    total_frames = len(replay_df)
    if "replay_frame_wide" not in st.session_state:
        st.session_state["replay_frame_wide"] = 0
    st.session_state["replay_frame_wide"] = min(max(0, int(st.session_state["replay_frame_wide"])), total_frames - 1)

    frame = st.slider(
        "Mission timeline",
        min_value=0,
        max_value=total_frames - 1,
        value=st.session_state["replay_frame_wide"],
        step=1,
        key="replay_timeline_slider_wide",
        help="Manual scrub mode: move through frames directly.",
    )
    st.session_state["replay_frame_wide"] = frame
    controls = st.columns(3)
    reset = controls[0].button("↺ Reset frame", use_container_width=True, key="replay_reset_btn_wide")
    jump_end = controls[1].button("⏭ End", use_container_width=True, key="replay_end_btn_wide")
    if reset:
        st.session_state["replay_frame_wide"] = 0
        st.rerun()
    if jump_end:
        st.session_state["replay_frame_wide"] = total_frames - 1
        st.rerun()

    chart_slot = st.empty()
    frame_idx = min(max(0, int(st.session_state["replay_frame_wide"])), total_frames - 1)
    sub = replay_df.iloc[: frame_idx + 1].copy()
    if trail_mode != "Full trail" and not sub.empty:
        seconds = float(trail_mode.split()[1])
        t_now = float(sub["__REPLAY_TIME_S"].iloc[-1])
        sub = sub[sub["__REPLAY_TIME_S"] >= t_now - seconds]
    t_now = float(replay_df["__REPLAY_TIME_S"].iloc[frame_idx])
    st.markdown(f'<div class="cfds-mini-help">Replay time: <b>{t_now:.1f} s</b> / {replay_end:.1f} s • Frame {frame_idx+1}/{total_frames}</div>', unsafe_allow_html=True)

    if graph_type == "GPS map path":
        import pandas as pd
        lat_col, lat = _numeric_series(sub, ["GPS_LAT", "GPS_LATITUDE", "GNSS_LAT", "LAT", "LATITUDE"])
        lon_col, lon = _numeric_series(sub, ["GPS_LON", "GPS_LONGITUDE", "GNSS_LON", "LON", "LONGITUDE", "LONG"])
        if lat_col is None or lon_col is None:
            chart_slot.info("No GPS latitude/longitude columns found for map replay.")
        else:
            gps = pd.DataFrame({"lat": lat, "lon": lon}).dropna()
            gps = gps[(gps["lat"].abs() > 0.0001) & (gps["lon"].abs() > 0.0001)]
            if gps.empty:
                chart_slot.info("GPS map has no valid coordinates yet at this frame.")
            else:
                chart_slot.map(gps, use_container_width=True)
    elif graph_type == "GPS XY path":
        gps_df, msg = _gps_path_data(sub)
        if gps_df is None:
            chart_slot.info(msg)
        else:
            fig = _make_gps_xy_animation_fig(gps_df, replay_df, frame_duration_ms=0)
            if fig is not None:
                fig.update_layout(updatemenus=[], sliders=[])
                chart_slot.plotly_chart(fig, use_container_width=True, theme=None, config={"displayModeBar": True, "displaylogo": False, "responsive": True, "scrollZoom": True, "modeBarButtonsToRemove": ["lasso2d", "select2d", "toImage"]})
            else:
                chart_slot.info("GPS XY path needs more valid points.")
    elif graph_type == "GPS XYZ path":
        gps_df, msg = _gps_path_data(sub)
        if gps_df is None:
            chart_slot.info(msg)
        else:
            fig = _make_gps_xyz_fig(gps_df)
            if fig is not None:
                chart_slot.plotly_chart(fig, use_container_width=True, theme=None, config={"displayModeBar": True, "displaylogo": False, "responsive": True, "scrollZoom": True})
            else:
                chart_slot.info("GPS XYZ path needs more valid points.")
    elif graph_type in ("Acceleration XYZ", "Gyro XYZ", "Angular velocity XYZ", "Tilt XYZ"):
        plot_df, label = _motion_xyz_data(sub, graph_type)
        if plot_df is None:
            chart_slot.info(label)
        else:
            fig = _make_v1256_multitrace_animation_fig(plot_df, label, replay_df, graph_type, frame_duration_ms=0)
            if fig is not None:
                fig.update_layout(updatemenus=[], sliders=[], height=620 if mobile_fast else 680, margin=dict(l=62, r=24, t=34, b=74), dragmode="pan")
                chart_slot.plotly_chart(fig, use_container_width=True, theme=None, config={"displayModeBar": True, "displaylogo": False, "responsive": True, "scrollZoom": True, "modeBarButtonsToRemove": ["lasso2d", "select2d", "toImage"]})
            else:
                chart_slot.info("No numeric data available yet for this replay frame.")
    else:
        plot_df, label = _replay_plot_data(sub, graph_type)
        if plot_df is None:
            chart_slot.info(label)
        else:
            plot_df = plot_df.dropna()
            if plot_df.empty:
                chart_slot.info("No numeric data available yet for this replay frame.")
            else:
                fig = _make_v1256_replay_fig(plot_df, label, replay_df, graph_type, t_now)
                fig.update_layout(height=620 if mobile_fast else 680, margin=dict(l=62, r=24, t=34, b=74), dragmode="pan")
                chart_slot.plotly_chart(fig, use_container_width=True, theme=None, config={"displayModeBar": True, "displaylogo": False, "responsive": True, "scrollZoom": True, "modeBarButtonsToRemove": ["lasso2d", "select2d", "toImage"]})
    st.markdown(_state_legend_strip_html(replay_df), unsafe_allow_html=True)
    chips = []
    for tx, name, _color in _event_markers_for_replay(replay_df)[:6]:
        chips.append(f'<div class="cfds-event-chip"><span>{name}</span><b>{tx:.1f} s</b></div>')
    if chips:
        st.markdown('<div class="cfds-event-strip cfds-event-strip-wide">' + ''.join(chips) + '</div>', unsafe_allow_html=True)

def quick_data_diagnostics(input_path: Path) -> dict:
    try:
        import pandas as pd
        suffix = input_path.suffix.lower()
        if suffix in [".xlsx", ".xlsm", ".xls"]:
            df = pd.read_excel(input_path, nrows=8)
        else:
            df = pd.read_csv(input_path, nrows=8)
        cols = [str(c) for c in df.columns]
        upper = {c.upper().replace(" ", "_") for c in cols}
        def has_any(names):
            return any(n in upper for n in names)
        return {
            "ok": True,
            "columns": cols[:18],
            "has_packet": has_any(["PACKET_COUNT", "PACKET", "PKT"]),
            "has_altitude": has_any(["ALTITUDE", "ALT", "ALTITUDE_M"]),
            "has_state": has_any(["STATE", "FLIGHT_STATE", "MODE"]),
            "has_gps": has_any(["GPS_LAT", "LAT", "LATITUDE"]) and has_any(["GPS_LON", "LON", "LONGITUDE"]),
            "has_motion": has_any(["ACCEL_R", "ACCEL_X", "GYRO_R", "GYRO_X", "TILT_ROLL_DERIVED", "ROLL"]),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def render_data_diagnostics(diag: dict) -> None:
    with st.expander("Pre-flight data check", expanded=False):
        if not diag.get("ok"):
            st.warning(f"Could not read a quick preview of the input file: {diag.get('error')}")
            return
        c1, c2, c3 = st.columns(3)
        c1.metric("Altitude column", "OK" if diag.get("has_altitude") else "Check")
        c2.metric("State column", "OK" if diag.get("has_state") else "Can infer")
        c3.metric("GPS columns", "OK" if diag.get("has_gps") else "Missing/optional")
        c4, c5 = st.columns(2)
        c4.metric("Packet/timebase", "OK" if diag.get("has_packet") else "Index fallback")
        c5.metric("Motion columns", "OK" if diag.get("has_motion") else "Missing/optional")
        st.caption("Detected columns: " + ", ".join(diag.get("columns", [])))


def render_family_selector(preset_name: str) -> list[str]:
    default = PRESETS.get(preset_name, PRESETS["Quick Check"])
    selected = []
    st.markdown("**Graph families**")
    # Visibility-first: sidebar is narrow on iPhone, so two-column checkboxes
    # make labels wrap badly. Stack them as full-width controls.
    for key, meta in GRAPH_FAMILIES.items():
        checked = st.checkbox(
            meta["label"],
            value=(key in default),
            key=f"family_{preset_name}_{key}",
            help=meta["hint"],
            disabled=(preset_name != "Custom"),
        )
        if checked:
            selected.append(key)
    return selected



def render_scientific_calculator() -> None:
    """Dark scientific calculator component for mission math.

    This is intentionally client-side so it never forces Streamlit reruns while typing.
    The expression evaluator only allows numbers/operators and a small Math function map.
    """
    components.html(
        r"""
        <div class="cfds-sci-calc">
          <div class="calc-topline">
            <div>
              <div class="calc-kicker">MISSION SCIENTIFIC CALCULATOR</div>
              <div class="calc-sub">Quick checks: 681×0.8, descent rate, trig, sqrt, log, powers</div>
            </div>
            <div class="calc-status">SAFE LOCAL EVAL</div>
          </div>
          <div class="calc-display-wrap">
            <input id="cfdsCalcDisplay" class="calc-display" value="681*0.8" autocomplete="off" spellcheck="false" />
            <div id="cfdsCalcResult" class="calc-result">= 544.8</div>
          </div>
          <div class="calc-grid">
            <button data-act="clear" class="danger">AC</button><button data-act="back">⌫</button><button data-in="(">(</button><button data-in=")">)</button><button data-in="/">÷</button>
            <button data-fn="sin">sin</button><button data-fn="cos">cos</button><button data-fn="tan">tan</button><button data-fn="sqrt">√</button><button data-in="*">×</button>
            <button data-fn="log10">log</button><button data-fn="ln">ln</button><button data-in="^">xʸ</button><button data-in="pi">π</button><button data-in="-">−</button>
            <button data-in="7">7</button><button data-in="8">8</button><button data-in="9">9</button><button data-in="e">e</button><button data-in="+">+</button>
            <button data-in="4">4</button><button data-in="5">5</button><button data-in="6">6</button><button data-act="ans">ANS</button><button data-act="eval" class="equals">=</button>
            <button data-in="1">1</button><button data-in="2">2</button><button data-in="3">3</button><button data-in=".">.</button><button data-in="0">0</button>
          </div>
          <div class="calc-formulas">
            <button data-template="681*0.8">80% apogee</button>
            <button data-template="(850.8-497.1)/(43.1-12.7)">descent rate</button>
            <button data-template="sqrt(2*9.81*10)">impact speed</button>
            <button data-template="(733.4-432)/15">stage time</button>
          </div>
        </div>
        <style>
          :root { color-scheme: dark; }
          html, body { margin:0; background:#050B12; font-family: Inter, system-ui, -apple-system, Segoe UI, sans-serif; }
          .cfds-sci-calc { box-sizing:border-box; width:100%; border:1px solid rgba(56,213,255,.34); border-radius:18px; background:linear-gradient(180deg,#071827,#050B12); padding:16px; color:#EAFBFF; box-shadow:0 0 24px rgba(56,213,255,.08), inset 0 1px 0 rgba(255,255,255,.05); }
          .calc-topline { display:flex; justify-content:space-between; gap:12px; align-items:center; margin-bottom:14px; }
          .calc-kicker { color:#38D5FF; letter-spacing:.16em; font-size:12px; font-weight:900; }
          .calc-sub { color:#9DB7C9; font-size:12px; margin-top:4px; }
          .calc-status { border:1px solid rgba(56,213,255,.35); border-radius:999px; padding:7px 10px; font-size:11px; font-weight:800; color:#BFF6FF; background:#0B2136; white-space:nowrap; }
          .calc-display-wrap { border:1px solid rgba(56,213,255,.42); background:#06111F; border-radius:14px; padding:12px; margin-bottom:12px; }
          .calc-display { width:100%; box-sizing:border-box; border:0; outline:0; background:#06111F; color:#EAFBFF; font-size:26px; font-weight:850; letter-spacing:.04em; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
          .calc-result { margin-top:8px; color:#38D5FF; font-size:20px; font-weight:900; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; min-height:26px; }
          .calc-grid { display:grid; grid-template-columns: repeat(5, minmax(0,1fr)); gap:8px; }
          .calc-grid button, .calc-formulas button { border:1px solid rgba(56,213,255,.25); color:#EAFBFF; background:#0E2B45; border-radius:12px; min-height:44px; font-weight:900; font-size:15px; box-shadow:inset 0 1px 0 rgba(255,255,255,.04); }
          .calc-grid button:hover, .calc-formulas button:hover { border-color:#38D5FF; background:#123B60; }
          .calc-grid .equals { grid-row: span 2; min-height:96px; background:linear-gradient(180deg,#0B84FF,#005FB8); }
          .calc-grid .danger { background:linear-gradient(180deg,#FF4B55,#991B1B); }
          .calc-formulas { display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap:8px; margin-top:12px; }
          .calc-formulas button { min-height:36px; font-size:12px; color:#BFF6FF; }
          @media (max-width: 650px) { .calc-grid { gap:6px; } .calc-grid button { min-height:42px; } .calc-formulas { grid-template-columns:1fr 1fr; } .calc-status { display:none; } .calc-display { font-size:22px; } }
        </style>
        <script>
          const display = document.getElementById('cfdsCalcDisplay');
          const result = document.getElementById('cfdsCalcResult');
          let lastAns = 0;
          function insert(txt){ const a=display.selectionStart ?? display.value.length; const b=display.selectionEnd ?? display.value.length; display.value = display.value.slice(0,a)+txt+display.value.slice(b); display.focus(); display.selectionStart=display.selectionEnd=a+txt.length; quickEval(); }
          function normalize(expr){
            return expr.replaceAll('×','*').replaceAll('÷','/').replaceAll('−','-').replaceAll('π','pi')
              .replace(/\bpi\b/g,'Math.PI').replace(/\be\b/g,'Math.E')
              .replace(/\bsqrt\s*\(/g,'Math.sqrt(').replace(/\bsin\s*\(/g,'Math.sin(').replace(/\bcos\s*\(/g,'Math.cos(').replace(/\btan\s*\(/g,'Math.tan(')
              .replace(/\blog10\s*\(/g,'Math.log10(').replace(/\bln\s*\(/g,'Math.log(').replace(/\blog\s*\(/g,'Math.log10(')
              .replace(/\^/g,'**');
          }
          function safeEval(){
            let expr = display.value.trim();
            if(!expr){ result.textContent=''; return null; }
            expr = expr.replace(/ANS/g, String(lastAns));
            const norm = normalize(expr);
            if(!/^[0-9+\-*/().,\sA-Za-z_]*$/.test(norm)) throw new Error('blocked token');
            if(/(constructor|window|document|globalThis|Function|eval|import|fetch|XMLHttpRequest)/i.test(norm)) throw new Error('blocked name');
            const val = Function('"use strict"; return (' + norm + ')')();
            if(typeof val !== 'number' || !Number.isFinite(val)) throw new Error('not finite');
            lastAns = val;
            return val;
          }
          function quickEval(){ try { const v=safeEval(); if(v!==null) result.textContent='= '+Number(v.toPrecision(12)); } catch(e){ result.textContent='check expression'; } }
          document.querySelectorAll('button').forEach(btn => btn.addEventListener('click', () => {
            if(btn.dataset.in) insert(btn.dataset.in);
            if(btn.dataset.fn) insert(btn.dataset.fn + '(');
            if(btn.dataset.template){ display.value=btn.dataset.template; quickEval(); }
            if(btn.dataset.act==='clear'){ display.value=''; result.textContent=''; display.focus(); }
            if(btn.dataset.act==='back'){ display.value=display.value.slice(0,-1); quickEval(); }
            if(btn.dataset.act==='ans') insert('ANS');
            if(btn.dataset.act==='eval') quickEval();
          }));
          display.addEventListener('input', quickEval);
          display.addEventListener('keydown', e => { if(e.key==='Enter'){ e.preventDefault(); quickEval(); }});
          quickEval();
        </script>
        """,
        height=520,
        scrolling=False,
    )

if "cfds_last_export" not in st.session_state:
    st.session_state["cfds_last_export"] = None
if "cfds_export_cache" not in st.session_state:
    st.session_state["cfds_export_cache"] = {}


st.markdown(
    """
    <a id="import"></a>
    <div class="cfds-v12-top">
      <div class="cfds-v12-brand">
        <div class="cfds-logo">
          <div class="cfds-mark">CF</div>
          <div>
            <div class="cfds-title">CFDS</div>
            <div class="cfds-sub">CanSat Flight Data Studio • Daedalus • AAS CanSat 2026</div>
          </div>
        </div>
        <div class="cfds-metrics">
          <div class="cfds-chip"><b>Status</b><span>Web Console Ready</span></div>
          <div class="cfds-chip"><b>Mode</b><span>Mobile Pro</span></div>
          <div class="cfds-chip"><b>Replay</b><span>Log Playback</span></div>
          <div class="cfds-chip"><b>Export</b><span>ZIP / PNG / Report</span></div>
        </div>
      </div>
      <div class="cfds-dock">
        <a class="active" href="#import">Import</a>
        <a href="#generate">Generate</a>
        <a href="#preview">Preview</a>
        <a href="#replay">Replay</a>
        <a href="#export">Export</a>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("CFDS Mobile Pro")
    mobile_fast = st.toggle("Mobile fast mode", value=True, help="Compressed previews, compact layout, and phone-first defaults.")
    preset_name = st.selectbox(
        "Graph preset",
        list(PRESETS.keys()),
        index=list(PRESETS.keys()).index("Quick Check"),
        help="Generate only the graph families you need. This is the biggest speed boost on iPhone.",
    )
    selected_families = render_family_selector(preset_name)
    mode_label = "Selected export"
    mode = "all"
    speed_label = st.radio(
        "Export quality",
        ["Mobile Fast", "Report Quality"],
        index=0,
        help="Mobile Fast skips SVG and uses lighter PNGs. Report Quality keeps 300 dpi PNG + SVG for final reports.",
    )
    speed = "fast" if speed_label == "Mobile Fast" else "quality"
    if mobile_fast:
        max_preview = st.slider("Max preview images", min_value=3, max_value=80, value=12, step=1)
        show_full_png = False
        show_all_folders = st.checkbox("Show folder summary", value=False)
    else:
        max_preview = st.slider("Max preview images", min_value=3, max_value=80, value=24, step=3)
        show_full_png = st.checkbox("Show original full PNG previews", value=False)
        show_all_folders = st.checkbox("Show folder summary", value=False)
    use_cached = st.checkbox("Use cached result if same log/settings", value=True, help="Skip regeneration if this exact log + selected pack was already generated in this session.")
    clear_cache_now = st.button("Clear session cache", use_container_width=True)
    if clear_cache_now:
        st.session_state["cfds_export_cache"] = {}
        st.session_state["cfds_last_export"] = None
        st.success("Cache cleared.")
    use_demo = st.checkbox("Use included demo log", value=False)
    show_logs_when_success = st.checkbox("Show worker logs after success", value=False)

st.markdown(
    """
    <div class="cfds-card">
    <b>Phone speed tip:</b> choose a preset first. Generating only Altitude + Velocity + CONOPS is much faster than building every graph family. Use Mobile Fast for field checks and Report Quality only for final files.
    </div>
    """,
    unsafe_allow_html=True,
)


# Mascot card: Elfaria Albis Serfort. Keep small so it does not create empty layout gaps.
_mascot_path = Path(__file__).with_name("elfaria_mascot.png")
if _mascot_path.exists():
    with st.expander("CFDS Mascot", expanded=False):
        c_m1, c_m2 = st.columns([1, 3])
        with c_m1:
            st.image(str(_mascot_path), use_container_width=True)
        with c_m2:
            st.markdown("**Elfaria Albis Serfort** — Daedalus CFDS assistant mascot.")
            st.caption("Used only as a lightweight app identity panel so it does not slow down graph replay.")

# Mission input and generation command use real Streamlit layout, not open HTML wrappers.
# Open raw <div> wrappers around widgets caused empty dark boxes and inconsistent white file chips.
st.markdown('<a id="import"></a><div class="cfds-section-banner">MISSION INPUT</div>', unsafe_allow_html=True)
uploaded = None
if not use_demo:
    uploaded = st.file_uploader("Upload flight log", type=SUPPORTED_TYPES, key="cfds_log_uploader")
    if uploaded is not None:
        try:
            _up_size_mb = uploaded.size / (1024*1024)
            st.markdown(
                f'<div class="cfds-uploaded-chip"><span class="cfds-upload-icon">▣</span>'
                f'<div><b>{safe_filename(uploaded.name)}</b><small>{_up_size_mb:.2f} MB • ready</small></div></div>',
                unsafe_allow_html=True,
            )
        except Exception:
            pass

st.markdown('<a id="generate"></a><div class="cfds-section-banner">GENERATION COMMAND</div>', unsafe_allow_html=True)
start = st.button("Generate selected graphs", type="primary", use_container_width=True)

if start:
    with tempfile.TemporaryDirectory(prefix="cfds_web_") as tmp:
        work = Path(tmp)
        input_dir = work / "input"
        output_dir = work / "outputs"
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        if use_demo:
            demo_path = Path(__file__).parent / "data" / "normalized_flight1043.csv"
            if not demo_path.exists():
                st.error("Demo file not found: data/normalized_flight1043.csv")
                st.stop()
            input_path = input_dir / demo_path.name
            shutil.copy2(demo_path, input_path)
        else:
            if uploaded is None:
                st.error("Upload a CSV/XLSX log first, or enable the demo log in the sidebar.")
                st.stop()
            input_path = input_dir / safe_filename(uploaded.name)
            input_path.write_bytes(uploaded.getbuffer())

        file_hash = make_file_hash(input_path)
        cache_key = make_cache_key(file_hash, selected_families, speed)
        render_data_diagnostics(quick_data_diagnostics(input_path))

        st.info(f"Input: {input_path.name} | Preset: {preset_name} | Families: {', '.join(selected_families) or 'diagnostics only'} | Quality: {speed_label}")

        if use_cached and cache_key in st.session_state["cfds_export_cache"]:
            st.success("Using cached result for this log/settings. No regeneration needed.")
            st.session_state["cfds_last_export"] = st.session_state["cfds_export_cache"][cache_key]
            # Rerun so the Export center renders outside this button-click block.
            # st.stop() would prevent cached downloads from appearing.
            st.rerun()

        progress = st.progress(0, text="Starting CFDS engine...")
        with st.spinner("Generating selected graphs inside the CFDS engine..."):
            progress.progress(20, text="Normalizing log and building diagnostics...")
            code, logs = run_worker(input_path, output_dir, mode, speed, selected_families)
            progress.progress(82, text="Packing exports and mobile previews...")

        if code != 0:
            st.error("CFDS generation failed. Open logs below, then download ZIP for diagnostics if available.")
        else:
            st.success("Graph generation completed.")

        show_report(output_dir)

        if code != 0 or show_logs_when_success:
            with st.expander("Worker logs", expanded=code != 0):
                st.code(logs[-20000:], language="text")

        st.session_state["cfds_last_export"] = collect_export_payload(output_dir, code, logs)
        st.session_state["cfds_export_cache"][cache_key] = st.session_state["cfds_last_export"]
        progress.progress(100, text="Done")

if st.session_state.get("cfds_last_export") is not None:
    show_previews_from_payload(st.session_state["cfds_last_export"], max_preview, show_full_png, show_all_folders)
    render_flight_replay(st.session_state["cfds_last_export"], mobile_fast=mobile_fast)
    show_export_center(st.session_state["cfds_last_export"])



# Utility deck: full scientific calculator for mission math without leaving the web app.
with st.expander("🧮 Mission scientific calculator", expanded=False):
    render_scientific_calculator()

st.divider()
st.caption("CFDS Web keeps the original graph engine, but uses a mobile-optimized browser interface for iPhone/iPad/desktop.")


# Final mobile readability override: Streamlit widgets can inherit muted opacity from
# internal wrappers on mobile. Keep this CSS at the end so it wins the cascade.
st.markdown(
    """
    <style>
    /* ---------- CFDS mobile control readability override ---------- */
    :root {
        --cfds-readable-text: #EAFBFF;
        --cfds-readable-muted: #BFD7EA;
        --cfds-readable-dim: #9DB7C9;
        --cfds-readable-panel: rgba(7,24,39,.94);
        --cfds-readable-card: rgba(14,43,69,.82);
        --cfds-readable-border: rgba(56,213,255,.36);
    }

    /* Global widget labels: fix dim/low-opacity Streamlit text on iPhone */
    [data-testid="stWidgetLabel"],
    [data-testid="stWidgetLabel"] *,
    [data-testid="stCheckbox"] label,
    [data-testid="stCheckbox"] label *,
    [data-testid="stRadio"] label,
    [data-testid="stRadio"] label *,
    [data-testid="stSlider"] label,
    [data-testid="stSlider"] label *,
    [data-testid="stSelectbox"] label,
    [data-testid="stSelectbox"] label *,
    [data-testid="stMultiSelect"] label,
    [data-testid="stMultiSelect"] label *,
    div[role="radiogroup"] label,
    div[role="radiogroup"] label *,
    div[data-testid="stMarkdownContainer"] p,
    div[data-testid="stCaptionContainer"],
    div[data-testid="stCaptionContainer"] * {
        color: var(--cfds-readable-text) !important;
        opacity: 1 !important;
        filter: none !important;
    }

    /* Secondary/help text should be readable, not nearly black */
    small, .stCaptionContainer, [data-testid="stHelp"], [data-testid="stTooltipIcon"] {
        color: var(--cfds-readable-muted) !important;
        opacity: 1 !important;
    }

    /* Radio/checkbox option rows: give each line enough visual weight */
    div[role="radiogroup"] > label,
    [data-testid="stCheckbox"] > label,
    [data-testid="stRadio"] > label {
        min-height: 2.05rem !important;
        align-items: center !important;
    }
    div[role="radiogroup"] p,
    [data-testid="stCheckbox"] p,
    [data-testid="stRadio"] p {
        font-size: .93rem !important;
        line-height: 1.35 !important;
        letter-spacing: .01em !important;
    }

    /* Section headers inside control panels */
    .cfds-panel h1, .cfds-panel h2, .cfds-panel h3,
    .cfds-panel p, .cfds-panel span, .cfds-panel label,
    .cfds-panel [data-testid="stMarkdownContainer"] * {
        color: var(--cfds-readable-text) !important;
        opacity: 1 !important;
    }
    .cfds-panel-title,
    .cfds-control-title,
    .cfds-replay-kicker {
        color: #38D5FF !important;
        opacity: 1 !important;
        text-shadow: 0 0 10px rgba(56,213,255,.20);
    }

    /* Selectbox / dropdown text */
    [data-baseweb="select"],
    [data-baseweb="select"] *,
    [data-baseweb="popover"] *,
    [data-baseweb="menu"] * {
        color: #071827 !important;
        opacity: 1 !important;
    }
    [data-baseweb="select"] > div {
        background: #F7FCFF !important;
        border: 1px solid rgba(56,213,255,.55) !important;
        border-radius: 12px !important;
    }

    /* Sliders: make numeric value and track easier to see */
    [data-testid="stSlider"] * {
        opacity: 1 !important;
    }
    [data-testid="stSlider"] [data-testid="stTickBar"] * {
        color: var(--cfds-readable-muted) !important;
    }
    [data-testid="stSlider"] div[role="slider"] {
        box-shadow: 0 0 0 4px rgba(255,75,85,.18) !important;
    }

    /* File uploader: remove white unreadable button / dim description */
    div[data-testid="stFileUploader"],
    div[data-testid="stFileUploader"] section,
    div[data-testid="stFileUploaderDropzone"] {
        background: var(--cfds-readable-card) !important;
        border: 1px dashed rgba(56,213,255,.50) !important;
        border-radius: 14px !important;
    }
    div[data-testid="stFileUploader"] *,
    div[data-testid="stFileUploaderDropzone"] * {
        color: var(--cfds-readable-text) !important;
        opacity: 1 !important;
    }
    div[data-testid="stFileUploader"] button,
    div[data-testid="stFileUploaderDropzone"] button {
        background: linear-gradient(180deg, #0EA5E9, #0369A1) !important;
        color: #FFFFFF !important;
        border: 1px solid rgba(234,251,255,.75) !important;
        border-radius: 12px !important;
        font-weight: 900 !important;
    }

    /* Panel/card readability on phones */
    .cfds-card, .metric-card, .replay-card,
    [data-testid="stExpander"],
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: var(--cfds-readable-panel) !important;
        border-color: var(--cfds-readable-border) !important;
    }

    @media (max-width: 760px) {
        .block-container { padding-left: .72rem !important; padding-right: .72rem !important; }
        [data-testid="stWidgetLabel"] p,
        div[role="radiogroup"] p,
        [data-testid="stCheckbox"] p,
        [data-testid="stRadio"] p {
            font-size: .98rem !important;
            line-height: 1.45 !important;
        }
        .cfds-panel { padding: 1rem .95rem !important; }
        .cfds-panel-title { font-size: 1.02rem !important; letter-spacing: .16em !important; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- GLOBAL UI VISIBILITY HARDENING FIX (final override layer) ---
# Keep this block at the very end so it wins over older V12.56 skin rules and Streamlit defaults.
st.markdown(
    """
    <style>
    :root {
        --cfds-readable-text-strong: #F3FCFF;
        --cfds-readable-text: #DDF4FF;
        --cfds-readable-muted: #B7C9D9;
        --cfds-readable-dim: #8EA8BA;
        --cfds-readable-panel: #071827;
        --cfds-readable-card: #0B2136;
        --cfds-readable-card-2: #0E2B45;
        --cfds-readable-border: rgba(56, 213, 255, .42);
        --cfds-readable-border-soft: rgba(56, 213, 255, .24);
        --cfds-readable-cyan: #38D5FF;
        --cfds-readable-blue: #0B84FF;
        --cfds-readable-red: #FF4B55;
    }

    /* Global text hierarchy: no more dim labels on mobile */
    html, body, [data-testid="stAppViewContainer"], .stApp,
    [data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] *,
    [data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] *,
    label, label *, p, span, small, div[role="radiogroup"] *,
    [data-testid="stCheckbox"] *, [data-testid="stRadio"] *, [data-testid="stSlider"] *,
    [data-testid="stSelectbox"] *, [data-testid="stMultiSelect"] * {
        color: var(--cfds-readable-text) !important;
        opacity: 1 !important;
        text-shadow: none !important;
    }

    h1, h2, h3, h4, h5, h6,
    .cfds-panel-title, .cfds-control-title, .cfds-replay-kicker,
    .cfds-graph-titlebar h3 {
        color: var(--cfds-readable-cyan) !important;
        opacity: 1 !important;
        text-shadow: 0 0 10px rgba(56, 213, 255, .16) !important;
    }

    .stCaptionContainer, .stCaptionContainer *, small,
    .cfds-mobile-note, .cfds-replay-sub, .cfds-mini-help,
    .cfds-event-chip span, .cfds-status-cell span {
        color: var(--cfds-readable-muted) !important;
        opacity: 1 !important;
    }

    /* Panels/cards: visible edges and readable contents */
    .cfds-panel, .cfds-card, .metric-card, .replay-card,
    .cfds-control-block, .cfds-graph-card,
    [data-testid="stExpander"], [data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(7, 24, 39, .94) !important;
        border-color: var(--cfds-readable-border-soft) !important;
        color: var(--cfds-readable-text) !important;
    }

    /* Buttons should never become white-on-white or pale-on-white */
    .stButton button, .stDownloadButton button,
    div[data-testid="stFileUploader"] button,
    div[data-testid="stFileUploaderDropzone"] button {
        background: linear-gradient(180deg, #0B84FF, #005FB8) !important;
        color: #FFFFFF !important;
        border: 1px solid rgba(234, 251, 255, .75) !important;
        border-radius: 12px !important;
        font-weight: 900 !important;
        opacity: 1 !important;
    }
    .stButton button *, .stDownloadButton button *,
    div[data-testid="stFileUploader"] button *,
    div[data-testid="stFileUploaderDropzone"] button * {
        color: #FFFFFF !important;
        fill: #FFFFFF !important;
        opacity: 1 !important;
    }

    /* File uploader: full dropzone + selected file chip readability */
    div[data-testid="stFileUploader"] {
        background: rgba(7, 24, 39, .96) !important;
        border: 1px solid var(--cfds-readable-border-soft) !important;
        border-radius: 16px !important;
        padding: .65rem !important;
        color: var(--cfds-readable-text) !important;
    }
    div[data-testid="stFileUploader"] section,
    div[data-testid="stFileUploaderDropzone"] {
        background: rgba(11, 33, 54, .98) !important;
        border: 1px dashed var(--cfds-readable-border) !important;
        border-radius: 14px !important;
        color: var(--cfds-readable-text) !important;
    }
    div[data-testid="stFileUploader"] section *,
    div[data-testid="stFileUploaderDropzone"] *,
    div[data-testid="stFileUploader"] small,
    div[data-testid="stFileUploader"] label,
    div[data-testid="stFileUploader"] label * {
        color: var(--cfds-readable-text) !important;
        opacity: 1 !important;
    }
    div[data-testid="stFileUploader"] svg,
    div[data-testid="stFileUploaderDropzone"] svg {
        color: var(--cfds-readable-cyan) !important;
        fill: var(--cfds-readable-cyan) !important;
        opacity: 1 !important;
    }

    /* Uploaded-file chip selectors vary by Streamlit version; cover the common wrappers. */
    div[data-testid="stFileUploader"] [data-testid="stFileUploaderFile"],
    div[data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] *,
    div[data-testid="stFileUploader"] [data-testid="stFileUploaderFileName"],
    div[data-testid="stFileUploader"] [data-testid="stFileUploaderFileSize"],
    div[data-testid="stFileUploader"] section + div,
    div[data-testid="stFileUploader"] section + div *,
    div[data-testid="stFileUploader"] [class*="uploaded"],
    div[data-testid="stFileUploader"] [class*="Uploaded"],
    div[data-testid="stFileUploader"] [class*="file"],
    div[data-testid="stFileUploader"] [class*="File"] {
        color: var(--cfds-readable-text-strong) !important;
        opacity: 1 !important;
    }
    div[data-testid="stFileUploader"] [data-testid="stFileUploaderFile"],
    div[data-testid="stFileUploader"] section + div > div {
        background: var(--cfds-readable-card-2) !important;
        border: 1px solid var(--cfds-readable-border) !important;
        border-radius: 12px !important;
    }

    /* Inputs/select boxes: keep readable even if Streamlit theme creates white controls. */
    input, textarea, [data-baseweb="input"] *, [data-baseweb="textarea"] *,
    [data-baseweb="select"], [data-baseweb="select"] *,
    [data-baseweb="popover"] *, [data-baseweb="menu"] * {
        color: #06111F !important;
        opacity: 1 !important;
    }
    [data-baseweb="select"] > div,
    [data-baseweb="input"] > div,
    [data-baseweb="textarea"] > div {
        background: #F7FCFF !important;
        border: 1px solid rgba(56, 213, 255, .55) !important;
    }

    /* Checkbox/radio controls: label contrast and spacing */
    [data-testid="stCheckbox"] label,
    [data-testid="stRadio"] label,
    [data-testid="stCheckbox"] label *,
    [data-testid="stRadio"] label * {
        color: var(--cfds-readable-text) !important;
        opacity: 1 !important;
        line-height: 1.45 !important;
    }
    [data-testid="stCheckbox"] svg,
    [data-testid="stRadio"] svg {
        opacity: 1 !important;
        filter: drop-shadow(0 0 3px rgba(56,213,255,.18));
    }

    /* Slider text/ticks/value: brighter and separated */
    [data-testid="stSlider"] *,
    [data-testid="stSlider"] [data-testid="stTickBar"] * {
        color: var(--cfds-readable-text) !important;
        opacity: 1 !important;
    }
    [data-testid="stSlider"] div[role="slider"] {
        box-shadow: 0 0 0 4px rgba(255,75,85,.22), 0 0 10px rgba(255,75,85,.18) !important;
    }

    /* Mobile spacing: controls must breathe on iPhone */
    @media (max-width: 760px) {
        .block-container { padding-left: .85rem !important; padding-right: .85rem !important; }
        .cfds-panel, .cfds-control-block, .cfds-graph-card { padding: 1rem !important; }
        [data-testid="stWidgetLabel"] p,
        [data-testid="stCheckbox"] p,
        [data-testid="stRadio"] p,
        div[role="radiogroup"] p {
            font-size: 1rem !important;
            line-height: 1.55 !important;
        }
        [data-testid="stCheckbox"], [data-testid="stRadio"] {
            margin-bottom: .28rem !important;
        }
        div[data-testid="stFileUploader"] { padding: .75rem !important; }
        div[data-testid="stFileUploader"] section { min-height: 76px !important; }
        .cfds-panel-title { font-size: 1.02rem !important; letter-spacing: .14em !important; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Replay wide-layout final override: put controls above the graph and give Plotly max width.
st.markdown(
    """
    <style>
    .cfds-replay-wide-shell {
        padding: 1.05rem !important;
        max-width: 100% !important;
    }
    .cfds-wide-controls {
        border: 1px solid rgba(56,213,255,.34);
        background: linear-gradient(180deg, rgba(7,24,39,.92), rgba(5,11,18,.88));
        border-radius: 18px;
        padding: .95rem 1rem 1rem 1rem;
        margin: .85rem 0 .8rem 0;
        box-shadow: inset 0 1px 0 rgba(255,255,255,.05);
    }
    .cfds-wide-controls-title {
        color: #38D5FF;
        font-size: .82rem;
        letter-spacing: .18em;
        text-transform: uppercase;
        font-weight: 900;
        margin-bottom: .45rem;
    }
    .cfds-wide-status-strip {
        display: grid;
        grid-template-columns: repeat(5, minmax(0, 1fr));
        gap: .65rem;
        margin: .7rem 0 .8rem 0;
    }
    .cfds-graph-card-wide {
        padding: .75rem .85rem 1rem .85rem !important;
        width: 100% !important;
    }
    .cfds-graph-card-wide .js-plotly-plot,
    .cfds-graph-card-wide [data-testid="stPlotlyChart"] {
        width: 100% !important;
    }
    .cfds-event-strip-wide {
        margin-top: .7rem !important;
    }
    .cfds-wide-help {
        color: #BFD7EA !important;
        margin-top: .4rem;
        line-height: 1.55;
    }
    /* Make the modebar usable and visible on dark backgrounds. */
    .modebar {
        background: rgba(7,24,39,.90) !important;
        border: 1px solid rgba(56,213,255,.34) !important;
        border-radius: 10px !important;
        padding: 2px !important;
    }
    .modebar-btn svg path { fill: #DDF6FF !important; }
    .modebar-btn:hover svg path { fill: #38D5FF !important; }
    @media (max-width: 760px) {
        .cfds-wide-status-strip { grid-template-columns: 1fr 1fr; }
        .cfds-wide-controls { padding: .78rem .72rem; }
        .cfds-graph-card-wide { padding: .5rem !important; }
        .cfds-graph-card-wide [data-testid="stPlotlyChart"] { min-height: 520px; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# Replay spacing polish override: keep graph wide, but stop x-axis / state / event text from crowding.
st.markdown(
    """
    <style>
    .cfds-graph-card-wide {
        padding: .95rem 1rem 1.05rem 1rem !important;
        overflow: visible !important;
    }
    .cfds-graph-titlebar {
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important;
        min-height: 2.35rem !important;
        padding: .22rem .25rem .72rem .25rem !important;
        margin-bottom: .15rem !important;
    }
    .cfds-graph-titlebar h3 {
        color: #EAFBFF !important;
        font-size: clamp(1.05rem, 1.4vw, 1.28rem) !important;
        letter-spacing: .11em !important;
        line-height: 1.25 !important;
        margin: 0 !important;
    }
    .cfds-graph-titlebar span { display: none !important; }

    .cfds-state-strip {
        display: grid !important;
        grid-template-columns: repeat(7, minmax(90px, 1fr)) !important;
        gap: .78rem !important;
        margin: 1.38rem .15rem .86rem .15rem !important;
        padding: .95rem .90rem .82rem .90rem !important;
        overflow-x: auto !important;
        align-items: stretch !important;
    }
    .cfds-state-strip-title {
        top: -.82rem !important;
        left: .90rem !important;
        font-size: .67rem !important;
        padding: 0 .55rem !important;
        letter-spacing: .13em !important;
    }
    .cfds-state-chip {
        min-height: 2.55rem !important;
        padding: .46rem .56rem !important;
        justify-content: center !important;
        gap: .42rem !important;
        line-height: 1.1 !important;
        white-space: nowrap !important;
        overflow: visible !important;
        text-overflow: clip !important;
    }
    .cfds-state-dot {
        width: .82rem !important;
        height: .82rem !important;
        min-width: .82rem !important;
    }

    .cfds-event-strip-wide {
        display: grid !important;
        grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)) !important;
        gap: .72rem !important;
        margin: .92rem .15rem .20rem .15rem !important;
    }
    .cfds-event-chip {
        min-height: 3.05rem !important;
        padding: .64rem .72rem !important;
    }
    .cfds-event-chip span {
        font-size: .66rem !important;
        line-height: 1.05 !important;
        margin-bottom: .18rem !important;
    }
    .cfds-event-chip b {
        font-size: .88rem !important;
        line-height: 1.15 !important;
    }

    .cfds-replay-tipbar {
        margin-top: .82rem !important;
        padding-top: .70rem !important;
        line-height: 1.55 !important;
    }

    .modebar {
        margin-top: .18rem !important;
        margin-right: .18rem !important;
        z-index: 20 !important;
    }

    @media (max-width: 760px) {
        .cfds-graph-card-wide { padding: .72rem .55rem .82rem .55rem !important; }
        .cfds-graph-titlebar { min-height: 2rem !important; padding-bottom: .55rem !important; }
        .cfds-state-strip {
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
            gap: .55rem !important;
            padding: .88rem .62rem .70rem .62rem !important;
            margin-top: 1.25rem !important;
        }
        .cfds-state-chip { justify-content: flex-start !important; min-height: 2.35rem !important; }
        .cfds-event-strip-wide { grid-template-columns: 1fr 1fr !important; gap: .55rem !important; }
        .cfds-event-chip { min-height: 2.75rem !important; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# Replay color + butter smooth final override.
st.markdown(
    """
    <style>
    .cfds-state-pill {
        background: rgba(14,43,69,.78) !important;
        border: 1px solid rgba(56,213,255,.75) !important;
        color: #EAFBFF !important;
        box-shadow: inset 0 0 0 1px rgba(255,255,255,.04) !important;
    }
    .cfds-wide-controls [data-testid="stSelectbox"] label,
    .cfds-wide-controls [data-testid="stRadio"] label,
    .cfds-wide-controls [data-testid="stSlider"] label {
        color: #EAFBFF !important;
        font-weight: 800 !important;
    }
    .cfds-wide-controls [data-testid="stSelectbox"] div[data-baseweb="select"] > div {
        background: #0E2B45 !important;
        border: 1px solid rgba(56,213,255,.70) !important;
        color: #EAFBFF !important;
    }
    .cfds-state-strip { margin-top: 1.55rem !important; }
    .cfds-state-chip {
        background: rgba(7,24,39,.90) !important;
        color: #EAFBFF !important;
        box-shadow: 0 0 0 1px rgba(255,255,255,.04), inset 0 0 16px rgba(56,213,255,.05) !important;
    }
    .cfds-state-dot { box-shadow: 0 0 10px currentColor !important; }
    .stFileUploader [data-testid="stFileUploaderFile"] {
        background: #0E2B45 !important;
        border: 1px solid rgba(56,213,255,.65) !important;
        color: #EAFBFF !important;
    }
    .stFileUploader [data-testid="stFileUploaderFileName"],
    .stFileUploader [data-testid="stFileUploaderFileSize"] {
        color: #EAFBFF !important;
        opacity: 1 !important;
        font-weight: 800 !important;
    }
    .stFileUploader button { color: #EAFBFF !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


# Final visibility + dark-control + butter smooth option override.
st.markdown(
    """
    <style>
    /* No white controls: keep Streamlit/BaseWeb widgets in CFDS dark HUD style. */
    :root {
        --cfds-control-bg: #0E2B45;
        --cfds-control-bg-2: #071827;
        --cfds-control-border: rgba(56,213,255,.72);
        --cfds-control-text: #EAFBFF;
        --cfds-control-muted: #BFD7EA;
        --cfds-control-accent: #38D5FF;
    }

    /* Selectbox / dropdown closed state */
    div[data-baseweb="select"] > div,
    div[data-baseweb="select"] div,
    div[data-baseweb="input"] > div,
    div[data-baseweb="textarea"] > div {
        background: var(--cfds-control-bg) !important;
        color: var(--cfds-control-text) !important;
        border-color: var(--cfds-control-border) !important;
        box-shadow: none !important;
    }
    div[data-baseweb="select"] span,
    div[data-baseweb="select"] input,
    div[data-baseweb="select"] svg,
    div[data-baseweb="input"] input,
    div[data-baseweb="textarea"] textarea {
        color: var(--cfds-control-text) !important;
        fill: var(--cfds-control-text) !important;
        -webkit-text-fill-color: var(--cfds-control-text) !important;
        opacity: 1 !important;
    }

    /* Dropdown open menu */
    div[data-baseweb="popover"],
    div[data-baseweb="popover"] *,
    ul[role="listbox"],
    ul[role="listbox"] * {
        background: #071827 !important;
        color: var(--cfds-control-text) !important;
        opacity: 1 !important;
    }
    li[role="option"], div[role="option"] {
        background: #0B2136 !important;
        border-bottom: 1px solid rgba(56,213,255,.12) !important;
    }
    li[role="option"]:hover, div[role="option"]:hover {
        background: #0E2B45 !important;
    }

    /* File uploader whole area + selected-file chip. */
    [data-testid="stFileUploader"] section {
        background: rgba(11,33,54,.78) !important;
        border: 1px dashed rgba(56,213,255,.70) !important;
        border-radius: 14px !important;
    }
    [data-testid="stFileUploader"] section * {
        color: var(--cfds-control-text) !important;
        -webkit-text-fill-color: var(--cfds-control-text) !important;
        opacity: 1 !important;
    }
    [data-testid="stFileUploaderDropzone"] {
        background: rgba(11,33,54,.78) !important;
        color: var(--cfds-control-text) !important;
    }
    [data-testid="stFileUploaderFile"],
    [data-testid="stFileUploaderFile"] div,
    [data-testid="stFileUploaderFile"] span,
    [data-testid="stFileUploaderFile"] p,
    [data-testid="stFileUploaderFile"] small {
        background: #0E2B45 !important;
        color: var(--cfds-control-text) !important;
        -webkit-text-fill-color: var(--cfds-control-text) !important;
        opacity: 1 !important;
        font-weight: 800 !important;
    }
    [data-testid="stFileUploaderFile"] {
        border: 1px solid rgba(56,213,255,.70) !important;
        border-radius: 12px !important;
        box-shadow: inset 0 0 0 1px rgba(255,255,255,.04), 0 0 10px rgba(56,213,255,.10) !important;
    }
    [data-testid="stFileUploaderFile"] button,
    [data-testid="stFileUploader"] button {
        background: #0B2136 !important;
        border: 1px solid rgba(56,213,255,.65) !important;
        color: var(--cfds-control-text) !important;
        -webkit-text-fill-color: var(--cfds-control-text) !important;
    }
    [data-testid="stFileUploaderFile"] svg,
    [data-testid="stFileUploader"] svg {
        fill: var(--cfds-control-accent) !important;
        color: var(--cfds-control-accent) !important;
    }

    /* Checkbox / radio: readable labels, no dim disabled-looking text. */
    [data-testid="stCheckbox"], [data-testid="stRadio"] { color: var(--cfds-control-text) !important; }
    [data-testid="stCheckbox"] label,
    [data-testid="stRadio"] label,
    [data-testid="stCheckbox"] label *,
    [data-testid="stRadio"] label *,
    div[role="radiogroup"] label,
    div[role="radiogroup"] label * {
        color: var(--cfds-control-text) !important;
        -webkit-text-fill-color: var(--cfds-control-text) !important;
        opacity: 1 !important;
        font-weight: 750 !important;
        line-height: 1.55 !important;
    }
    [data-testid="stWidgetLabel"] p,
    [data-testid="stSlider"] label,
    [data-testid="stSlider"] label *,
    [data-testid="stSlider"] * {
        color: var(--cfds-control-text) !important;
        opacity: 1 !important;
    }
    [data-testid="stSlider"] [data-testid="stTickBar"] * {
        color: var(--cfds-control-muted) !important;
    }

    /* State pill: no cyan blob. Use dark pill with bright border. */
    .cfds-state-pill {
        background: #0E2B45 !important;
        border: 1px solid rgba(56,213,255,.82) !important;
        color: #EAFBFF !important;
        -webkit-text-fill-color: #EAFBFF !important;
        box-shadow: inset 0 0 0 1px rgba(255,255,255,.05), 0 0 10px rgba(56,213,255,.12) !important;
        text-shadow: none !important;
    }

    /* Wide replay controls: let the controls breathe and avoid white dropdowns. */
    .cfds-wide-controls [data-testid="column"] { min-width: 0 !important; }
    .cfds-wide-controls div[data-baseweb="select"] > div,
    .cfds-wide-controls div[data-baseweb="select"] div {
        background: #0E2B45 !important;
        color: #EAFBFF !important;
        border-color: rgba(56,213,255,.78) !important;
    }

    /* Sidebar: stack graph families cleanly and avoid text wrapping into unreadable columns. */
    section[data-testid="stSidebar"] [data-testid="stCheckbox"] {
        display: block !important;
        margin: .34rem 0 !important;
        padding: .08rem 0 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stCheckbox"] p,
    section[data-testid="stSidebar"] [data-testid="stRadio"] p {
        font-size: .97rem !important;
        line-height: 1.45 !important;
    }

    /* Animation feel selector emphasis */
    .cfds-wide-controls [data-testid="stSelectbox"]:has(label) {
        margin-bottom: .15rem !important;
    }

    @media (max-width: 760px) {
        [data-testid="stFileUploader"] section { min-height: 86px !important; padding: .75rem !important; }
        [data-testid="stFileUploaderFile"] { max-width: 100% !important; }
        .cfds-wide-controls { display: block !important; }
        .cfds-wide-controls [data-testid="column"] { width: 100% !important; margin-bottom: .85rem !important; }
        section[data-testid="stSidebar"] { width: min(92vw, 390px) !important; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# --- CFDS FINAL NO-WHITE / NO-EMPTY / INSIGHT POLISH OVERRIDE ---
st.markdown(
    """
    <style>
    /* No white widget boxes: selectbox, dropdown, uploader chips, and buttons stay dark HUD. */
    [data-baseweb="select"] > div,
    [data-baseweb="select"] div,
    [data-baseweb="input"] input,
    [data-testid="stFileUploaderFile"],
    [data-testid="stFileUploaderFile"] *,
    div[data-testid="stFileUploader"] li,
    div[data-testid="stFileUploader"] li *,
    div[data-testid="stFileUploader"] section div[role="button"],
    div[data-testid="stFileUploader"] section div[role="button"] * {
        background: #0B2136 !important;
        color: #EAFBFF !important;
        border-color: rgba(56,213,255,.46) !important;
        opacity: 1 !important;
        text-shadow: none !important;
    }
    [data-baseweb="select"] svg,
    [data-testid="stFileUploader"] svg { color:#38D5FF !important; fill:#38D5FF !important; }
    [data-baseweb="popover"], [data-baseweb="popover"] *, [data-baseweb="menu"], [data-baseweb="menu"] * {
        background: #071827 !important; color:#EAFBFF !important; opacity:1 !important;
    }
    [data-baseweb="menu"] li:hover { background:#0E2B45 !important; }

    /* White checkbox squares are allowed as controls, but selected/labels must be high contrast. */
    [data-testid="stCheckbox"] label p, [data-testid="stRadio"] label p { color:#EAFBFF !important; font-weight:750 !important; }

    /* Hide truly empty decorative panels/containers that create wasted blank gaps. */
    .cfds-panel:empty, .cfds-card:empty, .cfds-graph-card:empty,
    div[data-testid="stVerticalBlock"] > div:empty { display:none !important; min-height:0 !important; padding:0 !important; margin:0 !important; }

    .cfds-insight-strip { display:grid; grid-template-columns:repeat(auto-fit,minmax(155px,1fr)); gap:.55rem; margin:.7rem .15rem .25rem .15rem; }
    .cfds-insight-card { border:1px solid rgba(56,213,255,.26); background:rgba(7,24,39,.82); border-radius:12px; padding:.58rem .68rem; }
    .cfds-insight-card span { display:block; color:#9DB7C9 !important; font-size:.66rem; letter-spacing:.10em; text-transform:uppercase; font-weight:900; }
    .cfds-insight-card b { display:block; color:#EAFBFF !important; margin-top:.16rem; font-size:.92rem; }

    .cfds-state-pill { color:#EAFBFF !important; background:rgba(14,43,69,.92) !important; border:1px solid rgba(56,213,255,.72) !important; }
    </style>
    """,
    unsafe_allow_html=True,
)




# --- CLEAN STREAMLIT REBUILD POLISH: one final policy layer, no open wrappers ---
st.markdown(
    """
    <style>
    /* 1) No white input/select/uploader boxes anywhere in the app. */
    [data-testid="stFileUploader"],
    [data-testid="stFileUploader"] section,
    [data-testid="stFileUploaderDropzone"],
    [data-testid="stFileUploaderFile"],
    [data-testid="stFileUploaderFile"] *,
    [data-baseweb="select"] > div,
    [data-baseweb="select"] div,
    [data-baseweb="input"] > div,
    [data-baseweb="input"] input,
    [data-baseweb="textarea"] > div,
    [data-baseweb="textarea"] textarea {
        background: #0B2136 !important;
        color: #EAFBFF !important;
        -webkit-text-fill-color: #EAFBFF !important;
        border-color: rgba(56,213,255,.58) !important;
        opacity: 1 !important;
        box-shadow: none !important;
        text-shadow: none !important;
    }
    [data-baseweb="select"] svg,
    [data-testid="stFileUploader"] svg,
    [data-testid="stFileUploaderDropzone"] svg {
        color: #38D5FF !important;
        fill: #38D5FF !important;
        opacity: 1 !important;
    }
    [data-baseweb="popover"], [data-baseweb="popover"] *,
    [data-baseweb="menu"], [data-baseweb="menu"] *,
    ul[role="listbox"], ul[role="listbox"] * {
        background: #071827 !important;
        color: #EAFBFF !important;
        -webkit-text-fill-color: #EAFBFF !important;
        opacity: 1 !important;
    }
    [data-baseweb="menu"] li:hover, ul[role="listbox"] li:hover {
        background: #0E2B45 !important;
    }

    /* 2) Keep checkbox/radio labels readable but allow the small square indicator. */
    [data-testid="stCheckbox"] label p,
    [data-testid="stRadio"] label p,
    [data-testid="stSlider"] label p,
    [data-testid="stSelectbox"] label p,
    [data-testid="stTextInput"] label p,
    [data-testid="stExpander"] summary,
    [data-testid="stExpander"] summary * {
        color: #EAFBFF !important;
        opacity: 1 !important;
        font-weight: 760 !important;
        line-height: 1.45 !important;
    }

    /* 3) No empty boxes: the replay graph no longer uses an open div wrapper. */
    .cfds-graph-titlebar-only {
        border: 1px solid rgba(56,213,255,.30);
        background: rgba(7,24,39,.88);
        border-radius: 14px;
        padding: .72rem .95rem;
        margin: .85rem 0 .45rem 0;
    }
    .cfds-graph-titlebar-only h3 {
        margin: 0 !important;
        color: #EAFBFF !important;
        letter-spacing: .10em !important;
        font-size: clamp(1.02rem, 1.35vw, 1.24rem) !important;
    }
    .cfds-panel:empty, .cfds-card:empty, .cfds-graph-card:empty,
    div[data-testid="stVerticalBlock"] > div:empty {
        display: none !important;
        height: 0 !important;
        min-height: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
        border: 0 !important;
    }

    /* 4) Metric cards replace blank space under each graph. */
    .cfds-insight-strip {
        display: grid !important;
        grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)) !important;
        gap: .58rem !important;
        margin: .76rem .10rem .35rem .10rem !important;
    }
    .cfds-insight-card {
        background: rgba(7,24,39,.86) !important;
        border: 1px solid rgba(56,213,255,.28) !important;
        border-radius: 12px !important;
        padding: .62rem .70rem !important;
    }
    .cfds-insight-card span {
        color: #9DB7C9 !important;
        font-size: .66rem !important;
        letter-spacing: .11em !important;
        text-transform: uppercase !important;
        font-weight: 900 !important;
    }
    .cfds-insight-card b { color: #EAFBFF !important; font-size: .92rem !important; }

    /* 5) Phone layout: no weird wrapped two-column labels. */
    @media (max-width: 760px) {
        .block-container { padding-left: .82rem !important; padding-right: .82rem !important; }
        .cfds-wide-status-strip { grid-template-columns: 1fr 1fr !important; }
        .cfds-wide-controls [data-testid="column"] { width: 100% !important; margin-bottom: .80rem !important; }
        .cfds-state-strip { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; }
        .cfds-event-strip-wide { grid-template-columns: 1fr 1fr !important; }
        [data-testid="stFileUploaderFile"] { max-width: 100% !important; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)



# --- CFDS DEEP FIX FINAL POLICY: no white uploader chips, no blank wrappers, scientific calculator skin ---
st.markdown(
    """
    <style>
    /* Self-contained section headings replace raw open cfds-panel wrappers, preventing empty boxes. */
    .cfds-section-banner {
        border: 1px solid rgba(56,213,255,.32) !important;
        background: linear-gradient(180deg, rgba(7,24,39,.94), rgba(5,11,18,.90)) !important;
        border-radius: 14px !important;
        padding: .72rem .95rem !important;
        margin: .85rem 0 .55rem 0 !important;
        color: #38D5FF !important;
        font-weight: 900 !important;
        letter-spacing: .16em !important;
        font-size: .86rem !important;
        text-transform: uppercase !important;
        min-height: auto !important;
    }

    /* Uploaded file: hide Streamlit's native white chip and show our own dark chip below it. */
    div[data-testid="stFileUploader"] [data-testid="stFileUploaderFile"],
    div[data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] *,
    div[data-testid="stFileUploader"] section + div,
    div[data-testid="stFileUploader"] section + div * {
        display: none !important;
        visibility: hidden !important;
        height: 0 !important;
        min-height: 0 !important;
        max-height: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
        border: 0 !important;
        overflow: hidden !important;
    }
    .cfds-uploaded-chip {
        display: inline-flex !important;
        align-items: center !important;
        gap: .72rem !important;
        margin: .45rem 0 .15rem 0 !important;
        padding: .64rem .78rem !important;
        border-radius: 14px !important;
        border: 1px solid rgba(56,213,255,.55) !important;
        background: #0E2B45 !important;
        color: #EAFBFF !important;
        max-width: min(100%, 430px) !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,.05), 0 0 14px rgba(56,213,255,.08) !important;
    }
    .cfds-uploaded-chip b { display:block !important; color:#EAFBFF !important; font-weight:900 !important; max-width:310px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .cfds-uploaded-chip small { display:block !important; color:#9DB7C9 !important; font-size:.74rem !important; margin-top:.08rem !important; }
    .cfds-upload-icon { width:2.05rem; height:2.05rem; border-radius:10px; background:#071827; border:1px solid rgba(56,213,255,.5); display:grid; place-items:center; color:#38D5FF !important; font-weight:900; }

    /* Absolute no-white controls, including report inline-code pills like Source log. */
    code, pre, kbd, samp,
    [data-testid="stCodeBlock"], [data-testid="stCodeBlock"] *,
    [data-testid="stFileUploader"], [data-testid="stFileUploader"] *,
    [data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea,
    [data-baseweb="input"] input, [data-baseweb="textarea"] textarea,
    [data-baseweb="select"] > div, [data-baseweb="select"] div {
        background-color: #0B2136 !important;
        color: #EAFBFF !important;
        -webkit-text-fill-color: #EAFBFF !important;
        border-color: rgba(56,213,255,.52) !important;
        opacity: 1 !important;
    }
    [data-testid="stFileUploader"] button, [data-testid="stFileUploader"] button * {
        background: linear-gradient(180deg, #0B84FF, #005FB8) !important;
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
    }

    /* Checkbox/radio white squares were visually loud; keep controls dark while selected state stays obvious. */
    [data-testid="stCheckbox"] span[data-baseweb="checkbox"] > div,
    [data-testid="stRadio"] span[data-baseweb="radio"] > div,
    input[type="checkbox"], input[type="radio"] {
        background-color: #0E2B45 !important;
        border-color: rgba(234,251,255,.82) !important;
        color: #38D5FF !important;
        accent-color: #FF4B55 !important;
    }

    /* Remove blank decorative panels that may remain from earlier HTML wrapper patches. */
    .cfds-panel:empty, .cfds-card:empty, .cfds-graph-card:empty,
    .cfds-panel:not(:has(*:not(style):not(script))) {
        display: none !important;
        height: 0 !important;
        min-height: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
        border: 0 !important;
    }

    /* Calculator expander should look like an instrument panel, not a default Streamlit card. */
    [data-testid="stExpander"]:has(iframe) {
        background: #071827 !important;
        border: 1px solid rgba(56,213,255,.34) !important;
        border-radius: 18px !important;
        overflow: hidden !important;
    }
    [data-testid="stExpander"]:has(iframe) summary {
        background: #0B2136 !important;
        color: #EAFBFF !important;
        font-weight: 900 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

CLEAN_REBUILD_POLICY_NOTE = "Clean rebuild layer: no white controls, no open HTML wrappers, AAS 2026 descent bands, CONOPS accuracy, GPS XY/XYZ, split motion, metric cards."

# FINAL_VISIBILITY_POLICY_NOTE = "No white controls, no empty cards, AAS 2026 bands 12-18 and 2-8, CONOPS planned-vs-actual accuracy, XYZ min/max/range cards."
