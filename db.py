import sqlite3
import os
from datetime import datetime, timedelta, date

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "birthdays.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            date_of_birth TEXT,
            first_day_job TEXT,
            name_day TEXT,
            about_info TEXT,
            status TEXT DEFAULT 'pending_verification',
            verification_code TEXT,
            code_expires_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS admin_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code_hash TEXT NOT NULL,
            used INTEGER DEFAULT 0,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def now_iso():
    return datetime.utcnow().isoformat()


def add_or_update_person(email, name, date_of_birth, first_day_job, name_day, about_info, verification_code, code_expires_at):
    conn = get_connection()
    c = conn.cursor()
    now = now_iso()
    existing = c.execute("SELECT id FROM people WHERE email = ?", (email,)).fetchone()
    if existing:
        c.execute("""
            UPDATE people
            SET name = ?, date_of_birth = ?, first_day_job = ?, name_day = ?,
                about_info = ?, status = 'pending_verification',
                verification_code = ?, code_expires_at = ?, updated_at = ?
            WHERE email = ?
        """, (name, date_of_birth, first_day_job, name_day, about_info,
              verification_code, code_expires_at, now, email))
        person_id = existing["id"]
    else:
        c.execute("""
            INSERT INTO people (email, name, date_of_birth, first_day_job, name_day, about_info,
                                status, verification_code, code_expires_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending_verification', ?, ?, ?, ?)
        """, (email, name, date_of_birth, first_day_job, name_day, about_info,
              verification_code, code_expires_at, now, now))
        person_id = c.lastrowid
    conn.commit()
    conn.close()
    return person_id


def get_person_by_email(email):
    conn = get_connection()
    row = conn.execute("SELECT * FROM people WHERE email = ?", (email,)).fetchone()
    conn.close()
    return row


def get_person_by_id(person_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
    conn.close()
    return row
    return datetime.utcnow().isoformat()


def verify_code(email, code):
    person = get_person_by_email(email)
    if not person:
        return None
    if person["status"] != "pending_verification":
        return None
    if person["verification_code"] != code:
        return None
    if person["code_expires_at"]:
        try:
            expires = datetime.fromisoformat(person["code_expires_at"])
        except ValueError:
            return None
        if datetime.utcnow() > expires:
            return None
    return person


def mark_verified(person_id):
    conn = get_connection()
    now = now_iso()
    conn.execute("""
        UPDATE people
        SET status = 'pending_approval', verification_code = NULL,
            code_expires_at = NULL, updated_at = ?
        WHERE id = ?
    """, (now, person_id))
    conn.commit()
    conn.close()


def get_pending_approvals():
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM people
        WHERE status = 'pending_approval'
        ORDER BY created_at DESC
    """).fetchall()
    conn.close()
    return rows


def get_all_people():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM people ORDER BY name").fetchall()
    conn.close()
    return rows


def get_approved_people():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM people WHERE status = 'approved' ORDER BY name").fetchall()
    conn.close()
    return rows


def approve_person(person_id):
    conn = get_connection()
    now = now_iso()
    conn.execute("""
        UPDATE people SET status = 'approved', updated_at = ? WHERE id = ?
    """, (now, person_id))
    conn.commit()
    conn.close()


def reject_person(person_id):
    conn = get_connection()


def get_upcoming_events(days_ahead=30):
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)
    results = []

    people = get_approved_people()
    for p in people:
        events = []

        if p["date_of_birth"]:
            try:
                dob = date.fromisoformat(p["date_of_birth"])
                next_birthday = date(today.year, dob.month, dob.day)
                if next_birthday < today:
                    next_birthday = date(today.year + 1, dob.month, dob.day)
                if today <= next_birthday <= cutoff:
                    events.append(("birthday", next_birthday, (next_birthday - today).days))
            except ValueError:
                pass

        if p["name_day"]:
            try:
                month, day = p["name_day"].split("-")
                nd = date(today.year, int(month), int(day))
                if nd < today:
                    nd = date(today.year + 1, int(month), int(day))
                if today <= nd <= cutoff:
                    events.append(("name_day", nd, (nd - today).days))
            except (ValueError, AttributeError):
                pass

        if p["first_day_job"]:
            try:
                fdj = date.fromisoformat(p["first_day_job"])
                next_anniv = date(today.year, fdj.month, fdj.day)
                if next_anniv < today:
                    next_anniv = date(today.year + 1, fdj.month, fdj.day)
                if today <= next_anniv <= cutoff:
                    events.append(("job_anniversary", next_anniv, (next_anniv - today).days))
            except ValueError:
                pass

        for event_type, event_date, days_until in events:
            results.append((dict(p), event_type, event_date, days_until))

    return results


def create_admin_code(plain_code, expires_minutes=15):
    from werkzeug.security import generate_password_hash
    conn = get_connection()
    c = conn.cursor()
    code_hash = generate_password_hash(plain_code)
    expires = (datetime.utcnow() + timedelta(minutes=expires_minutes)).isoformat()
    created = now_iso()
    c.execute("""
        INSERT INTO admin_codes (code_hash, used, expires_at, created_at)
        VALUES (?, 0, ?, ?)
    """, (code_hash, expires, created))
    code_id = c.lastrowid
    conn.commit()
    conn.close()
    return code_id


def verify_admin_code(plain_code):
    from werkzeug.security import check_password_hash
    conn = get_connection()
    row = conn.execute("""
        SELECT * FROM admin_codes
        WHERE used = 0 AND expires_at > ?
        ORDER BY created_at DESC LIMIT 1
    """, (now_iso(),)).fetchone()
    if not row:
        conn.close()
        return False
    if not check_password_hash(row["code_hash"], plain_code):
        conn.close()
        return False
    conn.execute("UPDATE admin_codes SET used = 1 WHERE id = ?", (row["id"],))
    conn.commit()
    conn.close()
    return True
    now = now_iso()
    conn.execute("""
        UPDATE people SET status = 'rejected', updated_at = ? WHERE id = ?
    """, (now, person_id))
    conn.commit()
    conn.close()