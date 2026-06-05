# CFDS v0.5.7 — V12.56 Web Console Adapt Design

เวอร์ชันนี้เป็นการ adapt interface ให้ใกล้ V12.56 มากขึ้น โดยไม่รื้อ graph engine เดิม

## ปรับหลัก
- เพิ่ม top mission console header แบบ CFDS/V12.56
- เพิ่ม mission dock: Import / Generate / Preview / Replay / Export
- เปลี่ยนสี UI เป็น dark aerospace HUD + cyan accent
- ปรับ card/panel/button/sidebar ให้เป็น control-deck feel
- Flight Replay ใช้ Plotly V12.56-style graph skin แทน Streamlit line_chart default
- Replay graph ใช้ pale plot background, stage bands, current cursor, event markers
- ใช้ `theme=None` กับ Plotly เพื่อไม่ให้ Streamlit override สีกราฟ
- เพิ่ม `plotly` ใน requirements.txt

## อัปเดต GitHub
อัปโหลดทับอย่างน้อย:
- streamlit_app.py
- requirements.txt

ถ้า Streamlit Cloud ไม่ rebuild ให้กด Manage app → Reboot app
