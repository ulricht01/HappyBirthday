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
    return _events_html_table(events)


def _format_days_until(days_until: int) -> str:
    if days_until == 0:
        return "<strong style='color:#de401a;'>Dnes! 🎂</strong>"
    if days_until == 1:
        return "Zítra"
    if days_until in (2, 3, 4):
        return f"Za {days_until} dny"
    return f"Za {days_until} dní"


def _format_days_until_plain(days_until: int) -> str:
    if days_until == 0:
        return "Dnes!"
    if days_until == 1:
        return "Zítra"
    if days_until in (2, 3, 4):
        return f"Za {days_until} dny"
    return f"Za {days_until} dní"


def _format_event_label(ev):
    event_type = ev.get("event_type")
    years_count = ev.get("years_count")
    if event_type == "birthday":
        if years_count and years_count > 0:
            if years_count == 1:
                return "🎂 1. narozeniny (1 rok)"
            elif years_count in (2, 3, 4):
                return f"🎂 {years_count}. narozeniny ({years_count} roky)"
            else:
                return f"🎂 {years_count}. narozeniny ({years_count} let)"
        return "🎂 Narozeniny"
    elif event_type == "name_day":
        return "💐 Svátek"
    elif event_type == "job_anniversary":
        if years_count and years_count > 0:
            if years_count == 1:
                return "🏢 1. pracovní výročí (1 rok na SPŠUL)"
            elif years_count in (2, 3, 4):
                return f"🏢 {years_count}. pracovní výročí ({years_count} roky na SPŠUL)"
            else:
                return f"🏢 {years_count}. pracovní výročí ({years_count} let na SPŠUL)"
        return "🏢 Pracovní výročí"
    return event_type or "Událost"


def _format_event_label_plain(ev):
    event_type = ev.get("event_type")
    years_count = ev.get("years_count")
    if event_type == "birthday":
        if years_count and years_count > 0:
            if years_count == 1:
                return "1. narozeniny (1 rok)"
            elif years_count in (2, 3, 4):
                return f"{years_count}. narozeniny ({years_count} roky)"
            else:
                return f"{years_count}. narozeniny ({years_count} let)"
        return "narozeniny"
    elif event_type == "name_day":
        return "svátek"
    elif event_type == "job_anniversary":
        if years_count and years_count > 0:
            if years_count == 1:
                return "1. pracovní výročí (1 rok na SPŠUL)"
            elif years_count in (2, 3, 4):
                return f"{years_count}. pracovní výročí ({years_count} roky na SPŠUL)"
            else:
                return f"{years_count}. pracovní výročí ({years_count} let na SPŠUL)"
        return "pracovní výročí"
    return event_type or "událost"


def _events_html_table(events):
    html = (
        "<table border='0' cellpadding='10' cellspacing='0' style='width:100%; border-collapse:collapse; "
        "font-family:Roboto,Helvetica,Arial,sans-serif; font-size:14px; margin-top:16px; margin-bottom:20px;'>"
    )
    html += (
        "<tr style='background-color:#fff0eb; border-bottom:2px solid #de401a; color:#222222;'>"
        "<th style='padding:10px 12px; text-align:left;'>Událost</th>"
        "<th style='padding:10px 12px; text-align:left;'>Kolega / kolegyně</th>"
        "<th style='padding:10px 12px; text-align:left;'>Datum</th>"
        "<th style='padding:10px 12px; text-align:left;'>Kdy</th>"
        "</tr>"
    )
    for i, ev in enumerate(events):
        label = _format_event_label(ev)
        event_date = ev["event_date"]
        if hasattr(event_date, "strftime"):
            date_str = event_date.strftime("%d. %m. %Y")
        else:
            date_str = str(event_date)
        bg = "#ffffff" if i % 2 == 0 else "#fcfcfd"
        html += (
            f"<tr style='background-color:{bg}; border-bottom:1px solid #e5e7eb;'>"
            f"<td style='padding:10px 12px;'>{label}</td>"
            f"<td style='padding:10px 12px; font-weight:600;'>{ev['person_name']}</td>"
            f"<td style='padding:10px 12px; color:#555555;'>{date_str}</td>"
            f"<td style='padding:10px 12px;'>{_format_days_until(ev['days_until'])}</td>"
            f"</tr>"
        )
    html += "</table>"
    return html


def send_event_notifications(recipient_email, recipient_name, events):
    """Send one email to a recipient with a table of upcoming events (not their own)."""
    if not events:
        return

    if len(events) == 1:
        ev = events[0]
        event_type = ev.get("event_type")
        years_count = ev.get("years_count")

        if event_type == "job_anniversary" and years_count and years_count > 0:
            if ev["days_until"] == 0:
                subject = f"🎉 Dnes slaví {ev['person_name']} své {years_count}. pracovní výročí na SPŠUL!"
            elif ev["days_until"] == 1:
                subject = f"🎉 Zítra slaví {ev['person_name']} své {years_count}. pracovní výročí na SPŠUL"
            else:
                subject = f"🎉 {ev['person_name']} slaví své {years_count}. pracovní výročí na SPŠUL ({_format_days_until_plain(ev['days_until']).lower()})"
        elif event_type == "birthday" and years_count and years_count > 0:
            age_label = f"{years_count} rok" if years_count == 1 else (f"{years_count} roky" if 2 <= years_count <= 4 else f"{years_count} let")
            if ev["days_until"] == 0:
                subject = f"🎉 Dnes slaví {ev['person_name']} své {years_count}. narozeniny ({age_label})!"
            elif ev["days_until"] == 1:
                subject = f"🎉 Zítra slaví {ev['person_name']} své {years_count}. narozeniny ({age_label})"
            else:
                subject = f"🎉 {ev['person_name']} slaví své {years_count}. narozeniny ({age_label}, {_format_days_until_plain(ev['days_until']).lower()})"
        else:
            label = _format_event_label_plain(ev)
            if ev["days_until"] == 0:
                subject = f"🎉 Dnes má {label} {ev['person_name']}!"
            elif ev["days_until"] == 1:
                subject = f"🎉 Zítra má {label} {ev['person_name']}"
            else:
                subject = f"🎉 {ev['person_name']} má {label} {_format_days_until_plain(ev['days_until']).lower()}"
    else:
        if all(ev["days_until"] == 0 for ev in events):
            subject = f"🎉 Dnešní oslavenci na SPŠUL ({len(events)})"
        else:
            subject = f"🎉 Nadcházející události a oslavenci ({len(events)})"

    msg = EmailMessage()
    msg["To"] = recipient_email
    msg["Subject"] = subject

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>{subject}</title>
    </head>
    <body style='font-family:Roboto,Helvetica,Arial,sans-serif; background-color:#fffaf5; margin:0; padding:24px; color:#222222;'>
      <div style='max-width:640px; margin:0 auto; background-color:#ffffff; border-radius:12px; border:1px solid #f0e6dd; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.04);'>
        <div style='background-color:#de401a; padding:20px 24px; color:#ffffff;'>
          <h2 style='margin:0; font-size:1.25rem; font-weight:700;'>🎉 Narozeniny a svátky SPŠUL</h2>
        </div>
        <div style='padding:24px;'>
          <p style='font-size:1rem; margin-top:0;'>Dobrý den, <strong>{recipient_name}</strong>,</p>
          <p style='color:#555555; line-height:1.5;'>přinášíme vám přehled nadcházejících událostí a výročí vašich kolegů:</p>
          {_events_html_table(events)}
          <p style='color:#666666; font-size:0.9rem; margin-top:20px; line-height:1.5;'>
            Nezapomeňte kolegům popřát a oslavit jejich den! ☕🎂
          </p>
          <hr style='border:none; border-top:1px solid #eeeeee; margin:24px 0;' />
          <p style='font-size:0.8rem; color:#888888; margin-bottom:0;'>
            Střední průmyslová škola Ústí nad Labem &bull; Automatické interní oznámení
          </p>
        </div>
      </div>
    </body>
    </html>
    """

    lines = [
        f"Narozeniny a svátky SPŠUL",
        "========================================",
        f"Dobrý den, {recipient_name},",
        "",
        "přinášíme vám přehled nadcházejících událostí a výročí vašich kolegů:",
        "",
    ]
    for ev in events:
        label = _format_event_label_plain(ev)
        event_date = ev["event_date"]
        if hasattr(event_date, "strftime"):
            date_str = event_date.strftime("%d. %m. %Y")
        else:
            date_str = str(event_date)
        timing = _format_days_until_plain(ev['days_until'])
        lines.append(f"- {ev['person_name']} ({label}): {date_str} [{timing}]")
    lines.extend([
        "",
        "Přejeme hezký den,",
        "Střední průmyslová škola Ústí nad Labem",
    ])

    msg.set_content("\n".join(lines))
    msg.add_alternative(html, subtype="html")
    _send(msg)