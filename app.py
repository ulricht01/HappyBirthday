import os
import secrets
import string
from datetime import datetime, timedelta

from flask import Flask, render_template, request, redirect, url_for, session, flash

from db import (
    init_db,
    add_or_update_person,
    get_person_by_email,
    get_person_by_id,
    verify_code as verify_email_code,
    mark_verified,
    get_pending_approvals,
    get_all_people,
    get_approved_people,
    approve_person,
    reject_person,
    get_upcoming_events,
    create_admin_code,
    verify_admin_code,
)
from emailer import (
    send_verification_code,
    send_owner_notification,
    send_admin_code,
    send_event_notification,
)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24).hex())

init_db()


# ---------------------------------------------------------------------------
# Public: add person
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return redirect(url_for("add_person"))


@app.route("/add", methods=["GET", "POST"])
def add_person():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        name = request.form.get("name", "").strip()
        date_of_birth = request.form.get("date_of_birth", "").strip() or None
        first_day_job = request.form.get("first_day_job", "").strip() or None
        name_day = request.form.get("name_day", "").strip() or None
        about_info = request.form.get("about_info", "").strip()

        if not email or not name:
            flash("Name and email are required.", "error")
            return render_template("add_person.html")

        code = "".join(secrets.choice(string.digits) for _ in range(6))
        expires = (datetime.utcnow() + timedelta(hours=24)).isoformat()

        add_or_update_person(
            email, name, date_of_birth, first_day_job, name_day,
            about_info, code, expires,
        )

        send_verification_code(email, code)

        session["verify_email"] = email
        flash("A verification code has been sent to your email. Please check your inbox.", "info")
        return redirect(url_for("verify_code"))

    return render_template("add_person.html")


# ---------------------------------------------------------------------------
# Public: verify code
# ---------------------------------------------------------------------------
@app.route("/verify", methods=["GET", "POST"])
def verify_code():
    email = session.get("verify_email")
    if not email:
        flash("No verification in progress. Please start at /add.", "warning")
        return redirect(url_for("add_person"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        person = verify_email_code(email, code)
        if not person:
            flash("Invalid or expired code. Please request a new one at /add.", "error")
            return render_template("verify.html", email=email)

        mark_verified(person["id"])
        send_owner_notification(person["name"], person["email"])
        session.pop("verify_email", None)
        flash("Email verified! The owner has been notified and will review your request.", "success")
        return redirect(url_for("verify_success"))

    return render_template("verify.html", email=email)


@app.route("/verify/success")
def verify_success():
    return render_template("verify_success.html")


# ---------------------------------------------------------------------------
# Admin: one-time access
# ---------------------------------------------------------------------------
def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_auth"):
            return redirect(url_for("admin_request"))
        return f(*args, **kwargs)
    return decorated


@app.route("/admin", methods=["GET"])
def admin_request():
    return render_template("admin_request.html")


@app.route("/admin/request-code", methods=["POST"])
def admin_request_code():
    owner_email = os.getenv("OWNER_EMAIL")
    if not owner_email:
        flash("OWNER_EMAIL is not configured on the server.", "error")
        return redirect(url_for("admin_request"))

    alphabet = string.ascii_uppercase + string.digits
    code = "".join(secrets.choice(alphabet) for _ in range(8))
    create_admin_code(code, expires_minutes=15)
    send_admin_code(owner_email, code)

    flash("A one-time admin code has been sent to the owner's email.", "info")
    return redirect(url_for("admin_enter_code"))


@app.route("/admin/enter-code", methods=["GET", "POST"])
def admin_enter_code():
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        if verify_admin_code(code):
            session["admin_auth"] = True
            flash("Admin access granted.", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Invalid or expired admin code.", "error")
    return render_template("admin_enter_code.html")


@app.route("/admin/dashboard", methods=["GET"])
@admin_required
def admin_dashboard():
    pending = get_pending_approvals()
    all_people = get_all_people()
    return render_template("admin_dashboard.html", pending=pending, all_people=all_people)


@app.route("/admin/approve/<int:person_id>", methods=["POST"])
@admin_required
def admin_approve(person_id):
    person = get_person_by_id(person_id)
    if person:
        approve_person(person_id)
        flash(f"{person['name']} has been approved.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/reject/<int:person_id>", methods=["POST"])
@admin_required
def admin_reject(person_id):
    person = get_person_by_id(person_id)
    if person:
        reject_person(person_id)
        flash(f"{person['name']} has been rejected. They can resubmit at /add.", "info")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/logout", methods=["GET"])
def admin_logout():
    session.pop("admin_auth", None)
    flash("Logged out.", "info")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Notifications: +30 days scan
# ---------------------------------------------------------------------------
@app.route("/people", methods=["GET"])
def list_people():
    people = get_all_people()
    return render_template("list_people.html", people=people)


@app.route("/send-notifications", methods=["POST"])
def send_notifications():
    events = get_upcoming_events(days_ahead=30)
    approved = get_approved_people()
    sent = 0
    skipped_self = 0

    for event_person, event_type, event_date, days_until in events:
        for recipient in approved:
            if recipient["id"] == event_person["id"]:
                skipped_self += 1
                continue
            send_event_notification(recipient["email"], event_person, event_type, days_until)
            sent += 1

    flash(
        f"Notifications processed: {sent} email(s) sent for {len(events)} upcoming event(s). "
        f"{skipped_self} self-notifications skipped.",
        "success",
    )
    return redirect(url_for("list_people"))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)