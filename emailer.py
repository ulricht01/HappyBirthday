import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()


def _send(msg: EmailMessage):
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587") or 587)
    user = os.getenv("SMTP_USER")
    pwd = os.getenv("SMTP_PASS")
    from_email = os.getenv("FROM_EMAIL", "HappyBirthday <noreply@example.com>")

    msg["From"] = from_email

    if not host or not user or not pwd:
        # Fallback for local testing without SMTP configured
        _print_email(msg)
        return

    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port)
        else:
            server = smtplib.SMTP(host, port)
            server.starttls()
        if user and pwd:
            server.login(user, pwd)
        server.send_message(msg)
        server.quit()
    except Exception:
        # SMTP server unavailable or misconfigured — fall back to stdout
        _print_email(msg)


def _print_email(msg: EmailMessage):
    print("=" * 60)
    print("EMAIL (SMTP not configured or unavailable, printing to stdout):")
    print(msg)
    print("=" * 60)


def send_verification_code(to_email, code):
    msg = EmailMessage()
    msg["To"] = to_email
    msg["Subject"] = "Your HappyBirthday verification code"
    msg.set_content(
        f"Hello,\n\nYour verification code is: {code}\n\n"
        f"This code expires in 24 hours.\n\n"
        f"HappyBirthday Team"
    )
    _send(msg)


def send_owner_notification(person_name, person_email):
    owner = os.getenv("OWNER_EMAIL")
    if not owner:
        return
    msg = EmailMessage()
    msg["To"] = owner
    msg["Subject"] = "New person awaiting approval - HappyBirthday"
    msg.set_content(
        f"A new person has submitted their info and verified their email.\n\n"
        f"Name: {person_name}\n"
        f"Email: {person_email}\n\n"
        f"Please request admin access at /admin to review and approve or reject.\n\n"
        f"HappyBirthday Team"
    )
    _send(msg)


def send_admin_code(to_email, code):
    msg = EmailMessage()
    msg["To"] = to_email
    msg["Subject"] = "Your one-time HappyBirthday admin access code"
    msg.set_content(
        f"Hello,\n\nYour one-time admin access code is: {code}\n\n"
        f"This code can be used only once and expires shortly.\n"
        f"Use it at /admin to review pending people.\n\n"
        f"HappyBirthday Team"
    )
    _send(msg)


def _person_html_table(person):
    rows = [
        ("Name", person.get("name", "")),
        ("Email", person.get("email", "")),
        ("Date of birth", person.get("date_of_birth") or "—"),
        ("First day in job", person.get("first_day_job") or "—"),
        ("Name day", person.get("name_day") or "—"),
        ("About", person.get("about_info") or "—"),
    ]
    html = "<table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse; font-family:sans-serif; font-size:14px;'>"
    for label, value in rows:
        html += f"<tr><td style='font-weight:bold;'>{label}</td><td>{value}</td></tr>"
    html += "</table>"
    return html


def send_event_notification(recipient_email, event_person, event_type, days_until):
    """Send an email to one recipient about an upcoming event for another person."""
    event_labels = {
        "birthday": "Birthday",
        "name_day": "Name day",
        "job_anniversary": "Work anniversary",
    }
    label = event_labels.get(event_type, event_type)
    owner = os.getenv("FROM_EMAIL", "HappyBirthday <noreply@example.com>")

    msg = EmailMessage()
    msg["To"] = recipient_email
    msg["Subject"] = f"🎉 {event_person['name']}'s {label} is in {days_until} day(s)"

    html = f"""
    <html>
    <body style='font-family:sans-serif;'>
      <h2>🎉 Upcoming {label}</h2>
      <p>{event_person['name']}'s {label.lower()} is in <b>{days_until}</b> day(s).</p>
      <p>Here is their info:</p>
      {_person_html_table(event_person)}
      <p><br/><br/>HappyBirthday Team</p>
    </body>
    </html>
    """
    msg.set_content(
        f"🎉 Upcoming {label}\n\n"
        f"{event_person['name']}'s {label.lower()} is in {days_until} day(s).\n\n"
        f"Name: {event_person.get('name', '')}\n"
        f"Email: {event_person.get('email', '')}\n"
        f"Date of birth: {event_person.get('date_of_birth') or '—'}\n"
        f"First day in job: {event_person.get('first_day_job') or '—'}\n"
        f"Name day: {event_person.get('name_day') or '—'}\n"
        f"About: {event_person.get('about_info') or '—'}\n\n"
        f"HappyBirthday Team"
    )
    msg.add_alternative(html, subtype="html")
    _send(msg)