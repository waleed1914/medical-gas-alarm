"""Public read-only cloud endpoint and dashboard for medical-gas telemetry."""

import hmac
import json
import os
import threading
import time
from datetime import timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash


BASE_DIR = Path(__file__).resolve().parent
with (BASE_DIR / "cloud_config.json").open("r", encoding="utf-8") as file:
    config = json.load(file)

app = Flask(__name__)
app.secret_key = config["secret_key"]
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("CLOUD_COOKIE_SECURE", "true").lower() == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=float(config.get("session_hours", 12))),
    MAX_CONTENT_LENGTH=256 * 1024,
)

state_lock = threading.Lock()
latest_panels = []
last_ingest = 0.0
failed_logins = {}
failed_login_lock = threading.Lock()
LOGIN_LIMIT = 5
LOGIN_WINDOW = 300


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("authenticated"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "authentication required"}), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def login_blocked(address):
    now = time.time()
    with failed_login_lock:
        recent = [stamp for stamp in failed_logins.get(address, []) if now - stamp < LOGIN_WINDOW]
        failed_logins[address] = recent
        return len(recent) >= LOGIN_LIMIT


@app.after_request
def security_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("authenticated"):
        return redirect(url_for("dashboard"))
    error = ""
    if request.method == "POST":
        address = request.remote_addr or "unknown"
        if login_blocked(address):
            error = "Too many attempts. Wait 5 minutes and try again."
        else:
            valid = request.form.get("username", "") == config["username"]
            valid = valid and check_password_hash(
                config["password_hash"], request.form.get("password", "")
            )
            if valid:
                with failed_login_lock:
                    failed_logins.pop(address, None)
                session.clear()
                session["authenticated"] = True
                session.permanent = True
                return redirect(url_for("dashboard"))
            with failed_login_lock:
                failed_logins.setdefault(address, []).append(time.time())
            error = "Invalid username or password."
    return render_template("login.html", error=error)


@app.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_required
def dashboard():
    return render_template("dashboard.html")


@app.post("/api/ingest")
def ingest():
    global latest_panels, last_ingest
    supplied = request.headers.get("Authorization", "")
    expected = "Bearer " + config["ingest_token"]
    if not hmac.compare_digest(supplied, expected):
        return jsonify({"error": "unauthorized"}), 401
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("panels"), list):
        return jsonify({"error": "invalid payload"}), 400
    clean = []
    allowed = {
        "id", "name", "oxygen", "air", "vacuum", "oxygen_alarm", "air_alarm",
        "vacuum_alarm", "alarm_active", "muted", "test_active"
    }
    for panel in payload["panels"][:20]:
        if isinstance(panel, dict) and "id" in panel:
            clean.append({key: panel[key] for key in allowed if key in panel})
    with state_lock:
        latest_panels = clean
        last_ingest = time.time()
    return jsonify({"accepted": len(clean)})


@app.get("/api/panels")
@login_required
def panels_api():
    with state_lock:
        age = time.time() - last_ingest if last_ingest else None
        panels = list(latest_panels) if age is not None and age <= float(config["offline_seconds"]) else []
    return jsonify({"panels": panels, "connected": len(panels), "server_time": time.time()})


@app.get("/health")
def health():
    return jsonify({"status": "ok"})
