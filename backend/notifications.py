```python
import os
import smtplib
import threading
import urllib.parse
import urllib.request
import urllib.error

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

            msg.attach(
                MIMEText(
                    _lead_summary(lead),
                    "plain"
                )
            )

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


def _find_photo_file(app, lead):
    """
    Find the uploaded photo file belonging to this lead.
    """

    if not lead.photos:
        return None

    filename = os.path.basename(str(lead.photos).strip())

    if not filename:
        return None

    upload_folder = app.config.get("UPLOAD_FOLDER")

    if not upload_folder:
        return None

    photo_path = os.path.join(
        upload_folder,
        filename
    )

    if os.path.isfile(photo_path):
        return photo_path

    # Extra fallback:
    # search inside the uploads directory.
    try:
        for root, dirs, files in os.walk(upload_folder):

            if filename in files:
                return os.path.join(
                    root,
                    filename
                )

    except Exception as exc:
        app.logger.error(
            "Error searching for photo %s: %s",
            filename,
            exc
        )

    return None


def _telegram_request(
    bot_token,
    method,
    fields=None,
    file_field=None,
    file_path=None
):
    """
    Send a request to Telegram Bot API.

    If file_path is supplied, send the file as multipart/form-data.
    """

    if not file_path:
        url = (
            f"https://api.telegram.org/"
            f"bot{bot_token}/{method}"
        )

        data = urllib.parse.urlencode(
            fields or {}
        ).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=data,
            method="POST"
        )

        with urllib.request.urlopen(
            request,
            timeout=20
        ) as response:

            return response.read().decode("utf-8")

    # Multipart upload for photo/document
    boundary = "----ChanduInteriorsTelegramBoundary"

    body = bytearray()

    def add_field(name, value):
        body.extend(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; '
                f'name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        )

    for name, value in (fields or {}).items():
        add_field(name, value)

    filename = os.path.basename(file_path)

    with open(file_path, "rb") as file:
        file_data = file.read()

    body.extend(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; '
            f'name="{file_field}"; '
            f'filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8")
    )

    body.extend(file_data)
    body.extend(
        f"\r\n--{boundary}--\r\n".encode("utf-8")
    )

    url = (
        f"https://api.telegram.org/"
        f"bot{bot_token}/{method}"
    )

    request = urllib.request.Request(
        url,
        data=bytes(body),
        method="POST",
        headers={
            "Content-Type": (
                f"multipart/form-data; boundary={boundary}"
            )
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=30
    ) as response:

        return response.read().decode("utf-8")


def send_telegram_notification(app, lead_id):
    """
    Send lead details to Telegram.

    If the lead contains an uploaded photo,
    send the actual photo/file after the text message.
    """

    with app.app_context():
        from models import db, Lead

        lead = db.session.get(
            Lead,
            lead_id
        )

        if lead is None:
            return

        cfg = app.config

        bot_token = cfg.get(
            "TELEGRAM_BOT_TOKEN"
        )

        chat_id = cfg.get(
            "TELEGRAM_CHAT_ID"
        )

        if not bot_token or not chat_id:
            app.logger.info(
                "Telegram not configured "
                "(TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID) — skipping."
            )
            return

        try:
            # -------------------------------------------------
            # 1. Send lead text
            # -------------------------------------------------

            message = _lead_summary(lead)

            result = _telegram_request(
                bot_token=bot_token,
                method="sendMessage",
                fields={
                    "chat_id": str(chat_id),
                    "text": message
                }
            )

            app.logger.info(
                "Telegram text notification sent for lead %s: %s",
                lead_id,
                result
            )

            # -------------------------------------------------
            # 2. Find uploaded photo
            # -------------------------------------------------

            photo_path = _find_photo_file(
                app,
                lead
            )

            if not photo_path:
                app.logger.info(
                    "No uploaded photo file found for lead %s",
                    lead_id
                )
                return

            # -------------------------------------------------
            # 3. Send actual file to Telegram
            # -------------------------------------------------

            filename = os.path.basename(
                photo_path
            )

            # Image extensions that Telegram can display as photo
            image_extensions = {
                ".jpg",
                ".jpeg",
                ".png",
                ".webp"
            }

            extension = os.path.splitext(
                filename
            )[1].lower()

            if extension in image_extensions:

                _telegram_request(
                    bot_token=bot_token,
                    method="sendPhoto",
                    fields={
                        "chat_id": str(chat_id),
                        "caption": (
                            f"Photo for lead #{lead_id}\n"
                            f"{lead.name}"
                        )
                    },
                    file_field="photo",
                    file_path=photo_path
                )

                app.logger.info(
                    "Telegram photo sent successfully "
                    "for lead %s: %s",
                    lead_id,
                    filename
                )

            else:

                _telegram_request(
                    bot_token=bot_token,
                    method="sendDocument",
                    fields={
                        "chat_id": str(chat_id),
                        "caption": (
                            f"Attachment for lead #{lead_id}\n"
                            f"{lead.name}"
                        )
                    },
                    file_field="document",
                    file_path=photo_path
                )

                app.logger.info(
                    "Telegram document sent successfully "
                    "for lead %s: %s",
                    lead_id,
                    filename
                )

        except urllib.error.HTTPError as exc:

            try:
                error_body = exc.read().decode(
                    "utf-8",
                    errors="replace"
                )
            except Exception:
                error_body = "Unable to read Telegram error."

            app.logger.error(
                "Telegram notification failed for lead %s: "
                "HTTP %s - %s",
                lead_id,
                exc.code,
                error_body
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
    in background threads.
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
```
