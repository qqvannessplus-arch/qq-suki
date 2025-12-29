document.addEventListener("DOMContentLoaded", function () {
    
    // ============================================
    // 0. จำตำแหน่ง Scroll (เวลารีเฟรชจะได้ไม่เด้งขึ้นบนสุด)
    // ============================================
    const scrollpos = localStorage.getItem('scrollpos');
    if (scrollpos) {
        window.scrollTo(0, scrollpos);
    }
    window.addEventListener('beforeunload', function () {
        localStorage.setItem('scrollpos', window.scrollY);
    });
    
    // ============================================
    // 1. จัดการฟอร์มลบโต๊ะ (Delete Table)
    // ============================================
    const deleteForms = document.querySelectorAll('.js-delete-form');
    deleteForms.forEach(form => {
        form.addEventListener('submit', function (e) {
            const tableName = this.dataset.name || "นี้"; // ดึงชื่อโต๊ะ (ถ้ามี)
            const isConfirmed = confirm(`⚠️ คุณแน่ใจหรือไม่ที่จะลบโต๊ะ "${tableName}" ?\n(ข้อมูลจะหายไปถาวร)`);
            
            if (!isConfirmed) {
                e.preventDefault();
            }
        });
    });

    // ============================================
    // 2. จัดการฟอร์มเช็คบิล (Clear Table)
    // ============================================
    const clearForms = document.querySelectorAll('.js-clear-form');
    clearForms.forEach(form => {
        form.addEventListener('submit', function (e) {
            const isConfirmed = confirm("ยืนยันเช็คบิลและเคลียร์โต๊ะ? (สถานะจะว่างทันที)");
            
            if (!isConfirmed) {
                e.preventDefault();
            }
        });
    });

    // ============================================
    // 3. จัดการฟอร์มเปิดโต๊ะ (Start Table)
    // ============================================
    const startForms = document.querySelectorAll('.js-start-form');
    startForms.forEach(form => {
        form.addEventListener('submit', function (e) {
            // ดึงค่าเวลาจากช่องด้านบน (ถ้าไม่มีให้ Default 90)
            const minutes = document.getElementById('globalDuration').value || 90;
            
            // ยัดค่าใส่ใน hidden input ของฟอร์มนั้นๆ
            const hiddenInput = this.querySelector('input[name="duration"]');
            if (hiddenInput) {
                hiddenInput.value = minutes;
            }
        });
    });

    // ============================================
    // 4. จัดการ QR Code Walk-in (สีเหลือง)
    // ============================================
    const qrModal = document.getElementById('qrModal');
    if (qrModal) {
        qrModal.addEventListener('shown.bs.modal', function () {
            const qrContainer = document.getElementById("qrcode");
            const linkText = document.getElementById("linkText");
            
            // ล้างรูปเก่าก่อน
            qrContainer.innerHTML = "";

            //const walkinUrl = window.location.protocol + "//" + window.location.host + "/walkin";

            // ✅ เปลี่ยนเป็น LIFF URL (เพื่อให้ iPhone เด้งเข้าแอป LINE)
            // (เอา LIFF ID ที่คุณเพิ่งสร้างมาใส่ตรงนี้)
            const walkinUrl = "https://liff.line.me/2008763658-K62w632B";

            // สร้าง QR Code
            new QRCode(qrContainer, {
                text: walkinUrl,
                width: 200,
                height: 200
            });

            // แสดงลิงก์ด้านล่างเผื่อคลิก
            if (linkText) {
                linkText.innerHTML = `<a href="${walkinUrl}" target="_blank" class="text-decoration-none fw-bold">${walkinUrl}</a>`;
            }
        });
    }

    // ============================================
    // 5. จัดการ QR Code Booking (สีเขียว)
    // ============================================
    const qrBookingModal = document.getElementById('qrBookingModal');
    if (qrBookingModal) {
        qrBookingModal.addEventListener('shown.bs.modal', function () {
            const qrContainer = document.getElementById("qrcodeBooking");
            const linkText = document.getElementById("linkTextBooking");
            
            qrContainer.innerHTML = "";

            // สำหรับ Booking ใช้ URL เว็บปกติไปก่อน (เพราะเรายังไม่ได้ทำ LIFF แยกให้หน้า Booking)
            // อนาคตถ้าอยากให้เด้งเข้า LINE ต้องสร้าง LIFF ID อีกอันสำหรับ URL /booking
            const bookingUrl = window.location.protocol + "//" + window.location.host + "/booking";

            new QRCode(qrContainer, {
                text: bookingUrl,
                width: 200,
                height: 200,
                correctLevel : QRCode.CorrectLevel.H
            });

            if (linkText) {
                linkText.innerHTML = `<a href="${bookingUrl}" target="_blank" class="text-success text-decoration-none">${bookingUrl}</a>`;
            }
        });
    }
});