import os
from datetime import datetime

from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor

import cloudinary
import cloudinary.uploader


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)

    # --- Configuration from environment ---
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable is required for Neon connection.")

    cloudinary_url = os.getenv("CLOUDINARY_URL")
    if not cloudinary_url:
        # Cloudinary can also be configured with individual vars, but this keeps it simple
        raise RuntimeError("CLOUDINARY_URL environment variable is required for Cloudinary.")

    cloudinary.config(cloudinary_url=cloudinary_url)

    # --- Database helper ---
    def get_conn():
        return psycopg2.connect(db_url, cursor_factory=RealDictCursor)

    def init_db():
        ddl = """
        CREATE TABLE IF NOT EXISTS meetings (
            id          BIGSERIAL PRIMARY KEY,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            date        DATE NOT NULL,
            time        TEXT NOT NULL,
            name        TEXT NOT NULL,
            country     TEXT NOT NULL,
            email       TEXT NOT NULL,
            channel     TEXT NOT NULL  -- 'whatsapp' or 'email'
        );

        CREATE TABLE IF NOT EXISTS contacts (
            id          BIGSERIAL PRIMARY KEY,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            first_name  TEXT NOT NULL,
            last_name   TEXT,
            email       TEXT NOT NULL,
            organisation TEXT,
            message     TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS feedback (
            id          BIGSERIAL PRIMARY KEY,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            name        TEXT NOT NULL,
            role        TEXT,
            rating      INT,
            message     TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS media (
            id          BIGSERIAL PRIMARY KEY,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            media_id    TEXT NOT NULL,
            url         TEXT NOT NULL,
            kind        TEXT NOT NULL,   -- 'image' or 'video'
            file_name   TEXT
        );
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
            conn.commit()

    # Ensure tables exist at cold start
    init_db()

    # --- Health check ---
    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "time": datetime.utcnow().isoformat() + "Z"})

    # --- Meetings (book a meeting) ---
    @app.post("/api/book-meeting")
    def book_meeting():
        data = request.get_json(silent=True) or {}
        date = data.get("date")
        time_val = data.get("time")
        name = data.get("name")
        country = data.get("country")
        email = data.get("email")
        channel = data.get("channel") or "unknown"

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
                        (date, time_val, name, country, email, channel),
                    )
                    row = cur.fetchone()
                conn.commit()
        except Exception as exc:  # pragma: no cover - simple error surface
            return jsonify({"error": "Failed to save meeting", "details": str(exc)}), 500

        return jsonify({"ok": True, "id": row["id"], "created_at": row["created_at"].isoformat()})

    # --- Contact form ---
    @app.post("/api/contact")
    def contact():
        data = request.get_json(silent=True) or {}
        first = data.get("first_name")
        email = data.get("email")
        message = data.get("message")
        if not first or not email or not message:
            return jsonify({"error": "first_name, email and message are required"}), 400

        last = data.get("last_name")
        organisation = data.get("organisation")

        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO contacts (first_name, last_name, email, organisation, message)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING id, created_at
                        """,
                        (first, last, email, organisation, message),
                    )
                    row = cur.fetchone()
                conn.commit()
        except Exception as exc:
            return jsonify({"error": "Failed to save contact", "details": str(exc)}), 500

        return jsonify({"ok": True, "id": row["id"], "created_at": row["created_at"].isoformat()})

    # --- Feedback form ---
    @app.post("/api/feedback")
    def feedback():
        data = request.get_json(silent=True) or {}
        name = data.get("name")
        message = data.get("message")
        if not name or not message:
            return jsonify({"error": "name and message are required"}), 400

        role = data.get("role")
        rating = data.get("rating")
        try:
            rating_val = int(rating) if rating is not None else None
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
                        (name, role, rating_val, message),
                    )
                    row = cur.fetchone()
                conn.commit()
        except Exception as exc:
            return jsonify({"error": "Failed to save feedback", "details": str(exc)}), 500

        return jsonify({"ok": True, "id": row["id"], "created_at": row["created_at"].isoformat()})

    # --- Media upload to Cloudinary (file) ---
    @app.post("/api/media/upload")
    def media_upload():
        if "file" not in request.files:
            return jsonify({"error": "file is required"}), 400

        file = request.files["file"]
        if not file.filename:
            return jsonify({"error": "empty file name"}), 400

        media_id = request.form.get("media_id") or ""

        try:
            result = cloudinary.uploader.upload(
                file,
                resource_type="auto",
                folder="aidobot",
                invalidate=True,
            )
        except Exception as exc:
            return jsonify({"error": "Cloudinary upload failed", "details": str(exc)}), 500

        url = result.get("secure_url") or result.get("url")
        kind = "video" if result.get("resource_type") == "video" else "image"

        if url and media_id:
            try:
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO media (media_id, url, kind, file_name)
                            VALUES (%s, %s, %s, %s)
                            """,
                            (media_id, url, kind, file.filename),
                        )
                    conn.commit()
            except Exception:
                # Do not fail the whole request if DB logging fails
                pass

        return jsonify(
            {"ok": True, "url": url, "kind": kind, "public_id": result.get("public_id")}
        )

    # --- Media upload to Cloudinary (from remote URL, non-YouTube) ---
    @app.post("/api/media/upload-url")
    def media_upload_url():
        data = request.get_json(silent=True) or {}
        src_url = data.get("url")
        if not src_url:
            return jsonify({"error": "url is required"}), 400

        media_id = data.get("media_id") or ""

        try:
            result = cloudinary.uploader.upload(
                src_url,
                resource_type="auto",
                folder="aidobot",
                invalidate=True,
            )
        except Exception as exc:
            return jsonify({"error": "Cloudinary upload failed", "details": str(exc)}), 500

        url = result.get("secure_url") or result.get("url")
        kind = "video" if result.get("resource_type") == "video" else "image"

        if url and media_id:
            try:
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO media (media_id, url, kind, file_name)
                            VALUES (%s, %s, %s, %s)
                            """,
                            (media_id, url, kind, None),
                        )
                    conn.commit()
            except Exception:
                pass

        return jsonify(
            {"ok": True, "url": url, "kind": kind, "public_id": result.get("public_id")}
        )

    return app


app = create_app()


if __name__ == "__main__":
    # Local development entrypoint
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)

