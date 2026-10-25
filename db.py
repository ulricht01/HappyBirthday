import os
import sqlite3
from datetime import datetime, timedelta, date

from dotenv import load_dotenv

load_dotenv()

# Falls back to SQLite next to this file (/home/container/birthdays.db on Pterodactyl)
_DEFAULT_SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "birthdays.db")
DB_URL = os.getenv("DATABASE_URL") or f"sqlite:///{_DEFAULT_SQLITE_PATH}"
USE_SQLITE = DB_URL.startswith("sqlite")

if not USE_SQLITE:
    import psycopg2
    import psycopg2.extras


def _sqlite_dict_row(cursor, row):
    return {col[0]: value for col, value in zip(cursor.description, row)}


class _SqliteCursor:
    """Adapts the PostgreSQL-style SQL used in this module to SQLite."""

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=()):
        sql = sql.replace("%s", "?").replace(
            "SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT"
        )
        return self._cursor.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


def get_connection():
    if USE_SQLITE:
        conn = sqlite3.connect(DB_URL[len("sqlite:///"):])
        conn.row_factory = _sqlite_dict_row
        return conn
    conn = psycopg2.connect(DB_URL)
    return conn


def _dict_cursor(conn):
    """Return a cursor that yields rows as dicts."""
    if USE_SQLITE:
        return _SqliteCursor(conn.cursor())
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def init_db():
    conn = get_connection()
    c = _dict_cursor(conn)
    c.execute(
        "CREATE TABLE IF NOT EXISTS people ("
        "id SERIAL PRIMARY KEY, "
        "email TEXT UNIQUE NOT NULL, "
        "name TEXT NOT NULL, "
        "date_of_birth TEXT, "
        "first_day_job TEXT, "
        "name_day TEXT, "
        "about_info TEXT, "
        "status TEXT DEFAULT 'pending_verification', "
        "verification_code TEXT, "
        "code_expires_at TEXT, "
        "created_at TEXT NOT NULL, "
        "updated_at TEXT NOT NULL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS admin_codes ("
        "id SERIAL PRIMARY KEY, "
        "code_hash TEXT NOT NULL, "
        "used INTEGER DEFAULT 0, "
        "expires_at TEXT NOT NULL, "
        "created_at TEXT NOT NULL)"
    )
    conn.commit()
    conn.close()

def add_or_update_person(email, name, date_of_birth, first_day_job, name_day, about_info, verification_code, code_expires_at):
    conn = get_connection()
    c = _dict_cursor(conn)
    now = now_iso()
    c.execute("SELECT id FROM people WHERE email = %s", (email,))
    existing = c.fetchone()
    if existing:
        c.execute(
            "UPDATE people SET name = %s, date_of_birth = %s, first_day_job = %s, "
            "name_day = %s, about_info = %s, status = 'pending_verification', "
            "verification_code = %s, code_expires_at = %s, updated_at = %s "
            "WHERE email = %s",
            (name, date_of_birth, first_day_job, name_day, about_info,
             verification_code, code_expires_at, now, email),
        )
        person_id = existing["id"]
    else:
        c.execute(
            "INSERT INTO people (email, name, date_of_birth, first_day_job, name_day, "
            "about_info, status, verification_code, code_expires_at, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, 'pending_verification', %s, %s, %s, %s) "
            "RETURNING id",
            (email, name, date_of_birth, first_day_job, name_day, about_info,
             verification_code, code_expires_at, now, now),
        )
        person_id = c.fetchone()["id"]
    conn.commit()
    conn.close()
    return person_id


def get_person_by_email(email):
    conn = get_connection()
    c = _dict_cursor(conn)
    c.execute("SELECT * FROM people WHERE email = %s", (email,))
    row = c.fetchone()
    conn.close()
    return row


def get_person_by_id(person_id):
    conn = get_connection()
    c = _dict_cursor(conn)
    c.execute("SELECT * FROM people WHERE id = %s", (person_id,))
    row = c.fetchone()
    conn.close()
    return row


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
    c = _dict_cursor(conn)
    now = now_iso()
    c.execute(
        "UPDATE people SET status = 'pending_approval', verification_code = NULL, "
        "code_expires_at = NULL, updated_at = %s WHERE id = %s",
        (now, person_id),
    )
    conn.commit()
    conn.close()

def get_all_people():
    conn = get_connection()
    c = _dict_cursor(conn)
    c.execute("SELECT * FROM people ORDER BY name")
    rows = c.fetchall()
    conn.close()
    return rows


def get_approved_people():
    conn = get_connection()
    c = _dict_cursor(conn)
    c.execute("SELECT * FROM people WHERE status = 'approved' ORDER BY name")
    rows = c.fetchall()
    conn.close()
    return rows


def approve_person(person_id):
    conn = get_connection()
    c = _dict_cursor(conn)
    now = now_iso()
    c.execute(
        "UPDATE people SET status = 'approved', updated_at = %s WHERE id = %s",
        (now, person_id),
    )
    conn.commit()
    conn.close()


def reject_person(person_id):
    conn = get_connection()
    c = _dict_cursor(conn)
    now = now_iso()
    c.execute(
        "UPDATE people SET status = 'rejected', updated_at = %s WHERE id = %s",
        (now, person_id),
    )
    conn.commit()
    conn.close()


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
    c = _dict_cursor(conn)
    code_hash = generate_password_hash(plain_code, method="pbkdf2:sha256")
    expires = (datetime.utcnow() + timedelta(minutes=expires_minutes)).isoformat()
    created = now_iso()
    c.execute(
        "INSERT INTO admin_codes (code_hash, used, expires_at, created_at) "
        "VALUES (%s, 0, %s, %s) RETURNING id",
        (code_hash, expires, created),
    )
    code_id = c.fetchone()["id"]
    conn.commit()
    conn.close()
    return code_id


def verify_admin_code(plain_code):
    from werkzeug.security import check_password_hash
    conn = get_connection()
    c = _dict_cursor(conn)
    c.execute(
        "SELECT * FROM admin_codes "
        "WHERE used = 0 AND expires_at > %s "
        "ORDER BY created_at DESC LIMIT 1",
        (now_iso(),),
    )
    row = c.fetchone()
    if not row:
        conn.close()
        return False
    if not check_password_hash(row["code_hash"], plain_code):
        conn.close()
        return False
    c.execute("UPDATE admin_codes SET used = 1 WHERE id = %s", (row["id"],))
    conn.commit()
    conn.close()
    return True


def get_pending_approvals():
    conn = get_connection()
    c = _dict_cursor(conn)
    c.execute(
        "SELECT * FROM people WHERE status = 'pending_approval' ORDER BY created_at DESC"
    )
    rows = c.fetchall()
    conn.close()
    return rows


def now_iso():
    return datetime.utcnow().isoformat()