"""Read-only browser dashboard for the medical-gas alarm panel network."""

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from datetime import timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from waitress import serve
from werkzeug.security import check_password_hash


BASE_DIR = Path(__file__).resolve().parent
PANEL_CONFIG_PATH = BASE_DIR / "dashboard_config.json"
WEB_CONFIG_PATH = BASE_DIR / "web_config.json"


def load_json(path):
    with path.open("r", encoding="utf-8") as config_file:
        return json.load(config_file)


panel_config = load_json(PANEL_CONFIG_PATH)
web_config = load_json(WEB_CONFIG_PATH)
panel_port = int(panel_config.get("listen_port", 5050))
offline_seconds = float(panel_config.get("offline_seconds", 5))

app = Flask(__name__)
app.secret_key = web_config["secret_key"]
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(
        hours=float(web_config.get("session_hours", 12))
    ),
)

state_lock = threading.Lock()
stop_event = threading.Event()
workers_started = False
states = {
    item["id"]: {
        "id": item["id"],
        "name": item["name"],
        "ip": item["ip"],
        "connected": False,
        "last_seen": 0.0,
        "data": {},
    }
    for item in panel_config["panels"]
}

# Small in-memory lockout to slow password guessing on an Internet-facing port.
failed_logins = {}
failed_login_lock = threading.Lock()
LOGIN_WINDOW = 300
LOGIN_LIMIT = 5


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("authenticated"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "authentication required"}), 401
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def login_blocked(address):
    now = time.time()
    with failed_login_lock:
        recent = [stamp for stamp in failed_logins.get(address, []) if now - stamp < LOGIN_WINDOW]
        failed_logins[address] = recent
        return len(recent) >= LOGIN_LIMIT


def record_failed_login(address):
    with failed_login_lock:
        failed_logins.setdefault(address, []).append(time.time())


def clear_failed_logins(address):
    with failed_login_lock:
        failed_logins.pop(address, None)


def panel_worker(panel_id):
    while not stop_event.is_set():
        connection = None
        try:
            with state_lock:
                panel_ip = states[panel_id]["ip"]
            connection = socket.create_connection((panel_ip, panel_port), timeout=2)
            connection.settimeout(4)
            buffer = b""
            while not stop_event.is_set():
                chunk = connection.recv(4096)
                if not chunk:
                    raise ConnectionError("panel closed the connection")
                buffer += chunk
                while b"\n" in buffer:
                    raw_line, buffer = buffer.split(b"\n", 1)
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue
                    data = json.loads(raw_line.decode("utf-8"))
                    with state_lock:
                        state = states[panel_id]
                        state["data"] = data
                        state["last_seen"] = time.time()
                        state["connected"] = True
        except (OSError, ConnectionError, UnicodeError, json.JSONDecodeError):
            with state_lock:
                states[panel_id]["connected"] = False
            stop_event.wait(2)
        finally:
            if connection is not None:
                try:
                    connection.close()
                except OSError:
                    pass


def start_panel_workers():
    global workers_started
    if workers_started:
        return
    workers_started = True
    for panel_id in states:
        threading.Thread(target=panel_worker, args=(panel_id,), daemon=True).start()
    cloud = web_config.get("cloud", {})
    if cloud.get("enabled"):
        threading.Thread(target=cloud_upload_worker, daemon=True).start()


def cloud_upload_worker():
    """Send a read-only snapshot outward; no inbound access to the PC is needed."""
    cloud = web_config["cloud"]
    delay = max(0.5, float(cloud.get("upload_seconds", 1)))
    while not stop_event.is_set():
        payload = json.dumps({"panels": public_panel_state()}).encode("utf-8")
        request_object = urllib.request.Request(
            cloud["ingest_url"],
            data=payload,
            headers={
                "Authorization": "Bearer " + cloud["token"],
                "Content-Type": "application/json",
                "User-Agent": "MedicalGasCollector/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request_object, timeout=10) as response:
                response.read()
        except (OSError, urllib.error.URLError, urllib.error.HTTPError):
            pass
        stop_event.wait(delay)


def public_panel_state():
    now = time.time()
    output = []
    with state_lock:
        for state in states.values():
            connected = state["connected"] and now - state["last_seen"] <= offline_seconds
            if not connected:
                continue
            data = state["data"]
            output.append(
                {
                    "id": state["id"],
                    "name": state["name"],
                    "oxygen": data.get("oxygen", 0),
                    "air": data.get("air", 0),
                    "vacuum": data.get("vacuum", 0),
                    "oxygen_alarm": bool(data.get("oxygen_alarm", False)),
                    "air_alarm": bool(data.get("air_alarm", False)),
                    "vacuum_alarm": bool(data.get("vacuum_alarm", False)),
                    "alarm_active": bool(data.get("alarm_active", False)),
                    "muted": bool(data.get("muted", False)),
                    "test_active": bool(data.get("test_active", False)),
                }
            )
    return output


@app.after_request
def add_security_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
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
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            valid = username == web_config["username"] and check_password_hash(
                web_config["password_hash"], password
            )
            if valid:
                clear_failed_logins(address)
                session.clear()
                session["authenticated"] = True
                session.permanent = True
                return redirect(url_for("dashboard"))
            record_failed_login(address)
            error = "Invalid username or password."
    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/panels")
@login_required
def panels_api():
    panels = public_panel_state()
    return jsonify({"panels": panels, "connected": len(panels), "server_time": time.time()})


if __name__ == "__main__":
    start_panel_workers()
    print("Medical Gas web dashboard")
    print("Open locally: http://127.0.0.1:%s" % web_config["port"])
    print("Listening on all network adapters. Press Ctrl+C to stop.")
    serve(app, host=web_config["host"], port=int(web_config["port"]), threads=8)
