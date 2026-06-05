# CFDS Mobile Pro — Flight Replay Update

เพิ่มหน้า **🎞️ Flight Replay** สำหรับ iPhone/Web:

- Replay จาก normalized CSV หลัง Generate graphs
- เลือกกราฟ replay ได้: Altitude, Velocity/Descent Rate, Voltage, Temperature, Pressure, Current, GPS Altitude, Motion Magnitude, GPS Path
- มี Mission timeline slider สำหรับ scrub เวลา
- มี Play / Reset / End
- มี Speed 1x / 2x / 5x / 10x
- มี Trail mode: Full trail / Last 10s / Last 30s / Last 60s
- ใช้ `st.session_state` เก็บ frame ข้าม rerun
- ใช้ `st.line_chart` และ `st.map` เพื่อลดภาระบนมือถือ ไม่ render Matplotlib PNG ใหม่ทุก frame

หมายเหตุ: นี่คือ log replay ไม่ใช่ sensor live telemetry จริงแบบ real-time radio stream
