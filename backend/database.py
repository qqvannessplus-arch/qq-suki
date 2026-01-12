import os
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import datetime, timedelta
import pytz
from datetime import datetime, timedelta
from itertools import groupby
import requests
from werkzeug.security import generate_password_hash, check_password_hash

# 1. โหลดค่าจากไฟล์ .env
load_dotenv()

# 2. ตั้งค่าการเชื่อมต่อ
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)
LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")

# ==========================================
# 🆕 ฟังก์ชันเกี่ยวกับสาขา (Branch)
# ==========================================
def get_all_branches():
    """ ดึงรายชื่อสาขาทั้งหมดที่มีสถานะ open หรือ busy """
    try:
        response = supabase.table("branches").select("*").neq("status", "closed").order("id").execute()
        return response.data
    except Exception as e:
        print("❌ Error getting branches:", e)
        return []

# ==========================================
# ฟังก์ชันจัดการโต๊ะ (Table Management)
# ==========================================

# เพิ่มโต๊ะใหม่ (เพิ่ม branch_id)
def add_table(branch_id, name, capacity, zone_type='walk_in'):
    check = supabase.table("tablestime").select(
        "*").eq("branch_id", branch_id).eq("table_name", name).execute() # <-- เพิ่มเช็คสาขา
    if len(check.data) > 0:
        return {"status": "error", "message": f"❌ ชื่อโต๊ะ '{name}' มีอยู่แล้วครับ!"}

    data = {
        "branch_id": branch_id, # <-- บันทึกสาขา
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

# ลบโต๊ะ (ใช้ ID เดิมได้เลย ไม่ต้องแก้)
def delete_table(table_id):
    try:
        # 🟢 STEP 1: ไปบอกตารางประวัติ (History) ว่าไม่ต้องจำโต๊ะนี้แล้ว (ให้เป็น NULL)
        # (เพื่อให้ Foreign Key ไม่ด่าเรา)
        try:
            supabase.table("queues_history").update({"table_id": None}).eq("table_id", table_id).execute()
        except:
            pass # ถ้าไม่มีประวัติก็ข้ามไป

        # 🟢 STEP 2: ไปบอกตารางคิวปัจจุบัน (Queues) ด้วย (เผื่อมีค้าง)
        try:
            supabase.table("queues").update({"table_id": None}).eq("table_id", table_id).execute()
        except:
            pass

        # 🟢 STEP 3: พอมันไม่มีใครจำแล้ว ก็ลบโต๊ะทิ้งได้เลย
        supabase.table("tablestime").delete().eq("id", table_id).execute()
        
        return {"status": "success", "message": "✅ ลบโต๊ะเรียบร้อย (เคลียร์ประวัติให้แล้ว)"}

    except Exception as e:
        # ถ้ายังพังอีก ให้ส่ง Error กลับไปดู
        return {"status": "error", "message": str(e)}

# ดึงเฉพาะโต๊ะโซนวอล์คอิน (Walk-in) (เพิ่ม branch_id)
def get_walkin_tables(branch_id):
    try:
        response = supabase.table("tablestime").select("*")\
            .eq("branch_id", branch_id)\
            .eq("zone_type", "walk_in")\
            .order("table_name")\
            .execute() # <-- เพิ่ม eq branch_id
        return response.data
    except Exception as e:
        print("❌ Error getting tables:", e)
        return []

# ดึงเฉพาะโต๊ะโซนจอง (Reservation) (เพิ่ม branch_id)
def get_reservation_tables(branch_id):
    """ ดึงเฉพาะโต๊ะโซนจอง (Reservation) """
    try:
        response = supabase.table("tablestime").select("*")\
            .eq("branch_id", branch_id)\
            .eq("zone_type", "reservation")\
            .order("table_name")\
            .execute() # <-- เพิ่ม eq branch_id
        return response.data
    except Exception as e:
        print("❌ Error getting reservation tables:", e)
        return []

# ดึงรายการจองวันนี้ (เพิ่ม branch_id)
def get_today_reservations(branch_id):
    try:
        today = datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%Y-%m-%d')

        response = supabase.table('reservations')\
            .select('*')\
            .eq("branch_id", branch_id)\
            .gte('booking_date', today)\
            .neq('status', 'cancelled')\
            .order('booking_date', desc=False)\
            .order('booking_time', desc=False)\
            .execute() 

        # (ส่วนกรอง status pending/confirmed เหมือนเดิม)
        waiting_reservations = [
            r for r in response.data
            if r['status'] in ['pending', 'confirmed']
        ]
        return waiting_reservations

    except Exception as e:
        print("❌ Error:", e)
        return []

# ==========================================
# ฟังก์ชันจัดการคิว (Queue Management)
def add_queue_walkin(branch_id, pax, line_user_id=None):
    try:
        pax_int = int(pax)
        # 1. แยกประเภท (<=4 คือ A, เกินนั้นคือ B)
        queue_type = 'A' if pax_int <= 4 else 'B'

        # 2. นับจำนวนเฉพาะ สาขานี้ และ ประเภทนี้ (เพื่อให้เลขมันแยกกัน)
        count_res = supabase.table("queues")\
            .select("id", count="exact")\
            .eq("branch_id", branch_id)\
            .eq("queue_type", queue_type)\
            .execute()
        
        # 3. เลขใหม่ = จำนวนที่มี + 1
        new_queue_no = count_res.count + 1

        data = {
            "branch_id": branch_id,
            "pax": pax_int,
            "queue_type": queue_type,
            "status": "waiting",
            "line_user_id": line_user_id,
            "queue_no": new_queue_no  # ✅ บันทึกเลขสวยๆ
        }

        response = supabase.table("queues").insert(data).execute()

        if response.data:
            return {"status": "success", "data": response.data[0]}
        else:
            return {"status": "error", "message": "Insert failed no data returned"}

    except Exception as e:
        print(f"Error add queue: {e}")
        return {"status": "error", "message": str(e)}

# ดึงคิวตาม ID (ใช้ ID เดิมได้เลย)
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

# (เพิ่ม branch_id เพื่อหาคิวในสาขานั้นๆ)
def start_table_service(branch_id, table_id, duration_minutes):
    """ เริ่มเปิดโต๊ะ: แก้ไข Logic การจับคู่โต๊ะจองให้ฉลาดขึ้น (Python Loop) """
    try:
        thai_tz = pytz.timezone('Asia/Bangkok')
        now = datetime.now(thai_tz)
        today_str = now.strftime('%Y-%m-%d')
        finish_time = now + timedelta(minutes=int(duration_minutes))
        finish_time_str = finish_time.strftime('%Y-%m-%d %H:%M:%S')

        # 1. ดึงข้อมูลโต๊ะ
        table_info = supabase.table("tablestime").select("*").eq("id", table_id).execute()
        if not table_info.data:
            return {"status": "error", "message": "ไม่พบโต๊ะนี้"}

        row = table_info.data[0]
        capacity = int(row['capacity'])
        zone_type = row.get('zone_type', '').strip()
        
        # เช็คสาขา
        if str(row.get('branch_id')) != str(branch_id):
            return {"status": "error", "message": "❌ โต๊ะนี้ไม่ได้อยู่ในสาขาปัจจุบัน"}

        queue_msg = ""
        target_customer = None 

        # =========================================================
        # 🟢 CASE 1: Walk-in (ยังคงเดิม)
        # =========================================================
        if zone_type == 'walk_in':
            target_type = 'A' if capacity <= 4 else 'B'
            
            queue_res = supabase.table("queues")\
                .select("*")\
                .eq("branch_id", branch_id)\
                .eq("status", "waiting")\
                .eq("queue_type", target_type)\
                .order("id")\
                .limit(1)\
                .execute()

            if queue_res.data:
                target_customer = queue_res.data[0]
                
                supabase.table("queues").update({
                    "status": "dining",
                    "table_id": table_id,
                    "started_at": now.isoformat()
                }).eq("id", target_customer['id']).execute()
                
                queue_msg = f" | 🎫 เรียกลูกค้าคิว {target_customer['queue_type']}-{target_customer['queue_no']:03d}"
            else:
                queue_msg = " | (เปิดโต๊ะเปล่า - ไม่มีคิวรอ)"

        # =========================================================
        # 🟡 CASE 2: Reservation (✅ แก้ใหม่: ใช้ Python Loop หาคนเข้าโต๊ะ)
        # =========================================================
        elif zone_type == 'reservation':
            
            # 1. ดึงคิวจองที่รออยู่ทั้งหมดของวันนี้ (เรียงตามเวลา)
            # ไม่ต้องกรองจำนวนคนใน SQL (เดี๋ยวมาเช็คเอง)
            all_reservations = supabase.table("reservations")\
                .select("*")\
                .eq("branch_id", branch_id)\
                .eq("booking_date", today_str)\
                .in_("status", ["pending", "confirmed"])\
                .order("booking_time")\
                .execute()
            
            # 2. วนลูปหาคนที่ "ใส่ลงในโต๊ะนี้ได้"
            # กฎ: จำนวนคนจอง (res['num']) ต้องน้อยกว่าหรือเท่ากับ ความจุโต๊ะ + 1
            # เช่น จอง 2 คน ลงโต๊ะ 4 -> (2 <= 5) -> ผ่าน!
            found = False
            for res in all_reservations.data:
                pax = int(res.get('num', 0))
                # อนุโลมให้นั่งเกินได้ 1 คน (Squeeze)
                if pax <= (capacity + 1):
                    target_customer = res
                    found = True
                    break # เจอปุ๊บ หยุดปั๊บ เอาคนนี้แหละ (เพราะเรียงตามเวลามาแล้ว)
            
            if found and target_customer:
                # อัปเดตสถานะ
                supabase.table("reservations").update({
                    "status": "dining",
                    "table_id": table_id
                }).eq("id", target_customer['id']).execute()

                queue_msg = f" | 📅 ลูกค้าจอง: คุณ{target_customer['customer_name']} ({target_customer['num']} ท่าน)"
            else:
                # ถ้าวนจนจบแล้วยังหาไม่ได้ แปลว่าที่รออยู่มีแต่กลุ่มใหญ่เกินโต๊ะนี้
                waiting_count = len(all_reservations.data)
                return {
                    "status": "error", 
                    "message": f"❌ ไม่พบคิวที่ลงโต๊ะ {capacity} ที่นั่งได้ (มีคิวรอ {waiting_count} คิว แต่น่าจะคนเยอะเกินโต๊ะนี้)"
                }

        # 3. อัปเดตสถานะโต๊ะ (เวลาหมด)
        supabase.table("tablestime").update({
            "status": "busy", 
            "final_time": finish_time_str
        }).eq("id", table_id).execute()

        return {"status": "success", "message": f"✅ เปิดโต๊ะสำเร็จ{queue_msg}"}

    except Exception as e:
        print(f"Start Table Error: {e}")
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

        # 🟡 เพิ่มใหม่: ปิดงานลูกค้าจองด้วย (ถ้ามี)
        supabase.table("reservations").update({
            "status": "completed"
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

# (เพิ่ม branch_id)
def get_waiting_list(branch_id):
    """ ดึงคิวที่สถานะเป็น waiting และแปลงเวลาเป็นไทย """
    try:
        # ดึงข้อมูลจาก Supabase (เรียงตาม ID) เฉพาะสาขานี้
        response = supabase.table('queues').select(
            '*').eq("branch_id", branch_id).eq('status', 'waiting').order('id').execute() # <-- เพิ่ม eq branch_id
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

# นับจำนวนคนรอคิวก่อนเรา (เพิ่ม branch_id)
def get_waiting_count_before(branch_id, queue_type, queue_id):
    """ นับจำนวนคิวที่มาก่อนเรา (นับทุกคนที่ยังไม่จบงานและยังไม่ยกเลิก) """
    try:
        # แปลงเป็นตัวเลขให้ชัวร์ๆ กันระบบเอ๋อ
        b_id = int(branch_id)
        q_id = int(queue_id)

        response = supabase.table('queues') \
            .select('*', count='exact') \
            .eq("branch_id", b_id) \
            .eq('queue_type', queue_type) \
            .neq('status', 'completed') \
            .neq('status', 'cancelled') \
            .lt('id', q_id) \
            .execute()
            
        # neq = Not Equal (ไม่เท่ากับ)
        # แปลว่า: นับคิวที่สาขาเดียวกัน + ประเภทเดียวกัน + ยังไม่เสร็จ + ยังไม่ยกเลิก + และมาก่อนเรา
        
        return response.count
    except Exception as e:
        print(f"Error counting: {e}")
        return 0

# ดึงโต๊ะตามประเภทคิว (เพิ่ม branch_id)

def get_tables_for_type(branch_id, queue_type):
    """ ดึงโต๊ะทั้งหมดที่รองรับ Queue Type นี้ (A หรือ B) และเป็นโซน Walk-in เท่านั้น """
    try:
        # ✅ แก้ไข: เพิ่ม .eq('zone_type', 'walk_in') เพื่อไม่ให้ไปนับรวมโต๊ะจอง
        # เพิ่ม .eq("branch_id", branch_id)
        query = supabase.table('tablestime').select('*').eq("branch_id", branch_id).eq('zone_type', 'walk_in')

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

# (เพิ่ม branch_id)
def add_reservation_service(branch_id, name, phone, pax, b_date, b_time):
    """ บันทึกการจองลูกค้า """
    data = {
        "branch_id": branch_id, # <-- บันทึกสาขา
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

# ตรวจสอบความว่างของโต๊ะจอง (เพิ่ม branch_id)
def check_availability(branch_id, pax, booking_date, booking_time):
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
            .eq("branch_id", branch_id)\
            .eq("zone_type", "reservation")\
            .gte("capacity", pax)\
            .execute().data # <-- เพิ่ม eq branch_id

        if not candidate_tables:
            # ลองหาโต๊ะใหญ่สุดที่มี เพื่อแจ้งลูกค้า (เฉพาะสาขานี้)
            max_cap_res = supabase.table("tablestime")\
                .select("capacity")\
                .eq("branch_id", branch_id)\
                .eq("zone_type", "reservation")\
                .order("capacity", desc=True)\
                .limit(1).execute().data

            max_pax = max_cap_res[0]['capacity'] if max_cap_res else 0
            return False, f"❌ สาขานี้ไม่มีโต๊ะที่รองรับ {pax} ท่านได้ (โซนจองรับสูงสุด {max_pax} ท่าน/โต๊ะ)"

        # 3. 💥 ดักจับ: ช่วงเวลานั้นเต็มหรือยัง (Time Overlap)
        req_end = req_start + timedelta(minutes=105)  # กฎ 105 นาที

        # ดึงการจองของวันนั้นมาเช็ค (เฉพาะสาขานี้)
        todays_reservations = supabase.table("reservations")\
            .select("booking_time, num")\
            .eq("branch_id", branch_id)\
            .eq("booking_date", booking_date)\
            .neq("status", "cancelled")\
            .execute().data # <-- เพิ่ม eq branch_id

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

# ดึงรายการจองตามวันที่ (เพิ่ม branch_id)
def get_reservations_by_date(branch_id, date_str):
    """ ดึงรายการจองของวันที่ระบุ เพื่อไปแสดงหน้าเว็บ (Public View) """
    try:
        # ดึงเฉพาะเวลา (booking_time) และสถานะ
        response = supabase.table("reservations")\
            .select("booking_time, status")\
            .eq("branch_id", branch_id)\
            .eq("booking_date", date_str)\
            .neq("status", "cancelled")\
            .execute() # <-- เพิ่ม eq branch_id
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

# ปิดยอดวัน (เพิ่ม branch_id เพื่อปิดทีละสาขา)
def close_day_service(branch_id):
    try:
        # 1. ดึงข้อมูลปัจจุบัน (เฉพาะสาขานี้)
        response = supabase.table("queues").select("*").eq("branch_id", branch_id).execute()
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

        # 3. ล้างตารางหลักเฉพาะสาขานี้ (ใช้ delete แทน rpc เพื่อความชัวร์เรื่องสาขา)
        supabase.table("queues").delete().eq("branch_id", branch_id).execute()

        return {"status": "success", "message": "✅ ปิดยอดและรีเซ็ตคิวสาขานี้เรียบร้อย"}

    except Exception as e:
        print(f"Error: {e}")
        return {"status": "error", "message": str(e)}

# ดึงข้อมูลสรุปยอดสำหรับ Dashboard (เพิ่ม branch_id)
def get_dashboard_data(branch_id):
    """ ดึงข้อมูลสรุปยอดเพื่อแสดงบน Dashboard """
    stats = {
        'total_pax': 0,
        'total_queues': 0,
        'type_a': 0,
        'type_b': 0,
        'daily_stats': {}
    }

    try:
        # 1. ดึงข้อมูลจากตาราง queues (ลูกค้าปัจจุบัน) เฉพาะสาขานี้
        q_res = supabase.table('queues').select('*').eq("branch_id", branch_id).execute()
        queues = q_res.data if q_res.data else []

        # 2. (Optional) ดึงข้อมูลจาก queues_history ด้วย (เฉพาะสาขานี้)
        # h_res = supabase.table('queues_history').select('*').eq("branch_id", branch_id).execute()
        # queues += h_res.data if h_res.data else []

        # 3. ดึงข้อมูล Reservation (เฉพาะสาขานี้)
        r_res = supabase.table('reservations').select(
            '*').eq("branch_id", branch_id).neq('status', 'cancelled').execute()
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

# ส่งข้อความหาลูกค้าผ่าน LINE Messaging API
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

# ดึงเวลาเฉลี่ยจากข้อมูลจริง (เพิ่ม branch_id)
def get_real_average_cycle_time(branch_id, default_cycle=80):
    """
    คำนวณเวลาเฉลี่ยจากข้อมูลจริง (Real Data)
    สูตร: หาค่าเฉลี่ยของ (completed_at - started_at) ในวันนี้
    """
    try:
        # ดึงคิวที่จบงานแล้ว และมีเวลาครบ (เฉพาะสาขานี้)
        response = supabase.table('queues')\
            .select('started_at, completed_at')\
            .eq("branch_id", branch_id)\
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

# ดึงการจองด้วยเบอร์โทร + ชื่อ (เพิ่ม branch_id)
def get_reservation_by_phone_and_name(branch_id, phone, name):
    """ ค้นหาการจองด้วยเบอร์โทร + ชื่อ (เพื่อความปลอดภัย) """
    try:
        # ใช้ ilike กับชื่อ เพื่อให้ค้นหาแบบยืดหยุ่น (เช่น จอง 'สมชาย ใจดี' พิมพ์แค่ 'สมชาย' ก็เจอ)
        response = supabase.table("reservations")\
            .select("*")\
            .eq("branch_id", branch_id)\
            .eq("phone", phone)\
            .ilike("customer_name", f"%{name}%")\
            .in_("status", ["pending", "confirmed"])\
            .order("id", desc=True)\
            .limit(1)\
            .execute()
        
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Check Booking Error: {e}")
        return None
    
# ✅ แก้ไขฟังก์ชันสมัครสมาชิก (เพิ่ม branch_id)
def create_admin(username, password, branch_id):
    try:
        # เช็คชื่อซ้ำ
        check = supabase.table("admin_users").select("username").eq("username", username).execute()
        if len(check.data) > 0:
            return {"status": "error", "message": "❌ ชื่อผู้ใช้นี้มีคนใช้แล้วครับ"}

        hashed_pw = generate_password_hash(password)

        data = {
            "username": username,
            "password_hash": hashed_pw,
            "branch_id": int(branch_id)  # ✅ บันทึกสาขาลงไปด้วย
        }
        supabase.table("admin_users").insert(data).execute()
        
        return {"status": "success", "message": "✅ สมัครสมาชิกสำเร็จ! กรุณาเข้าสู่ระบบ"}

    except Exception as e:
        print(f"Register Error: {e}")
        return {"status": "error", "message": str(e)}

# ✅ แก้ไขฟังก์ชันล็อกอิน (ไม่ต้องแก้โค้ด แต่ให้รู้ว่ามันจะดึง branch_id มาเองเพราะเรา select "*")
def login_admin(username, password):
    try:
        response = supabase.table("admin_users").select("*").eq("username", username).execute()
        
        if not response.data:
            return {"status": "error", "message": "❌ ไม่พบชื่อผู้ใช้นี้"}

        user = response.data[0]
        stored_hash = user['password_hash']

        if check_password_hash(stored_hash, password):
            # user ตัวนี้จะมี keys: 'id', 'username', 'password_hash', 'branch_id' ครบเลย
            return {"status": "success", "message": "Login Success", "user": user}
        else:
            return {"status": "error", "message": "❌ รหัสผ่านไม่ถูกต้อง"}

    except Exception as e:
        return {"status": "error", "message": "เกิดข้อผิดพลาดในการเข้าสู่ระบบ"}

# ดึงข้อมูลสาขาสำหรับมุมมองลูกค้า
def get_branches_for_customer():
    try:
        # 1. ดึงสาขา (เหมือนเดิม)
        response = supabase.table("branches").select("*").neq("status", "closed").order("id").execute()
        branches = response.data

        # เตรียมวันที่ปัจจุบัน (เพื่อดึงยอดจองของวันนี้)
        today = datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%Y-%m-%d')

        for branch in branches:
            # A. นับคิว Walk-in (เหมือนเดิม)
            count_res = supabase.table("queues")\
                .select("*", count="exact")\
                .eq("branch_id", branch['id'])\
                .eq("status", "waiting")\
                .execute()
            branch['waiting_count'] = count_res.count if count_res.count else 0

            # ✅ B. เพิ่ม: นับคิวจองล่วงหน้า (Booking) ของวันนี้
            res_booking = supabase.table("reservations")\
                .select("*", count="exact")\
                .eq("branch_id", branch['id'])\
                .eq("booking_date", today)\
                .in_("status", ["pending", "confirmed"])\
                .execute()
            
            # ยัดตัวแปร booking_count เข้าไปใน branch
            branch['booking_count'] = res_booking.count if res_booking.count else 0

        return branches

    except Exception as e:
        print("❌ Error getting customer view:", e)
        return []
# ดึงชื่อสาขาจาก ID
def get_branch_name(branch_id):
    """ ดึงชื่อสาขาจาก ID """
    try:
        response = supabase.table("branches").select("name").eq("id", branch_id).execute()
        if response.data:
            return response.data[0]['name']
        return "ไม่ระบุสาขา"
    except Exception as e:
        return "Error"
# นับเฉพาะคน 'ยืนรอ' จริงๆ (เพิ่ม branch_id)
def get_pure_waiting_count(branch_id, queue_type, queue_id):
    """ นับเฉพาะคน 'ยืนรอ' จริงๆ เพื่อเอาไปคำนวณเวลา (ไม่รวมคนกินอยู่) """
    try:
        response = supabase.table('queues') \
            .select('*', count='exact') \
            .eq("branch_id", branch_id) \
            .eq('queue_type', queue_type) \
            .eq('status', 'waiting') \
            .lt('id', queue_id) \
            .execute()
        return response.count
    except:
        return 0