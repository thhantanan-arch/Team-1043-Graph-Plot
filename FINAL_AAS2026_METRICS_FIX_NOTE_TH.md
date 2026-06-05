# FINAL AAS 2026 Metrics Fix

แก้ตามกติกาและการวิเคราะห์กราฟ:

- Velocity / Descent rate ใช้ AAS 2026 bands:
  - Container/parachute descent: 12–18 m/s
  - Payload paraglider descent: 2–8 m/s
- CONOPS เพิ่ม Actual vs Planned และคำนวณ accuracy / average absolute difference
- Multi-axis เพิ่ม metric cards สำหรับ X/Y/Z min/max และ magnitude max
- เพิ่ม CONOPS accuracy เป็น replay graph option
- ยืนยัน unit labels: m, m/s, V, A, °C, deg/s, deg
- ไม่แตะ state timing / event detection / export engine
