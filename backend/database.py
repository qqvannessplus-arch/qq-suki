import os
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import datetime, timedelta
import pytz
from datetime import datetime, timedelta
from itertools import groupby
import requests

# 1. โหลดค่าจากไฟล์ .env
load_dotenv()

# 2. ตั้งค่าการเชื่อมต่อ
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)
LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
# ==========================================
# ฟังก์ชันจัดการโต๊ะ (Table Management)
# ==========================================

# เพิ่มโต๊ะใหม่
def add_table(name, capacity, zone_type='walk_in'):
    check = supabase.table("tablestime").select(
        "*").eq("table_name", name).execute()
    if len(check.data) > 0:
        return {"status": "error", "message": f"❌ ชื่อโต๊ะ '{name}' มีอยู่แล้วครับ!"}

    data = {
        "table_name": name,
        "capacity": capacity,
        "zone_type": zone_type,
        "status": "empty",
        "final_time": None
    }
    try:
        response = supabase.table("tablestime").insert(data).execute()
        return {"status": "success", "message": f"✅ สร้างโต๊ะ {name} สำเร็จ!", "data": response.data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ลบโต๊ะ
def delete_table(table_id):
    try:
        supabase.table("tablestime").delete().eq("id", table_id).execute()
        return {"status": "success", "message": "✅ ลบโต๊ะเรียบร้อย"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ดึงเฉพาะโต๊ะโซนวอล์คอิน (Walk-in)
def get_walkin_tables():
    try:
        response = supabase.table("tablestime").select("*")\
            .eq("zone_type", "walk_in")\
            .order("table_name")\
            .execute()
        return response.data
    except Exception as e:
        print("❌ Error getting tables:", e)
        return []

# ดึงเฉพาะโต๊ะโซนจอง (Reservation)
def get_reservation_tables():
    """ ดึงเฉพาะโต๊ะโซนจอง (Reservation) """
    try:
        response = supabase.table("tablestime").select("*")\
            .eq("zone_type", "reservation")\
            .order("table_name")\
            .execute()
        return response.data
    except Exception as e:
        print("❌ Error getting reservation tables:", e)
        return []

# ดึงรายการจองวันนี้
def get_today_reservations():
    """ ดึงรายการคนจอง 'เฉพาะวันนี้' ที่ยังรอดำเนินการ (Pending/Confirmed) """
    try:
        today = datetime.now(pytz.timezone(
            'Asia/Bangkok')).strftime('%Y-%m-%d')

        # ดึงข้อมูลมาก่อน (กรองเบื้องต้นแค่ Cancelled)
        response = supabase.table('reservations')\
            .select('*')\
            .eq('booking_date', today)\
            .neq('status', 'cancelled')\
            .order('booking_time')\
            .execute()

        # 🔥 Filter ใน Python: เอาเฉพาะคนสถานะ 'pending' หรือ 'confirmed' เท่านั้น
        # คนที่ 'dining' หรือ 'completed' จะไม่ถูกส่งไปหน้าเว็บ
        waiting_reservations = [
            r for r in response.data
            if r['status'] in ['pending', 'confirmed']
        ]

        return waiting_reservations

    except Exception as e:
        print("❌ Error getting today reservations:", e)
        return []

# ==========================================
# ฟังก์ชันจัดการคิว (Queue Management)
# ==========================================
def add_queue_walkin(pax, line_user_id=None):  # <--- รับตัวแปรเพิ่ม
    """ รับคิวลูกค้า Walk-in (รองรับ LINE ID) """
    try:
        pax_int = int(pax)
        queue_type = 'A' if pax_int <= 4 else 'B'

        data = {
            "pax": pax_int,
            "queue_type": queue_type,
            "status": "waiting",
            "line_user_id": line_user_id  # <--- บันทึกลงฐานข้อมูล
        }

        response = supabase.table("queues").insert(data).execute()

        # เช็คว่ามี data กลับมาไหม (กัน error)
        if response.data:
            return {"status": "success", "data": response.data[0]}
        else:
            return {"status": "error", "message": "Insert failed no data returned"}

    except Exception as e:
        print(f"Error add queue: {e}")
        return {"status": "error", "message": str(e)}

# ดึงคิวตาม ID
def get_queue_by_id(queue_id):
    try:
        response = supabase.table("queues").select(
            "*").eq("id", queue_id).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        return None

# ==========================================
# ฟังก์ชันเปิดโต๊ะ / ปิดโต๊ะ (Service)
# ==========================================


def start_table_service(table_id, duration_minutes):
    """ เริ่มเปิดโต๊ะ: แบบ Fast Flow (ไม่ต้องรอ Check-in) """
    try:
        thai_tz = pytz.timezone('Asia/Bangkok')
        now = datetime.now(thai_tz)
        today_str = now.strftime('%Y-%m-%d')
        finish_time = now + timedelta(minutes=int(duration_minutes))
        finish_time_str = finish_time.strftime('%Y-%m-%d %H:%M:%S')

        # 1. ดึงข้อมูลโต๊ะ
        table_info = supabase.table("tablestime").select(
            "*").eq("id", table_id).execute()
        if not table_info.data:
            return {"status": "error", "message": "ไม่พบโต๊ะนี้"}

        row = table_info.data[0]
        capacity = row['capacity']
        zone_type = row.get('zone_type', '').strip()

        queue_msg = ""

        # =========================================================
        # 🟢 CASE 1: Walk-in (แก้ไขตรงนี้)
        # =========================================================
        if zone_type == 'walk_in':
            target_type = 'A' if capacity <= 4 else 'B'

            queue_res = supabase.table("queues")\
                .select("id, queue_type")\
                .eq("status", "waiting")\
                .eq("queue_type", target_type)\
                .order("id")\
                .limit(1)\
                .execute()

            if queue_res.data:
                q = queue_res.data[0]
                
                # ✅ UPDATE: บันทึก table_id ลงไปในคิวด้วย
                supabase.table("queues").update({
                    "status": "dining",
                    "table_id": table_id ,
                    "started_at": now.isoformat()
                }).eq("id", q['id']).execute()
                
                queue_msg = f" | 🎫 เรียกลูกค้าคิว {q['queue_type']}-{q['id']:03d}"
            else:
                queue_msg = " | (ไม่มีคิว Walk-in)"

        # =========================================================
        # 🟡 CASE 2: Reservation
        # =========================================================
        elif zone_type == 'reservation':

            # ดึงลูกค้าจองวันนี้ ที่ยังไม่ได้กิน
            res_query = supabase.table("reservations")\
                .select("*")\
                .eq("booking_date", today_str)\
                .neq("status", "cancelled")\
                .neq("status", "dining")\
                .neq("status", "completed")\
                .lte("num", capacity)\
                .order("booking_time")\
                .limit(1)\
                .execute()

            if res_query.data:
                target_res = res_query.data[0]

                # เปลี่ยนสถานะเป็น dining
                supabase.table("reservations").update(
                    {"status": "dining"}).eq("id", target_res['id']).execute()

                queue_msg = f" | 📅 เรียกลูกค้าจอง: คุณ{target_res['customer_name']} ({target_res['booking_time'][:5]} น.)"
            else:
                queue_msg = " | (ไม่พบคิวจองที่รออยู่ หรือโต๊ะเล็กไป)"

        else:
            queue_msg = f" | (Zone type ผิด: {zone_type})"

        # 3. อัปเดตสถานะโต๊ะ (เวลาหมด)
        supabase.table("tablestime").update(
            {"status": "busy", "final_time": finish_time_str}).eq("id", table_id).execute()

        return {"status": "success", "message": f"✅ เปิดโต๊ะสำเร็จ{queue_msg}"}

    except Exception as e:
        print(f"Error: {e}")
        return {"status": "error", "message": str(e)}


# ✅ เพิ่มฟังก์ชันนี้กลับมา (สำคัญมาก ไม่งั้น app.py error)
def clear_table_service(table_id):
    """ เช็คบิล: เคลียร์โต๊ะให้ว่าง และจบงานคิวที่นั่งอยู่ """
    try:
        # 1. ✅ หาคิวที่นั่งอยู่โต๊ะนี้ (status='dining') และปิดงานมันซะ
        thai_tz = pytz.timezone('Asia/Bangkok')
        now = datetime.now(thai_tz)

        # อัปเดตคิว: เปลี่ยนเป็น completed และใส่เวลาจบ
        supabase.table("queues").update({
            "status": "completed",
            "completed_at": now.isoformat() # <--- บันทึกเวลาจบจริง
        }).eq("table_id", table_id).eq("status", "dining").execute()

        # 2. ✅ เคลียร์โต๊ะ (โค้ดเดิม)
        data = {
            "status": "empty",
            "final_time": None
        }
        supabase.table("tablestime").update(data).eq("id", table_id).execute()
        
        return {"status": "success", "message": "✅ เช็คบิลเรียบร้อย (บันทึกเวลาจริงแล้ว)"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# เรียงตามลำดับมาก่อน-หลัง


def get_waiting_list():
    """ ดึงคิวที่สถานะเป็น waiting และแปลงเวลาเป็นไทย """
    try:
        # ดึงข้อมูลจาก Supabase (เรียงตาม ID)
        response = supabase.table('queues').select(
            '*').eq('status', 'waiting').order('id').execute()
        data = response.data if response.data else []

        # ✅ ส่วนที่เพิ่ม: วนลูปแปลงเวลา UTC -> ไทย
        bkk_tz = pytz.timezone('Asia/Bangkok')

        for item in data:
            # ได้มาเป็น 2023-12-23T08:32:00+00:00 (UTC)
            raw_time = item.get('created_at')
            if raw_time:
                # 1. แปลง String เป็น Object Time
                dt_utc = datetime.fromisoformat(
                    raw_time.replace('Z', '+00:00'))

                # 2. ย้ายโซนเวลาเป็นไทย
                dt_bkk = dt_utc.astimezone(bkk_tz)

                # 3. ยัดกลับเข้าไปในตัวแปรเดิม (เพื่อให้ HTML ตัวเก่า [11:16] ทำงานได้ถูกต้อง)
                # ผลลัพธ์จะเป็น 2023-12-23T15:32:00+07:00
                item['created_at'] = dt_bkk.isoformat()

        return data

    except Exception as e:
        print(f"Error getting waiting list: {e}")
        return []

# ลูกค้าไม่มา -> กดยกเลิกคิว


def cancel_queue_service(queue_id):
    try:
        # เปลี่ยนสถานะเป็น cancelled (จะไม่ถูกดึงไปใช้งาน)
        supabase.table("queues").update(
            {"status": "cancelled"}).eq("id", queue_id).execute()
        return {"status": "success", "message": f"❌ ยกเลิกคิว {queue_id} แล้ว"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# นับจำนวนคนรอคิวก่อนเรา
def get_waiting_count_before(queue_type, queue_id):
    """ นับจำนวนคนรอคิว (Type เดียวกัน) ที่มาก่อนเรา """
    try:
        response = supabase.table('queues') \
            .select('*', count='exact') \
            .eq('status', 'waiting') \
            .eq('queue_type', queue_type) \
            .lt('id', queue_id) \
            .execute()
        return response.count
    except Exception as e:
        print(f"Error counting waiting queue: {e}")
        return 0

# ดึงโต๊ะตามประเภทคิว


def get_tables_for_type(queue_type):
    """ ดึงโต๊ะทั้งหมดที่รองรับ Queue Type นี้ (A หรือ B) และเป็นโซน Walk-in เท่านั้น """
    try:
        # ✅ แก้ไข: เพิ่ม .eq('zone_type', 'walk_in') เพื่อไม่ให้ไปนับรวมโต๊ะจอง
        query = supabase.table('tablestime').select('*').eq('zone_type', 'walk_in')

        if queue_type == 'A':
            # Type A: โต๊ะเล็ก (<= 4)
            query = query.lte('capacity', 4)
        else:
            # Type B: โต๊ะใหญ่ (> 4)
            query = query.gt('capacity', 4)

        response = query.execute()
        return response.data
    except Exception as e:
        print(f"Error getting tables for type: {e}")
        return []


def add_reservation_service(name, phone, pax, b_date, b_time):
    """ บันทึกการจองลูกค้า """
    data = {
        "customer_name": name,
        "phone": phone,
        "num": int(pax),
        "booking_date": b_date,  # Format: YYYY-MM-DD
        "booking_time": b_time,  # Format: HH:MM
        "status": "pending"     # ค่าเริ่มต้นคือ รอมาถึง
        # table_id ปล่อย NULL ไว้ก่อน ค่อยให้ Admin จัดโต๊ะหน้างาน หรือระบบ Auto ทีหลัง
    }

    try:
        response = supabase.table("reservations").insert(data).execute()
        return {"status": "success", "message": "✅ จองสำเร็จ! กรุณารอที่หน้าร้านตามเวลาที่กำหนด"}
    except Exception as e:
        print(f"Error booking: {e}")
        return {"status": "error", "message": "เกิดข้อผิดพลาดในการจอง"}

# ตรวจสอบความว่างของโต๊ะจอง


def check_availability(pax, booking_date, booking_time):
    """
    ตรวจสอบความว่าง โดยระบุสาเหตุที่ชัดเจนหากไม่ว่าง
    Returns: (bool, message)
    """
    try:
        pax = int(pax)

        # 1. 🕒 ดักจับ: จองเวลาย้อนหลังหรือไม่?
        tz = pytz.timezone('Asia/Bangkok')
        now = datetime.now(tz)

        # แปลงเวลาที่ขอจองเป็น datetime object (ใส่ timezone ให้ตรงกัน)
        booking_dt_str = f"{booking_date} {booking_time}"
        req_start = datetime.strptime(booking_dt_str, "%Y-%m-%d %H:%M")
        req_start = tz.localize(req_start)  # ทำให้เป็น Timezone Aware

        if req_start < now:
            return False, f"⚠️ ไม่สามารถจองเวลาย้อนหลังได้ครับ (เวลาปัจจุบัน: {now.strftime('%H:%M')})"

        # 2. 🪑 ดักจับ: มีโต๊ะขนาดที่รองรับจำนวนคนนี้ไหม?
        # หาโต๊ะโซนจอง ที่นั่งพอ (capacity >= pax)
        candidate_tables = supabase.table("tablestime")\
            .select("id, capacity")\
            .eq("zone_type", "reservation")\
            .gte("capacity", pax)\
            .execute().data

        if not candidate_tables:
            # ลองหาโต๊ะใหญ่สุดที่มี เพื่อแจ้งลูกค้า
            max_cap_res = supabase.table("tablestime")\
                .select("capacity")\
                .eq("zone_type", "reservation")\
                .order("capacity", desc=True)\
                .limit(1).execute().data

            max_pax = max_cap_res[0]['capacity'] if max_cap_res else 0
            return False, f"❌ ไม่มีโต๊ะที่รองรับ {pax} ท่านได้ (โซนจองรับสูงสุด {max_pax} ท่าน/โต๊ะ)"

        # 3. 💥 ดักจับ: ช่วงเวลานั้นเต็มหรือยัง (Time Overlap)
        req_end = req_start + timedelta(minutes=105)  # กฎ 105 นาที

        # ดึงการจองของวันนั้นมาเช็ค
        todays_reservations = supabase.table("reservations")\
            .select("booking_time, num")\
            .eq("booking_date", booking_date)\
            .neq("status", "cancelled")\
            .execute().data

        busy_count = 0
        collision_details = []  # เก็บรายละเอียดว่าชนกับใครบ้าง (ถ้าอยาก debug)

        for res in todays_reservations:
            # เวลาของคนอื่นใน DB
            other_start_str = f"{booking_date} {res['booking_time']}"
            other_start = datetime.strptime(
                other_start_str, "%Y-%m-%d %H:%M:%S")  # Supabase มักคืน hh:mm:ss
            other_start = tz.localize(other_start)
            other_end = other_start + timedelta(minutes=105)

            # เช็คการซ้อนทับ: (StartA < EndB) และ (StartB < EndA)
            if req_start < other_end and other_start < req_end:
                # เช็คละเอียดอีกนิด: คนที่จองไว้ ใช้โต๊ะกลุ่มเดียวกับเราไหม?
                # (สมมติง่ายๆ ว่าถ้าเขาจองจำนวนคนใกล้เคียงกัน ถือว่าแย่งโต๊ะกัน)
                # ตรงนี้ Logic แบบง่ายคือนับรวมไปก่อน
                busy_count += 1

        # คำนวณ: โต๊ะที่มีทั้งหมด - โต๊ะที่ถูกจองเวลานั้น = โต๊ะเหลือ
        total_suitable_tables = len(candidate_tables)
        available_tables = total_suitable_tables - busy_count

        if available_tables <= 0:
            return False, f"⚠️ เต็มแล้ว: รอบเวลา {booking_time} น. สำหรับ {pax} ท่าน มีคิวจองเต็มหมดแล้วครับ"

        # ✅ ผ่านทุกด่าน
        return True, "ว่างจองได้"

    except Exception as e:
        print(f"Availability Check Error: {e}")
        return False, "เกิดข้อผิดพลาดในการตรวจสอบระบบ (System Error)"

# ดึงรายการจองตามวันที่


def get_reservations_by_date(date_str):
    """ ดึงรายการจองของวันที่ระบุ เพื่อไปแสดงหน้าเว็บ (Public View) """
    try:
        # ดึงเฉพาะเวลา (booking_time) และสถานะ
        response = supabase.table("reservations")\
            .select("booking_time, status")\
            .eq("booking_date", date_str)\
            .neq("status", "cancelled")\
            .execute()
        return response.data
    except Exception as e:
        print(f"Error getting reservations: {e}")
        return []

# เช็คอินลูกค้าที่จองมาแล้ว


def checkin_reservation_service(res_id):
    try:
        # เปลี่ยนสถานะเป็น confirmed (แปลว่ามายืนรอหน้าร้านแล้ว พร้อมเข้าโต๊ะ)
        supabase.table("reservations").update(
            {"status": "confirmed"}).eq("id", res_id).execute()
        return {"status": "success", "message": "✅ เช็คอินสำเร็จ ลูกค้าพร้อมเข้าโต๊ะครับ"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ยกเลิกการจอง


def cancel_reservation_service(res_id):
    """ ยกเลิกการจอง (เปลี่ยนสถานะเป็น cancelled) """
    try:
        # อัปเดตสถานะเป็น cancelled เพื่อไม่ให้โชว์ในรายการรอ และคืนสิทธิ์โต๊ะให้คนอื่น
        supabase.table("reservations").update(
            {"status": "cancelled"}).eq("id", res_id).execute()
        return {"status": "success", "message": "❌ ยกเลิกการจองเรียบร้อย"}
    except Exception as e:
        print(f"Error cancelling reservation: {e}")
        return {"status": "error", "message": str(e)}

# ปิดยอดวัน (ย้ายข้อมูลคิวไป History แล้วรีเซ็ตเลขคิว)


def close_day_service():
    try:
        # 1. ดึงข้อมูลปัจจุบัน
        response = supabase.table("queues").select("*").execute()
        current_queues = response.data

        # 2. ย้ายไป History (ถ้ามีข้อมูล)
        if current_queues:
            history_data = []
            for q in current_queues:
                new_item = q.copy()
                if 'id' in new_item:
                    del new_item['id']  # ลบ ID เก่าทิ้ง
                history_data.append(new_item)

            # บันทึกเข้า history
            supabase.table("queues_history").insert(history_data).execute()

        # 3. ล้างตารางหลัก (เรียก SQL ที่เพิ่งสร้าง)
        supabase.rpc("reset_queues").execute()

        return {"status": "success", "message": "✅ ปิดยอดและรีเซ็ตคิวเรียบร้อย"}

    except Exception as e:
        print(f"Error: {e}")
        return {"status": "error", "message": str(e)}

# ดึงข้อมูลสรุปยอดสำหรับ Dashboard
def get_dashboard_data():
    """ ดึงข้อมูลสรุปยอดเพื่อแสดงบน Dashboard """
    stats = {
        'total_pax': 0,
        'total_queues': 0,
        'type_a': 0,
        'type_b': 0,
        'daily_stats': {}
    }

    try:
        # 1. ดึงข้อมูลจากตาราง queues (ลูกค้าปัจจุบัน)
        q_res = supabase.table('queues').select('*').execute()
        queues = q_res.data if q_res.data else []

        # 2. (Optional) ดึงข้อมูลจาก queues_history ด้วย (ลูกค้าเก่าที่ปิดยอดไปแล้ว)
        # ถ้าอยากดูยอดรวมทั้งหมดตั้งแต่อดีต ให้เปิดคอมเมนต์บรรทัดล่างนี้
        h_res = supabase.table('queues_history').select('*').execute()
        queues += h_res.data if h_res.data else []

        # 3. ดึงข้อมูล Reservation
        r_res = supabase.table('reservations').select(
            '*').neq('status', 'cancelled').execute()
        reservations = r_res.data if r_res.data else []

        # --- คำนวณยอด Walk-in ---
        for q in queues:
            # ข้ามรายการที่ยกเลิก
            if q.get('status') == 'cancelled':
                continue

            stats['total_pax'] += q.get('pax', 0)
            stats['total_queues'] += 1

            if q.get('queue_type') == 'A':
                stats['type_a'] += 1
            elif q.get('queue_type') == 'B':
                stats['type_b'] += 1

            # นับยอดรายวัน
            created_at = q.get('created_at')
            if created_at:
                # แปลงเวลาให้เป็นวันที่ไทย
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                date_str = dt.astimezone(pytz.timezone(
                    'Asia/Bangkok')).strftime('%Y-%m-%d')

                stats['daily_stats'][date_str] = stats['daily_stats'].get(
                    date_str, 0) + 1

        # --- คำนวณยอด Reservation ---
        for r in reservations:
            stats['total_pax'] += r.get('num', 0)

            # นับยอดรายวันของการจอง (ใช้วันที่จอง)
            b_date = r.get('booking_date')
            if b_date:
                # นับรวมเป็น 1 Transaction หรือจะนับแยกก็ได้
                stats['daily_stats'][b_date] = stats['daily_stats'].get(
                    b_date, 0) + 1

        # เรียงวันที่ในกราฟ
        stats['daily_stats'] = dict(sorted(stats['daily_stats'].items()))

        return stats

    except Exception as e:
        print(f"Dashboard Error: {e}")
        return stats  # ส่งค่าว่าง (0) กลับไปกันหน้าเว็บพัง

def send_line_notification(user_id, message_text):
    """ ส่งข้อความหาลูกค้าผ่าน LINE Messaging API """
    if not user_id:
        return {"status": "error", "message": "No User ID"}
        
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    data = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": message_text
            }
        ]
    }
    try:
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 200:
            return {"status": "success", "message": "ส่ง LINE สำเร็จ"}
        else:
            print(f"LINE Error: {response.text}")
            return {"status": "error", "message": f"LINE API Error: {response.text}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ดึงเวลา Final Time ของโต๊ะ
def get_table_finish_time(table_id):
    """ ดึงเวลา Final Time ของโต๊ะ """
    try:
        response = supabase.table("tablestime").select("final_time").eq("id", table_id).execute()
        if response.data:
            return response.data[0].get('final_time')
        return None
    except Exception as e:
        print(f"Error getting table time: {e}")
        return None

# ดึงเวลาเฉลี่ยจากข้อมูลจริง
def get_real_average_cycle_time(default_cycle=80):
    """
    คำนวณเวลาเฉลี่ยจากข้อมูลจริง (Real Data)
    สูตร: หาค่าเฉลี่ยของ (completed_at - started_at) ในวันนี้
    """
    try:
        # ดึงคิวที่จบงานแล้ว และมีเวลาครบ
        response = supabase.table('queues')\
            .select('started_at, completed_at')\
            .eq('status', 'completed')\
            .neq('started_at', 'null')\
            .neq('completed_at', 'null')\
            .execute()
        
        finished_queues = response.data
        
        # ถ้าไม่มีข้อมูลเลย ให้ใช้ค่า Default ไปก่อน
        if not finished_queues:
            return default_cycle

        total_minutes = 0
        count = 0

        for q in finished_queues:
            # แปลง String -> Datetime Object (รองรับ Timezone)
            start = datetime.fromisoformat(q['started_at'].replace('Z', '+00:00'))
            end = datetime.fromisoformat(q['completed_at'].replace('Z', '+00:00'))
            
            # หาผลต่างเป็นนาที
            duration = (end - start).total_seconds() / 60
            
            # กรองข้อมูลขยะ (กันค่าเพี้ยน เช่น กดผิด)
            if 5 < duration < 300: 
                total_minutes += duration
                count += 1
        
        if count == 0:
            return default_cycle

        # หาค่าเฉลี่ย
        avg_time = int(total_minutes / count)
        
        # คืนค่ากลับไป (แต่ไม่ให้ต่ำกว่า 45 นาที กันระบบรวน)
        return max(avg_time, 45)

    except Exception as e:
        print(f"Error calculating real avg time: {e}")
        return default_cycle