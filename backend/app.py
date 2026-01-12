from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import os
from dotenv import load_dotenv
import heapq
from datetime import datetime, timedelta
from itertools import groupby
import pytz   
from database import (
    get_all_branches,
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
    get_real_average_cycle_time,
    get_reservation_by_phone_and_name,
    create_admin,
    login_admin,
    get_branches_for_customer,
    get_branch_name,
    get_pure_waiting_count
)

# ---------------------------------------------------------
# Config & Setup (ตั้งค่าพื้นฐาน)
load_dotenv()
current_dir = os.path.dirname(os.path.abspath(__file__))
frontend_dir = os.path.join(current_dir, '../frontend')

app = Flask(__name__, template_folder=frontend_dir, static_folder=frontend_dir)
app.secret_key = "SECRET_KEY_FOR_SESSION"
SHOP_SECRET_KEY = os.environ.get("SHOP_SECRET_KEY")

# =========================================================
# 🔐 0. ระบบ Authentication (Login/Register)
# =========================================================

# [หน้า Login] หน้าเข้าสู่ระบบ Admin
@app.route('/login', methods=['GET', 'POST'])
def login():
    # ถ้าล็อกอินอยู่แล้ว ดีดไปหน้าแรก
    if 'admin_user' in session:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        result = login_admin(username, password)

        if result['status'] == 'success':
            user = result['user']
            
            # ✅ เก็บ Session ครบชุด
            session['admin_user'] = user['username']
            session['admin_id'] = user['id']
            session['branch_id'] = user['branch_id'] # <--- จำสาขาไว้เลย
            
            # ไปดึงชื่อสาขามาเก็บไว้ด้วย (เพื่อความสวยงามตอนแสดงผล)
            # (ขี้เกียจ query ใหม่ ให้มันไปหาเอาหน้า admin ก็ได้ หรือจะ query ตรงนี้ก็ได้)
            # สมมติง่ายๆ คือ redirect ไปเลย เดี๋ยวหน้า admin มันจัดการต่อ
            
            return redirect(url_for('admin_page')) # <--- 🚀 ไป Dashboard เลย ไม่ต้องเลือกสาขาแล้ว
        else:
            flash(result['message'], 'error')
            return redirect(url_for('login'))

    # ✅ ส่งรายชื่อสาขาไปให้ Dropdown ตอนสมัครสมาชิกเลือก
    branches = get_all_branches()
    return render_template('auth/login.html', branches=branches)

# [Action] สมัครสมาชิก Admin
@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username')
    password = request.form.get('password')
    confirm_pw = request.form.get('confirm_password')
    branch_id = request.form.get('branch_id')
    secret_key = request.form.get('secret_key')

    # 1. ตรวจรหัสลับร้าน
    if secret_key != SHOP_SECRET_KEY:
        flash("❌ รหัสลับร้านไม่ถูกต้อง! (คุณไม่ใช่พนักงาน)", 'error')
        return redirect(url_for('login'))

    # 2. ตรวจรหัสผ่าน
    if password != confirm_pw:
        flash("❌ รหัสผ่านยืนยันไม่ตรงกัน", 'error')
        return redirect(url_for('login'))
    
    # 3. ตรวจสาขา
    if not branch_id:
        flash("❌ กรุณาเลือกสาขาที่ประจำการ", 'error')
        return redirect(url_for('login'))

    # 4. สร้าง User
    result = create_admin(username, password, branch_id)

    if result['status'] == 'success':
        flash(result['message'], 'success')
    else:
        flash(result['message'], 'error')

    return redirect(url_for('login'))

# [Action] ออกจากระบบ Admin
@app.route('/logout')
def logout():
    session.clear() # ล้างทุกอย่าง (รวมถึง branch_id ด้วย)
    flash("ออกจากระบบเรียบร้อยแล้ว", "success")
    return redirect(url_for('login'))

# =========================================================
# 📍 1. แก้ไขหน้าเลือกสาขา (Protect Route)
# =========================================================
# [หน้าเลือกสาขา] หน้าแรกหลังล็อกอิน (ถ้ายังไม่มีสาขาใน session)
@app.route('/')
def home():
    # ถ้ายังไม่ล็อกอิน -> ไป Login
    if 'admin_user' not in session:
        return redirect(url_for('login'))
    
    # ถ้าล็อกอินแล้ว -> พุ่งไป Admin Dashboard เลย (เพราะมี branch_id ใน session แล้ว)
    return redirect(url_for('admin_page'))

# Logic: รับค่า branch_id จากฟอร์ม -> เก็บลง Session -> พาไปหน้า Admin
# [Action] ตั้งค่าสาขาที่จะทำงาน
@app.route('/set-branch', methods=['POST'])
def set_branch():
    branch_id = request.form.get('branch_id')
    branch_name = request.form.get('branch_name')
    
    # จำค่าสาขาไว้ใน Session (Browser Memory)
    session['branch_id'] = int(branch_id)
    session['branch_name'] = branch_name
    
    print(f"✅ Admin Working on: {branch_name} (ID: {branch_id})")
    
    return redirect(url_for('admin_page'))

# [Action] ออกจากระบบสาขา (Logout Branch)
# Logic: ลบ Session ทิ้ง -> ดีดกลับไปหน้าเลือกสาขา
@app.route('/logout-branch')
def logout_branch():
    session.pop('branch_id', None)
    session.pop('branch_name', None)
    return redirect(url_for('home'))

# =========================================================
# 👔 2. ส่วน Admin Dashboard (จัดการร้าน)
# =========================================================

# [หน้า Admin] หน้าจอหลักสำหรับผู้จัดการร้าน
# Logic: เช็ค Session -> ดึงข้อมูลโต๊ะ/คิว เฉพาะสาขานั้นๆ -> แสดงผล
@app.route('/admin')
def admin_page():
    # ถ้าไม่มี branch_id แปลว่ายังไม่ล็อกอิน ให้กลับไปหน้า login
    if 'branch_id' not in session:
        return redirect(url_for('login'))

    branch_id = session['branch_id']

    # ✅ 1. เรียกฟังก์ชันดึงชื่อสาขาจาก DB
    branch_name = get_branch_name(branch_id)

    # 2. ดึงข้อมูลอื่นๆ
    walkin_tables = get_walkin_tables(branch_id)
    reserve_tables = get_reservation_tables(branch_id)
    waiting_list = get_waiting_list(branch_id)
    reservations = get_today_reservations(branch_id)

    # 3. ส่งข้อมูลไปหน้าเว็บ (แก้ตรง current_branch_name ให้ใช้ตัวแปรที่ดึงมา)
    return render_template('admin/admin.html', 
                           walkin_tables=walkin_tables, 
                           reservation_tables=reserve_tables,
                           waiting_list=waiting_list,
                           reservations=reservations,
                           current_branch_name=branch_name,
                           session=session)

# [Action] เพิ่มโต๊ะใหม่
# Logic: รับค่าจากฟอร์ม -> ส่ง branch_id ไปบันทึกลง DB
@app.route('/add-table', methods=['POST'])
def submit_table():
    if 'branch_id' not in session: return redirect('/')
    
    name = request.form['table_name']
    capacity = int(request.form['capacity'])
    zone = request.form['zone_type']

    result = add_table(session['branch_id'], name, capacity, zone)

    if result['status'] == 'error':
        return f"<h1>⚠️ เกิดข้อผิดพลาด</h1><h3>{result['message']}</h3><a href='/admin'>กลับไปแก้ไข</a>"

    return redirect(url_for('admin_page'))

# [Action] ลบโต๊ะ
# Logic: ลบโต๊ะตาม ID ที่ระบุ
@app.route('/delete-table/<int:table_id>', methods=['POST'])
def delete_table_route(table_id):
    # 1. รับผลลัพธ์จาก Database มาเก็บไว้ในตัวแปร result
    result = delete_table(table_id)
    
    # 2. เช็คสถานะ
    if result['status'] == 'error':
        # ถ้าพัง: ส่งข้อความ Error ไปแจ้งเตือนหน้าเว็บ
        flash(f"⚠️ ลบไม่ได้ครับ: {result['message']}", 'error')
    else:
        # ถ้าผ่าน: แจ้งเตือนสีเขียว
        flash(result['message'], 'success')

    return redirect(url_for('admin_page'))

# [Action] เปิดโต๊ะ (Start Service)
# Logic: หาคิวที่รออยู่ของสาขานั้น -> เอาลงโต๊ะ -> เปลี่ยนสถานะเป็น Dining
@app.route('/start-table/<int:table_id>', methods=['POST'])
def start_table_route(table_id):
    if 'branch_id' not in session: return redirect('/')

    duration = request.form.get('duration') 
    if not duration: duration = 90
        
    result = start_table_service(session['branch_id'], table_id, duration)
    
    if result['status'] == 'error':
        flash(result['message'], 'error')
    
    return redirect(url_for('admin_page'))

# [Action] เช็คบิล/เคลียร์โต๊ะ (Clear Table)
# Logic: เปลี่ยนสถานะโต๊ะเป็น Empty -> จบคิว (Completed)
@app.route('/clear-table/<int:table_id>', methods=['POST'])
def clear_table_route(table_id):
    clear_table_service(table_id)
    return redirect(url_for('admin_page'))

# [Action] ปิดยอดวัน (Close Day)
# Logic: ย้ายข้อมูลคิวลง History -> รีเซ็ตตารางคิว (เฉพาะสาขานั้น)
@app.route('/close-day', methods=['POST'])
def close_day_route():
    if 'branch_id' not in session: return redirect('/')

    result = close_day_service(session['branch_id'])
    
    if result['status'] == 'error':
        flash(result['message'], 'error')
    else:
        flash(result['message'], 'success')
    return redirect(url_for('admin_page'))

# =========================================================
# 🚶‍♂️ 3. ส่วนลูกค้า Walk-in (หน้าร้าน)
# =========================================================

# [หน้าลูกค้า] ฟอร์มกดรับบัตรคิว
# Logic: รับ branch_id จาก URL -> แสดงฟอร์ม
@app.route('/walkin')
def walkin_index():
    branch_id = request.args.get('branch_id')
    
    # กรณี Admin กดเทสต์เอง ให้ใช้ branch จาก session
    if not branch_id and 'branch_id' in session:
        branch_id = session['branch_id']
    
    if not branch_id:
        return "<h1>⚠️ Error: ไม่ระบุสาขา (Missing branch_id)</h1>"

    return render_template('walkin/walkin_form.html', branch_id=branch_id)

# [Action] บันทึกคิว (Submit Queue)
# Logic: รับข้อมูลลูกค้า -> บันทึกลง DB ตามสาขา -> Redirect ไปหน้าบัตรคิว
@app.route('/walkin/submit', methods=['POST'])
def walkin_submit():
    pax = request.form.get('pax')
    line_user_id = request.form.get('line_user_id')
    branch_id = request.form.get('branch_id') 

    if not pax or not branch_id:
        return "❌ Error: ข้อมูลไม่ครบ", 400

    result = add_queue_walkin(int(branch_id), pax, line_user_id)
    
    if result['status'] == 'success':
        queue_id = result['data']['id']
        return redirect(url_for('my_queue_status', queue_id=queue_id, branch_id=branch_id))
    
    return f"<h1>⚠️ Database Error</h1><p>{result.get('message')}</p>", 400

# [หน้าลูกค้า] แสดงสถานะบัตรคิว (Real-time Status)
# Logic: คำนวณเวลา (Heap Queue Algorithm) -> แสดงเวลารอ
@app.route('/queue/<int:queue_id>')
def my_queue_status(queue_id):
    branch_id = request.args.get('branch_id')
    if not branch_id: branch_id = 1 # Fallback

    my_queue = get_queue_by_id(queue_id)

    # ถ้าคิวโดนยกเลิก หรือเสร็จแล้ว -> กลับหน้าจอง
    if not my_queue or my_queue['status'] in ['cancelled', 'completed']:
        return redirect(url_for('walkin_index', branch_id=branch_id, reset=1))

    # ถ้ากำลังกินอยู่ -> โชว์เวลาหมด
    if my_queue['status'] == 'dining':
        finish_time_display = "ไม่ระบุ"
        if my_queue.get('table_id'):
            raw_time = get_table_finish_time(my_queue['table_id'])
            if raw_time:
                tz = pytz.timezone('Asia/Bangkok')
                try:
                    ft = datetime.fromisoformat(raw_time.replace('Z', '+00:00')).astimezone(tz)
                    finish_time_display = ft.strftime('%H:%M น.')
                except: pass
        return render_template('walkin/walkin_status.html', queue=my_queue, is_dining=True, finish_time=finish_time_display, estimated_time="Served", time_diff=0)

    # 1. ตัวเลขสำหรับโชว์หน้าเว็บ (นับรวม Waiting + Dining)
    my_position_index = get_waiting_count_before(branch_id, my_queue['queue_type'], queue_id)
    my_queue['position_wait'] = my_position_index

    # ✅ 2. ตัวเลขสำหรับคำนวณเวลา (นับเฉพาะ Waiting) เพื่อไม่ให้เวลาเบิ้ล
    math_position_index = get_pure_waiting_count(branch_id, my_queue['queue_type'], queue_id)

    target_tables = get_tables_for_type(branch_id, my_queue['queue_type'])
    
    if not target_tables:
        return render_template('walkin/walkin_status.html', 
                               queue=my_queue, 
                               estimated_time="N/A", 
                               time_diff=0,
                               no_tables=True)

    # --- ส่วนคำนวณเวลา (Time Estimation) ---
    timezone = pytz.timezone('Asia/Bangkok')
    now = datetime.now(timezone)

    DEFAULT_CYCLE = 80
    real_avg_time = get_real_average_cycle_time(branch_id, default_cycle=DEFAULT_CYCLE)
    REALISTIC_CYCLE = max(real_avg_time, 45)
    MAX_CYCLE = 90

    timeline_max = []
    for t in target_tables:
        if t['status'] == 'empty':
            heapq.heappush(timeline_max, now)
        else:
            if t.get('final_time'):
                ft_str = t['final_time'].replace('Z', '+00:00')
                ft = datetime.fromisoformat(ft_str).astimezone(timezone)
                heapq.heappush(timeline_max, ft)
            else:
                fallback = now + timedelta(minutes=DEFAULT_CYCLE)
                heapq.heappush(timeline_max, fallback)

    my_time_max = now
    
    # 🔴 แก้ตรงนี้: ใช้ math_position_index ในการวนลูปคำนวณเวลา
    for i in range(math_position_index + 1):
        earliest_free_max = heapq.heappop(timeline_max)
        
        if i == math_position_index:
            my_time_max = earliest_free_max
        else:
            next_free_max = earliest_free_max + timedelta(minutes=MAX_CYCLE)
            heapq.heappush(timeline_max, next_free_max)

    diff_seconds = (my_time_max - now).total_seconds()
    wait_min_max = int(diff_seconds / 60)

    # 🛑 ดักจับ: ถ้าติดลบ ให้เป็น 0 (แปลว่าถึงเวลาแล้ว หรือรอสักครู่)
    if wait_min_max < 0:
        wait_min_max = 0

    return render_template(
        'walkin/walkin_status.html', 
        queue=my_queue, 
        estimated_time=(my_time_max + timedelta(minutes=5)).strftime('%H:%M น.'), 
        time_diff=wait_min_max
    )

# [Action] ยกเลิกคิว (Cancel Queue)
# Logic: เปลี่ยนสถานะคิวเป็น cancelled
# ✅ UPDATE: ถ้าลูกค้ากดเอง -> ส่ง reset=1 กลับไปลบความจำเครื่อง
@app.route('/cancel-queue/<int:queue_id>', methods=['POST'])
def cancel_queue_route(queue_id):
    cancel_queue_service(queue_id)
    
    source = request.args.get('source')
    branch_id = request.args.get('branch_id', 1)
    
    if source == 'walkin':
        # ✅ ลูกค้ากดเอง -> ส่ง reset=1 ไปหน้า Walk-in
        # หน้า Walk-in จะมี JS (initSystem) คอยดักจับ reset=1 เพื่อลบ LocalStorage
        return redirect(url_for('walkin_index', branch_id=branch_id, reset=1))
    
    # Admin กด -> กลับหน้า Admin ปกติ
    return redirect(url_for('admin_page'))

# =========================================================
# 📅 4. ส่วนการจองล่วงหน้า (Booking)
# =========================================================

# [หน้าลูกค้า] ฟอร์มจองล่วงหน้า
@app.route('/booking', methods=['GET', 'POST'])
def booking_page():
    branch_id = request.args.get('branch_id')
    if not branch_id: branch_id = 1 

    if request.method == 'POST':
        name = request.form.get('customer_name')
        phone = request.form.get('phone')
        pax = request.form.get('pax')
        b_date = request.form.get('booking_date')
        b_time = request.form.get('booking_time')
        branch_id_form = request.form.get('branch_id') 

        # เช็คว่าโต๊ะว่างไหม (เฉพาะสาขานั้น)
        is_available, fail_reason = check_availability(branch_id_form, pax, b_date, b_time)
        
        if not is_available:
            flash(fail_reason, 'error') 
            return redirect(url_for('booking_page', branch_id=branch_id_form))

        # บันทึกการจอง
        result = add_reservation_service(branch_id_form, name, phone, pax, b_date, b_time)

        if result['status'] == 'success':
            return render_template('booking/booking_success.html', name=name, time=b_time, date=b_date, pax=pax)
        else:
            flash(f"ระบบขัดข้อง: {result['message']}", 'error')
            return redirect(url_for('booking_page', branch_id=branch_id_form))

    return render_template('booking/booking_form.html', branch_id=branch_id)

# [API] เช็ค Slot เวลาที่ว่าง (ใช้ AJAX เรียก)
@app.route('/api/check-bookings')
def check_bookings_api():
    date_str = request.args.get('date')
    branch_id = request.args.get('branch_id', 1)
    
    if not date_str: return jsonify([])

    reservations = get_reservations_by_date(branch_id, date_str)
    
    usage_summary = {}
    for r in reservations:
        time_key = r['booking_time'][:5]
        usage_summary[time_key] = usage_summary.get(time_key, 0) + 1
            
    return jsonify(usage_summary)

# [Action] Admin เช็คอินลูกค้าจอง (เปลี่ยนสถานะเป็น Confirmed)
@app.route('/checkin-reservation/<int:res_id>', methods=['POST'])
def checkin_reservation_route(res_id):
    checkin_reservation_service(res_id)
    return redirect(url_for('admin_page'))

# [Action] Admin ยกเลิกการจอง
@app.route('/cancel-reservation/<int:res_id>', methods=['POST'])
def cancel_reservation_route(res_id):
    cancel_reservation_service(res_id)
    return redirect(url_for('admin_page'))

@app.route('/api/my-booking', methods=['POST'])
def my_booking_api():
    data = request.json
    phone = data.get('phone')
    name = data.get('name')  # <--- รับชื่อเพิ่ม
    branch_id = data.get('branch_id')
    
    # ต้องกรอกทั้งคู่
    if not phone or not branch_id or not name:
        return jsonify({'found': False, 'message': 'กรุณากรอกเบอร์โทรและชื่อผู้จอง'})

    # ส่งไปเช็คทั้งคู่
    reservation = get_reservation_by_phone_and_name(branch_id, phone, name)
    
    if reservation:
        return jsonify({'found': True, 'data': reservation})
    else:
        return jsonify({'found': False, 'message': 'ไม่พบข้อมูล (เบอร์โทรหรือชื่อไม่ถูกต้อง)'})

# =========================================================
# 📊 5. ส่วนเสริม (Dashboard & Notification)
# =========================================================

# [หน้า Dashboard] สรุปสถิติ
@app.route('/dashboard')
def dashboard_page():
    if 'branch_id' not in session: return redirect('/')
    
    stats = get_dashboard_data(session['branch_id'])
    return render_template('admin/dashboard.html', stats=stats)

# [Action] ส่ง LINE แจ้งเตือนลูกค้า
@app.route('/admin/notify/<int:queue_id>', methods=['POST'])
def notify_queue_route(queue_id):
    queue = get_queue_by_id(queue_id)
    
    if queue and queue.get('line_user_id'):
        msg = f"📢 ถึงคิวคุณแล้วครับ! (คิว {queue['queue_type']}-{queue['id']:03d})\nกรุณามาที่หน้าร้านภายใน 5 นาทีครับ"
        res = send_line_notification(queue['line_user_id'], msg)
        
        if res['status'] == 'success':
            flash(f"✅ ส่ง LINE เรียกคิว {queue['id']} แล้ว", "success")
        else:
            flash(f"❌ ส่งไม่ผ่าน: {res['message']}", "error")
    else:
        flash("⚠️ ลูกค้ารายนี้ไม่ได้เชื่อมต่อ LINE (Walk-in ปกติ)", "warning")

    return redirect(url_for('admin_page'))

# [หน้าลูกค้า] หน้ารวมสาขาสำหรับลูกค้า (ดูคิว + แผนที่)
@app.route('/hub')
def customer_hub():
    """ หน้ารวมสาขาสำหรับลูกค้า (ดูคิว + แผนที่) """
    branches = get_branches_for_customer()
    return render_template('customer/customer_hub.html', branches=branches)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)