from flask import Flask, request, jsonify
from flask_cors import CORS
import cloudinary
import cloudinary.uploader
import cloudinary.api
import os
import json
import urllib.request
import urllib.error
import pg8000.native
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "aidoBot2026!")
DATABASE_URL   = os.getenv("DATABASE_URL", "")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "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")
GROQ_MODEL     = "llama-3.3-70b-versatile" 

# ─── DEFAULT DATA ────────────────────────────────────────────
DEFAULT_DATA = {
    "hero": {"robot_image": "", "headline": "Healthcare that comes to you."},
    "hero_images": [],
    "stats": {"accuracy": 98, "time_saved": 70, "daily_screenings": 500},
    "gallery": [],
    "reviews_video": [],
    "vreviews": [],
    "journey_steps": [
        {"title": "Patient Interaction & Face Detection",
         "desc": "AiDoBot greets the patient, detects their face, and begins a natural voice conversation in their preferred language.", "video": ""},
        {"title": "Health Data Collection",
         "desc": "The robot guides the patient through each measurement — weight, temperature, blood oxygen, heart rate, and blood pressure.", "video": ""},
        {"title": "AI Face Analysis",
         "desc": "The camera captures the patient's face. AI analyses emotion, pallor, fatigue, and age — all added automatically to the patient report.", "video": ""},
        {"title": "Doctor Consultation",
         "desc": "Live video call with a verified doctor. The doctor reviews the robot-generated report before speaking.", "video": ""},
        {"title": "Digital Prescription & Medicine Delivery",
         "desc": "The doctor issues a digital prescription. Patient orders medicine by voice — delivered to their home.", "video": ""},
        {"title": "Lifetime Health Record",
         "desc": "Every visit is stored securely. Patients access their full health history from any phone, at any time.", "video": ""}
    ],
    "team": [
        {"name": "Abdoukadir Jabbi",     "role": "Inventor & Lead Developer",    "bio": "B.Sc. Computer Science. Technical lead responsible for system architecture, AI integration, and hardware design of AiDoBot.", "photo": "", "emoji": "👨‍💻"},
        {"name": "Anushka",              "role": "AI & Systems Design",           "bio": "Leads AI modelling and intelligent interaction design, ensuring AiDoBot responds naturally and accurately in every situation.", "photo": "", "emoji": "👩‍🔬"},
        {"name": "Isatou I Jallow",      "role": "Accountant & Finance",          "bio": "Manages financial planning, budgeting, and compliance for sustainable and responsible growth.", "photo": "", "emoji": "👩‍💼"},
        {"name": "Nuna",                 "role": "Social Media & Communications", "bio": "Oversees brand communication, digital presence, and strategic messaging to share AiDoBot's mission worldwide.", "photo": "", "emoji": "📣"},
        {"name": "Dr. Shiv Kumar Verma", "role": "Mentor & Advisor",             "bio": "Professor providing expert guidance on AI development, system architecture, and academic rigor.", "photo": "", "emoji": "🎓"},
        {"name": "Dr. Sanjay Kumar",     "role": "Mentor & Advisor",             "bio": "Associate Professor advising on medical applications, healthcare integration, and clinical accuracy.", "photo": "", "emoji": "⚕️"}
    ],
    "events": [
        {"title": "Healthcare Innovation Summit", "date": "Mar 2026", "location": "Banjul, The Gambia",
         "desc": "AiDoBot will be demonstrating live patient screening and telemedicine capabilities.", "icon": "🏥", "image": ""},
        {"title": "University Tech Expo",         "date": "Apr 2026", "location": "New Delhi, India",
         "desc": "Join us at the national university technology fair showcasing AI face analysis.", "icon": "🏫", "image": ""},
        {"title": "Community Health Outreach",    "date": "May 2026", "location": "Rural Communities, West Africa",
         "desc": "Free health screening drive — bringing AiDoBot directly to underserved rural communities.", "icon": "🌍", "image": ""}
    ],
    "announcements": [
        {"icon": "🚀", "date": "Feb 28, 2026", "title": "AiDoBot Version 2.0 Launched",
         "body": "AiDoBot V2.0 features enhanced AI face analysis, improved multilingual support for 12 new languages, and screening under 4 minutes."},
        {"icon": "🤝", "date": "Feb 15, 2026", "title": "New Partnership with Regional Health Ministry",
         "body": "AiDoBot has entered a formal partnership to deploy robots across 20 public health centres. Rollout begins March 2026."},
        {"icon": "🏆", "date": "Jan 30, 2026", "title": "AiDoBot Wins Best Health Innovation Award",
         "body": "We are honoured to have received the Best Health Innovation Award at the Africa Tech Summit 2026."}
    ],
    "partners": [
        {"icon": "🏥", "name": "Regional Health Ministry", "type": "Government", "desc": "Official ministry partner supporting nationwide deployment."},
        {"icon": "🎓", "name": "University Research Lab",  "type": "Academic",   "desc": "Research partnership advancing AI diagnostic capabilities."},
        {"icon": "🌐", "name": "Global Health NGO",        "type": "NGO",        "desc": "Funding and deploying AiDoBot in underserved communities."},
        {"icon": "💊", "name": "PharmaCare Network",       "type": "Healthcare", "desc": "Pharmacy network enabling home medicine delivery."}
    ],
    "social": {"youtube": "#", "facebook": "#", "instagram": "#", "whatsapp": "https://wa.me/918800510790", "tiktok": "", "linkedin": ""},
    "latest_youtube": "",
    "contact_info": {
        "email1": "hello@aidoBot.com",
        "email2": "info@aidoBot.com",
        "whatsapp": "+91 8800 510 790",
        "deployment": "Available worldwide — hospitals, clinics, communities, homes.",
        "partnerships": "Ministries of Health, hospitals, NGOs — let\'s build together."
    },
    "avatar_idle_video": "",
    "avatar_talk_video": "",
    "popup_greeting":    "Hello! I'm AiDoBot, your AI healthcare companion. Would you like to learn more about how I can bring quality healthcare to you?",
    "chatbot_name":      "AiDoBot Assistant",
    "chatbot_greeting":  "Hi! I'm AiDoBot's AI assistant. Ask me anything about AiDoBot — our features, how it works, team, or pricing!",
    "chatbot_emoji":     "🤖",
    "ai_knowledge_base": "AiDoBot is an AI-powered medical robot. Features: heart rate, SpO2, temperature, blood pressure, weight/height, AI face analysis, video doctor consultations, digital prescriptions, home medicine delivery. Contact: hello@aidoBot.com"
}

# ─── DB HELPERS ──────────────────────────────────────────────
def parse_db_url(url):
    url = url.replace("postgresql://", "").replace("postgres://", "")
    if "?" in url:
        url, _ = url.split("?", 1)
    at       = url.rindex("@")
    userpass = url[:at]
    hostdb   = url[at+1:]
    user, password = userpass.split(":", 1) if ":" in userpass else (userpass, "")
    if "/" in hostdb:
        hostport, database = hostdb.rsplit("/", 1)
    else:
        hostport, database = hostdb, "neondb"
    host, port = (hostport.rsplit(":", 1)[0], int(hostport.rsplit(":", 1)[1])) if ":" in hostport else (hostport, 5432)
    return dict(host=host, port=port, user=user, password=password, database=database)

def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set!")
    return pg8000.native.Connection(ssl_context=True, **parse_db_url(DATABASE_URL))

def init_db():
    conn = get_conn()
    # Site data table (key-value)
    conn.run("""
        CREATE TABLE IF NOT EXISTS site_data (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)
    # Contact messages table
    conn.run("""
        CREATE TABLE IF NOT EXISTS contact_messages (
            id         SERIAL PRIMARY KEY,
            first      TEXT,
            last       TEXT,
            email      TEXT,
            org        TEXT,
            message    TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    # Seed defaults
    for key, value in DEFAULT_DATA.items():
        conn.run(
            "INSERT INTO site_data (key, value) VALUES (:key, :value) ON CONFLICT (key) DO NOTHING;",
            key=key, value=json.dumps(value)
        )
    conn.close()
    print("✅ Neon DB initialized successfully")

def db_set(key, value):
    conn = get_conn()
    conn.run(
        "INSERT INTO site_data (key, value) VALUES (:key, :value) ON CONFLICT (key) DO UPDATE SET value = :value;",
        key=key, value=json.dumps(value)
    )
    conn.close()

def load_all_data():
    conn = get_conn()
    rows = conn.run("SELECT key, value FROM site_data;")
    conn.close()
    result = dict(DEFAULT_DATA)
    for key, value in rows:
        result[key] = json.loads(value)
    return result

# ─── PUBLIC ROUTES ───────────────────────────────────────────

@app.route("/api/data", methods=["GET"])
def get_data():
    try:
        return jsonify(load_all_data())
    except Exception as e:
        print("DB error GET /api/data:", e)
        return jsonify(DEFAULT_DATA)

@app.route("/")
@app.route("/<path:path>")
def serve_frontend(path=""):
    from flask import send_from_directory
    return send_from_directory(app.static_folder, "index.html")

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "storage": "neon+cloudinary"})

@app.route("/api/contact", methods=["POST"])
def contact():
    body = request.json or {}
    try:
        conn = get_conn()
        conn.run(
            "INSERT INTO contact_messages (first, last, email, org, message) VALUES (:first, :last, :email, :org, :message);",
            first=body.get("first",""), last=body.get("last",""),
            email=body.get("email",""), org=body.get("org",""),
            message=body.get("message","")
        )
        conn.close()
        print(f"📩 Contact from {body.get('email')}: {body.get('message','')[:60]}")
        return jsonify({"ok": True, "message": "Message received!"})
    except Exception as e:
        print("Contact save error:", e)
        return jsonify({"ok": True, "message": "Message received!"})  # still return ok to user

# ─── ADMIN AUTH ──────────────────────────────────────────────

@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    body = request.json or {}
    if body.get("password") == ADMIN_PASSWORD:
        return jsonify({"ok": True, "token": "admin-token-aidoBot"})
    return jsonify({"ok": False, "message": "Wrong password"}), 401

def require_admin():
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    return token == "admin-token-aidoBot"

# ─── ADMIN: UPLOAD MEDIA ─────────────────────────────────────

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
    return jsonify({"url": result["secure_url"], "public_id": result["public_id"], "resource_type": resource_type})

# ─── ADMIN: SAVE SECTION DATA ────────────────────────────────

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

# ─── ADMIN: INBOX ────────────────────────────────────────────

@app.route("/api/admin/inbox", methods=["GET"])
def get_inbox():
    if not require_admin():
        return jsonify({"error": "Unauthorized"}), 401
    try:
        conn = get_conn()
        rows = conn.run("SELECT id, first, last, email, org, message, created_at FROM contact_messages ORDER BY created_at DESC;")
        conn.close()
        messages = []
        for row in rows:
            messages.append({
                "id": row[0], "first": row[1], "last": row[2],
                "email": row[3], "org": row[4], "message": row[5],
                "created_at": str(row[6]) if row[6] else ""
            })
        return jsonify(messages)
    except Exception as e:
        print("Inbox error:", e)
        return jsonify([])

@app.route("/api/admin/inbox/<int:msg_id>", methods=["DELETE"])
def delete_message(msg_id):
    if not require_admin():
        return jsonify({"error": "Unauthorized"}), 401
    try:
        conn = get_conn()
        conn.run("DELETE FROM contact_messages WHERE id = :id;", id=msg_id)
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─── STARTUP ─────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
else:
    try:
        init_db()
    except Exception as e:
        print(f"❌ DB init error: {e}")
        print("⚠️  Check DATABASE_URL in Render environment variables.")
