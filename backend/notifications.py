import smtplib
import threading
import urllib.parse
import urllib.request

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


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
    """Send lead notification by email in a background thread."""
    with app.app_context():
        from models import db, Lead

        lead = db.session.get(Lead, lead_id)
        if lead is None:
            return

        cfg = app.config

        if not cfg.get("SMTP_USER") or not cfg.get("NOTIFY_EMAIL"):
            app.logger.info(
                "Email not configured (SMTP_USER / NOTIFY_EMAIL) — skipping."
            )
            return

        try:
            msg = MIMEMultipart()
            msg["From"] = cfg["SMTP_USER"]
            msg["To"] = cfg["NOTIFY_EMAIL"]
            msg["Subject"] = (
                f"New Quote Request — {lead.name} "
                f"({lead.service or 'General'})"
            )

            msg.attach(MIMEText(_lead_summary(lead), "plain"))

            with smtplib.SMTP(
                cfg["SMTP_HOST"],
                cfg["SMTP_PORT"],
                timeout=15
            ) as server:
                server.starttls()
                server.login(
                    cfg["SMTP_USER"],
                    cfg["SMTP_PASSWORD"]
                )
                server.send_message(msg)

            lead.email_sent = True
            db.session.commit()

        except Exception as exc:
            app.logger.error(
                "Email notification failed for lead %s: %s",
                lead_id,
                exc
            )


def send_whatsapp_notification(app, lead_id):
    """Send lead notification through Twilio WhatsApp."""
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
            app.logger.info(
                "WhatsApp not configured (Twilio env vars) — skipping."
            )
            return

        try:
            from twilio.rest import Client

            client = Client(sid, token)

            client.messages.create(
                from_=from_num,
                to=to_num,
                body=_lead_summary(lead)
            )

            lead.whatsapp_sent = True
            db.session.commit()

        except Exception as exc:
            app.logger.error(
                "WhatsApp notification failed for lead %s: %s",
                lead_id,
                exc
            )


def send_telegram_notification(app, lead_id):
    """Send lead notification to the Chandu Interiors Telegram bot."""
    with app.app_context():
        from models import db, Lead

        lead = db.session.get(Lead, lead_id)
        if lead is None:
            return

        cfg = app.config

        bot_token = cfg.get("TELEGRAM_BOT_TOKEN")
        chat_id = cfg.get("TELEGRAM_CHAT_ID")

        if not bot_token or not chat_id:
            app.logger.info(
                "Telegram not configured (TELEGRAM_BOT_TOKEN / "
                "TELEGRAM_CHAT_ID) — skipping."
            )
            return

        try:
            message = _lead_summary(lead)

            url = (
                f"https://api.telegram.org/bot{bot_token}/sendMessage"
            )

            data = urllib.parse.urlencode({
                "chat_id": chat_id,
                "text": message
            }).encode("utf-8")

            request = urllib.request.Request(
                url,
                data=data,
                method="POST"
            )

            with urllib.request.urlopen(request, timeout=15) as response:
                response.read()

            app.logger.info(
                "Telegram notification sent successfully for lead %s",
                lead_id
            )

        except Exception as exc:
            app.logger.error(
                "Telegram notification failed for lead %s: %s",
                lead_id,
                exc
            )


def notify_new_lead(app, lead_id):
    """
    Send Email, WhatsApp and Telegram notifications
    in background threads so the customer form responds quickly.
    """

    threading.Thread(
        target=send_email_notification,
        args=(app, lead_id),
        daemon=True
    ).start()

    threading.Thread(
        target=send_whatsapp_notification,
        args=(app, lead_id),
        daemon=True
    ).start()

    threading.Thread(
        target=send_telegram_notification,
        args=(app, lead_id),
        daemon=True
    ).start()