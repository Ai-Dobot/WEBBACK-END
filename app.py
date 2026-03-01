from flask import Flask, request, jsonify
from flask_cors import CORS
import cloudinary
import cloudinary.uploader
import cloudinary.api
import os
import json
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ─── CLOUDINARY CONFIG ──────────────────────────────────────
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "aidoBot2026!")
DATABASE_URL   = os.getenv("DATABASE_URL")

# ─── DEFAULT DATA ────────────────────────────────────────────
DEFAULT_DATA = {
    "hero": {"robot_image": "", "headline": "Healthcare that comes to you."},
    "stats": {"accuracy": 98, "time_saved": 70, "daily_screenings": 500},
    "gallery": [],
    "reviews_video": [],
    "vreviews": [],
    "journey_steps": [
        {"title": "Patient Interaction & Face Detection",
         "desc": "AiDoBot greets the patient, detects their face, and begins a natural voice conversation in their preferred language.",
         "video": ""},
        {"title": "Health Data Collection",
         "desc": "The robot guides the patient through each measurement — weight, temperature, blood oxygen, heart rate, and blood pressure.",
         "video": ""},
        {"title": "AI Face Analysis",
         "desc": "The camera captures the patient's face. AI analyses emotion, pallor, fatigue, and age — all added automatically to the patient report.",
         "video": ""},
        {"title": "Doctor Consultation",
         "desc": "Live video call with a verified doctor. The doctor reviews the robot-generated report before speaking.",
         "video": ""},
        {"title": "Digital Prescription & Medicine Delivery",
         "desc": "The doctor issues a digital prescription. Patient orders medicine by voice — delivered to their home.",
         "video": ""},
        {"title": "Lifetime Health Record",
         "desc": "Every visit is stored securely. Patients access their full health history from any phone, at any time.",
         "video": ""}
    ],
    "team": [
        {"name": "Abdoukadir Jabbi",     "role": "Inventor & Lead Developer",    "bio": "B.Sc. Computer Science. Technical lead responsible for system architecture, AI integration, and hardware design of AiDoBot.", "photo": "", "emoji": "👨‍💻"},
        {"name": "Anushka",              "role": "AI & Systems Design",           "bio": "Leads AI modelling and intelligent interaction design, ensuring AiDoBot responds naturally and accurately in every situation.", "photo": "", "emoji": "👩‍🔬"},
        {"name": "Isatou I Jallow",      "role": "Accountant & Finance",          "bio": "Manages financial planning, budgeting, and compliance for sustainable and responsible growth.", "photo": "", "emoji": "👩‍💼"},
        {"name": "Nuna",                 "role": "Social Media & Communications", "bio": "Oversees brand communication, digital presence, and strategic messaging to share AiDoBot's mission worldwide.", "photo": "", "emoji": "📣"},
        {"name": "Dr. Shiv Kumar Verma", "role": "Mentor & Advisor",             "bio": "Professor providing expert guidance on AI development, system architecture, and academic rigor behind AiDoBot's intelligence.", "photo": "", "emoji": "🎓"},
        {"name": "Dr. Sanjay Kumar",     "role": "Mentor & Advisor",             "bio": "Associate Professor advising on medical applications, healthcare integration, and clinical accuracy of the robot's assessments.", "photo": "", "emoji": "⚕️"}
    ],
    "events": [
        {"title": "Healthcare Innovation Summit", "date": "Mar 2026", "location": "Banjul, The Gambia",         "desc": "AiDoBot will be demonstrating live patient screening and telemedicine capabilities at the region's largest annual health innovation summit.", "icon": "🏥", "image": ""},
        {"title": "University Tech Expo",         "date": "Apr 2026", "location": "New Delhi, India",           "desc": "Join us at the national university technology fair showcasing AI face analysis and multilingual health screening.", "icon": "🏫", "image": ""},
        {"title": "Community Health Outreach",    "date": "May 2026", "location": "Rural Communities, West Africa", "desc": "Free health screening drive — bringing AiDoBot directly to underserved rural communities.", "icon": "🌍", "image": ""}
    ],
    "announcements": [
        {"icon": "🚀", "date": "Feb 28, 2026", "title": "AiDoBot Version 2.0 Launched",
         "body": "AiDoBot V2.0 features enhanced AI face analysis, improved multilingual support for 12 new languages, and screening under 4 minutes."},
        {"icon": "🤝", "date": "Feb 15, 2026", "title": "New Partnership with Regional Health Ministry",
         "body": "AiDoBot has entered a formal partnership agreement to deploy robots across 20 public health centres. Rollout begins March 2026."},
        {"icon": "🏆", "date": "Jan 30, 2026", "title": "AiDoBot Wins Best Health Innovation Award",
         "body": "We are honoured to have received the Best Health Innovation Award at the Africa Tech Summit 2026."}
    ],
    "partners": [
        {"icon": "🏥", "name": "Regional Health Ministry", "type": "Government", "desc": "Official ministry partner supporting nationwide deployment."},
        {"icon": "🎓", "name": "University Research Lab",  "type": "Academic",   "desc": "Research partnership advancing AI diagnostic capabilities."},
        {"icon": "🌐", "name": "Global Health NGO",        "type": "NGO",        "desc": "Funding and deploying AiDoBot in underserved communities."},
        {"icon": "💊", "name": "PharmaCare Network",       "type": "Healthcare", "desc": "Pharmacy network enabling home medicine delivery."}
    ],
    "social": {"youtube": "#", "facebook": "#", "instagram": "#", "whatsapp": "https://wa.me/918800510790"},
    "latest_youtube": ""
}

# ─── DATABASE HELPERS ────────────────────────────────────────
def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS site_data (
                    key   TEXT PRIMARY KEY,
                    value JSONB NOT NULL
                );
            """)
            conn.commit()
            for key, value in DEFAULT_DATA.items():
                cur.execute("""
                    INSERT INTO site_data (key, value)
                    VALUES (%s, %s)
                    ON CONFLICT (key) DO NOTHING;
                """, (key, json.dumps(value)))
            conn.commit()

def db_get(key):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM site_data WHERE key = %s;", (key,))
            row = cur.fetchone()
            return row[0] if row else None

def db_set(key, value):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO site_data (key, value)
                VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
            """, (key, json.dumps(value)))
            conn.commit()

def load_all_data():
    result = dict(DEFAULT_DATA)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT key, value FROM site_data;")
            for key, value in cur.fetchall():
                result[key] = value
    return result

# ─── PUBLIC ROUTES ───────────────────────────────────────────

@app.route("/api/data", methods=["GET"])
def get_data():
    try:
        return jsonify(load_all_data())
    except Exception as e:
        print("DB error GET /api/data:", e)
        return jsonify(DEFAULT_DATA)

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "storage": "neon+cloudinary"})

# ─── ADMIN ROUTES ────────────────────────────────────────────

@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    body = request.json or {}
    if body.get("password") == ADMIN_PASSWORD:
        return jsonify({"ok": True, "token": "admin-token-aidoBot"})
    return jsonify({"ok": False, "message": "Wrong password"}), 401

def require_admin():
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    return token == "admin-token-aidoBot"

@app.route("/api/admin/upload", methods=["POST"])
def upload_media():
    if not require_admin():
        return jsonify({"error": "Unauthorized"}), 401
    section       = request.form.get("section", "general")
    resource_type = request.form.get("resource_type", "image")
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file   = request.files["file"]
    result = cloudinary.uploader.upload(
        file,
        folder=f"aidoBot/{section}",
        resource_type=resource_type,
        overwrite=False
    )
    return jsonify({
        "url":           result["secure_url"],
        "public_id":     result["public_id"],
        "resource_type": resource_type
    })

@app.route("/api/admin/update", methods=["POST"])
def update_data():
    if not require_admin():
        return jsonify({"error": "Unauthorized"}), 401
    body    = request.json or {}
    section = body.get("section")
    payload = body.get("data")
    if section is None or payload is None:
        return jsonify({"error": "Missing section or data"}), 400
    try:
        db_set(section, payload)
        return jsonify({"ok": True})
    except Exception as e:
        print("DB error on update:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/contact", methods=["POST"])
def contact():
    body = request.json or {}
    print("Contact form:", body)
    return jsonify({"ok": True, "message": "Message received!"})

# ─── STARTUP ─────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
else:
    try:
        init_db()
        print("✅ Neon DB initialized")
    except Exception as e:
        print("❌ DB init error:", e)
