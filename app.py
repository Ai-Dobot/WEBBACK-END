from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import cloudinary
import cloudinary.uploader
import cloudinary.api
import os
import json
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

# Cloudinary config — set these in your .env file
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME", "your_cloud_name"),
    api_key=os.getenv("CLOUDINARY_API_KEY", "your_api_key"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET", "your_api_secret"),
    secure=True
)

# Simple JSON file as lightweight DB (replace with real DB in production)
DATA_FILE = "site_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {
        "hero": {"robot_image": "", "headline": "Healthcare that comes to you."},
        "stats": {"accuracy": 98, "time_saved": 70, "daily_screenings": 500},
        "gallery": [],
        "reviews_video": [],
        "reviews_text": [],
        "journey_steps": [],
        "team": [],
        "events": [],
        "announcements": [],
        "partners": [],
        "social": {"youtube": "", "facebook": "", "instagram": "", "whatsapp": ""},
        "latest_youtube": ""
    }

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ─── PUBLIC ROUTES ───────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("../frontend", "index.html")

@app.route("/api/data", methods=["GET"])
def get_data():
    return jsonify(load_data())

# ─── ADMIN ROUTES ────────────────────────────────────────────

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "aidoBot2026!")

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

    section = request.form.get("section", "general")
    resource_type = request.form.get("resource_type", "image")  # image or video

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    result = cloudinary.uploader.upload(
        file,
        folder=f"aidoBot/{section}",
        resource_type=resource_type
    )
    return jsonify({
        "url": result["secure_url"],
        "public_id": result["public_id"],
        "resource_type": resource_type
    })

@app.route("/api/admin/update", methods=["POST"])
def update_data():
    if not require_admin():
        return jsonify({"error": "Unauthorized"}), 401

    body = request.json or {}
    data = load_data()
    section = body.get("section")
    payload = body.get("data")

    if section and payload is not None:
        data[section] = payload
        save_data(data)
        return jsonify({"ok": True})

    return jsonify({"error": "Invalid payload"}), 400

@app.route("/api/contact", methods=["POST"])
def contact():
    body = request.json or {}
    # In production, send email here via SendGrid or similar
    print("Contact form submission:", body)
    return jsonify({"ok": True, "message": "Message received!"})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
