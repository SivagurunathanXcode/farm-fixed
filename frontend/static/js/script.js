/* =============================================
   FARM WORKERS APP – script.js
   Payment modal: Cash / UPI App / UPI QR
   QR codes generated server-side (Python + Pillow)
   ============================================= */

/* ─── PASSWORD VALIDATION ──────────────────── */
function validatePassword(){
    var pw = document.getElementById("password");
    var cf = document.getElementById("confirmPassword");
    if(!pw||!cf) return true;
    if(pw.value!==cf.value){ alert("Passwords do not match!"); return false; }
    return true;
}

/* ══════════════════════════════════════════════
   PAYMENT MODAL STATE
══════════════════════════════════════════════ */
var PM = {
    worker    : null,
    work      : null,
    due       : 0,
    mode      : "work",   // "work" | "total"
    method    : null,
    pendingAmt: 0,
};

/* ─── OPEN helpers ─────────────────────────── */
function openPayDialog(btn){
    PM.worker = btn.dataset.worker;
    PM.work   = btn.dataset.work;
    PM.due    = parseFloat(btn.dataset.due||0);
    PM.mode   = "work";
    _pmOpen(btn.dataset.label||"Worker");
}
function openWorkerPayTotal(btn){
    PM.worker = btn.dataset.worker;
    PM.work   = null;
    PM.due    = parseFloat(btn.dataset.due||0);
    PM.mode   = "total";
    _pmOpen(btn.dataset.label||"Worker");
}
function _pmOpen(label){
    document.getElementById("pmLabel").textContent = label;
    document.getElementById("pmDue").textContent   = "₹" + PM.due.toFixed(2);
    document.getElementById("pmAmount").value      = "";
    pmClearError();
    pmShowStep(1);
    var m = document.getElementById("payModal");
    m.style.display = "flex"; m.classList.add("open");
    setTimeout(function(){ document.getElementById("pmAmount").focus(); }, 100);
}

/* ─── CLOSE / BACK ─────────────────────────── */
function pmClose(){
    var m = document.getElementById("payModal");
    m.style.display = "none"; m.classList.remove("open");
    pmShowStep(1);
    PM.worker=PM.work=PM.method=null; PM.due=PM.pendingAmt=0;
    document.getElementById("upiAppMarkWrap").style.display = "none";
    document.getElementById("qrMarkWrap").style.display     = "none";
    /* Reset QR image */
    var qrImg = document.getElementById("qrImg");
    if(qrImg){ qrImg.src=""; qrImg.style.display="none"; }
    document.getElementById("qrSpinner").style.display = "block";
}
function pmBack(){ pmShowStep(1); }

function pmShowStep(n){
    document.getElementById("pmStep1").style.display = n===1?"block":"none";
    document.getElementById("pmStep2").style.display = n===2?"block":"none";
    document.getElementById("pmStep3").style.display = n===3?"block":"none";
}

/* ─── VALIDATION ───────────────────────────── */
function pmClearError(){
    var e=document.getElementById("pmError");
    e.textContent=""; e.style.display="none";
}
function pmError(msg){
    var e=document.getElementById("pmError");
    e.textContent=msg; e.style.display="block";
}
function pmGetAmount(){
    pmClearError();
    var a=parseFloat(document.getElementById("pmAmount").value);
    if(!a||a<=0){ pmError("Please enter a valid amount greater than ₹0."); return null; }
    if(PM.mode==="work" && a>PM.due){ pmError("Amount cannot exceed due ₹"+PM.due.toFixed(2)); return null; }
    return a;
}

/* ─── METHOD CHOICE ────────────────────────── */
function pmChoose(method){
    var amount=pmGetAmount();
    if(amount===null) return;
    PM.method=method; PM.pendingAmt=amount;
    if(method==="cash")        _pmCashPay(amount);
    else if(method==="upiapp") _pmUpiApp(amount);
    else if(method==="qr")     _pmUpiQr(amount);
}

/* ─── CASH ─────────────────────────────────── */
function _pmCashPay(amount){
    var ep  = PM.mode==="total" ? "/pay_worker_total" : "/pay_cash";
    var body= "worker_id="+PM.worker+"&amount="+amount;
    if(PM.mode==="work"&&PM.work) body+="&work_id="+PM.work;
    _pmPost(ep, body, function(ok){
        if(ok){ pmClose(); location.reload(); }
        else pmError("Payment failed. Please try again.");
    });
}

/* ─── UPI APP ──────────────────────────────── */
function _pmUpiApp(amount){
    _pmPost("/generate_upi_link",
        "worker_id="+PM.worker+"&work_id="+PM.work+"&amount="+amount,
        function(ok, data){
            if(!ok){ pmError(data||"Could not generate UPI link."); return; }
            document.getElementById("upiAppAmt").textContent  = "₹"+amount.toFixed(2);
            document.getElementById("upiAppName").textContent = data.worker_name||"";
            document.getElementById("upiAppId").textContent   = "📲 "+data.upi_id;
            document.getElementById("upiAppLink").href        = data.upi_link;
            document.getElementById("upiAppMarkWrap").style.display = "none";
            pmShowStep(2);
        }, true);
}
function pmUpiLinkTapped(){
    setTimeout(function(){
        document.getElementById("upiAppMarkWrap").style.display = "block";
    }, 1500);
}

/* ─── UPI QR  (server-side PNG, shown in <img>) */
function _pmUpiQr(amount){
    /* show step 3 immediately with spinner */
    document.getElementById("qrAmt").textContent = "₹"+amount.toFixed(2);
    document.getElementById("qrName").textContent = "";
    document.getElementById("qrUpiId").textContent = "";
    document.getElementById("qrMarkWrap").style.display = "none";
    var qrImg    = document.getElementById("qrImg");
    var spinner  = document.getElementById("qrSpinner");
    qrImg.style.display   = "none";
    spinner.style.display = "block";
    spinner.textContent   = "Generating QR code…";
    pmShowStep(3);

    _pmPost("/generate_upi_qr",
        "worker_id="+PM.worker+"&work_id="+PM.work+"&amount="+amount,
        function(ok, data){
            if(!ok){
                spinner.textContent = "❌ "+( data||"QR generation failed.");
                return;
            }
            /* display worker info */
            document.getElementById("qrName").textContent   = data.worker_name||"";
            document.getElementById("qrUpiId").textContent  = "📲 "+data.upi_id;
            /* set the <img> source to the base64 PNG */
            qrImg.onload = function(){
                spinner.style.display = "none";
                qrImg.style.display   = "block";
                setTimeout(function(){
                    document.getElementById("qrMarkWrap").style.display = "block";
                }, 400);
            };
            qrImg.onerror = function(){
                spinner.textContent = "❌ Failed to load QR image.";
            };
            qrImg.src = "data:image/png;base64," + data.qr;
        }, true);
}

/* ─── MARK AS PAID ─────────────────────────── */
function pmMarkDone(){
    var body="worker_id="+PM.worker+"&work_id="+PM.work+"&amount="+PM.pendingAmt;
    _pmPost("/mark_payment_done", body, function(ok){
        if(ok){ pmClose(); location.reload(); }
        else alert("Failed to mark as paid. Please try again.");
    });
}

/* ─── FETCH HELPER ─────────────────────────── */
function _pmPost(url, body, cb, json){
    fetch(url, {
        method:"POST",
        headers:{"Content-Type":"application/x-www-form-urlencoded"},
        body: body
    })
    .then(function(r){ return json ? r.json() : r.text(); })
    .then(function(d){
        if(json) cb(!d.error, d.error ? d.error : d);
        else     cb(d==="success");
    })
    .catch(function(){ cb(false, "Network error. Please try again."); });
}

/* ─── LEGACY compat ────────────────────────── */
function closePayModal(){ pmClose(); }
function submitPayment(){ pmChoose("cash"); }

/* ─── EVENT LISTENERS ──────────────────────── */
document.addEventListener("DOMContentLoaded", function(){
    var modal = document.getElementById("payModal");
    if(modal) modal.addEventListener("click", function(e){ if(e.target===modal) pmClose(); });
    var inp = document.getElementById("pmAmount");
    if(inp){
        inp.addEventListener("keydown", function(e){ if(e.key==="Enter") pmChoose("cash"); });
        inp.addEventListener("input",   pmClearError);
    }
});
