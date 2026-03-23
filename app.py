"""
Ai-Dobot Platform Backend v3.0
Accounts: Private Doctors, Patients, Hospitals, Pharmacies
Features: Medicine upload, Shop, Regional doctor search, Personal doctor
DB: Neon PostgreSQL
"""
from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import psycopg2, psycopg2.extras, hashlib, secrets, string, random
from datetime import datetime, timedelta
import os, json

DB_URL = os.getenv("DATABASE_URL",
  "postgresql://neondb_owner:npg_AdjC2Un1YgPe@ep-fancy-pine-aite2ono-pooler.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
)

def get_conn():
    return psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)

def _hash(pw): return hashlib.sha256(pw.encode()).hexdigest()
def _gen_id(prefix): return prefix+'-'+''.join(random.choices(string.ascii_uppercase+string.digits, k=8))
def _tok(): return secrets.token_urlsafe(32)
def _bearer(h): return (h or "").replace("Bearer ","")

def _session(table, id_col, eid):
    tok = _tok(); exp = datetime.utcnow()+timedelta(days=7)
    conn=get_conn(); cur=conn.cursor()
    cur.execute(f"INSERT INTO {table} ({id_col},token,expires_at) VALUES (%s,%s,%s)",(eid,tok,exp))
    conn.commit(); cur.close(); conn.close(); return tok

def _verify(table, token):
    conn=get_conn(); cur=conn.cursor()
    cur.execute(f"SELECT * FROM {table} WHERE token=%s AND expires_at>NOW()",(token,))
    row=cur.fetchone(); cur.close(); conn.close()
    return dict(row) if row else None

def init_db():
    conn=get_conn(); cur=conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS hospitals (
        id SERIAL PRIMARY KEY, system_id TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
        country TEXT, city TEXT, district TEXT, address TEXT, phone TEXT,
        registration_no TEXT, created_at TIMESTAMPTZ DEFAULT NOW()
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS doctors (
        id SERIAL PRIMARY KEY, system_id TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
        specialty TEXT, country TEXT, city TEXT, district TEXT, phone TEXT,
        qualifications TEXT, bio TEXT, avatar TEXT DEFAULT '👨‍⚕️',
        hospital_id INTEGER REFERENCES hospitals(id) ON DELETE SET NULL,
        is_online BOOLEAN DEFAULT FALSE, is_public BOOLEAN DEFAULT TRUE,
        consultation_fee NUMERIC(10,2) DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT NOW()
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS patients (
        id SERIAL PRIMARY KEY, system_id TEXT UNIQUE NOT NULL,
        password_hash TEXT, name TEXT, email TEXT, phone TEXT,
        country TEXT, city TEXT, date_of_birth DATE,
        personal_doctor_id INTEGER REFERENCES doctors(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ DEFAULT NOW()
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS pharmacies (
        id SERIAL PRIMARY KEY, system_id TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
        country TEXT, city TEXT, district TEXT, address TEXT, phone TEXT,
        license_no TEXT, created_at TIMESTAMPTZ DEFAULT NOW()
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS medicines (
        id SERIAL PRIMARY KEY, pharmacy_id INTEGER REFERENCES pharmacies(id) ON DELETE CASCADE,
        name TEXT NOT NULL, brand TEXT, category TEXT, description TEXT,
        dosage TEXT, price NUMERIC(10,2) NOT NULL, stock INTEGER DEFAULT 0,
        image_url TEXT, requires_prescription BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMPTZ DEFAULT NOW()
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id SERIAL PRIMARY KEY, patient_id INTEGER REFERENCES patients(id) ON DELETE SET NULL,
        pharmacy_id INTEGER REFERENCES pharmacies(id) ON DELETE SET NULL,
        items JSONB NOT NULL, total NUMERIC(10,2) NOT NULL,
        status TEXT DEFAULT 'pending', delivery_address TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS patient_records (
        id SERIAL PRIMARY KEY, patient_id INTEGER REFERENCES patients(id) ON DELETE CASCADE,
        robot_record_id INTEGER, timestamp TIMESTAMPTZ DEFAULT NOW(),
        chief_complaint TEXT, medical_history TEXT,
        temperature FLOAT, heart_rate FLOAT, spo2 FLOAT,
        systolic INTEGER, diastolic INTEGER, pulse_bp INTEGER,
        bp_result TEXT, weight FLOAT, height FLOAT, bmi FLOAT,
        fatigue TEXT, emotion TEXT, raw_json JSONB
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS active_calls (
        id SERIAL PRIMARY KEY, call_id TEXT UNIQUE NOT NULL,
        patient_id TEXT, patient_name TEXT, symptom TEXT,
        doctor_id TEXT, status TEXT DEFAULT 'waiting',
        created_at TIMESTAMPTZ DEFAULT NOW()
    )""")
    # Sessions tables
    for t,col in [("doctor_sessions","doctor_id"),("hospital_sessions","hospital_id"),
                  ("patient_sessions","patient_id"),("pharmacy_sessions","pharmacy_id")]:
        ref = col.replace("_id","s")
        cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {t} (
            id SERIAL PRIMARY KEY,
            {col} INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL, expires_at TIMESTAMPTZ NOT NULL
        )""")
    conn.commit(); cur.close(); conn.close()

app = FastAPI(title="Ai-Dobot Platform v3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup(): init_db()

@app.get("/")
def root(): return {"status":"ok","platform":"Ai-Dobot v3.0"}

# ═══════════════════════════════════════════════════════════════
# DOCTORS
# ═══════════════════════════════════════════════════════════════
class DoctorReg(BaseModel):
    name:str; email:str; password:str
    specialty:Optional[str]=None; country:Optional[str]=None
    city:Optional[str]=None; district:Optional[str]=None
    phone:Optional[str]=None; qualifications:Optional[str]=None
    bio:Optional[str]=None; avatar:Optional[str]="👨‍⚕️"
    consultation_fee:Optional[float]=0

class LoginReq(BaseModel):
    email:str; password:str

@app.post("/api/doctors/register")
def doc_register(d:DoctorReg):
    sid=_gen_id("DOC"); conn=get_conn(); cur=conn.cursor()
    try:
        cur.execute("""INSERT INTO doctors
            (system_id,name,email,password_hash,specialty,country,city,district,phone,qualifications,bio,avatar,consultation_fee)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id,system_id""",
            (sid,d.name,d.email,_hash(d.password),d.specialty,d.country,d.city,d.district,
             d.phone,d.qualifications,d.bio,d.avatar,d.consultation_fee))
        row=cur.fetchone(); conn.commit()
        tok=_session("doctor_sessions","doctor_id",row["id"])
        return {"success":True,"system_id":row["system_id"],"token":tok}
    except psycopg2.errors.UniqueViolation:
        conn.rollback(); raise HTTPException(400,"Email already registered")
    finally: cur.close(); conn.close()

@app.post("/api/doctors/login")
def doc_login(d:LoginReq):
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT * FROM doctors WHERE email=%s AND password_hash=%s",(d.email,_hash(d.password)))
    doc=cur.fetchone(); cur.close(); conn.close()
    if not doc: raise HTTPException(401,"Invalid credentials")
    tok=_session("doctor_sessions","doctor_id",doc["id"])
    r=dict(doc); r.pop("password_hash",None)
    return {"success":True,"token":tok,"doctor":r}

@app.get("/api/doctors/me")
def doc_me(authorization:str=Header(None)):
    sess=_verify("doctor_sessions",_bearer(authorization))
    if not sess: raise HTTPException(401,"Unauthorized")
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT id,system_id,name,email,specialty,country,city,district,phone,qualifications,bio,avatar,hospital_id,is_online,is_public,consultation_fee,created_at FROM doctors WHERE id=%s",(sess["doctor_id"],))
    doc=cur.fetchone(); cur.close(); conn.close()
    if not doc: raise HTTPException(404,"Not found")
    return dict(doc)

@app.put("/api/doctors/me")
def doc_update(data:dict, authorization:str=Header(None)):
    sess=_verify("doctor_sessions",_bearer(authorization))
    if not sess: raise HTTPException(401,"Unauthorized")
    allowed=["name","specialty","country","city","district","phone","qualifications","bio","avatar","consultation_fee"]
    fields={k:v for k,v in data.items() if k in allowed}
    if not fields: raise HTTPException(400,"Nothing to update")
    q=",".join(f"{k}=%s" for k in fields)
    conn=get_conn(); cur=conn.cursor()
    cur.execute(f"UPDATE doctors SET {q} WHERE id=%s",(*fields.values(),sess["doctor_id"]))
    conn.commit(); cur.close(); conn.close()
    return {"success":True}

@app.post("/api/doctors/set-online")
def doc_online(authorization:str=Header(None)):
    sess=_verify("doctor_sessions",_bearer(authorization))
    if not sess: raise HTTPException(401,"Unauthorized")
    conn=get_conn(); cur=conn.cursor()
    cur.execute("UPDATE doctors SET is_online=TRUE WHERE id=%s RETURNING name",(sess["doctor_id"],))
    doc=cur.fetchone(); conn.commit(); cur.close(); conn.close()
    return {"success":True,"message":f"Dr. {doc['name']} is now online"}

@app.post("/api/doctors/set-offline")
def doc_offline(authorization:str=Header(None)):
    sess=_verify("doctor_sessions",_bearer(authorization))
    if not sess: raise HTTPException(401,"Unauthorized")
    conn=get_conn(); cur=conn.cursor()
    cur.execute("UPDATE doctors SET is_online=FALSE WHERE id=%s",(sess["doctor_id"],))
    conn.commit(); cur.close(); conn.close()
    return {"success":True}

# Public search — used by robot
@app.get("/api/doctors/online")
def docs_online(country:str=None, city:str=None, doctor_id:str=None):
    conn=get_conn(); cur=conn.cursor()
    if doctor_id:
        # Personal doctor — return that specific doctor regardless of region
        cur.execute("SELECT id,system_id,name,specialty,avatar,country,city,is_online FROM doctors WHERE system_id=%s",(doctor_id,))
        rows=[dict(r) for r in cur.fetchall()]
    else:
        q="SELECT id,system_id,name,specialty,avatar,country,city,is_online FROM doctors WHERE is_online=TRUE AND is_public=TRUE AND hospital_id IS NULL"
        p=[]
        if country: q+=" AND country ILIKE %s"; p.append(f"%{country}%")
        if city: q+=" AND city ILIKE %s"; p.append(f"%{city}%")
        cur.execute(q,p); rows=[dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"doctors":rows}

@app.get("/api/doctors/search")
def docs_search(country:str=None,city:str=None,name:str=None):
    conn=get_conn(); cur=conn.cursor()
    q="SELECT id,system_id,name,specialty,avatar,country,city,district,is_online,consultation_fee FROM doctors WHERE is_public=TRUE AND hospital_id IS NULL"
    p=[]
    if country: q+=" AND country ILIKE %s"; p.append(f"%{country}%")
    if city: q+=" AND city ILIKE %s"; p.append(f"%{city}%")
    if name: q+=" AND name ILIKE %s"; p.append(f"%{name}%")
    q+=" ORDER BY is_online DESC, name LIMIT 50"
    cur.execute(q,p); rows=[dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"doctors":rows}

@app.get("/api/doctors/patients")
def doc_patients(authorization:str=Header(None)):
    sess=_verify("doctor_sessions",_bearer(authorization))
    if not sess: raise HTTPException(401,"Unauthorized")
    conn=get_conn(); cur=conn.cursor()
    cur.execute("""SELECT pr.*,p.name as patient_name,p.system_id as patient_sys_id
        FROM patient_records pr LEFT JOIN patients p ON pr.patient_id=p.id
        ORDER BY pr.timestamp DESC LIMIT 100""")
    rows=[dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"patients":rows,"total":len(rows)}

# ═══════════════════════════════════════════════════════════════
# HOSPITALS
# ═══════════════════════════════════════════════════════════════
class HospReg(BaseModel):
    name:str; email:str; password:str
    country:Optional[str]=None; city:Optional[str]=None
    district:Optional[str]=None; address:Optional[str]=None
    phone:Optional[str]=None; registration_no:Optional[str]=None

@app.post("/api/hospitals/register")
def hosp_register(d:HospReg):
    sid=_gen_id("HSP"); conn=get_conn(); cur=conn.cursor()
    try:
        cur.execute("""INSERT INTO hospitals (system_id,name,email,password_hash,country,city,district,address,phone,registration_no)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id,system_id""",
            (sid,d.name,d.email,_hash(d.password),d.country,d.city,d.district,d.address,d.phone,d.registration_no))
        row=cur.fetchone(); conn.commit()
        tok=_session("hospital_sessions","hospital_id",row["id"])
        return {"success":True,"system_id":row["system_id"],"token":tok}
    except psycopg2.errors.UniqueViolation:
        conn.rollback(); raise HTTPException(400,"Email already registered")
    finally: cur.close(); conn.close()

@app.post("/api/hospitals/login")
def hosp_login(d:LoginReq):
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT * FROM hospitals WHERE email=%s AND password_hash=%s",(d.email,_hash(d.password)))
    h=cur.fetchone(); cur.close(); conn.close()
    if not h: raise HTTPException(401,"Invalid credentials")
    tok=_session("hospital_sessions","hospital_id",h["id"])
    r=dict(h); r.pop("password_hash",None)
    return {"success":True,"token":tok,"hospital":r}

@app.get("/api/hospitals/me")
def hosp_me(authorization:str=Header(None)):
    sess=_verify("hospital_sessions",_bearer(authorization))
    if not sess: raise HTTPException(401,"Unauthorized")
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT id,system_id,name,email,country,city,district,address,phone,registration_no,created_at FROM hospitals WHERE id=%s",(sess["hospital_id"],))
    h=cur.fetchone(); cur.close(); conn.close()
    return dict(h) if h else HTTPException(404,"Not found")

@app.get("/api/hospitals/doctors")
def hosp_doctors(authorization:str=Header(None)):
    sess=_verify("hospital_sessions",_bearer(authorization))
    if not sess: raise HTTPException(401,"Unauthorized")
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT id,system_id,name,specialty,avatar,country,city,is_online,created_at FROM doctors WHERE hospital_id=%s ORDER BY name",(sess["hospital_id"],))
    rows=[dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"doctors":rows}

@app.post("/api/hospitals/add-doctor")
def hosp_add_doctor(data:dict, authorization:str=Header(None)):
    sess=_verify("hospital_sessions",_bearer(authorization))
    if not sess: raise HTTPException(401,"Unauthorized")
    conn=get_conn(); cur=conn.cursor()
    cur.execute("UPDATE doctors SET hospital_id=%s,is_public=FALSE WHERE system_id=%s RETURNING name",(sess["hospital_id"],data.get("doctor_system_id","")))
    doc=cur.fetchone()
    if not doc: raise HTTPException(404,"Doctor not found")
    conn.commit(); cur.close(); conn.close()
    return {"success":True,"message":f"Dr. {doc['name']} added"}

@app.post("/api/hospitals/remove-doctor")
def hosp_remove_doctor(data:dict, authorization:str=Header(None)):
    sess=_verify("hospital_sessions",_bearer(authorization))
    if not sess: raise HTTPException(401,"Unauthorized")
    conn=get_conn(); cur=conn.cursor()
    cur.execute("UPDATE doctors SET hospital_id=NULL,is_public=TRUE WHERE system_id=%s AND hospital_id=%s RETURNING name",(data.get("doctor_system_id",""),sess["hospital_id"]))
    doc=cur.fetchone()
    if not doc: raise HTTPException(404,"Not found in your hospital")
    conn.commit(); cur.close(); conn.close()
    return {"success":True}

@app.get("/api/hospitals/{system_id}/doctors")
def hosp_doctors_public(system_id:str):
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT id FROM hospitals WHERE system_id=%s",(system_id,))
    h=cur.fetchone()
    if not h: raise HTTPException(404,"Hospital not found")
    cur.execute("SELECT id,system_id,name,specialty,avatar,country,city,is_online FROM doctors WHERE hospital_id=%s ORDER BY name",(h["id"],))
    rows=[dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"doctors":rows}

# ═══════════════════════════════════════════════════════════════
# PATIENTS
# ═══════════════════════════════════════════════════════════════
class PatientSetup(BaseModel):
    system_id:str; password:str
    name:Optional[str]=None; email:Optional[str]=None
    phone:Optional[str]=None; country:Optional[str]=None
    city:Optional[str]=None; date_of_birth:Optional[str]=None

class PatientLogin(BaseModel):
    system_id:str; password:str

@app.post("/api/patients/create-from-robot")
def patient_create(data:dict):
    sid=_gen_id("USR")
    conn=get_conn(); cur=conn.cursor()
    cur.execute("INSERT INTO patients (system_id) VALUES (%s) RETURNING id,system_id",(sid,))
    row=cur.fetchone()
    rid=data.get("robot_record_id")
    if rid:
        cur.execute("INSERT INTO patient_records (patient_id,robot_record_id,raw_json) VALUES (%s,%s,%s)",
                    (row["id"],rid,psycopg2.extras.Json(data.get("record",{}))))
    conn.commit(); cur.close(); conn.close()
    return {"success":True,"system_id":row["system_id"]}

@app.post("/api/patients/setup")
def patient_setup(d:PatientSetup):
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT id,password_hash FROM patients WHERE system_id=%s",(d.system_id,))
    u=cur.fetchone()
    if not u: raise HTTPException(404,"System ID not found. Complete a robot Q&A session first.")
    if u["password_hash"]: raise HTTPException(400,"Account already activated. Please log in.")
    dob=None
    if d.date_of_birth:
        try: dob=datetime.strptime(d.date_of_birth,"%Y-%m-%d").date()
        except: pass
    cur.execute("UPDATE patients SET password_hash=%s,name=%s,email=%s,phone=%s,country=%s,city=%s,date_of_birth=%s WHERE id=%s",
                (_hash(d.password),d.name,d.email,d.phone,d.country,d.city,dob,u["id"]))
    conn.commit()
    tok=_session("patient_sessions","patient_id",u["id"])
    cur.close(); conn.close()
    return {"success":True,"token":tok}

@app.post("/api/patients/login")
def patient_login(d:PatientLogin):
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT * FROM patients WHERE system_id=%s AND password_hash=%s",(d.system_id,_hash(d.password)))
    u=cur.fetchone(); cur.close(); conn.close()
    if not u: raise HTTPException(401,"Invalid system ID or password")
    tok=_session("patient_sessions","patient_id",u["id"])
    r=dict(u); r.pop("password_hash",None)
    return {"success":True,"token":tok,"patient":r}

@app.get("/api/patients/me")
def patient_me(authorization:str=Header(None)):
    sess=_verify("patient_sessions",_bearer(authorization))
    if not sess: raise HTTPException(401,"Unauthorized")
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT id,system_id,name,email,phone,country,city,date_of_birth,personal_doctor_id,created_at FROM patients WHERE id=%s",(sess["patient_id"],))
    u=cur.fetchone(); cur.close(); conn.close()
    return dict(u) if u else HTTPException(404,"Not found")

@app.get("/api/patients/records")
def patient_records(authorization:str=Header(None)):
    sess=_verify("patient_sessions",_bearer(authorization))
    if not sess: raise HTTPException(401,"Unauthorized")
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT * FROM patient_records WHERE patient_id=%s ORDER BY timestamp DESC",(sess["patient_id"],))
    rows=[dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"records":rows}

@app.post("/api/patients/set-personal-doctor")
def set_personal_doctor(data:dict, authorization:str=Header(None)):
    sess=_verify("patient_sessions",_bearer(authorization))
    if not sess: raise HTTPException(401,"Unauthorized")
    conn=get_conn(); cur=conn.cursor()
    doctor_sid=data.get("doctor_system_id","")
    cur.execute("SELECT id,name FROM doctors WHERE system_id=%s",(doctor_sid,))
    doc=cur.fetchone()
    if not doc: raise HTTPException(404,"Doctor not found")
    cur.execute("UPDATE patients SET personal_doctor_id=%s WHERE id=%s",(doc["id"],sess["patient_id"]))
    conn.commit(); cur.close(); conn.close()
    return {"success":True,"message":f"Dr. {doc['name']} set as your personal doctor"}

# ═══════════════════════════════════════════════════════════════
# PHARMACIES
# ═══════════════════════════════════════════════════════════════
class PharmReg(BaseModel):
    name:str; email:str; password:str
    country:Optional[str]=None; city:Optional[str]=None
    district:Optional[str]=None; address:Optional[str]=None
    phone:Optional[str]=None; license_no:Optional[str]=None

@app.post("/api/pharmacies/register")
def pharm_register(d:PharmReg):
    sid=_gen_id("PHM"); conn=get_conn(); cur=conn.cursor()
    try:
        cur.execute("""INSERT INTO pharmacies (system_id,name,email,password_hash,country,city,district,address,phone,license_no)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id,system_id""",
            (sid,d.name,d.email,_hash(d.password),d.country,d.city,d.district,d.address,d.phone,d.license_no))
        row=cur.fetchone(); conn.commit()
        tok=_session("pharmacy_sessions","pharmacy_id",row["id"])
        return {"success":True,"system_id":row["system_id"],"token":tok}
    except psycopg2.errors.UniqueViolation:
        conn.rollback(); raise HTTPException(400,"Email already registered")
    finally: cur.close(); conn.close()

@app.post("/api/pharmacies/login")
def pharm_login(d:LoginReq):
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT * FROM pharmacies WHERE email=%s AND password_hash=%s",(d.email,_hash(d.password)))
    p=cur.fetchone(); cur.close(); conn.close()
    if not p: raise HTTPException(401,"Invalid credentials")
    tok=_session("pharmacy_sessions","pharmacy_id",p["id"])
    r=dict(p); r.pop("password_hash",None)
    return {"success":True,"token":tok,"pharmacy":r}

@app.get("/api/pharmacies/me")
def pharm_me(authorization:str=Header(None)):
    sess=_verify("pharmacy_sessions",_bearer(authorization))
    if not sess: raise HTTPException(401,"Unauthorized")
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT id,system_id,name,email,country,city,address,phone,license_no,created_at FROM pharmacies WHERE id=%s",(sess["pharmacy_id"],))
    p=cur.fetchone(); cur.close(); conn.close()
    return dict(p) if p else HTTPException(404,"Not found")

# ── MEDICINES ──
class MedCreate(BaseModel):
    name:str; brand:Optional[str]=None; category:Optional[str]=None
    description:Optional[str]=None; dosage:Optional[str]=None
    price:float; stock:int=0; image_url:Optional[str]=None
    requires_prescription:bool=False

@app.post("/api/pharmacies/medicines")
def add_medicine(d:MedCreate, authorization:str=Header(None)):
    sess=_verify("pharmacy_sessions",_bearer(authorization))
    if not sess: raise HTTPException(401,"Unauthorized")
    conn=get_conn(); cur=conn.cursor()
    cur.execute("""INSERT INTO medicines (pharmacy_id,name,brand,category,description,dosage,price,stock,image_url,requires_prescription)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (sess["pharmacy_id"],d.name,d.brand,d.category,d.description,d.dosage,d.price,d.stock,d.image_url,d.requires_prescription))
    row=cur.fetchone(); conn.commit(); cur.close(); conn.close()
    return {"success":True,"medicine_id":row["id"]}

@app.get("/api/pharmacies/medicines")
def my_medicines(authorization:str=Header(None)):
    sess=_verify("pharmacy_sessions",_bearer(authorization))
    if not sess: raise HTTPException(401,"Unauthorized")
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT * FROM medicines WHERE pharmacy_id=%s ORDER BY name",(sess["pharmacy_id"],))
    rows=[dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"medicines":rows}

@app.put("/api/pharmacies/medicines/{med_id}")
def update_medicine(med_id:int, data:dict, authorization:str=Header(None)):
    sess=_verify("pharmacy_sessions",_bearer(authorization))
    if not sess: raise HTTPException(401,"Unauthorized")
    allowed=["name","brand","category","description","dosage","price","stock","image_url","requires_prescription"]
    fields={k:v for k,v in data.items() if k in allowed}
    if not fields: raise HTTPException(400,"Nothing to update")
    q=",".join(f"{k}=%s" for k in fields)
    conn=get_conn(); cur=conn.cursor()
    cur.execute(f"UPDATE medicines SET {q} WHERE id=%s AND pharmacy_id=%s",(*fields.values(),med_id,sess["pharmacy_id"]))
    conn.commit(); cur.close(); conn.close()
    return {"success":True}

@app.delete("/api/pharmacies/medicines/{med_id}")
def delete_medicine(med_id:int, authorization:str=Header(None)):
    sess=_verify("pharmacy_sessions",_bearer(authorization))
    if not sess: raise HTTPException(401,"Unauthorized")
    conn=get_conn(); cur=conn.cursor()
    cur.execute("DELETE FROM medicines WHERE id=%s AND pharmacy_id=%s",(med_id,sess["pharmacy_id"]))
    conn.commit(); cur.close(); conn.close()
    return {"success":True}

# ── SHOP (public) ──
@app.get("/api/shop/medicines")
def shop_medicines(country:str=None, category:str=None, search:str=None, page:int=1):
    conn=get_conn(); cur=conn.cursor()
    q="""SELECT m.*,ph.name as pharmacy_name,ph.city as pharmacy_city,ph.country as pharmacy_country
         FROM medicines m JOIN pharmacies ph ON m.pharmacy_id=ph.id WHERE m.stock>0"""
    p=[]
    if country: q+=" AND ph.country ILIKE %s"; p.append(f"%{country}%")
    if category: q+=" AND m.category ILIKE %s"; p.append(f"%{category}%")
    if search: q+=" AND (m.name ILIKE %s OR m.brand ILIKE %s)"; p.extend([f"%{search}%",f"%{search}%"])
    q+=f" ORDER BY m.name LIMIT 20 OFFSET {(page-1)*20}"
    cur.execute(q,p); rows=[dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"medicines":rows,"page":page}

@app.post("/api/shop/order")
def place_order(data:dict, authorization:str=Header(None)):
    sess=_verify("patient_sessions",_bearer(authorization))
    patient_id=sess["patient_id"] if sess else None
    items=data.get("items",[])
    if not items: raise HTTPException(400,"No items in order")
    total=sum(i.get("price",0)*i.get("qty",1) for i in items)
    pharmacy_id=items[0].get("pharmacy_id") if items else None
    conn=get_conn(); cur=conn.cursor()
    cur.execute("INSERT INTO orders (patient_id,pharmacy_id,items,total,delivery_address) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                (patient_id,pharmacy_id,psycopg2.extras.Json(items),total,data.get("delivery_address","")))
    row=cur.fetchone(); conn.commit(); cur.close(); conn.close()
    return {"success":True,"order_id":row["id"],"total":total}

# ═══════════════════════════════════════════════════════════════
# OLD DOCTOR ROUTES — used by existing doctor-app — DO NOT REMOVE
# ═══════════════════════════════════════════════════════════════

class DocSignin(BaseModel):
    name:str; specialty:str; avatar:Optional[str]="👨‍⚕️"
    token:str; doctor_id:Optional[str]=None

@app.post("/api/doctor/signin")
def old_doc_signin(d:DocSignin):
    sid = d.doctor_id or _gen_id("DOC")
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT id FROM doctors WHERE system_id=%s",(sid,))
    row=cur.fetchone()
    if row:
        cur.execute("UPDATE doctors SET name=%s,specialty=%s,avatar=%s,is_online=TRUE WHERE system_id=%s",
                    (d.name,d.specialty,d.avatar,sid))
    else:
        try:
            cur.execute("INSERT INTO doctors (system_id,name,email,password_hash,specialty,avatar,is_online,is_public) VALUES (%s,%s,%s,%s,%s,%s,TRUE,TRUE)",
                        (sid,d.name,f"{sid}@dobot.local","fcm_user",d.specialty,d.avatar))
        except: pass
    conn.commit(); cur.close(); conn.close()
    return {"doctor_id":sid,"status":"online"}

@app.post("/api/doctor/heartbeat")
def old_doc_heartbeat(data:dict):
    did=data.get("doctor_id","")
    conn=get_conn(); cur=conn.cursor()
    cur.execute("UPDATE doctors SET is_online=TRUE WHERE system_id=%s",(did,))
    conn.commit(); cur.close(); conn.close()
    return {"ok":True}

@app.post("/api/doctor/signout")
def old_doc_signout(data:dict):
    did=data.get("doctor_id","")
    conn=get_conn(); cur=conn.cursor()
    cur.execute("UPDATE doctors SET is_online=FALSE WHERE system_id=%s",(did,))
    conn.commit(); cur.close(); conn.close()
    return {"ok":True}

@app.get("/api/calls/pending/{doctor_id}")
def calls_pending_for_doctor(doctor_id:str):
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT * FROM active_calls WHERE status='waiting' AND (doctor_id=%s OR doctor_id IS NULL) ORDER BY created_at",(doctor_id,))
    rows=[dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"calls":rows}

@app.delete("/api/calls/pending/{call_id}")
def ack_call(call_id:str):
    conn=get_conn(); cur=conn.cursor()
    cur.execute("UPDATE active_calls SET status='acknowledged' WHERE call_id=%s",(call_id,))
    conn.commit(); cur.close(); conn.close()
    return {"ok":True}

@app.get("/api/calls/ended/{call_id}")
def call_ended_check(call_id:str):
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT status FROM active_calls WHERE call_id=%s",(call_id,))
    row=cur.fetchone(); cur.close(); conn.close()
    if not row: return {"ended":True}
    return {"ended": row["status"] in ("ended","ended_by_patient")}

@app.post("/api/calls/end/{call_id}")
def call_end_by_id(call_id:str):
    conn=get_conn(); cur=conn.cursor()
    cur.execute("UPDATE active_calls SET status='ended' WHERE call_id=%s",(call_id,))
    conn.commit(); cur.close(); conn.close()
    return {"ok":True}

# ═══════════════════════════════════════════════════════════════
# CALLS (new style)
# ═══════════════════════════════════════════════════════════════
class CallReq(BaseModel):
    patient_id:str; patient_name:str; symptom:str; doctor_id:Optional[str]=None

@app.post("/api/calls/initiate")
def call_initiate(d:CallReq):
    cid=secrets.token_urlsafe(8)
    conn=get_conn(); cur=conn.cursor()
    cur.execute("INSERT INTO active_calls (call_id,patient_id,patient_name,symptom,doctor_id) VALUES (%s,%s,%s,%s,%s)",
                (cid,d.patient_id,d.patient_name,d.symptom,d.doctor_id))
    conn.commit(); cur.close(); conn.close()
    return {"status":"initiated","call_id":cid,"room":f"room-{cid}"}

@app.get("/api/calls/pending")
def calls_pending():
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT * FROM active_calls WHERE status='waiting' ORDER BY created_at")
    rows=[dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"calls":rows}

@app.post("/api/calls/{call_id}/accept")
def call_accept(call_id:str):
    conn=get_conn(); cur=conn.cursor()
    cur.execute("UPDATE active_calls SET status='active' WHERE call_id=%s",(call_id,))
    conn.commit(); cur.close(); conn.close()
    return {"status":"accepted","room":f"room-{call_id}"}

@app.post("/api/calls/{call_id}/end")
def call_end(call_id:str):
    conn=get_conn(); cur=conn.cursor()
    cur.execute("DELETE FROM active_calls WHERE call_id=%s",(call_id,))
    conn.commit(); cur.close(); conn.close()
    return {"status":"ended"}

import psycopg2.extras
