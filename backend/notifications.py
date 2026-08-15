import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import current_app


def _lead_summary(lead):
    return (
        f"New quote request from the website\n"
        f"{'-' * 36}\n"
        f"Name:      {lead.name}\n"
        f"Phone:     {lead.phone}\n"
        f"WhatsApp:  {lead.whatsapp or '-'}\n"
        f"Location:  {lead.location or '-'}\n"
        f"Service:   {lead.service or '-'}\n"
        f"Details:   {lead.details or '-'}\n"
        f"Photos:    {lead.photos or 'None'}\n"
        f"Submitted: {lead.created_at}\n"
    )


def send_email_notification(app, lead_id):
    """Runs in a background thread. Needs the app for its own context."""
    with app.app_context():
        from models import db, Lead

        lead = db.session.get(Lead, lead_id)
        if lead is None:
            return

        cfg = app.config
        if not cfg.get("SMTP_USER") or not cfg.get("NOTIFY_EMAIL"):
            app.logger.info("Email not configured (SMTP_USER / NOTIFY_EMAIL) — skipping.")
            return

        try:
            msg = MIMEMultipart()
            msg["From"] = cfg["SMTP_USER"]
            msg["To"] = cfg["NOTIFY_EMAIL"]
            msg["Subject"] = f"New Quote Request — {lead.name} ({lead.service or 'General'})"
            msg.attach(MIMEText(_lead_summary(lead), "plain"))

            with smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=15) as server:
                server.starttls()
                server.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
                server.send_message(msg)

            lead.email_sent = True
            db.session.commit()
        except Exception as exc:  # noqa: BLE001 - log and move on, never crash the request
            app.logger.error("Email notification failed for lead %s: %s", lead_id, exc)


def send_whatsapp_notification(app, lead_id):
    """Runs in a background thread. Sends a WhatsApp alert via Twilio's API."""
    with app.app_context():
        from models import db, Lead

        lead = db.session.get(Lead, lead_id)
        if lead is None:
            return

        cfg = app.config
        sid = cfg.get("TWILIO_ACCOUNT_SID")
        token = cfg.get("TWILIO_AUTH_TOKEN")
        from_num = cfg.get("TWILIO_WHATSAPP_FROM")
        to_num = cfg.get("NOTIFY_WHATSAPP_TO")

        if not all([sid, token, from_num, to_num]):
            app.logger.info("WhatsApp not configured (Twilio env vars) — skipping.")
            return

        try:
            from twilio.rest import Client

            client = Client(sid, token)
            client.messages.create(from_=from_num, to=to_num, body=_lead_summary(lead))

            lead.whatsapp_sent = True
            db.session.commit()
        except Exception as exc:  # noqa: BLE001
            app.logger.error("WhatsApp notification failed for lead %s: %s", lead_id, exc)


def notify_new_lead(app, lead_id):
    """Fire both notifications off the main request thread so the form
    submission returns instantly, even if email/WhatsApp are slow or down."""
    threading.Thread(target=send_email_notification, args=(app, lead_id), daemon=True).start()
    threading.Thread(target=send_whatsapp_notification, args=(app, lead_id), daemon=True).start()
