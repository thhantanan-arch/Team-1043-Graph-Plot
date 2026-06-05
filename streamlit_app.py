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

    # Stable mission-time axis for replay. Prefer T_REL from the normalizer;
    # fall back to PACKET_COUNT/5 Hz; then row index.
    if "T_REL" in df.columns:
        t = pd.to_numeric(df["T_REL"], errors="coerce")
    elif "PACKET_COUNT" in df.columns:
        t = pd.to_numeric(df["PACKET_COUNT"], errors="coerce") / 5.0
        t = t - t.min(skipna=True)
    else:
        t = pd.Series(range(len(df)), dtype="float")
    t = t.ffill().fillna(0.0)
    t = t - t.min(skipna=True)
    df = df.copy()
    df["__REPLAY_TIME_S"] = t
    return df, ""


def _downsample_for_replay(df, max_points: int):
    """Downsample by index for phone-friendly replay without changing the original export."""
    if len(df) <= max_points:
        return df.reset_index(drop=True)
    step = max(1, int(len(df) / max_points))
    sampled = df.iloc[::step].copy()
    if sampled.index[-1] != df.index[-1]:
        sampled = __import__("pandas").concat([sampled, df.tail(1)], ignore_index=False)
    return sampled.reset_index(drop=True)


def _replay_plot_data(df, graph_type: str):
    """Choose columns and display labels for the selected replay graph."""
    import pandas as pd
    graph_map = {
        "Altitude": (["ALTITUDE", "ALT", "ALTITUDE_M"], "Altitude (m)"),
        "Velocity / Descent rate": (["DESCENT_RATE_DERIVED", "VELOCITY_DERIVED", "VELOCITY"], "Velocity / descent rate"),
        "Voltage": (["VOLTAGE", "VBATT", "BATTERY_VOLTAGE"], "Voltage (V)"),
        "Temperature": (["TEMPERATURE", "TEMP", "TEMP_C"], "Temperature (°C)"),
        "Pressure": (["PRESSURE", "PRES", "BARO_PRESSURE"], "Pressure"),
        "Current": (["CURRENT", "CURR", "BATTERY_CURRENT"], "Current (A)"),
        "GPS altitude": (["GPS_ALT", "GNSS_ALT", "GPS_ALTITUDE"], "GPS altitude (m)"),
    }
    if graph_type == "Motion magnitude":
        candidates = [
            (["ACCEL_R", "ACCEL_P", "ACCEL_Y"], "Acceleration magnitude"),
            (["GYRO_R", "GYRO_P", "GYRO_Y"], "Gyro magnitude"),
        ]
        for cols, label in candidates:
            if all(c in df.columns for c in cols):
                x = pd.to_numeric(df[cols[0]], errors="coerce")
                y = pd.to_numeric(df[cols[1]], errors="coerce")
                z = pd.to_numeric(df[cols[2]], errors="coerce")
                return pd.DataFrame({"Mission time (s)": df["__REPLAY_TIME_S"], label: (x*x + y*y + z*z) ** 0.5}), label
        return None, "No acceleration/gyro XYZ columns found."

    if graph_type not in graph_map:
        return None, "Unsupported replay graph."
    col, y = _numeric_series(df, graph_map[graph_type][0])
    if col is None:
        return None, f"No usable column found for {graph_type}."
    label = graph_map[graph_type][1]
    return pd.DataFrame({"Mission time (s)": df["__REPLAY_TIME_S"], label: y}), label


def _event_markers_for_replay(df):
    """Infer basic event markers for replay charts."""
    events = []
    if df is None or df.empty or "__REPLAY_TIME_S" not in df.columns:
        return events
    try:
        t0 = float(df["__REPLAY_TIME_S"].iloc[0])
        t_end = float(df["__REPLAY_TIME_S"].iloc[-1])
        alt_col, alt = _numeric_series(df, ["ALTITUDE", "ALT", "ALTITUDE_M"])
        if alt_col is not None and alt.notna().any():
            imax = int(alt.idxmax()) if hasattr(alt, "idxmax") else 0
            events.append((float(df.loc[imax, "__REPLAY_TIME_S"]), "Apogee", "#ef4444"))
            # Payload release fallback: first point after apogee below 80% of max altitude.
            peak = float(alt.max(skipna=True))
            after = df.loc[imax:].copy()
            alt_after = alt.loc[imax:]
            below = alt_after[alt_after <= peak * 0.80]
            if len(below):
                ridx = below.index[0]
                events.append((float(df.loc[ridx, "__REPLAY_TIME_S"]), "Payload", "#f59e0b"))
        events.insert(0, (t0, "Launch", "#ef4444"))
        events.append((t_end, "End", "#38d5ff"))
    except Exception:
        pass
    # De-duplicate near-identical times.
    clean = []
    for ev in events:
        if not any(abs(ev[0] - x[0]) < 0.5 and ev[1] == x[1] for x in clean):
            clean.append(ev)
    return clean


def _v1256_stage_rects(t_min: float, t_max: float, events):
    """Create V12.56-like stage bands using inferred event times."""
    if t_max <= t_min:
        return []
    labels = ["Launch / Ascent", "Coast", "Payload Descent", "Main Descent", "Landed"]
    colors = ["rgba(239,68,68,.18)", "rgba(245,158,11,.16)", "rgba(249,115,22,.16)", "rgba(34,197,94,.16)", "rgba(56,213,255,.12)"]
    apogee = next((t for t, name, _ in events if name == "Apogee"), t_min + .22 * (t_max-t_min))
    payload = next((t for t, name, _ in events if name == "Payload"), t_min + .36 * (t_max-t_min))
    landed = t_max
    b = [t_min, apogee, payload, t_min + .72*(t_max-t_min), landed]
    b = [max(t_min, min(t_max, float(x))) for x in b]
    ranges = [(b[0], b[1]), (b[1], b[2]), (b[2], b[3]), (b[3], b[4]), (b[4], t_max)]
    return [(a, c, labels[i], colors[i]) for i, (a, c) in enumerate(ranges) if c > a]


def _make_v1256_replay_fig(plot_df, label: str, full_df, graph_type: str, frame_time: float):
    import plotly.graph_objects as go
    x = plot_df["Mission time (s)"]
    y = plot_df[label]
    fig = go.Figure()
    events = _event_markers_for_replay(full_df)
    t_min = float(full_df["__REPLAY_TIME_S"].min())
    t_max = float(full_df["__REPLAY_TIME_S"].max())
    for x0, x1, name, color in _v1256_stage_rects(t_min, t_max, events):
        fig.add_vrect(x0=x0, x1=x1, fillcolor=color, opacity=1, line_width=0,
                      annotation_text=name, annotation_position="top left",
                      annotation_font_size=10, annotation_font_color="#334155")
    line_color = "#0077A7"
    if "Velocity" in graph_type:
        line_color = "#1d4ed8"
    elif graph_type in {"Voltage", "Current"}:
        line_color = "#7c3aed"
    elif graph_type in {"Temperature", "Pressure"}:
        line_color = "#ea580c"
    elif graph_type == "Motion magnitude":
        line_color = "#16a34a"
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="lines", name=label,
        line=dict(color=line_color, width=3, shape="spline", smoothing=0.75),
        fill="tozeroy" if graph_type == "Altitude" else None,
        fillcolor="rgba(0,119,167,.08)" if graph_type == "Altitude" else None,
    ))
    if len(plot_df):
        fig.add_trace(go.Scatter(
            x=[x.iloc[-1]], y=[y.iloc[-1]], mode="markers", name="Current point",
            marker=dict(size=11, color="#ef4444", line=dict(color="white", width=1.6)),
            hovertemplate="t=%{x:.1f}s<br>value=%{y:.3g}<extra></extra>",
        ))
    fig.add_vline(x=frame_time, line_width=2, line_color="#111827", line_dash="dash")
    y_min = float(y.min()) if len(y) else 0.0
    y_max = float(y.max()) if len(y) else 1.0
    if y_min == y_max:
        y_min -= 1; y_max += 1
    for tx, name, color in events:
        if tx <= frame_time + 1e-6:
            fig.add_vline(x=tx, line_width=1, line_color=color, line_dash="dot")
            fig.add_annotation(x=tx, y=y_max, text=name, showarrow=False, yanchor="bottom", font=dict(size=10, color="#111827"), bgcolor="rgba(255,255,255,.62)")
    fig.update_layout(
        title=dict(text=f"{graph_type} Replay", x=0.02, y=0.96, font=dict(size=18, color="#111827")),
        height=430,
        margin=dict(l=58, r=28, t=62, b=52),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#F7FCFF",
        font=dict(color="#111827", size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, bgcolor="rgba(255,255,255,.65)"),
        hovermode="x unified",
    )
    fig.update_xaxes(title_text="Mission time (s)", gridcolor="rgba(100,116,139,.22)", zeroline=False, linecolor="#64748b", mirror=True)
    fig.update_yaxes(title_text=label, gridcolor="rgba(100,116,139,.24)", zeroline=False, linecolor="#64748b", mirror=True)
    return fig


def render_flight_replay(payload: dict, mobile_fast: bool = True) -> None:
    """V12.56-style phone-friendly log replay."""
    st.markdown('<a id="replay"></a><div class="cfds-panel"><div class="cfds-panel-title">Flight replay deck</div>', unsafe_allow_html=True)
    st.subheader("🎞️ Flight Replay")
    st.caption("Mission playback from the normalized log. The graph skin matches the exported CFDS/V12.56 graph language: pale plot surface, state bands, event markers, and current-time cursor.")

    df, err = _replay_dataframe_from_payload(payload)
    if err:
        st.info(err)
        st.markdown('</div>', unsafe_allow_html=True)
        return

    max_points_default = 300 if mobile_fast else 650
    c1, c2, c3 = st.columns([1.35, 1, 1])
    with c1:
        graph_type = st.radio(
            "Replay graph",
            ["Altitude", "Velocity / Descent rate", "Voltage", "Temperature", "Pressure", "Current", "GPS altitude", "Motion magnitude", "GPS path"],
            index=0,
            horizontal=False,
            key="replay_graph_type",
        )
    with c2:
        speed = st.radio("Speed", ["1x", "2x", "5x", "10x"], index=2 if mobile_fast else 1, horizontal=True, key="replay_speed")
        trail_mode = st.radio("Trail", ["Full trail", "Last 10 s", "Last 30 s", "Last 60 s"], index=0, key="replay_trail")
    with c3:
        max_points = st.slider("Smoothness frames", min_value=120, max_value=900, value=max_points_default, step=20, help="Higher = smoother but heavier on iPhone.", key="replay_max_points")
        st.markdown('<div class="cfds-mobile-note">Use 300–600 frames on iPhone. 900 is for final demo playback.</div>', unsafe_allow_html=True)

    replay_df = _downsample_for_replay(df, max_points)
    if replay_df.empty:
        st.warning("No replay data after downsampling.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    total_frames = len(replay_df)
    if "replay_frame" not in st.session_state:
        st.session_state["replay_frame"] = 0
    st.session_state["replay_frame"] = min(max(0, int(st.session_state["replay_frame"])), total_frames - 1)

    frame = st.slider(
        "Mission timeline",
        min_value=0,
        max_value=total_frames - 1,
        value=st.session_state["replay_frame"],
        step=1,
        key="replay_timeline_slider",
        help="Scrub the flight manually. Press Play to animate from this frame.",
    )
    st.session_state["replay_frame"] = frame

    controls = st.columns(4)
    play = controls[0].button("▶ Play", use_container_width=True, key="replay_play_btn")
    pause = controls[1].button("⏸ Pause", use_container_width=True, key="replay_pause_btn")
    reset = controls[2].button("↺ Reset", use_container_width=True, key="replay_reset_btn")
    jump_end = controls[3].button("⏭ End", use_container_width=True, key="replay_end_btn")
    if reset:
        st.session_state["replay_frame"] = 0
        st.rerun()
    if jump_end:
        st.session_state["replay_frame"] = total_frames - 1
        st.rerun()

    status = st.empty()
    chart_slot = st.empty()

    def _windowed(sub):
        if trail_mode == "Full trail" or sub.empty:
            return sub
        seconds = float(trail_mode.split()[1])
        t_now = float(sub["__REPLAY_TIME_S"].iloc[-1]) if "__REPLAY_TIME_S" in sub.columns else 0.0
        return sub[sub["__REPLAY_TIME_S"] >= t_now - seconds]

    def _render_one(frame_idx: int):
        frame_idx = min(max(0, int(frame_idx)), total_frames - 1)
        sub = replay_df.iloc[: frame_idx + 1].copy()
        sub = _windowed(sub)
        t_now = float(replay_df["__REPLAY_TIME_S"].iloc[frame_idx])
        status.markdown(f"**Replay time:** {t_now:.1f} s / {float(replay_df['__REPLAY_TIME_S'].iloc[-1]):.1f} s · **Frame:** {frame_idx + 1}/{total_frames}")

        if graph_type == "GPS path":
            import pandas as pd
            lat_col, lat = _numeric_series(sub, ["GPS_LAT", "LAT", "LATITUDE"])
            lon_col, lon = _numeric_series(sub, ["GPS_LON", "LON", "LONGITUDE"])
            if lat_col is None or lon_col is None:
                chart_slot.info("No GPS latitude/longitude columns found for path replay.")
                return
            gps = pd.DataFrame({"lat": lat, "lon": lon}).dropna()
            gps = gps[(gps["lat"].abs() > 0.0001) & (gps["lon"].abs() > 0.0001)]
            if gps.empty:
                chart_slot.info("GPS path has no valid coordinates yet at this frame.")
                return
            chart_slot.map(gps, use_container_width=True)
            return

        plot_df, label = _replay_plot_data(sub, graph_type)
        if plot_df is None:
            chart_slot.info(label)
            return
        plot_df = plot_df.dropna()
        if plot_df.empty:
            chart_slot.info("No numeric data available yet for this replay frame.")
            return
        fig = _make_v1256_replay_fig(plot_df, label, replay_df, graph_type, t_now)
        chart_slot.plotly_chart(fig, use_container_width=True, theme=None)

    _render_one(st.session_state["replay_frame"])

    if play and not pause:
        speed_factor = int(speed.replace("x", ""))
        frame_step = max(1, speed_factor)
        delay = 0.10 if mobile_fast else 0.08
        end_frame = min(total_frames - 1, st.session_state["replay_frame"] + 90 * frame_step)
        for frame_idx in range(st.session_state["replay_frame"], end_frame + 1, frame_step):
            _render_one(frame_idx)
            st.session_state["replay_frame"] = frame_idx
            time.sleep(delay)
        st.caption("Playback chunk finished. Tap ▶ Play again to continue, or scrub the timeline.")
    st.markdown('</div>', unsafe_allow_html=True)

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
    cols = st.columns(2)
    for i, (key, meta) in enumerate(GRAPH_FAMILIES.items()):
        with cols[i % 2]:
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

st.markdown('<div class="cfds-panel"><div class="cfds-panel-title">Mission input</div>', unsafe_allow_html=True)
uploaded = None
if not use_demo:
    uploaded = st.file_uploader("Upload flight log", type=SUPPORTED_TYPES)

st.markdown('</div><a id="generate"></a><div class="cfds-panel"><div class="cfds-panel-title">Generation command</div>', unsafe_allow_html=True)
start = st.button("Generate selected graphs", type="primary", use_container_width=True)
st.markdown('</div>', unsafe_allow_html=True)

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

st.divider()
st.caption("CFDS Web keeps the original graph engine, but uses a mobile-optimized browser interface for iPhone/iPad/desktop.")
