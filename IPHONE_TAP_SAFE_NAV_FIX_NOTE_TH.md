# CFDS iPhone Tap-Safe Navigation Fix

This build removes searchable selectboxes from the graph/export browser because iPhone Safari can leave typed filter text in the selectbox, causing a red invalid-looking state or stale selection display.

## Changed
- Graph export browser folder picker: selectbox -> tap-only radio list
- Individual PNG picker: selectbox -> tap-only radio list
- Preview folder picker: selectbox -> tap-only radio list
- Download buttons still use on_click="ignore" to avoid page reset after download

## Why
Streamlit widgets rerun the page when their value changes. On mobile, searchable selectbox state can desync visually from the returned value. Tap-only radio controls are less compact but more reliable on iPhone.

## Update files
Upload/replace at least:
- streamlit_app.py

Recommended also upload this note for tracking:
- IPHONE_TAP_SAFE_NAV_FIX_NOTE_TH.md
