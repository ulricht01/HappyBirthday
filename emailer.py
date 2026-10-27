import os
import smtplib
from datetime import date
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

def _events_html_table(events):
    """Build an HTML table listing only the upcoming events (no personal bio)."""
    event_labels_cs = {
        "birthday": "Narozeniny",
        "name_day": "Svatky",
        "job_anniversary": "Vyroci v zamestnani",
    }

    html = (
        "<table border='1' cellpadding='6' cellspacing='0' "
        "style='border-collapse:collapse; font-family:sans-serif; font-size:14px;'>"
    )
    html += (
        "<tr>"
        "<th style='font-weight:bold; text-align:left;'>Udalost</th>"
        "<th style='font-weight:bold; text-align:left;'>Osoba</th>"
        "<th style='font-weight:bold; text-align:left;'>Datum</th>"
        "<th style='font-weight:bold; text-align:left;'>Za kolik dni</th>"
        "</tr>"
    )
    for ev in events:
        label = event_labels_cs.get(ev["event_type"], ev["event_type"])
        event_date = ev["event_date"]
        if hasattr(event_date, "strftime"):
            date_str = event_date.strftime("%d. %m. %Y")
        else:
            date_str = str(event_date)
        html += (
            f"<tr>"
            f"<td>{label}</td>"
            f"<td>{ev['person_name']}</td>"
            f"<td>{date_str}</td>"
            f"<td>{ev['days_until']} dni</td>"
            f"</tr>"
        )
    html += "</table>"
    return html


def send_event_notifications(recipient_email, recipient_name, events):
    """Send one email to a recipient with a table of upcoming events (not their own)."""
    event_labels_cs = {
        "birthday": "Narozeniny",
        "name_day": "Svatky",
        "job_anniversary": "Vyroci v zamestnani",
    }

    if len(events) == 1:
        label = event_labels_cs.get(events[0]["event_type"], events[0]["event_type"])
        subject = f"\U0001f389 {label} je za {events[0]['days_until']} dnu"
    else:
        subject = f"\U0001f389 Blizici se udalosti ({len(events)})"

    msg = EmailMessage()
    msg["To"] = recipient_email
    msg["Subject"] = subject

    html = f"""
    <html>
    <body style='font-family:sans-serif;'>
      <h2>\U0001f389 Blizici se udalosti</h2>
      <p>Ahoj {recipient_name},</p>
      <p>Mame pro vas seznam nadchazejicich udalosti (krome vasich vlastnich):</p>
      {_events_html_table(events)}
      <p><br/><br/>Prejeme hezky den,<br/>Tym HappyBirthday</p>
    </body>
    </html>
    """

    lines = [
        f"\U0001f389 Blizici se udalosti",
        "",
        f"Ahoj {recipient_name},",
        "",
        "Mame pro vas seznam nadchazejicich udalosti (krome vasich vlastnich):",
        "",
    ]
    for ev in events:
        label = event_labels_cs.get(ev["event_type"], ev["event_type"])
        event_date = ev["event_date"]
        if hasattr(event_date, "strftime"):
            date_str = event_date.strftime("%d. %m. %Y")
        else:
            date_str = str(event_date)
        lines.append(
            f"- {label}: {ev['person_name']}, {date_str} (za {ev['days_until']} dni)"
        )
    lines.extend(
        [
            "",
            "Prejeme hezky den,",
            "Tym HappyBirthday",
        ]
    )

    msg.set_content("\n".join(lines))
    msg.add_alternative(html, subtype="html")
    _send(msg)