import os
import secrets
import string
from collections import defaultdict
from datetime import datetime, timedelta, date

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify

from db import (
    init_db,
    add_or_update_person,
    add_or_update_person_entra,
    get_person_by_email,
    get_person_by_id,
    delete_person,
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
    get_name_day_for_first_name,
    get_name_day_info,
)
from emailer import (
    send_verification_code,
    send_owner_notification,
    send_admin_code,
    send_event_notifications,
    verify_smtp_config,
)
import czech_calendar
from entra_auth import (
    is_entra_configured,
    build_authorization_url,
    exchange_code_for_user_info,
)
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24).hex())
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

init_db()
verify_smtp_config()


def _get_entra_redirect_uri():
    """
    Returns the redirect URI for Microsoft Entra ID callback.
    Prefers explicit ENTRA_REDIRECT_URI from .env, or forces HTTPS for public domains behind reverse proxy.
    Cleans up any accidental trailing dots or slashes.
    """
    env_redirect = os.getenv("ENTRA_REDIRECT_URI")
    if env_redirect:
        return env_redirect.strip().rstrip(".").rstrip("/")

    uri = url_for("auth_callback", _external=True)
    proto = request.headers.get("X-Forwarded-Proto", "").lower()
    if proto == "https" or (not uri.startswith("http://localhost") and not uri.startswith("http://127.0.0.1")):
        uri = uri.replace("http://", "https://", 1)
    return uri.rstrip(".").rstrip("/")


@app.before_request
def enforce_profile_completion():
    """
    If a user logged in via Entra ID but lacks birth date or work start date,
    force them to complete the form before they can navigate anywhere else.
    """
    if session.get("requires_completion"):
        allowed = {"add_person", "api_name_day", "user_logout", "static"}
        if request.endpoint and request.endpoint not in allowed:
            flash("Pro dokončení přihlášení musíte nejprve vyplnit své datum narození a datum nástupu do zaměstnání.", "warning")
            return redirect(url_for("add_person"))


# ---------------------------------------------------------------------------
# Template Filters for Czech Formats (SPŠUL Handbook Standard)
# ---------------------------------------------------------------------------
@app.template_filter("format_name_day")
def format_name_day_filter(val):
    if not val:
        return "—"
    try:
        s = str(val).strip()
        if "." in s:
            parts = s.split(".")
            d, m = int(parts[0]), int(parts[1])
        elif "-" in s:
            parts = s.split("-")
            m, d = int(parts[0]), int(parts[1])
        else:
            return str(val)
        names = get_name_day_info(m, d)
        if names:
            return f"{d}. {m}. ({names})"
        return f"{d}. {m}."
    except Exception:
        return str(val)


@app.template_filter("format_date_cz")
def format_date_cz_filter(val):
    if not val:
        return "—"
    try:
        if isinstance(val, (datetime, date)):
            return val.strftime("%d. %m. %Y")
        parts = str(val).split("-")
        if len(parts) == 3:
            return f"{int(parts[2])}. {int(parts[1])}. {parts[0]}"
        return str(val)
    except Exception:
        return str(val)


# ---------------------------------------------------------------------------
# Public: add / update person
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    if session.get("admin_auth"):
        return redirect(url_for("list_people"))
    return redirect(url_for("add_person"))


@app.route("/add", methods=["GET", "POST"])
def add_person():
    if session.get("admin_auth"):
        return redirect(url_for("list_people"))

    entra_user = session.get("entra_user", {})

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        name = request.form.get("name", "").strip()
        date_of_birth = request.form.get("date_of_birth", "").strip() or None
        first_day_job = request.form.get("first_day_job", "").strip() or None
        name_day = request.form.get("name_day", "").strip() or None
        about_info = request.form.get("about_info", "").strip()

        if not email or not name or not date_of_birth or not first_day_job or not name_day:
            flash("Všechny údaje (jméno, e-mail, datum narození, nástup do zaměstnání i datum svátku) jsou povinné. Pouze pole 'Něco o mně' je volitelné.", "error")
            return render_template(
                "add_person.html",
                entra_user=entra_user,
                entra_configured=is_entra_configured(),
            )

        # Validate and normalize name_day format (DD.MM)
        clean_nd = str(name_day).strip()
        valid_nd = False
        if "." in clean_nd:
            parts = clean_nd.split(".")
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                d_val, m_val = int(parts[0]), int(parts[1])
                if 1 <= d_val <= 31 and 1 <= m_val <= 12:
                    valid_nd = True
                    name_day = f"{d_val:02d}.{m_val:02d}"
        elif "-" in clean_nd:
            parts = clean_nd.split("-")
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                m_val, d_val = int(parts[0]), int(parts[1])
                if 1 <= d_val <= 31 and 1 <= m_val <= 12:
                    valid_nd = True
                    name_day = f"{d_val:02d}.{m_val:02d}"

        if not valid_nd:
            flash("Zadejte prosím platné datum svátku ve formátu DD.MM (např. 25.11 nebo 19.03).", "error")
            return render_template(
                "add_person.html",
                entra_user=entra_user,
                entra_configured=is_entra_configured(),
            )

        # If user came from verified Entra login, update profile and activate
        if entra_user and entra_user.get("email") == email:
            add_or_update_person_entra(
                email, name, date_of_birth, first_day_job, name_day, about_info, status="approved"
            )
            session["entra_user"]["date_of_birth"] = date_of_birth or ""
            session["entra_user"]["first_day_job"] = first_day_job or ""
            session["entra_user"]["name_day"] = name_day or ""
            session.pop("requires_completion", None)
            flash("Váš profil byl úspěšně uložen! Oznámení o narozeninách a svátcích kolegů vám budou chodit automaticky.", "success")
            return redirect(url_for("verify_success"))

        # Manual entry -> require email verification code
        code = "".join(secrets.choice(string.digits) for _ in range(6))
        expires = (datetime.utcnow() + timedelta(hours=24)).isoformat()

        add_or_update_person(
            email, name, date_of_birth, first_day_job, name_day,
            about_info, code, expires,
        )

        send_verification_code(email, code)

        session["verify_email"] = email
        flash("Ověřovací kód byl odeslán na váš e-mail. Zkontrolujte prosím svoji doručenou poštu.", "info")
        return redirect(url_for("verify_code"))

    return render_template(
        "add_person.html",
        entra_user=entra_user,
        entra_configured=is_entra_configured(),
    )


# ---------------------------------------------------------------------------
# API: Real-time Czech Name Day Detection
# ---------------------------------------------------------------------------
@app.route("/api/name-day", methods=["GET"])
def api_name_day():
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"found": False, "matches": []})

    matches = czech_calendar.find_name_day(name)
    if matches:
        return jsonify({
            "found": True,
            "code": matches[0]["code"],
            "formatted": matches[0]["formatted"],
            "names": matches[0]["names"],
            "matches": matches,
        })
    return jsonify({"found": False, "matches": []})


# ---------------------------------------------------------------------------
# Microsoft Entra ID SSO & Profile Extraction
# ---------------------------------------------------------------------------
@app.route("/auth/entra")
def auth_entra():
    if not is_entra_configured():
        flash("Přihlášení přes Microsoft Entra ID není na serveru nakonfigurováno.", "warning")
        return redirect(url_for("add_person"))
    redirect_uri = _get_entra_redirect_uri()
    return redirect(build_authorization_url(redirect_uri))


@app.route("/auth/callback")
def auth_callback():
    code = request.args.get("code")
    error = request.args.get("error_description") or request.args.get("error")
    if error:
        flash(f"Chyba při přihlášení přes Microsoft Entra ID: {error}", "error")
        return redirect(url_for("add_person"))
    if not code:
        flash("Chybí autorizační kód od Microsoft Entra ID.", "error")
        return redirect(url_for("add_person"))

    try:
        redirect_uri = _get_entra_redirect_uri()
        user_info = exchange_code_for_user_info(code, redirect_uri)
        email = user_info["email"]
        name = user_info["name"]
        dob = user_info["date_of_birth"]
        fdj = user_info["first_day_job"]

        # Auto-detect Czech name day from first name
        code_nd, _, _ = get_name_day_for_first_name(name)

        # Check if user is the admin (owner)
        owner_email = os.getenv("OWNER_EMAIL", "oslavnik@spsul.cz").strip().lower()
        if email.lower() == owner_email:
            session["admin_auth"] = True
            session["user_email"] = email
            session["user_name"] = name
            session.pop("requires_completion", None)
            flash(f"Vítejte v administraci, {name}!", "success")
            return redirect(url_for("admin_dashboard"))

        # Regular school employee logged in via Entra:
        existing_person = get_person_by_email(email)
        effective_dob = dob or (existing_person["date_of_birth"] if existing_person else None)
        effective_fdj = fdj or (existing_person["first_day_job"] if existing_person else None)
        effective_nd = (existing_person["name_day"] if existing_person and existing_person["name_day"] else None) or code_nd

        session["entra_user"] = {
            "email": email,
            "name": name,
            "date_of_birth": effective_dob or "",
            "first_day_job": effective_fdj or "",
            "name_day": effective_nd or "",
        }
        session["user_email"] = email
        session["user_name"] = name

        # If birth date or hire date is missing in Entra, force user to complete both!
        if not effective_dob or not effective_fdj:
            session["requires_completion"] = True
            flash(f"Vítejte, {name}! Váš školní účet Microsoft Entra ID nemá vyplněné datum narození a/nebo datum nástupu do zaměstnání. Doplňte prosím obě povinná pole níže pro dokončení aktivace.", "warning")
            return redirect(url_for("add_person"))

        # Both dates are present -> save directly as approved!
        add_or_update_person_entra(
            email=email,
            name=name,
            date_of_birth=effective_dob,
            first_day_job=effective_fdj,
            name_day=effective_nd,
            about_info=existing_person["about_info"] if existing_person else "",
            status="approved",
        )
        session.pop("requires_completion", None)
        flash(f"Vítejte, {name}! Váš profil je aktivní a e-mailová upozornění vám budou chodit.", "success")
        return redirect(url_for("verify_success"))
    except Exception as exc:
        flash(f"Chyba při zpracování účtu Microsoft Entra ID: {exc}", "error")
        return redirect(url_for("add_person"))


@app.route("/auth/demo-entra")
def auth_demo_entra():
    """Demo login for testing UX without a registered Azure AD app."""
    sample = {
        "email": "novakp@spsul.cz",
        "name": "Ing. Petr Novák",
        "date_of_birth": "1988-06-15",
        "first_day_job": "2020-09-01",
        "name_day": "22.02",
    }
    session["entra_user"] = sample
    session["user_email"] = sample["email"]
    session["user_name"] = sample["name"]
    add_or_update_person_entra(
        sample["email"], sample["name"], sample["date_of_birth"],
        sample["first_day_job"], sample["name_day"], "", status="approved"
    )
    flash("Údaje byly předvyplněny ze školního účtu Microsoft Entra ID (Demo: novakp@spsul.cz).", "info")
    return redirect(url_for("add_person"))


@app.route("/auth/clear-entra")
def auth_clear_entra():
    session.pop("entra_user", None)
    flash("Předvyplněné údaje byly vymazány.", "info")
    return redirect(url_for("add_person"))


# ---------------------------------------------------------------------------
# Public: verify email code
# ---------------------------------------------------------------------------
@app.route("/verify", methods=["GET", "POST"])
def verify_code():
    email = session.get("verify_email")
    if not email:
        flash("Žádné ověřování neprobíhá. Začněte prosím na formuláři.", "warning")
        return redirect(url_for("add_person"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        person = verify_email_code(email, code)
        if not person:
            flash("Neplatný nebo expirovaný kód. Požádejte o nový zadáním údajů.", "error")
            return render_template("verify.html", email=email)

        mark_verified(person["id"])
        send_owner_notification(person["name"], person["email"])
        session.pop("verify_email", None)
        flash("E-mail byl úspěšně ověřen. Požadavek byl odeslán správci ke schválení.", "success")
        return redirect(url_for("verify_success"))

    return render_template("verify.html", email=email)


@app.route("/verify/success")
def verify_success():
    return render_template("verify_success.html")


# ---------------------------------------------------------------------------
# Admin & User Access Control
# ---------------------------------------------------------------------------
def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_auth"):
            flash("Tato sekce je přístupná pouze pro administrátora aplikace (oslavnik@spsul.cz).", "error")
            return redirect(url_for("admin_request"))
        return f(*args, **kwargs)
    return decorated


@app.route("/logout", methods=["GET"])
def user_logout():
    session.clear()
    flash("Byli jste úspěšně odhlášeni.", "info")
    return redirect(url_for("add_person"))


@app.route("/admin", methods=["GET"])
def admin_request():
    if session.get("admin_auth"):
        return redirect(url_for("admin_dashboard"))
    return render_template(
        "admin_request.html",
        entra_configured=is_entra_configured(),
    )


@app.route("/admin/request-code", methods=["POST"])
def admin_request_code():
    owner_email = os.getenv("OWNER_EMAIL", "oslavnik@spsul.cz")
    if not owner_email:
        flash("OWNER_EMAIL není nakonfigurováno na serveru.", "error")
        return redirect(url_for("admin_request"))

    alphabet = string.ascii_uppercase + string.digits
    code = "".join(secrets.choice(alphabet) for _ in range(8))
    create_admin_code(code, expires_minutes=15)
    send_admin_code(owner_email, code)

    flash(f"Jednorázový administrátorský kód byl odeslán na e-mail správce ({owner_email}).", "info")
    return redirect(url_for("admin_enter_code"))


@app.route("/admin/enter-code", methods=["GET", "POST"])
def admin_enter_code():
    if request.method == "POST":
        code = request.form.get("code", "").strip().upper()
        if verify_admin_code(code):
            session["admin_auth"] = True
            session["user_email"] = os.getenv("OWNER_EMAIL", "oslavnik@spsul.cz")
            session["user_name"] = "Správce"
            flash("Přístup do administrace byl udělen.", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Neplatný nebo expirovaný kód správce.", "error")
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
        flash(f"{person['name']} byl(a) úspěšně schválen(a).", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/reject/<int:person_id>", methods=["POST"])
@admin_required
def admin_reject(person_id):
    person = get_person_by_id(person_id)
    if person:
        reject_person(person_id)
        flash(f"{person['name']} byl(a) zamítnut(a).", "info")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete/<int:person_id>", methods=["POST"])
@admin_required
def admin_delete(person_id):
    person = get_person_by_id(person_id)
    if person:
        delete_person(person_id)
        flash(f"{person['name']} byl(a) úspěšně trvale odstraněn(a) z databáze.", "success")
    referrer = request.referrer or ""
    if "dashboard" in referrer:
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("list_people"))


@app.route("/admin/logout", methods=["GET"])
def admin_logout():
    session.pop("admin_auth", None)
    flash("Byli jste odhlášeni z administrace.", "info")
    return redirect(url_for("add_person"))


# ---------------------------------------------------------------------------
# Notifications & People (Admin Only)
# ---------------------------------------------------------------------------
@app.route("/people", methods=["GET"])
@admin_required
def list_people():
    people = get_all_people()
    return render_template("list_people.html", people=people)


@app.route("/send-notifications", methods=["POST"])
@admin_required
def send_notifications():
    events = get_upcoming_events(days_ahead=30)
    approved = get_approved_people()
    sent = 0
    skipped_self = 0

    recipient_events = defaultdict(list)
    for event_person, event_type, event_date, days_until in events:
        for recipient in approved:
            if recipient["id"] == event_person["id"]:
                skipped_self += 1
                continue
            recipient_events[recipient["id"]].append({
                "recipient": recipient,
                "event_person": event_person,
                "event_type": event_type,
                "event_date": event_date,
                "days_until": days_until,
            })

    for recipient_id, items in recipient_events.items():
        recipient = items[0]["recipient"]
        event_list = [
            {
                "person_name": it["event_person"]["name"],
                "event_type": it["event_type"],
                "event_date": it["event_date"],
                "days_until": it["days_until"],
            }
            for it in items
        ]
        event_list.sort(key=lambda ev: ev["event_date"])
        send_event_notifications(
            recipient["email"],
            recipient.get("name", recipient["email"]),
            event_list,
        )
        sent += len(event_list)

    flash(
        f"Odesláno {sent} oznámení pro {len(recipient_events)} příjemců. "
        f"{skipped_self} vlastních událostí přeskočeno.",
        "success",
    )
    return redirect(url_for("list_people"))


if __name__ == "__main__":
    port = int(os.getenv("SERVER_PORT") or os.getenv("PORT") or 5001)
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, host="0.0.0.0", port=port)
