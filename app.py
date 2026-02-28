"""
AiDoBot Flask API — Production-ready backend.
- Neon PostgreSQL (parameterized queries, no connection leaks)
- Cloudinary (secure_url only, resource_type="auto")
- CORS restricted to allowed origins
- Media: UNIQUE(slot) + UPSERT for one record per slot
- No internal error leaking in 500 responses
- Vercel serverless compatible (no global state, short-lived connections)
"""
import os
import re
from datetime import datetime
from urllib.parse import urlparse

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor

import cloudinary
import cloudinary.uploader

# Only allow http/https URLs for upload-url (SSRF mitigation)
ALLOWED_URL_SCHEMES = ("https", "http")
MAX_URL_LENGTH = 2048
# Slot: alphanumeric, hyphen, underscore only; max length
SLOT_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,120}$")


def create_app() -> Flask:
    app = Flask(__name__)

    # --- CORS: restrict to allowed origins. Production: set ALLOWED_ORIGINS to your GitHub Pages URL(s) ---
    allowed_origins = os.getenv("ALLOWED_ORIGINS", "").strip()
    if allowed_origins:
        origins = [o.strip() for o in allowed_origins.split(",") if o.strip()]
    else:
        # Default: localhost only (production must set ALLOWED_ORIGINS e.g. https://youruser.github.io)
        origins = [
            "http://localhost:3000",
            "http://127.0.0.1:5500",
            "http://localhost:5000",
            "http://127.0.0.1:3000",
        ]
    CORS(app, origins=origins, allow_headers=["Content-Type"], methods=["GET", "POST", "OPTIONS"])

    # --- Configuration from environment ---
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable is required for Neon connection.")

    cloudinary_url = os.getenv("CLOUDINARY_URL")
    if not cloudinary_url:
        raise RuntimeError("CLOUDINARY_URL environment variable is required for Cloudinary.")

    cloudinary.config(cloudinary_url=cloudinary_url)
    is_production = os.getenv("FLASK_ENV") == "production" or os.getenv("VERCEL_ENV") == "production"

    # --- Database helper (serverless: new connection per request, closed by context manager) ---
    def get_conn():
        return psycopg2.connect(db_url, cursor_factory=RealDictCursor)

    def init_db():
        ddl_statements = [
            """
            CREATE TABLE IF NOT EXISTS meetings (
                id          BIGSERIAL PRIMARY KEY,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                date        DATE NOT NULL,
                time        TEXT NOT NULL,
                name        TEXT NOT NULL,
                country     TEXT NOT NULL,
                email       TEXT NOT NULL,
                channel     TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS contacts (
                id           BIGSERIAL PRIMARY KEY,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                first_name   TEXT NOT NULL,
                last_name    TEXT,
                email        TEXT NOT NULL,
                organisation TEXT,
                message      TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id          BIGSERIAL PRIMARY KEY,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                name        TEXT NOT NULL,
                role        TEXT,
                rating      INT,
                message     TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS media (
                id         BIGSERIAL PRIMARY KEY,
                type       VARCHAR(50) NOT NULL,
                url        TEXT NOT NULL,
                slot       TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """,
            # One record per slot: unique index (NULL slot allowed for "new slide" entries)
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_media_slot_unique
            ON media (slot) WHERE slot IS NOT NULL;
            """,
        ]
        with get_conn() as conn:
            with conn.cursor() as cur:
                for ddl in ddl_statements:
                    cur.execute(ddl)
            conn.commit()

    init_db()

    def safe_error_message(exc: Exception) -> str:
        if is_production:
            return "An error occurred. Please try again later."
        return str(exc)

    # --- Health check ---
    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "time": datetime.utcnow().isoformat() + "Z"})

    # --- Meetings ---
    @app.post("/api/book-meeting")
    def book_meeting():
        data = request.get_json(silent=True) or {}
        missing = [f for f in ("date", "time", "name", "country", "email") if not data.get(f)]
        if missing:
            return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO meetings (date, time, name, country, email, channel)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id, created_at
                        """,
                        (
                            data.get("date"),
                            data.get("time"),
                            data.get("name"),
                            data.get("country"),
                            data.get("email"),
                            data.get("channel") or "unknown",
                        ),
                    )
                    row = cur.fetchone()
                conn.commit()
        except Exception as exc:
            return jsonify({"error": "Failed to save meeting", "details": safe_error_message(exc)}), 500
        return jsonify({"ok": True, "id": row["id"], "created_at": row["created_at"].isoformat()})

    # --- Contact ---
    @app.post("/api/contact")
    def contact():
        data = request.get_json(silent=True) or {}
        first, email, message = data.get("first_name"), data.get("email"), data.get("message")
        if not first or not email or not message:
            return jsonify({"error": "first_name, email and message are required"}), 400
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO contacts (first_name, last_name, email, organisation, message)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING id, created_at
                        """,
                        (
                            first,
                            data.get("last_name"),
                            email,
                            data.get("organisation"),
                            message,
                        ),
                    )
                    row = cur.fetchone()
                conn.commit()
        except Exception as exc:
            return jsonify({"error": "Failed to save contact", "details": safe_error_message(exc)}), 500
        return jsonify({"ok": True, "id": row["id"], "created_at": row["created_at"].isoformat()})

    # --- Feedback ---
    @app.post("/api/feedback")
    def feedback():
        data = request.get_json(silent=True) or {}
        name, message = data.get("name"), data.get("message")
        if not name or not message:
            return jsonify({"error": "name and message are required"}), 400
        try:
            r = data.get("rating")
            rating_val = int(r) if r is not None else None
        except (TypeError, ValueError):
            rating_val = None
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO feedback (name, role, rating, message)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id, created_at
                        """,
                        (name, data.get("role"), rating_val, message),
                    )
                    row = cur.fetchone()
                conn.commit()
        except Exception as exc:
            return jsonify({"error": "Failed to save feedback", "details": safe_error_message(exc)}), 500
        return jsonify({"ok": True, "id": row["id"], "created_at": row["created_at"].isoformat()})

    # --- Media upload (file) → Cloudinary, then Neon (UPSERT when slot present) ---
    @app.post("/api/media/upload")
    def media_upload():
        if "file" not in request.files:
            return jsonify({"error": "file is required"}), 400
        file = request.files["file"]
        if not file.filename:
            return jsonify({"error": "empty file name"}), 400
        slot = request.form.get("slot") or request.form.get("media_id") or None
        if slot is not None and not SLOT_PATTERN.match(slot):
            return jsonify({"error": "invalid slot format"}), 400

        try:
            result = cloudinary.uploader.upload(
                file,
                resource_type="auto",
                folder="aidobot",
                invalidate=True,
            )
        except Exception as exc:
            return jsonify({"error": "Cloudinary upload failed", "details": safe_error_message(exc)}), 500

        url = result.get("secure_url")
        if not url:
            url = result.get("url")
        if not url or not url.startswith("https://"):
            return jsonify({"error": "Cloudinary did not return a secure URL"}), 500
        media_type = "video" if result.get("resource_type") == "video" else "image"

        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    if slot:
                        cur.execute(
                            """
                            INSERT INTO media (type, url, slot)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (slot) WHERE slot IS NOT NULL
                            DO UPDATE SET type = EXCLUDED.type, url = EXCLUDED.url
                            RETURNING id, type, url, slot, created_at
                            """,
                            (media_type, url, slot),
                        )
                    else:
                        cur.execute(
                            """
                            INSERT INTO media (type, url, slot)
                            VALUES (%s, %s, %s)
                            RETURNING id, type, url, slot, created_at
                            """,
                            (media_type, url, slot),
                        )
                    row = cur.fetchone()
                conn.commit()
        except Exception as exc:
            return jsonify({"error": "Failed to save media", "details": safe_error_message(exc)}), 500

        return jsonify({
            "ok": True,
            "id": row["id"],
            "type": row["type"],
            "url": row["url"],
            "slot": row["slot"],
            "created_at": row["created_at"].isoformat(),
        })

    # --- Media upload from URL (YouTube → Neon only; other → Cloudinary then Neon, UPSERT when slot present) ---
    @app.post("/api/media/upload-url")
    def media_upload_url():
        data = request.get_json(silent=True) or {}
        src_url = (data.get("url") or "").strip()
        if not src_url:
            return jsonify({"error": "url is required"}), 400
        if len(src_url) > MAX_URL_LENGTH:
            return jsonify({"error": "url too long"}), 400
        try:
            parsed = urlparse(src_url)
            if parsed.scheme not in ALLOWED_URL_SCHEMES:
                return jsonify({"error": "url must be http or https"}), 400
        except Exception:
            return jsonify({"error": "invalid url"}), 400

        slot = data.get("slot") or data.get("media_id") or None
        if slot is not None and not SLOT_PATTERN.match(slot):
            return jsonify({"error": "invalid slot format"}), 400

        is_youtube = "youtube.com" in src_url or "youtu.be" in src_url

        if is_youtube:
            try:
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        if slot:
                            cur.execute(
                                """
                                INSERT INTO media (type, url, slot)
                                VALUES (%s, %s, %s)
                                ON CONFLICT (slot) WHERE slot IS NOT NULL
                                DO UPDATE SET type = EXCLUDED.type, url = EXCLUDED.url
                                RETURNING id, type, url, slot, created_at
                                """,
                                ("youtube", src_url, slot),
                            )
                        else:
                            cur.execute(
                                """
                                INSERT INTO media (type, url, slot)
                                VALUES (%s, %s, %s)
                                RETURNING id, type, url, slot, created_at
                                """,
                                ("youtube", src_url, slot),
                            )
                        row = cur.fetchone()
                    conn.commit()
            except Exception as exc:
                return jsonify({"error": "Failed to save YouTube link", "details": safe_error_message(exc)}), 500
        else:
            try:
                result = cloudinary.uploader.upload(
                    src_url,
                    resource_type="auto",
                    folder="aidobot",
                    invalidate=True,
                )
            except Exception as exc:
                return jsonify({"error": "Cloudinary upload failed", "details": safe_error_message(exc)}), 500
            url = result.get("secure_url")
            if not url:
                url = result.get("url")
            if not url or not url.startswith("https://"):
                return jsonify({"error": "Cloudinary did not return a secure URL"}), 500
            media_type = "video" if result.get("resource_type") == "video" else "image"
            try:
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        if slot:
                            cur.execute(
                                """
                                INSERT INTO media (type, url, slot)
                                VALUES (%s, %s, %s)
                                ON CONFLICT (slot) WHERE slot IS NOT NULL
                                DO UPDATE SET type = EXCLUDED.type, url = EXCLUDED.url
                                RETURNING id, type, url, slot, created_at
                                """,
                                (media_type, url, slot),
                            )
                        else:
                            cur.execute(
                                """
                                INSERT INTO media (type, url, slot)
                                VALUES (%s, %s, %s)
                                RETURNING id, type, url, slot, created_at
                                """,
                                (media_type, url, slot),
                            )
                        row = cur.fetchone()
                    conn.commit()
            except Exception as exc:
                return jsonify({"error": "Failed to save media", "details": safe_error_message(exc)}), 500

        return jsonify({
            "ok": True,
            "id": row["id"],
            "type": row["type"],
            "url": row["url"],
            "slot": row["slot"],
            "created_at": row["created_at"].isoformat(),
        })

    # --- Get all media (for frontend to render on load) ---
    @app.get("/api/content")
    def get_content():
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, type, url, slot, created_at
                        FROM media
                        ORDER BY created_at ASC
                        """
                    )
                    rows = cur.fetchall()
        except Exception as exc:
            return jsonify({"error": "Failed to load content", "details": safe_error_message(exc)}), 500

        return jsonify([
            {
                "id": r["id"],
                "type": r["type"],
                "url": r["url"],
                "slot": r["slot"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ])

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
