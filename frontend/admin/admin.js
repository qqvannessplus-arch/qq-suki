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
    // [แทรกเพิ่ม] Logic เพิ่มโต๊ะ (Dropdown + Validation)
    // ============================================
    const typeSelect = document.getElementById('tableTypeSelect');
    
    // ตรวจสอบว่าหน้า HTML มีฟอร์มนี้อยู่จริงไหม (กัน Error)
    if (typeSelect) {
        const namePrefix = document.getElementById('namePrefix');
        const capacityInput = document.getElementById('capacityInput');
        const zoneSelectWrapper = document.getElementById('zoneSelectWrapper');
        const manualZoneSelect = document.getElementById('manualZoneSelect');
        const finalZoneInput = document.getElementById('finalZoneInput');
        const addTableForm = document.getElementById('addTableForm');
        const tableSuffix = document.getElementById('tableSuffix');
        const finalTableName = document.getElementById('finalTableName');

        // ฟังก์ชันอัปเดตค่า UI ตาม Type
        function updateTableConfig() {
            const type = typeSelect.value;
            capacityInput.min = 1; capacityInput.max = 20; // Reset

            if (type === 'Custom') {
                namePrefix.style.display = 'none';
                tableSuffix.placeholder = "ชื่อ (เช่น VIP)";
                zoneSelectWrapper.style.display = 'block';
                capacityInput.value = ""; 
            } else {
                namePrefix.style.display = 'block';
                zoneSelectWrapper.style.display = 'none';
                
                if (type === 'A') {
                    namePrefix.textContent = "A-";
                    finalZoneInput.value = "walk_in";
                    capacityInput.min = 1; capacityInput.max = 4; 
                    capacityInput.value = 4;
                } else if (type === 'B') {
                    namePrefix.textContent = "B-";
                    finalZoneInput.value = "walk_in";
                    capacityInput.min = 5; capacityInput.max = 20; 
                    capacityInput.value = 6;
                } else if (type === 'C') {
                    namePrefix.textContent = "R-";
                    finalZoneInput.value = "reservation";
                    capacityInput.value = 4;
                }
            }
        }

        // Event: เปลี่ยน Type
        typeSelect.addEventListener('change', updateTableConfig);
        updateTableConfig(); // รันครั้งแรกทันที

        // Event: เปลี่ยน Zone (Custom)
        manualZoneSelect.addEventListener('change', function() {
            finalZoneInput.value = this.value;
        });

        // Event: ดักจับตัวเลข (Validation)
        capacityInput.addEventListener('change', function() {
            const val = parseInt(this.value);
            const min = parseInt(this.min);
            const max = parseInt(this.max);

            if (val < min) {
                alert(`⚠️ ต่ำไปครับ! Type นี้ต้อง ${min} ท่านขึ้นไป`);
                this.value = min;
            } else if (val > max) {
                alert(`⚠️ มากไปครับ! Type นี้ได้สูงสุด ${max} ท่าน`);
                this.value = max;
            }
        });

        // Event: กด Submit
        addTableForm.addEventListener('submit', function(e) {
            const type = typeSelect.value;
            const suffix = tableSuffix.value.trim();

            if(!suffix) {
                alert("กรุณากรอกชื่อ/หมายเลขโต๊ะ");
                e.preventDefault();
                return;
            }

            if (type === 'Custom') {
                finalTableName.value = suffix;
                finalZoneInput.value = manualZoneSelect.value;
            } else {
                finalTableName.value = namePrefix.textContent + suffix;
            }
        });
    }
    // ============================================

    // -----------------------------------------------------------
    // ✅ เตรียม Branch ID (เพิ่มใหม่ตรงนี้ เพื่อให้ QR ถูกสาขา)
    // -----------------------------------------------------------
    const branchIdInput = document.getElementById('currentBranchId');
    const branchId = branchIdInput ? branchIdInput.value : '1'; 

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

            // ✅ แก้ไข: เพิ่ม ?branch_id=XX ต่อท้าย URL
            const walkinUrl = window.location.protocol + "//" + window.location.host + "/walkin?branch_id=" + branchId;

            // ไปใช้ไลน์ LIFF แทน (ถ้ามี)
            // const liffBase = "https://liff.line.me/2008763658-K62w632B"; // LIFF ID ของคุณ
            // const walkinUrl = `${liffBase}?branch_id=${branchId}`; 

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
            
            // ✅ แก้ไข: เพิ่ม ?branch_id=XX ต่อท้าย URL
            const bookingUrl = window.location.protocol + "//" + window.location.host + "/booking?branch_id=" + branchId;

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