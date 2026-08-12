import os
import uuid
import base64
from datetime import datetime

import cv2
import numpy as np
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.security import generate_password_hash

from config import (
    SECRET_KEY, FRONTEND_URL, UPLOAD_DIR,
    MAX_UPLOAD_MB, ALLOWED_EXTENSIONS
)
from db import get_connection, init_db
from auth import (
    hash_password, verify_password, create_token, token_required
)
from image_processing import process_image

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
CORS(app, resources={r"/api/*": {"origins": [FRONTEND_URL, "http://localhost:5173"]}})

try:
    init_db()
except Exception as exc:
    print("Database initialization failed:", exc)

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def save_cv_image(image, prefix):
    filename = f"{prefix}_{uuid.uuid4().hex}.jpg"
    path = os.path.join(UPLOAD_DIR, filename)
    ok = cv2.imwrite(path, image, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok:
        raise RuntimeError("Could not save image")
    return filename

@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "WallVision API"})

@app.post("/api/auth/register")
def register():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not name or not email or len(password) < 6:
        return jsonify({
            "error": "Name, email and a password of at least 6 characters are required"
        }), 400

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM users WHERE email = %s",
                (email,)
            )
            if cur.fetchone():
                return jsonify({"error": "Email is already registered"}), 409

            cur.execute(
                """
                INSERT INTO users (name, email, password_hash)
                VALUES (%s, %s, %s)
                RETURNING id, name, email
                """,
                (name, email, hash_password(password))
            )
            user = cur.fetchone()
        conn.commit()
        token = create_token(user["id"], user["email"])
        return jsonify({"token": token, "user": user}), 201
    finally:
        conn.close()

@app.post("/api/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, email, password_hash FROM users WHERE email = %s",
                (email,)
            )
            user = cur.fetchone()

        if not user or not verify_password(user["password_hash"], password):
            return jsonify({"error": "Invalid email or password"}), 401

        token = create_token(user["id"], user["email"])
        return jsonify({
            "token": token,
            "user": {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"]
            }
        })
    finally:
        conn.close()

@app.post("/api/visualize")
@token_required
def visualize():
    if "image" not in request.files:
        return jsonify({"error": "Image is required"}), 400

    file = request.files["image"]
    color = request.form.get("color", "#C8A2C8")
    color_name = request.form.get("color_name", "Lavender")

    if not file.filename or not allowed_file(file.filename):
        return jsonify({"error": "Use PNG, JPG, JPEG or WEBP images"}), 400

    raw = file.read()
    image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)

    if image is None:
        return jsonify({"error": "Invalid image file"}), 400

    try:
        result, detected_color, wall_percentage = process_image(image, color)
        original_filename = save_cv_image(image, "original")
        result_filename = save_cv_image(result, "visualized")
    except Exception as exc:
        return jsonify({"error": f"Image processing failed: {exc}"}), 500

    return jsonify({
        "original_image": f"/api/uploads/{original_filename}",
        "result_image": f"/api/uploads/{result_filename}",
        "color": color,
        "color_name": color_name,
        "detected_color": detected_color,
        "wall_percentage": wall_percentage
    })

@app.post("/api/designs")
@token_required
def save_design():
    data = request.get_json(silent=True) or {}
    required = ["original_image", "result_image", "color", "color_name"]
    if not all(data.get(k) for k in required):
        return jsonify({"error": "Incomplete design data"}), 400

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO designs
                (user_id, original_image, result_image, color_hex, color_name, detected_color)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, original_image, result_image, color_hex,
                          color_name, detected_color, created_at
                """,
                (
                    request.user_id,
                    data["original_image"],
                    data["result_image"],
                    data["color"],
                    data["color_name"],
                    data.get("detected_color")
                )
            )
            design = cur.fetchone()
        conn.commit()
        return jsonify(design), 201
    finally:
        conn.close()

@app.get("/api/designs")
@token_required
def get_designs():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, original_image, result_image, color_hex,
                       color_name, detected_color, created_at
                FROM designs
                WHERE user_id = %s
                ORDER BY created_at DESC
                """,
                (request.user_id,)
            )
            rows = cur.fetchall()
        return jsonify(rows)
    finally:
        conn.close()

@app.delete("/api/designs/<int:design_id>")
@token_required
def delete_design(design_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM designs WHERE id = %s AND user_id = %s RETURNING id",
                (design_id, request.user_id)
            )
            deleted = cur.fetchone()
        conn.commit()

        if not deleted:
            return jsonify({"error": "Design not found"}), 404

        return jsonify({"message": "Design deleted"})
    finally:
        conn.close()

@app.get("/api/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
