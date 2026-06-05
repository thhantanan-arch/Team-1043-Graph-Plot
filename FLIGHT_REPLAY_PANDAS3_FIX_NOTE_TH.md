# Flight Replay Pandas 3 Fix

แก้บั๊ก Flight Replay ที่เกิดจาก `fillna(method="ffill")` บน pandas รุ่นใหม่ใน Streamlit Cloud.

เปลี่ยนเป็น `ffill().fillna(0.0)` เพื่อให้เข้ากับ pandas 3.x และยังทำ forward-fill mission time เหมือนเดิม.

อัปเดต GitHub อย่างน้อยไฟล์:
- streamlit_app.py

แนะนำเพิ่ม note นี้ด้วยถ้าต้องการเก็บ changelog.
