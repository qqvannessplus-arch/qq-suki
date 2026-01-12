// ===============================================
// 1. ฟังก์ชันสลับ Tab (จองใหม่ <-> เช็คสถานะ)
// ===============================================
function switchTab(mode) {
    const bookingSec = document.getElementById('bookingSection');
    const checkSec = document.getElementById('checkSection');
    const links = document.querySelectorAll('.nav-link');

    if (mode === 'booking') {
        bookingSec.style.display = 'block';
        checkSec.style.display = 'none';
        links[0].classList.add('active');
        links[1].classList.remove('active');
    } else {
        bookingSec.style.display = 'none';
        checkSec.style.display = 'block';
        links[0].classList.remove('active');
        links[1].classList.add('active');
    }
}

// ===============================================
// 2. ฟังก์ชันเช็คสถานะการจอง (ปลอดภัย: ไม่โชว์ชื่อ/สถานะ)
// ===============================================
async function checkMyBooking() {
    const name = document.getElementById('checkNameInput').value.trim();
    const phone = document.getElementById('checkPhoneInput').value.trim();
    const branchId = document.getElementById('branchIdField').value;
    const resultArea = document.getElementById('checkResultArea');

    if (!name || !phone) {
        alert("กรุณากรอกทั้งชื่อและเบอร์โทรครับ");
        return;
    }

    // โชว์ Loading
    resultArea.innerHTML = '<div class="text-center"><div class="spinner-border text-primary" role="status"></div><p class="mt-2">กำลังค้นหา...</p></div>';

    try {
        const response = await fetch('/api/my-booking', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, phone: phone, branch_id: branchId })
        });

        const data = await response.json();

        if (data.found) {
            const r = data.data;
            
            // ✅ ปลอดภัย: แสดงเฉพาะ วันที่, เวลา, จำนวนคน เท่านั้น (ตามที่สั่ง)
            resultArea.innerHTML = `
                <div class="alert alert-success border-success text-center shadow-sm">
                    <div class="fs-1">🎉</div>
                    <h4 class="fw-bold text-success">พบข้อมูลการจอง!</h4>
                    <p class="text-muted small mb-3">ยืนยันตัวตนถูกต้อง</p>
                    
                    <div class="card bg-white border-0 p-3 shadow-sm d-inline-block text-start" style="min-width: 250px;">
                        <div class="d-flex justify-content-between mb-2 border-bottom pb-2">
                            <span class="text-secondary">📅 วันที่:</span>
                            <span class="fw-bold text-dark">${r.booking_date}</span>
                        </div>
                        <div class="d-flex justify-content-between mb-2 border-bottom pb-2">
                            <span class="text-secondary">⏰ เวลา:</span>
                            <span class="fw-bold text-danger fs-5">${r.booking_time.slice(0,5)} น.</span>
                        </div>
                        <div class="d-flex justify-content-between">
                            <span class="text-secondary">👥 จำนวน:</span>
                            <span class="fw-bold text-dark">${r.num} ท่าน</span>
                        </div>
                    </div>

                    <div class="mt-4 text-muted small">
                        *กรุณามาถึงก่อนเวลา 10 นาทีนะครับ
                    </div>
                </div>
            `;
        } else {
            resultArea.innerHTML = `
                <div class="alert alert-danger text-center shadow-sm">
                    <h5>❌ ไม่พบข้อมูล</h5>
                    <p class="mb-0">ไม่พบการจอง หรือ ชื่อ/เบอร์โทร ไม่ถูกต้อง</p>
                </div>
            `;
        }

    } catch (error) {
        console.error(error);
        resultArea.innerHTML = '<div class="alert alert-warning text-center">เกิดข้อผิดพลาดในการเชื่อมต่อ</div>';
    }
}

// ===============================================
// 3. Helper Functions & Initialization
// ===============================================

// ฟังก์ชันหาวันที่ปัจจุบัน (Timezone: Asia/Bangkok)
function getThaiDate() {
    const thaiTime = new Date().toLocaleString("en-US", {timeZone: "Asia/Bangkok"});
    const dateObj = new Date(thaiTime);
    const year = dateObj.getFullYear();
    const month = String(dateObj.getMonth() + 1).padStart(2, '0');
    const day = String(dateObj.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

// ฟังก์ชันดึงตารางจอง (แสดง Badge เวลา)
async function fetchBookings() {
    const dateInput = document.getElementById('dateInput');
    const statusArea = document.getElementById('bookingStatusArea');
    const branchInput = document.getElementById('branchIdField');

    if (!dateInput) return; // กัน Error ถ้าหน้าเว็บโหลดไม่ครบ

    const selectedDate = dateInput.value;
    const branchId = branchInput ? branchInput.value : '1';

    statusArea.innerHTML = '<div class="spinner-border spinner-border-sm text-secondary" role="status"></div> <small class="text-muted">กำลังเช็คคิว...</small>';

    try {
        const response = await fetch(`/api/check-bookings?date=${selectedDate}&branch_id=${branchId}`);
        if (!response.ok) throw new Error("Network response was not ok");
        const data = await response.json(); 

        if (Object.keys(data).length === 0) {
            statusArea.innerHTML = `<div class="text-success py-2"><span class="fs-4">✅</span><br><strong>ยังไม่มีคิวจองในวันนี้</strong><br><small>เลือกเวลาที่ต้องการได้เลยครับ</small></div>`;
            return;
        }

        let html = '<div class="d-flex flex-wrap gap-2 justify-content-center">';
        const sortedTimes = Object.keys(data).sort();
        sortedTimes.forEach(time => {
            const count = data[time];
            const badgeClass = count >= 3 ? 'bg-danger text-white' : 'bg-warning text-dark';
            html += `<span class="badge ${badgeClass} status-badge p-2 shadow-sm">🕒 ${time} น. <br>(จองแล้ว ${count} ที่)</span>`;
        });
        html += '</div>';
        statusArea.innerHTML = html;

    } catch (error) {
        console.error("Fetch Error:", error);
        statusArea.innerHTML = '<small class="text-danger">❌ ไม่สามารถดึงข้อมูลตารางจองได้</small>';
    }
}

// เริ่มต้นทำงานเมื่อโหลดหน้าเสร็จ
document.addEventListener('DOMContentLoaded', function() {
    const dateInput = document.getElementById('dateInput');
    
    if (dateInput) {
        const todayStr = getThaiDate();
        dateInput.value = todayStr;
        dateInput.min = todayStr;

        // ดักจับ Event เปลี่ยนวันที่
        dateInput.addEventListener('change', fetchBookings);
        
        // โหลดข้อมูลครั้งแรก
        fetchBookings();
    }
});