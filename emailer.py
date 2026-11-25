import os
import sys
import smtplib
import logging
from datetime import date
from email.message import EmailMessage

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Fallback parser if python-dotenv is not installed in the current environment
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k not in os.environ:
                        os.environ[k] = v

logger = logging.getLogger("emailer")


def _send(msg: EmailMessage) -> bool:
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587") or 587)
    user = os.getenv("SMTP_USER")
    pwd = os.getenv("SMTP_PASS")
    from_email = os.getenv("FROM_EMAIL", "HappyBirthday <noreply@example.com>")
    timeout = int(os.getenv("SMTP_TIMEOUT", "10") or 10)
    use_tls_env = os.getenv("SMTP_USE_TLS", "true").strip().lower()
    use_tls = use_tls_env not in ("0", "false", "no", "off")

    if not msg.get("From"):
        msg["From"] = from_email

    # Check if host or credentials are missing
    if not host or not user or not pwd:
        # Fallback for local testing without SMTP configured
        _print_email(msg)
        return False

    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=timeout)
        else:
            server = smtplib.SMTP(host, port, timeout=timeout)
            if use_tls:
                server.starttls()
        if user and pwd:
            server.login(user, pwd)
        server.send_message(msg)
        server.quit()
        logger.info("Email sent successfully via SMTP to %s", msg.get("To"))
        return True
    except Exception as exc:
        # SMTP server unavailable or misconfigured — log warning and fall back to stdout
        logger.warning(
            "SMTP send failed (%s:%s) for recipient %s: %s. Falling back to stdout.",
            host, port, msg.get("To"), exc
        )
        print(f"[SMTP WARNING] Failed to send email via {host}:{port}: {exc}", file=sys.stderr)
        _print_email(msg)
        return False


def verify_smtp_config(send_test_email: bool = False, target_email: str = None) -> bool:
    """
    Check SMTP configuration and test server connectivity/authentication.
    Can be called on application startup or standalone.
    """
    host = os.getenv("SMTP_HOST")
    port_str = os.getenv("SMTP_PORT", "587")
    user = os.getenv("SMTP_USER")
    pwd = os.getenv("SMTP_PASS")
    from_email = os.getenv("FROM_EMAIL", "HappyBirthday <noreply@example.com>")
    timeout = int(os.getenv("SMTP_TIMEOUT", "10") or 10)
    use_tls_env = os.getenv("SMTP_USE_TLS", "true").strip().lower()
    use_tls = use_tls_env not in ("0", "false", "no", "off")

    print("\n" + "=" * 65)
    print("SMTP STARTUP DIAGNOSTIC CHECK")
    print("=" * 65)

    if not host or not user or not pwd:
        print("[SMTP] Status: NOT CONFIGURED (SMTP_HOST, SMTP_USER, or SMTP_PASS missing).")
        print("[SMTP] Fallback: Outgoing emails will be printed to stdout.")
        print("=" * 65 + "\n")
        return False

    placeholders = []
    if host in ("smtp.gmail.com",) and user == "your-email@gmail.com":
        placeholders.append("SMTP_USER='your-email@gmail.com'")
    if pwd == "your-app-password":
        placeholders.append("SMTP_PASS='your-app-password'")

    if placeholders:
        print(f"[SMTP WARNING] Placeholder values detected: {', '.join(placeholders)}")
        print("[SMTP WARNING] Please update .env with your real SMTP credentials.")
        print("[SMTP] Fallback: Outgoing emails will be printed to stdout.")
        print("=" * 65 + "\n")
        return False

    try:
        port = int(port_str)
    except ValueError:
        print(f"[SMTP ERROR] Invalid SMTP_PORT: '{port_str}'")
        print("=" * 65 + "\n")
        return False

    print(f"[SMTP] Connecting to {host}:{port} as '{user}' (timeout: {timeout}s)...")
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=timeout)
        else:
            server = smtplib.SMTP(host, port, timeout=timeout)
            if use_tls:
                server.starttls()

        server.login(user, pwd)
        print(f"[SMTP SUCCESS] Connected and authenticated successfully to {host}:{port}!")

        if send_test_email and target_email:
            msg = EmailMessage()
            msg["To"] = target_email
            msg["From"] = from_email
            msg["Subject"] = "HappyBirthday SMTP Test Email"
            msg.set_content(
                "Hello,\n\n"
                "This is a test email sent from HappyBirthday.\n"
                "If you see this, your SMTP configuration is working properly!\n\n"
                "HappyBirthday Team"
            )
            server.send_message(msg)
            print(f"[SMTP SUCCESS] Test email sent successfully to {target_email}.")

        server.quit()
        print("=" * 65 + "\n")
        return True
    except smtplib.SMTPAuthenticationError as exc:
        print(f"[SMTP ERROR] Authentication failed: {exc}")
        if "office365" in host.lower() or "outlook" in host.lower():
            print("  -> Microsoft 365 Tip: If 2FA/MFA is enabled, an App Password is required.")
            print("  -> Also check if your IT admin enabled 'Authenticated SMTP' for this mailbox.")
        elif "gmail" in host.lower():
            print("  -> Gmail Tip: Generate an App Password at https://myaccount.google.com/apppasswords")
        print("[SMTP] Fallback: Outgoing emails will be printed to stdout.")
        print("=" * 65 + "\n")
        return False
    except Exception as exc:
        print(f"[SMTP ERROR] Connection/TLS failed: {exc}")
        print("[SMTP] Fallback: Outgoing emails will be printed to stdout.")
        print("=" * 65 + "\n")
        return False


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