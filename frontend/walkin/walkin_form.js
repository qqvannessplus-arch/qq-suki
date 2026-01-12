// frontend/walkin/walkin_form.js
// 🟢 ระบบ Walk-in Form สำหรับลูกค้า (LIFF)
// ---------------------------------------------------------
document.addEventListener("DOMContentLoaded", function() {
    // ดึงค่า Config ที่ประกาศไว้ใน HTML
    const currentBranchId = window.ServerConfig.branchId;
    const liffId = window.ServerConfig.liffId;

    // 🟢 0. ตรวจสอบ Branch ID
    if (!currentBranchId || currentBranchId == "None") {
        alert("⚠️ ไม่พบข้อมูลสาขา! กรุณาเลือกสาขาใหม่");
        window.location.href = "/hub";
        return;
    }

    // เริ่มทำงาน
    initSystem();
});

// --- 1. Logic เลือกจำนวนคน ---
function selectPax(num) {
    const input = document.getElementById("paxInput");
    input.value = num;
    if (num >= 6) {
        input.style.display = "block";
        input.focus();
    } else {
        input.style.display = "none";
    }
    document.querySelectorAll(".pax-btn").forEach((btn) => btn.classList.remove("active"));
    event.target.classList.add("active");
}

// ต้อง export ให้ HTML เรียกใช้ได้ (เพราะ onclick="..." ใน HTML มันหา function นี้ไม่เจอถ้าไม่ทำแบบนี้)
window.selectPax = selectPax;

function checkLimit(form) {
    const input = document.getElementById("paxInput");
    const val = parseInt(input.value || 0);

    if (val > 20) {
        alert("⚠️ ขออภัยครับ! รองรับลูกค้าได้สูงสุด 20 ท่านต่อคิว\n\nหากมาเกินกว่านี้ รบกวนกดจองแยกเป็น 2 คิว หรือติดต่อพนักงานหน้าร้านครับ");
        return false;
    }

    const btn = form.querySelector("button[type=submit]");
    btn.disabled = true;
    btn.innerText = "⏳ กำลังบันทึก...";
    return true;
}
window.checkLimit = checkLimit;

// --- 2. Logic เริ่มต้นระบบ ---
async function initSystem() {
    const currentBranchId = window.ServerConfig.branchId;

    // A. เช็ค Reset
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has("reset")) {
        console.log("♻️ Resetting...");
        localStorage.removeItem("my_suki_queue_id");
        localStorage.removeItem("my_suki_branch_id");
        window.history.replaceState({}, document.title, window.location.pathname + "?branch_id=" + currentBranchId);
    }

    // B. เช็คคิวค้างในเครื่อง
    const savedQueueId = localStorage.getItem("my_suki_queue_id");
    const savedBranchId = localStorage.getItem("my_suki_branch_id");

    if (savedQueueId) {
        // ถ้ามี branch id เดิม และ ไม่ตรงกับ สาขาปัจจุบัน
        if (savedBranchId && savedBranchId !== currentBranchId) {
            const confirmSwitch = confirm(
                "⚠️ คุณมีคิวค้างอยู่ที่สาขาอื่น!\nต้องการ 'ยกเลิกคิวเดิม' เพื่อจองสาขานี้ไหม?"
            );

            if (confirmSwitch) {
                try {
                    await fetch(`/cancel-queue/${savedQueueId}?source=walkin`, { method: "POST" });
                } catch (e) { console.error(e); }
                
                localStorage.removeItem("my_suki_queue_id");
                localStorage.removeItem("my_suki_branch_id");
                window.location.reload();
                return;
            } else {
                window.location.href = "/queue/" + savedQueueId;
                return;
            }
        }
        // สาขาตรงกัน พาไปเลย
        window.location.href = "/queue/" + savedQueueId;
        return;
    }

    // C. เริ่มโหลด LIFF (ตั้งเวลา 5 วิ กันค้าง)
    setTimeout(() => {
         const loader = document.getElementById("loadingOverlay");
         if(loader) loader.style.display = "none";
    }, 5000);

    //await initLIFF();
        document.getElementById("loadingOverlay").style.display = "none";
}

// --- 3. Logic LIFF ---
async function initLIFF() {
    try {
        await liff.init({ liffId: window.ServerConfig.liffId });

        if (!liff.isLoggedIn()) {
             liff.login({ redirectUri: window.location.href });
             return; 
        }

        const profile = await liff.getProfile();
        document.getElementById("lineUserIdField").value = profile.userId;

        const statusDiv = document.getElementById("lineStatus");
        statusDiv.style.display = "block";
        statusDiv.className = "alert alert-success py-1";
        statusDiv.innerHTML = `✅ สวัสดีคุณ <b>${profile.displayName}</b>`;

        await checkLineAccount(profile.userId);

    } catch (err) {
        console.error("LIFF Error:", err);
    } finally {
        document.getElementById("loadingOverlay").style.display = "none";
    }
}

// --- 4. เช็ค Server ---
async function checkLineAccount(userId) {
    try {
        const response = await fetch("/api/check-my-queue", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ line_user_id: userId }),
        });
        const result = await response.json();

        if (result.status === "found") {
            localStorage.setItem("my_suki_queue_id", result.queue_id);
            localStorage.setItem("my_suki_branch_id", window.ServerConfig.branchId);
            window.location.href = "/queue/" + result.queue_id;
        }
    } catch (err) { console.error(err); }
}