from flask import Flask, render_template, request, redirect, url_for, flash,jsonify
import os
import heapq
from datetime import datetime, timedelta
from itertools import groupby
import pytz   
from database import (
    get_waiting_count_before,
    get_tables_for_type,
    add_table, 
    get_walkin_tables, 
    delete_table, 
    start_table_service, 
    clear_table_service, 
    get_queue_by_id, 
    add_queue_walkin, 
    get_waiting_list, 
    cancel_queue_service,
    get_today_reservations,
    get_reservation_tables,
    add_reservation_service,
    get_reservations_by_date,
    check_availability,
    checkin_reservation_service,
    cancel_reservation_service,
    close_day_service,
    get_dashboard_data,
    send_line_notification,
    get_table_finish_time,
    get_real_average_cycle_time
)

# หาที่อยู่ของไฟล์ app.py ปัจจุบัน (อยู่ใน backend)
current_dir = os.path.dirname(os.path.abspath(__file__))
# กำหนดที่อยู่โฟลเดอร์ frontend
frontend_dir = os.path.join(current_dir, '../frontend')
app = Flask(__name__, template_folder=frontend_dir,static_folder=frontend_dir)
app.secret_key = "123456789"

# 1. หน้าแรก
@app.route('/')
def home():
    return """
    <h1>หน้าหลัก</h1>
    <a href="/admin">👉 ไปหน้า Admin (จัดการร้าน)</a>
    """

# 2. หน้า Admin (แสดงฟอร์ม)
@app.route('/admin')
def admin_page():
    # 1. เรียก Service ดึงโต๊ะ Walk-in
    walkin_tables = get_walkin_tables()
    
    # 2. เรียก Service ดึงโต๊ะ Reservation (ที่เราเพิ่งสร้าง)
    reserve_tables = get_reservation_tables()
    
    # 3. เรียก Service ดึงคิวที่รอ
    waiting_list = get_waiting_list()
    
    # 4. เรียก Service ดึงรายการจองวันนี้
    reservations = get_today_reservations()

    return render_template('admin.html', 
                           walkin_tables=walkin_tables, 
                           reservation_tables=reserve_tables, # ส่งตัวแปรนี้ไปให้ HTML วนลูปโซนล่าง
                           waiting_list=waiting_list,
                           reservations=reservations)
# 3. ฝั่งรับข้อมูล (เมื่อกดปุ่มบันทึก)
@app.route('/add-table', methods=['POST'])
def submit_table():
    # รับค่าจากฟอร์ม HTML
    name = request.form['table_name']
    capacity = int(request.form['capacity'])
    zone = request.form['zone_type']

    # ส่งเข้า Database
    result = add_table(name, capacity, zone)

    # ส่งผลลัพธ์ไปโชว์ที่หน้า admin (เดี๋ยวเราไปแก้ html นิดนึง)
    # แต่ตอนนี้เอาแบบง่ายๆ คือ return ข้อความออกไปก่อน
    if result['status'] == 'error':
        return f"<h1>⚠️ เกิดข้อผิดพลาด</h1><h3>{result['message']}</h3><a href='/admin'>กลับไปแก้ไข</a>"

    # บันทึกเสร็จ ให้รีเฟรชกลับมาหน้าเดิม
    return redirect(url_for('admin_page'))

# 4. ลบโต๊ะ
@app.route('/delete-table/<int:table_id>', methods=['POST'])
def delete_table_route(table_id):
    result = delete_table(table_id)
    # ลบเสร็จแล้วให้กลับมาหน้าเดิม 
    return redirect(url_for('admin_page'))

# 5. เริ่มให้บริการโต๊ะ
@app.route('/start-table/<int:table_id>', methods=['POST'])
def start_table_route(table_id):
    # รับค่า 'duration' ที่ส่งมาจาก Form หน้าบ้าน
    duration = request.form.get('duration') 
    
    if not duration:
        duration = 90 # ค่า Default กันเหนียว เผื่อไม่มีการส่งมา
        
    start_table_service(table_id, duration)
    return redirect(url_for('admin_page'))

# 6. หน้า ลูกค้า Walk-in (Scan QR)
@app.route('/walkin')
def walkin_index():
    return render_template('walkin_form.html')

# 7. ฝั่งรับข้อมูลลูกค้า Walk-in
@app.route('/walkin/submit', methods=['POST'])
def walkin_submit():
    # 1. รับค่า pax และ line_user_id
    pax = request.form.get('pax')
    line_user_id = request.form.get('line_user_id') # <--- ✅ 2.1 รับค่าจาก LIFF
    
    print(f"DEBUG: PAX='{pax}', LINE_ID='{line_user_id}'")

    if not pax:
        return "❌ Error: ไม่ได้รับค่าจำนวนคน", 400

    # 2. ส่งเข้า Database (พร้อม ID)
    result = add_queue_walkin(pax, line_user_id) # <--- ✅ 2.2 ส่ง ID ไปบันทึก
    
    if result['status'] == 'success':
        queue_id = result['data']['id']
        return redirect(url_for('my_queue_status', queue_id=queue_id))
    
    return f"<h1>⚠️ Database Error</h1><p>{result.get('message')}</p>", 400

# 8. หน้าแสดงสถานะคิวลูกค้า Walk-in
# ในไฟล์ app.py

@app.route('/queue/<int:queue_id>')
def my_queue_status(queue_id):
    # 1. ดึงข้อมูลคิว
    my_queue = get_queue_by_id(queue_id)

    # เช็คสถานะ Reset
    if not my_queue or my_queue['status'] in ['cancelled', 'completed']:
        return redirect(url_for('walkin_index', reset=1))

    # ถ้ากินอยู่ (Dining)
    if my_queue['status'] == 'dining':
        finish_time_display = "ไม่ระบุ"
        if my_queue.get('table_id'):
            raw_time = get_table_finish_time(my_queue['table_id'])
            if raw_time:
                tz = pytz.timezone('Asia/Bangkok')
                try:
                    ft = datetime.fromisoformat(raw_time.replace('Z', '+00:00')).astimezone(tz)
                    finish_time_display = ft.strftime('%H:%M น.')
                except:
                    pass
        return render_template('walkin_status.html', queue=my_queue, is_dining=True, finish_time=finish_time_display, estimated_time="Served", time_diff=0)

    # =========================================================
    # 🟢 ZONE 3: Waiting (Logic: จำลองคิวแบบที่เพื่อนต้องการ)
    # =========================================================
    
    # ข้อมูลพื้นฐาน
    my_position_index = get_waiting_count_before(my_queue['queue_type'], queue_id)
    my_queue['position_wait'] = my_position_index + 1  # รวมตัวเองด้วย
    target_tables = get_tables_for_type(my_queue['queue_type'])
    
    if not target_tables:
        return render_template('walkin_status.html', queue=my_queue, estimated_time="N/A", time_diff=0)

    timezone = pytz.timezone('Asia/Bangkok')
    now = datetime.now(timezone)

    # 1. กำหนดเวลาต่อรอบ (CYCLE TIME)
    DEFAULT_CYCLE = 80  # <--- ✅ เพิ่มบรรทัดนี้กลับมาครับ
    
    # ✅ ใช้สูตรใหม่: ดึงค่าเฉลี่ยจริงจาก Database
    real_avg_time = get_real_average_cycle_time(default_cycle=DEFAULT_CYCLE)
    
    # ใช้ค่าที่คำนวณได้เลย
    REALISTIC_CYCLE = real_avg_time
    
    # (Optional) กันเหนียว: ไม่ให้ต่ำกว่า 45 นาที
    if REALISTIC_CYCLE < 45: 
        REALISTIC_CYCLE = 45

    MAX_CYCLE = 90

    # 2. เตรียมข้อมูลโต๊ะ (Heap Queue)
    # ใส่เวลาที่โต๊ะแต่ละตัวจะว่างลงไป
    timeline_real = []
    timeline_max = []

    for t in target_tables:
        if t['status'] == 'empty':
            # โต๊ะว่าง = ว่างเดี๋ยวนี้ (Now)
            heapq.heappush(timeline_real, now)
            heapq.heappush(timeline_max, now)
        else:
            # โต๊ะไม่ว่าง = ว่างตอน Final Time
            if t.get('final_time'):
                ft_str = t['final_time'].replace('Z', '+00:00')
                ft = datetime.fromisoformat(ft_str).astimezone(timezone)
                # สำหรับ Realistic เราเชื่อว่าลูกค้าลุกก่อนเวลาจบจริงนิดหน่อย (Buffer ตามประวัติ)
                # แต่เพื่อให้ Logic คิว 2 ต่อ คิว 1 เป๊ะๆ เรายึดเวลาจบเป็นหลัก แล้วลบ Buffer คงที่สัก 10 นาที
                buffer = 10 
                heapq.heappush(timeline_real, ft - timedelta(minutes=buffer))
                heapq.heappush(timeline_max, ft)
            else:
                # กันเหนียว
                fallback = now + timedelta(minutes=DEFAULT_CYCLE)
                heapq.heappush(timeline_real, fallback)
                heapq.heappush(timeline_max, fallback)

    # 3. เริ่มจำลองการเข้าคิว (Simulation Loop)
    # วนลูปตั้งแต่คิวแรก จนถึงคิวเรา
    
    my_time_real = now
    my_time_max = now

    # วนลูปตามจำนวนคนที่รอ + 1 (ตัวเรา)
    # รอบที่ 0 = คิวที่ 1
    # รอบที่ 1 = คิวที่ 2
    for i in range(my_position_index + 1):
        
        # --- สูตร Realistic ---
        # หยิบเวลาที่เร็วที่สุดออกมา
        earliest_free_real = heapq.heappop(timeline_real)
        
        if i == my_position_index:
            # ถ้าเป็นรอบของเรา -> นี่คือเวลาที่เราจะได้เข้า!
            my_time_real = earliest_free_real
        else:
            # ถ้าเป็นคิวคนอื่น -> เขาเข้าไปกิน (บวกเวลา 80 นาที) -> แล้วคืนโต๊ะออกมา
            next_free_real = earliest_free_real + timedelta(minutes=REALISTIC_CYCLE)
            heapq.heappush(timeline_real, next_free_real)

        # --- สูตร Max (ทำเหมือนกัน) ---
        earliest_free_max = heapq.heappop(timeline_max)
        if i == my_position_index:
            my_time_max = earliest_free_max
        else:
            next_free_max = earliest_free_max + timedelta(minutes=MAX_CYCLE)
            heapq.heappush(timeline_max, next_free_max)

    # 4. แปลงเป็นนาที
    wait_min_real = int((my_time_real - now).total_seconds() / 60)
    if wait_min_real < 0: wait_min_real = 0

    wait_min_max = int((my_time_max - now).total_seconds() / 60)
    if wait_min_max < 0: wait_min_max = 0

    # จัดระเบียบ
    if wait_min_real >= wait_min_max:
        wait_min_real = max(0, wait_min_max - 5)

    return render_template(
        'walkin_status.html', 
        queue=my_queue, 
        estimated_time=my_time_max.strftime('%H:%M น.'), 
        time_diff=wait_min_max,       
        min_time_diff=wait_min_real   
    )

# 9. ยกเลิกคิว
@app.route('/cancel-queue/<int:queue_id>', methods=['POST'])
def cancel_queue_route(queue_id):
    # 1. สั่งยกเลิกใน Database
    cancel_queue_service(queue_id)
    
    # 2. เช็คว่าใครเป็นคนกด? (ดูจาก Query Parameter)
    source = request.args.get('source')

    if source == 'walkin':
        # ✅ ถ้าลูกค้ากด -> ส่งกลับไปหน้าแรก + สั่งลบ LocalStorage (reset=1)
        return redirect(url_for('walkin_index', reset=1))
    
    # ✅ ถ้าแอดมินกด (ไม่มี source) -> กลับไปหน้า Admin เหมือนเดิม
    return redirect(url_for('admin_page'))

# 10. เคลียร์โต๊ะ (เมื่อบริการเสร็จ)
@app.route('/clear-table/<int:table_id>', methods=['POST'])
def clear_table_route(table_id):
    # เรียกใช้ฟังก์ชันเคลียร์โต๊ะจาก database.py
    clear_table_service(table_id)
    # เสร็จแล้วรีเฟรชหน้าเดิม
    return redirect(url_for('admin_page'))

#--------------------------------------------------------
# ส่วนของการจองโต๊ะล่วงหน้า (Reservation)

# 11. หน้า จองโต๊ะล่วงหน้า
@app.route('/booking', methods=['GET', 'POST'])
def booking_page():
    if request.method == 'POST':
        name = request.form.get('customer_name')
        phone = request.form.get('phone')
        pax = request.form.get('pax')
        b_date = request.form.get('booking_date')
        b_time = request.form.get('booking_time')

        # --------------------------------------------------------
        # 🛡️ VALIDATION: ตรวจสอบสาเหตุที่จองไม่ได้
        # -------------------------------------------------------
        
        # ฟังก์ชันจะคืนค่า (True/False) และ (ข้อความสาเหตุ)
        is_available, fail_reason = check_availability(pax, b_date, b_time)
        
        if not is_available:
            # ส่งข้อความสาเหตุกลับไปหน้าเว็บ
            # fail_reason จะเป็นข้อความที่เราเขียนดักไว้ใน database.py เช่น "เต็มแล้ว" หรือ "ไม่มีโต๊ะไซส์นี้"
            flash(fail_reason, 'error') 
            
            # (Optional) ส่งค่าเดิมกลับไป input form ไม่ต้องกรอกใหม่ (ถ้าอยากทำเพิ่ม)
            return redirect('/booking') 

        # --------------------------------------------------------
        # ✅ SUCCESS: ถ้าผ่านด่านค่อยบันทึก
        # --------------------------------------------------------
        result = add_reservation_service(name, phone, pax, b_date, b_time)

        if result['status'] == 'success':
            return render_template('booking_success.html', name=name, time=b_time, date=b_date)
        else:
            # Error ตอนบันทึกลง DB (เช่น เน็ตหลุด)
            flash(f"ระบบขัดข้อง: {result['message']}", 'error')
            return redirect('/booking')

    return render_template('booking_form.html')

# 12. API ตรวจสอบการจอง (สำหรับหน้า Admin)
@app.route('/api/check-bookings')
def check_bookings_api():
    # รับค่าวันที่จาก Query String (เช่น ?date=2025-12-23)
    date_str = request.args.get('date')
    
    if not date_str:
        return jsonify([])

    # ดึงข้อมูลจาก DB
    reservations = get_reservations_by_date(date_str)
    
    # 🔥 Logic: จัดกลุ่มข้อมูลเพื่อนับจำนวน
    # ผลลัพธ์ที่อยากได้: {'12:00': 3, '12:10': 1}
    usage_summary = {}
    for r in reservations:
        time_key = r['booking_time'][:5] # ตัดวินาทีออก เอาแค่ 12:00
        if time_key in usage_summary:
            usage_summary[time_key] += 1
        else:
            usage_summary[time_key] = 1
            
    # ส่งกลับเป็น JSON (ข้อมูลดิบที่ไม่มีชื่อคน)
    return jsonify(usage_summary)

# ✅ เพิ่ม Route สำหรับปุ่ม Check-in (กดเมื่อลูกค้าจองเดินมาถึงร้าน)
@app.route('/checkin-reservation/<int:res_id>', methods=['POST'])
def checkin_reservation_route(res_id):
    result = checkin_reservation_service(res_id)
    # เสร็จแล้วรีเฟรชหน้าเดิม
    return redirect(url_for('admin_page'))

# ✅ เพิ่ม Route สำหรับปุ่ม ยกเลิกการจอง
@app.route('/cancel-reservation/<int:res_id>', methods=['POST'])
def cancel_reservation_route(res_id):
    cancel_reservation_service(res_id)
    # เสร็จแล้วรีเฟรชกลับหน้า Admin
    return redirect(url_for('admin_page'))

# 13. ปิดวัน (Close Day)
@app.route('/close-day', methods=['POST'])
def close_day_route():
    result = close_day_service()
    if result['status'] == 'error':
        flash(result['message'], 'error')
    else:
        flash(result['message'], 'success')
    return redirect(url_for('admin_page'))

# 14. หน้า Dashboard (สถิติ)
@app.route('/dashboard')
def dashboard_page():
    # ดึงข้อมูลจาก DB
    stats = get_dashboard_data()
    return render_template('dashboard.html', stats=stats)

# ✅ 15. ปุ่มกดเรียกคิวผ่าน LINE (Admin กด)
@app.route('/admin/notify/<int:queue_id>', methods=['POST'])
def notify_queue_route(queue_id):
    # 1. ดึงข้อมูลคิวเพื่อเอา ID ลูกค้า
    queue = get_queue_by_id(queue_id)
    
    if queue and queue.get('line_user_id'):
        # 2. ข้อความที่จะส่ง
        msg = f"📢 ถึงคิวคุณแล้วครับ! (คิว {queue['queue_type']}-{queue['id']:03d})\nกรุณามาที่หน้าร้านภายใน 5 นาทีครับ"
        
        # 3. ส่ง LINE
        res = send_line_notification(queue['line_user_id'], msg)
        
        if res['status'] == 'success':
            flash(f"✅ ส่ง LINE เรียกคิว {queue['id']} แล้ว", "success")
        else:
            flash(f"❌ ส่งไม่ผ่าน: {res['message']}", "error")
    else:
        flash("⚠️ ลูกค้ารายนี้ไม่ได้เชื่อมต่อ LINE (Walk-in ปกติ)", "warning")

    return redirect(url_for('admin_page'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)