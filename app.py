from flask import Flask, render_template, request, redirect
import sqlite3
import subprocess
import platform
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# ---------- CONFIGURATION EMAIL ----------
SMTP_EMAIL = "maryemmlaaribi@gmail.com"        # ton email Gmail (expediteur)
SMTP_APP_PASSWORD = "Oqib tvrr jdso xjiw"      # App Password (16 caracteres, sans espaces)

# Garde en memoire le dernier etat connu de chaque device (pour detecter les transitions)
last_known_status = {}


def get_connection():
    connection = sqlite3.connect("network.db")
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    connection = get_connection()
    connection.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            ip TEXT NOT NULL,
            email TEXT
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS ping_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
            status INTEGER NOT NULL,
            response_time REAL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (device_id) REFERENCES devices (id)
        )
    """)
    connection.commit()
    connection.close()


def get_devices():
    connection = get_connection()
    devices = connection.execute("SELECT * FROM devices").fetchall()
    connection.close()
    return devices


def get_device(device_id):
    connection = get_connection()
    device = connection.execute(
        "SELECT * FROM devices WHERE id = ?", (device_id,)
    ).fetchone()
    connection.close()
    return device


def add_device(name, ip, email):
    connection = get_connection()
    connection.execute(
        "INSERT INTO devices (name, ip, email) VALUES (?, ?, ?)",
        (name, ip, email)
    )
    connection.commit()
    connection.close()


def update_device(device_id, name, ip, email):
    connection = get_connection()
    connection.execute(
        "UPDATE devices SET name = ?, ip = ?, email = ? WHERE id = ?",
        (name, ip, email, device_id)
    )
    connection.commit()
    connection.close()


def log_ping(device_id, status, response_time):
    connection = get_connection()
    connection.execute(
        "INSERT INTO ping_history (device_id, status, response_time, timestamp) VALUES (?, ?, ?, ?)",
        (device_id, 1 if status else 0, response_time, datetime.now().isoformat())
    )
    connection.commit()
    connection.close()


def get_uptime_percentage(device_id, hours=24):
    connection = get_connection()
    since = (datetime.now() - timedelta(hours=hours)).isoformat()
    rows = connection.execute(
        "SELECT status FROM ping_history WHERE device_id = ? AND timestamp >= ?",
        (device_id, since)
    ).fetchall()
    connection.close()

    if not rows:
        return None

    up_count = sum(1 for row in rows if row["status"] == 1)
    return round((up_count / len(rows)) * 100, 1)


def get_device_history(device_id, limit=50):
    connection = get_connection()
    history = connection.execute(
        "SELECT * FROM ping_history WHERE device_id = ? ORDER BY timestamp DESC LIMIT ?",
        (device_id, limit)
    ).fetchall()
    connection.close()
    return history


def ping_device(ip):
    if platform.system() == "Windows":
        command = ["ping", "-n", "1", "-w", "3000", ip]
    else:
        command = ["ping", "-c", "1", "-W", "3", ip]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode != 0:
            return False, None

        output = result.stdout.lower()

        if "time=" in output:
            try:
                time_part = output.split("time=")[1].split("ms")[0]
                response_time = float(time_part.replace(",", "."))
                return True, response_time
            except (ValueError, IndexError):
                return True, None

        return True, None

    except FileNotFoundError:
        print("[PING] ping command is not available.")
        return False, None

    except subprocess.TimeoutExpired:
        print(f"[PING] Timeout: {ip}")
        return False, None

# ---------- EMAIL ----------
def send_email_alert(device_name, ip, new_status, recipient_email):
    if not recipient_email:
        return
    subject_status = "UP" if new_status else "DOWN"
    subject = f"[Network Monitor] {device_name} est {subject_status}"

    body = f"""L'equipement a change d'etat :

Nom : {device_name}
IP : {ip}
Nouvel etat : {"UP" if new_status else "DOWN"}
Heure : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SMTP_EMAIL
    msg["To"] = recipient_email

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SMTP_EMAIL, SMTP_APP_PASSWORD)
            server.sendmail(SMTP_EMAIL, recipient_email, msg.as_string())
        print(f"[EMAIL] Alerte envoyee pour {device_name} ({subject_status}) a {recipient_email}")
    except Exception as e:
        print(f"[EMAIL] Erreur d'envoi : {e}")


# ---------- TACHE AUTOMATIQUE (toutes les 1 minute) ----------
def check_all_devices():
    devices = get_devices()

    for device in devices:
        status, response_time = ping_device(device["ip"])
        log_ping(device["id"], status, response_time)

        device_id = device["id"]
        previous_status = last_known_status.get(device_id)

        if previous_status is not None and previous_status != status:
            send_email_alert(device["name"], device["ip"], status, device["email"])

        last_known_status[device_id] = status

    print(f"[SCHEDULER] Verification effectuee a {datetime.now().strftime('%H:%M:%S')}")


scheduler = BackgroundScheduler()
scheduler.add_job(func=check_all_devices, trigger="interval", minutes=1)


# ---------- ROUTES ----------
@app.route("/", methods=["GET", "POST"])
def home():

    if request.method == "POST":
        name = request.form["name"]
        ip = request.form["ip"]
        email = request.form["email"]
        add_device(name, ip, email)
        return redirect("/")

    devices = get_devices()
    devices_with_status = []

    for device in devices:
        status, response_time = ping_device(device["ip"])
        uptime = get_uptime_percentage(device["id"])

        devices_with_status.append({
            "id": device["id"],
            "name": device["name"],
            "ip": device["ip"],
            "email": device["email"],
            "status": status,
            "response_time": response_time,
            "uptime": uptime
        })

    total_devices = len(devices_with_status)
    up_devices = sum(1 for device in devices_with_status if device["status"])
    down_devices = total_devices - up_devices

    return render_template(
        "index.html",
        devices=devices_with_status,
        total_devices=total_devices,
        up_devices=up_devices,
        down_devices=down_devices
    )


@app.route("/edit/<int:device_id>", methods=["GET", "POST"])
def edit_device(device_id):

    if request.method == "POST":
        name = request.form["name"]
        ip = request.form["ip"]
        email = request.form["email"]
        update_device(device_id, name, ip, email)
        return redirect("/")

    device = get_device(device_id)
    return render_template("edit.html", device=device)


@app.route("/history/<int:device_id>")
def history(device_id):
    device = get_device(device_id)
    records = get_device_history(device_id)
    uptime = get_uptime_percentage(device_id)

    return render_template(
        "history.html",
        device=device,
        records=records,
        uptime=uptime
    )


@app.route("/delete/<int:device_id>", methods=["POST"])
def delete_device(device_id):
    connection = get_connection()
    connection.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    connection.execute("DELETE FROM ping_history WHERE device_id = ?", (device_id,))
    connection.commit()
    connection.close()
    last_known_status.pop(device_id, None)
    return redirect("/")


if __name__ == "__main__":
    init_db()
    scheduler.start()
    app.run(debug=True, use_reloader=False)