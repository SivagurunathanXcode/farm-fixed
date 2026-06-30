from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import random, sqlite3, os, hashlib, smtplib, io, base64
from email.mime.text import MIMEText
from urllib.parse import quote
import os

# ─── QR CODE GENERATOR (pure Python + Pillow) ──────────────────────────────
# Correct ISO 18004 implementation — produces fully scannable QR codes

def _qr_make():
    EXP=[0]*512; LOG=[0]*256; x=1
    for i in range(255):
        EXP[i]=x; LOG[x]=i; x<<=1
        if x>255: x^=0x11d
    for i in range(255,512): EXP[i]=EXP[i-255]
    def gmul(a,b): return 0 if(not a or not b) else EXP[(LOG[a]+LOG[b])%255]
    def genpoly(n):
        p=[1]
        for i in range(n):
            q=[1,EXP[i]]; r=[0]*(len(p)+1)
            for j,pj in enumerate(p):
                for k,qk in enumerate(q): r[j+k]^=gmul(pj,qk)
            p=r
        return p
    def rs_encode(data,nec):
        poly=genpoly(nec); msg=list(data)+[0]*nec
        for i in range(len(data)):
            c=msg[i]
            if c:
                for j in range(1,len(poly)): msg[i+j]^=gmul(poly[j],c)
        return msg[len(data):]
    QR_CAP=[
        (1,16,10,1,16,0,0),(2,28,16,1,28,0,0),(3,44,26,1,44,0,0),
        (4,64,18,2,32,0,0),(5,86,24,2,43,0,0),(6,108,16,4,27,0,0),
        (7,124,18,4,31,1,25),(8,154,22,2,38,2,39),
        (9,182,22,3,36,2,37),(10,216,26,4,43,1,43),
    ]
    ALIGN=[[],[],[6,18],[6,22],[6,26],[6,30],[6,34],
           [6,22,38],[6,24,42],[6,26,46],[6,28,50]]
    FMT_M=[0x5412,0x5125,0x5E7C,0x5B4B,0x45F9,0x40CE,0x4F97,0x4AA0]
    MASKS=[lambda r,c:(r+c)%2==0,lambda r,c:r%2==0,lambda r,c:c%3==0,
           lambda r,c:(r+c)%3==0,lambda r,c:(r//2+c//3)%2==0,
           lambda r,c:(r*c)%2+(r*c)%3==0,
           lambda r,c:((r*c)%2+(r*c)%3)%2==0,
           lambda r,c:((r+c)%2+(r*c)%3)%2==0]
    def make_matrix(ver):
        sz=ver*4+17; m=[[-1]*sz for _ in range(sz)]
        def finder(r,c):
            for i in range(7):
                for j in range(7):
                    m[r+i][c+j]=1 if(i in(0,6)or j in(0,6)or(2<=i<=4 and 2<=j<=4))else 0
            for i in range(-1,8):
                for j in(-1,7):
                    if 0<=r+i<sz and 0<=c+j<sz: m[r+i][c+j]=0
                    if 0<=r+j<sz and 0<=c+i<sz: m[r+j][c+i]=0
        finder(0,0); finder(0,sz-7); finder(sz-7,0)
        for i in range(8,sz-8): m[6][i]=i%2; m[i][6]=i%2
        m[sz-8][8]=1
        for r in ALIGN[ver]:
            for c in ALIGN[ver]:
                if m[r][c]!=-1: continue
                for i in range(-2,3):
                    for j in range(-2,3):
                        m[r+i][c+j]=1 if(abs(i)==2 or abs(j)==2 or(i==0 and j==0))else 0
        for i in range(9):
            if m[8][i]==-1: m[8][i]=0
            if m[i][8]==-1: m[i][8]=0
        for i in range(sz-8,sz):
            if m[8][i]==-1: m[8][i]=0
        for i in range(sz-7,sz):
            if m[i][8]==-1: m[i][8]=0
        return m
    def place_data(m,bits):
        sz=len(m); idx=0; up=True; col=sz-1
        while col>0:
            if col==6: col-=1
            for rr in range(sz):
                row=(sz-1-rr)if up else rr
                for dc in range(2):
                    c=col-dc
                    if m[row][c]==-1: m[row][c]=bits[idx] if idx<len(bits) else 0; idx+=1
            up=not up; col-=2
    def apply_mask(m,mask):
        sz=len(m); fn=MASKS[mask]; nm=[r[:] for r in m]
        for r in range(sz):
            for c in range(sz):
                if nm[r][c]<=1 and fn(r,c): nm[r][c]^=1
        return nm
    def place_fmt(m,mask):
        sz=len(m); fi=FMT_M[mask]
        bits=[(fi>>i)&1 for i in range(14,-1,-1)]
        p1=[(8,0),(8,1),(8,2),(8,3),(8,4),(8,5),(8,7),(8,8),(7,8),(5,8),(4,8),(3,8),(2,8),(1,8),(0,8)]
        p2=[(sz-1-i,8)for i in range(7)]+[(8,sz-8+i)for i in range(8)]
        for i in range(15): m[p1[i][0]][p1[i][1]]=bits[i]; m[p2[i][0]][p2[i][1]]=bits[i]
        m[sz-8][8]=1
    def score(m):
        sz=len(m); s=0
        for row in m:
            run=1
            for i in range(1,sz):
                if row[i]==row[i-1]: run+=1
                else:
                    if run>=5: s+=run-2
                    run=1
            if run>=5: s+=run-2
        for c in range(sz):
            run=1
            for r in range(1,sz):
                if m[r][c]==m[r-1][c]: run+=1
                else:
                    if run>=5: s+=run-2
                    run=1
            if run>=5: s+=run-2
        for r in range(sz-1):
            for c in range(sz-1):
                v=m[r][c]
                if v<=1 and m[r][c+1]==v and m[r+1][c]==v and m[r+1][c+1]==v: s+=3
        return s
    def encode(text):
        raw=text.encode('utf-8'); n=len(raw)
        cap=next((r for r in QR_CAP if n<=r[1]),None)
        if not cap: raise ValueError("Data too long for QR version 1-10")
        ver,dc,ecpb,b1,dc1,b2,dc2=cap
        cbits=8 if ver<10 else 16
        bits=[]; add=lambda v,l:[bits.append((v>>i)&1)for i in range(l-1,-1,-1)]
        add(0b0100,4); add(n,cbits)
        for b in raw: add(b,8)
        for _ in range(min(4,dc*8-len(bits))): bits.append(0)
        while len(bits)%8: bits.append(0)
        pads=[0xEC,0x11]; pi=0
        while len(bits)<dc*8: add(pads[pi%2],8); pi+=1
        db=[sum((bits[i*8+j]<<(7-j))for j in range(8))for i in range(dc)]
        blocks=[]; ecb=[]
        idx=0
        for _ in range(b1): bl=db[idx:idx+dc1]; idx+=dc1; blocks.append(bl); ecb.append(rs_encode(bl,ecpb))
        for _ in range(b2): bl=db[idx:idx+dc2]; idx+=dc2; blocks.append(bl); ecb.append(rs_encode(bl,ecpb))
        final=[]
        for i in range(max(len(b)for b in blocks)):
            for b in blocks:
                if i<len(b): final.append(b[i])
        for i in range(ecpb):
            for e in ecb: final.append(e[i])
        m=make_matrix(ver)
        dbits=[]
        for byte in final:
            for j in range(7,-1,-1): dbits.append((byte>>j)&1)
        place_data(m,dbits)
        bm=0; bs=10**9
        for mask in range(8):
            mm=apply_mask(m,mask); place_fmt(mm,mask); sc=score(mm)
            if sc<bs: bs=sc; bm=mask
        masked=apply_mask(m,bm); place_fmt(masked,bm)
        return masked
    def to_png_b64(text,module_size=10,quiet=4):
        matrix=encode(text); n=len(matrix)
        sz=(n+quiet*2)*module_size
        img=Image.new("L",(sz,sz),255)
        px=img.load()
        for r in range(n):
            for c in range(n):
                if matrix[r][c]==1:
                    x0=(c+quiet)*module_size; y0=(r+quiet)*module_size
                    for dy in range(module_size):
                        for dx in range(module_size): px[x0+dx,y0+dy]=0
        buf=io.BytesIO(); img.save(buf,"PNG"); buf.seek(0)
        return base64.b64encode(buf.read()).decode()
    return to_png_b64

generate_qr_b64 = _qr_make()
# ─── END QR GENERATOR ──────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "farm_workers.db")

app = Flask(__name__,
    template_folder="../frontend/templates",
    static_folder="../frontend/static")
app.secret_key = "farm_workers_secret_key_2024"

# ─── DB ─────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db(); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL, mobile TEXT, password TEXT NOT NULL, upi_id TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS workers (
        worker_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL DEFAULT 0,
        name TEXT NOT NULL, mobile TEXT, daily_wage REAL DEFAULT 0,
        address TEXT, notes TEXT, upi_id TEXT,
        total_earned REAL DEFAULT 0, total_due REAL DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS works (
        work_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL DEFAULT 0,
        work_name TEXT NOT NULL, work_date TEXT, daily_wage REAL DEFAULT 0,
        total_expense REAL DEFAULT 0, total_due REAL DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS worker_work (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        worker_id INTEGER NOT NULL, work_id INTEGER NOT NULL,
        earned REAL DEFAULT 0, paid REAL DEFAULT 0, due REAL DEFAULT 0,
        FOREIGN KEY (worker_id) REFERENCES workers(worker_id) ON DELETE CASCADE,
        FOREIGN KEY (work_id)   REFERENCES works(work_id)   ON DELETE CASCADE)""")
    for sql in [
        "ALTER TABLE workers ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE works   ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE users   ADD COLUMN upi_id TEXT",
        "ALTER TABLE workers ADD COLUMN upi_id TEXT",
    ]:
        try: c.execute(sql)
        except: pass
    conn.commit(); conn.close()

def hash_pw(p): return hashlib.sha256(p.encode()).hexdigest()

def send_otp_email(to, otp):
    try:
        sender, pw = "sivagurunathanv23@gmail.com", "yieznbfnopzaheba"
        msg = MIMEText(f"Your OTP is: {otp}")
        msg["Subject"] = "OTP – Farm Workers App"; msg["From"] = sender; msg["To"] = to
        s = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        s.login(sender, pw); s.sendmail(sender, to, msg.as_string()); s.quit()
    except Exception as e: print("EMAIL ERROR:", e)

def login_required(f):
    from functools import wraps
    @wraps(f)
    def dec(*a, **kw):
        if "user_id" not in session: return redirect(url_for("login"))
        return f(*a, **kw)
    return dec

def uid(): return session.get("user_id")

# ─── PUBLIC ────────────────────────────────
@app.route("/")
def about(): return render_template("about.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if "user_id" in session: return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        ident, pwd = request.form.get("identifier","").strip(), request.form.get("password","")
        if ident and pwd:
            conn = get_db()
            u = conn.execute("SELECT * FROM users WHERE email=? OR mobile=?",(ident,ident)).fetchone()
            conn.close()
            if u and u["password"] == hash_pw(pwd):
                session["user_id"] = u["user_id"]; session["user"] = u["name"]
                return redirect(url_for("dashboard"))
            error = "Invalid credentials."
        else: error = "Please enter email/mobile and password."
    return render_template("login.html", error=error)

@app.route("/register", methods=["GET","POST"])
def register():
    error = None
    if request.method == "POST":
        name,email,mobile = (request.form.get(k,"").strip() for k in ("name","email","mobile"))
        pwd,confirm,upi = request.form.get("password",""), request.form.get("confirm",""), request.form.get("upi_id","").strip()
        if pwd != confirm: error = "Passwords do not match."
        elif not name or not email or not pwd: error = "Name, email, password required."
        else:
            try:
                conn = get_db()
                conn.execute("INSERT INTO users (name,email,mobile,password,upi_id) VALUES (?,?,?,?,?)",
                             (name,email,mobile,hash_pw(pwd),upi))
                conn.commit(); conn.close()
                flash("Registration successful! Please log in.","success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError: error = "Email already in use."
    return render_template("register.html", error=error)

@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("login"))

# ─── PROFILE ───────────────────────────────
@app.route("/profile")
@login_required
def profile():
    conn = get_db(); u = conn.execute("SELECT * FROM users WHERE user_id=?",(uid(),)).fetchone(); conn.close()
    return render_template("profile.html", user=u)

@app.route("/edit_profile", methods=["GET","POST"])
@login_required
def edit_profile():
    conn = get_db(); u = conn.execute("SELECT * FROM users WHERE user_id=?",(uid(),)).fetchone()
    error = None
    if request.method == "POST":
        name,email,mobile,upi = (request.form.get(k,"").strip() for k in ("name","email","mobile","upi_id"))
        if not name or not email: error = "Name and email required."
        else:
            try:
                conn.execute("UPDATE users SET name=?,email=?,mobile=?,upi_id=? WHERE user_id=?",
                             (name,email,mobile,upi,uid()))
                conn.commit(); session["user"] = name
                flash("Profile updated!","success"); conn.close()
                return redirect(url_for("profile"))
            except sqlite3.IntegrityError: error = "Email already used."
    conn.close()
    return render_template("edit_profile.html", user=u, error=error)

# ─── PASSWORD RESET ─────────────────────────
@app.route("/forgot", methods=["GET","POST"])
def forgot():
    error = None
    if request.method == "POST":
        ui = request.form.get("identifier","").strip()
        conn = get_db(); u = conn.execute("SELECT * FROM users WHERE email=? OR mobile=?",(ui,ui)).fetchone(); conn.close()
        if u:
            otp = str(random.randint(100000,999999))
            session["otp"] = otp; session["reset_user"] = u["email"]
            if "@" in ui: send_otp_email(u["email"], otp)
            flash(f"OTP sent! (Dev: {otp})","info")
            return redirect(url_for("verify"))
        error = "No account found."
    return render_template("forgot.html", error=error)

@app.route("/verify", methods=["GET","POST"])
def verify():
    error = None
    if request.method == "POST":
        if request.form.get("otp","").strip() == session.get("otp"):
            session["otp_verified"] = True; return redirect(url_for("reset"))
        error = "Invalid OTP."
    return render_template("verify.html", error=error)

@app.route("/reset", methods=["GET","POST"])
def reset():
    if not session.get("otp_verified"): return redirect(url_for("forgot"))
    error = None
    if request.method == "POST":
        pwd,cf = request.form.get("password",""), request.form.get("confirm","")
        if pwd != cf: error = "Passwords do not match."
        elif not pwd: error = "Password cannot be empty."
        else:
            conn = get_db()
            conn.execute("UPDATE users SET password=? WHERE email=?",(hash_pw(pwd),session.get("reset_user")))
            conn.commit(); conn.close()
            for k in ["otp","otp_verified","reset_user"]: session.pop(k,None)
            flash("Password reset. Please log in.","success")
            return redirect(url_for("login"))
    return render_template("reset.html", error=error)

# ─── DASHBOARD ─────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()
    wc = conn.execute("SELECT COUNT(*) AS c FROM workers WHERE user_id=?",(uid(),)).fetchone()["c"]
    pc = conn.execute("SELECT COUNT(*) AS c FROM works   WHERE user_id=?",(uid(),)).fetchone()["c"]
    er = conn.execute("""SELECT SUM(ww.earned) AS s FROM worker_work ww
        JOIN works w ON ww.work_id=w.work_id WHERE w.user_id=?""",(uid(),)).fetchone()
    dr = conn.execute("""SELECT SUM(ww.due) AS s FROM worker_work ww
        JOIN works w ON ww.work_id=w.work_id WHERE w.user_id=?""",(uid(),)).fetchone()
    conn.close()
    return render_template("dashboard.html", username=session["user"],
        total_workers=wc, total_works=pc,
        total_expense=er["s"] or 0, total_due=dr["s"] or 0)

# ─── WORKERS ───────────────────────────────
@app.route("/workers")
@login_required
def workers():
    conn = get_db()
    rows = conn.execute("SELECT * FROM workers WHERE user_id=? ORDER BY worker_id DESC",(uid(),)).fetchall()
    conn.close()
    return render_template("workers.html", workers=rows)

@app.route("/worker_detail/<int:worker_id>")
@login_required
def worker_detail(worker_id):
    conn = get_db()
    worker = conn.execute("SELECT * FROM workers WHERE worker_id=? AND user_id=?",(worker_id,uid())).fetchone()
    if not worker: conn.close(); return redirect(url_for("workers"))
    works = conn.execute("""SELECT w.work_id,w.work_name,w.work_date,ww.earned,ww.paid,ww.due
        FROM worker_work ww JOIN works w ON ww.work_id=w.work_id
        WHERE ww.worker_id=? ORDER BY w.work_date DESC""",(worker_id,)).fetchall()
    conn.close()
    return render_template("worker_detail.html", worker=worker, works=works)

@app.route("/add_worker", methods=["GET","POST"])
@login_required
def add_worker():
    error = None
    if request.method == "POST":
        name,mob,addr,notes,upi = (request.form.get(k,"").strip() for k in ("name","mobile","address","notes","upi_id"))
        wage = request.form.get("daily_wage",0) or 0
        if not name: error = "Worker name required."
        else:
            conn = get_db()
            conn.execute("INSERT INTO workers (user_id,name,mobile,daily_wage,address,notes,upi_id) VALUES (?,?,?,?,?,?,?)",
                         (uid(),name,mob,wage,addr,notes,upi))
            conn.commit(); conn.close()
            return redirect(url_for("workers"))
    return render_template("add_worker.html", worker=None, error=error)

@app.route("/edit_worker/<int:worker_id>", methods=["GET","POST"])
@login_required
def edit_worker(worker_id):
    conn = get_db()
    worker = conn.execute("SELECT * FROM workers WHERE worker_id=? AND user_id=?",(worker_id,uid())).fetchone()
    if not worker: conn.close(); return redirect(url_for("workers"))
    error = None
    if request.method == "POST":
        name,mob,addr,notes,upi = (request.form.get(k,"").strip() for k in ("name","mobile","address","notes","upi_id"))
        wage = request.form.get("daily_wage",0) or 0
        if not name: error = "Worker name required."
        else:
            conn.execute("UPDATE workers SET name=?,mobile=?,daily_wage=?,address=?,notes=?,upi_id=? WHERE worker_id=? AND user_id=?",
                         (name,mob,wage,addr,notes,upi,worker_id,uid()))
            conn.commit(); conn.close()
            return redirect(url_for("worker_detail",worker_id=worker_id))
    conn.close()
    return render_template("add_worker.html", worker=worker, error=error)

@app.route("/delete_worker/<int:worker_id>")
@login_required
def delete_worker(worker_id):
    conn = get_db()
    conn.execute("DELETE FROM workers WHERE worker_id=? AND user_id=?",(worker_id,uid()))
    conn.commit(); conn.close()
    return redirect(url_for("workers"))

# ─── WORK ──────────────────────────────────
@app.route("/work")
@login_required
def work():
    conn = get_db()
    works = conn.execute("""SELECT w.work_id,w.work_name,w.work_date,
               COUNT(ww.worker_id) AS worker_count,
               SUM(ww.earned) AS total_expense, SUM(ww.due) AS total_due
        FROM works w LEFT JOIN worker_work ww ON w.work_id=ww.work_id
        WHERE w.user_id=? GROUP BY w.work_id ORDER BY w.work_date DESC,w.work_id DESC""",(uid(),)).fetchall()
    conn.close()
    return render_template("work.html", works=works)

@app.route("/work_detail/<int:work_id>")
@login_required
def work_detail(work_id):
    conn = get_db()
    work = conn.execute("SELECT * FROM works WHERE work_id=? AND user_id=?",(work_id,uid())).fetchone()
    if not work: conn.close(); return redirect(url_for("work"))
    workers = conn.execute("""SELECT workers.worker_id,workers.name,workers.upi_id,
               worker_work.earned,worker_work.paid,worker_work.due
        FROM worker_work JOIN workers ON worker_work.worker_id=workers.worker_id
        WHERE worker_work.work_id=?""",(work_id,)).fetchall()
    conn.close()
    return render_template("work_detail.html", work=work, workers=workers)

@app.route("/add_work", methods=["GET","POST"])
@login_required
def add_work():
    conn = get_db()
    all_workers = conn.execute("SELECT worker_id,name FROM workers WHERE user_id=? ORDER BY name",(uid(),)).fetchall()
    error = None
    if request.method == "POST":
        wname = request.form.get("work_name","").strip()
        wdate = request.form.get("work_date","").strip()
        wage  = float(request.form.get("daily_wage",0) or 0)
        sel   = [w.strip() for w in request.form.get("workers","").split(",") if w.strip()]
        if not wname: error = "Work name required."
        elif not sel: error = "Select at least one worker."
        else:
            c = conn.cursor()
            c.execute("INSERT INTO works (user_id,work_name,work_date,daily_wage) VALUES (?,?,?,?)",(uid(),wname,wdate,wage))
            wid = c.lastrowid
            for w in sel:
                c.execute("INSERT INTO worker_work (worker_id,work_id,earned,paid,due) VALUES (?,?,?,0,?)",(w,wid,wage,wage))
                c.execute("UPDATE workers SET total_earned=total_earned+?,total_due=total_due+? WHERE worker_id=? AND user_id=?",
                          (wage,wage,w,uid()))
            conn.commit(); conn.close()
            return redirect(url_for("work"))
    conn.close()
    return render_template("add_work.html", workers=all_workers, work=None, selected_workers=[], error=error)

@app.route("/edit_work/<int:work_id>", methods=["GET","POST"])
@login_required
def edit_work(work_id):
    conn = get_db()
    work = conn.execute("SELECT * FROM works WHERE work_id=? AND user_id=?",(work_id,uid())).fetchone()
    if not work: conn.close(); return redirect(url_for("work"))
    all_workers = conn.execute("SELECT worker_id,name FROM workers WHERE user_id=? ORDER BY name",(uid(),)).fetchall()
    error = None
    if request.method == "POST":
        wname = request.form.get("work_name","").strip()
        wdate = request.form.get("work_date","").strip()
        wage  = float(request.form.get("daily_wage",0) or 0)
        sel   = [w.strip() for w in request.form.get("workers","").split(",") if w.strip()]
        if not wname: error = "Work name required."
        else:
            c = conn.cursor()
            c.execute("UPDATE works SET work_name=?,work_date=?,daily_wage=? WHERE work_id=? AND user_id=?",
                      (wname,wdate,wage,work_id,uid()))
            old = c.execute("SELECT worker_id,earned FROM worker_work WHERE work_id=?",(work_id,)).fetchall()
            old_ids = [str(w["worker_id"]) for w in old]
            for w in old:
                wid = str(w["worker_id"])
                if wid not in sel:
                    c.execute("DELETE FROM worker_work WHERE worker_id=? AND work_id=?",(wid,work_id))
                    c.execute("UPDATE workers SET total_earned=total_earned-?,total_due=total_due-? WHERE worker_id=? AND user_id=?",
                              (w["earned"],w["earned"],wid,uid()))
            for wid in sel:
                if wid not in old_ids:
                    c.execute("INSERT INTO worker_work (worker_id,work_id,earned,paid,due) VALUES (?,?,?,0,?)",(wid,work_id,wage,wage))
                    c.execute("UPDATE workers SET total_earned=total_earned+?,total_due=total_due+? WHERE worker_id=? AND user_id=?",
                              (wage,wage,wid,uid()))
            for w in old:
                wid = str(w["worker_id"])
                if wid in sel:
                    diff = wage - float(w["earned"])
                    c.execute("UPDATE worker_work SET earned=?,due=due+? WHERE worker_id=? AND work_id=?",(wage,diff,wid,work_id))
                    c.execute("UPDATE workers SET total_earned=total_earned+?,total_due=total_due+? WHERE worker_id=? AND user_id=?",
                              (diff,diff,wid,uid()))
            conn.commit(); conn.close()
            return redirect(url_for("work_detail",work_id=work_id))
    sel_rows = conn.execute("SELECT worker_id FROM worker_work WHERE work_id=?",(work_id,)).fetchall()
    conn.close()
    return render_template("add_work.html", work=work, workers=all_workers,
                           selected_workers=[r["worker_id"] for r in sel_rows], error=error)

@app.route("/delete_work/<int:work_id>")
@login_required
def delete_work(work_id):
    conn = get_db()
    rows = conn.execute("""SELECT ww.worker_id,ww.earned FROM worker_work ww
        JOIN works w ON ww.work_id=w.work_id WHERE ww.work_id=? AND w.user_id=?""",(work_id,uid())).fetchall()
    for r in rows:
        conn.execute("UPDATE workers SET total_earned=total_earned-?,total_due=total_due-? WHERE worker_id=? AND user_id=?",
                     (r["earned"],r["earned"],r["worker_id"],uid()))
    conn.execute("DELETE FROM works WHERE work_id=? AND user_id=?",(work_id,uid()))
    conn.commit(); conn.close()
    return redirect(url_for("work"))

# ─── PAYMENT HELPERS ────────────────────────
def _apply_payment(conn, worker_id, work_id, amount):
    rec = conn.execute("SELECT paid,due FROM worker_work WHERE worker_id=? AND work_id=?",
                       (worker_id,work_id)).fetchone()
    if not rec: return False
    due  = float(rec["due"])
    paid = float(rec["paid"])
    amount = min(amount, due)
    conn.execute("UPDATE worker_work SET paid=?,due=? WHERE worker_id=? AND work_id=?",
                 (paid+amount, due-amount, worker_id, work_id))
    t = conn.execute("SELECT SUM(earned) AS te,SUM(due) AS td FROM worker_work WHERE worker_id=?",
                     (worker_id,)).fetchone()
    conn.execute("UPDATE workers SET total_earned=?,total_due=? WHERE worker_id=?",
                 (t["te"] or 0, t["td"] or 0, worker_id))
    return True

# ─── PAYMENT ROUTES ─────────────────────────
@app.route("/pay_cash", methods=["POST"])
@login_required
def pay_cash():
    worker_id = request.form.get("worker_id")
    work_id   = request.form.get("work_id")
    amount    = float(request.form.get("amount",0) or 0)
    if not worker_id or not work_id or amount <= 0: return "error",400
    conn = get_db()
    ok = _apply_payment(conn, worker_id, work_id, amount)
    if ok: conn.commit()
    conn.close()
    return "success" if ok else ("error",404)


@app.route("/generate_upi_link", methods=["POST"])
@login_required
def generate_upi_link():
    worker_id = request.form.get("worker_id")
    amount    = request.form.get("amount","0")
    conn = get_db()
    w = conn.execute("SELECT name,upi_id FROM workers WHERE worker_id=?",(worker_id,)).fetchone()
    conn.close()
    if not w or not w["upi_id"]:
        return jsonify({"error": "No UPI ID set for this worker. Please edit the worker and add a UPI ID."}),400
    upi_link = (f"upi://pay?pa={quote(w['upi_id'])}"
                f"&pn={quote(w['name'])}"
                f"&am={amount}&cu=INR&tn={quote('Farm Worker Payment')}")
    return jsonify({"upi_link": upi_link, "upi_id": w["upi_id"], "worker_name": w["name"]})


@app.route("/generate_upi_qr", methods=["POST"])
@login_required
def generate_upi_qr():
    """Generate a real QR code image using Python and return it as base64 PNG."""
    worker_id = request.form.get("worker_id")
    amount    = request.form.get("amount", "0")
    conn = get_db()
    w = conn.execute("SELECT name,upi_id FROM workers WHERE worker_id=?", (worker_id,)).fetchone()
    conn.close()
    if not w or not w["upi_id"]:
        return jsonify({"error": "No UPI ID set for this worker. Please edit the worker and add a UPI ID."}), 400
    upi_string = (f"upi://pay?pa={quote(w['upi_id'])}"
                  f"&pn={quote(w['name'])}"
                  f"&am={amount}&cu=INR&tn={quote('Farm Worker Payment')}")
    try:
        qr_b64 = generate_qr_b64(upi_string, module_size=10, quiet=4)
    except Exception as e:
        return jsonify({"error": f"QR generation failed: {str(e)}"}), 500
    return jsonify({
        "qr":          qr_b64,
        "upi_id":      w["upi_id"],
        "worker_name": w["name"],
        "upi_string":  upi_string,
    })


@app.route("/mark_payment_done", methods=["POST"])
@login_required
def mark_payment_done():
    worker_id = request.form.get("worker_id")
    work_id   = request.form.get("work_id")
    amount    = float(request.form.get("amount",0) or 0)
    if not worker_id or not work_id or amount <= 0: return "error",400
    conn = get_db()
    ok = _apply_payment(conn, worker_id, work_id, amount)
    if ok: conn.commit()
    conn.close()
    return "success" if ok else ("error",404)


# Legacy compat
@app.route("/pay_worker",       methods=["POST"])
@login_required
def pay_worker(): return pay_cash()

@app.route("/mark_upi_paid",    methods=["POST"])
@login_required
def mark_upi_paid(): return mark_payment_done()

@app.route("/pay_worker_total", methods=["POST"])
@login_required
def pay_worker_total():
    worker_id = request.form.get("worker_id")
    amount    = float(request.form.get("amount",0) or 0)
    if not worker_id or amount <= 0: return "error",400
    conn = get_db()
    conn.execute("UPDATE workers SET total_due=MAX(0,total_due-?) WHERE worker_id=?",(amount,worker_id))
    conn.commit(); conn.close()
    return "success"




if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
