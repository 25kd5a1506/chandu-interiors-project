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


# ============================================================
# EMAIL NOTIFICATION
# ============================================================

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
                "Email not configured "
                "(SMTP_USER / NOTIFY_EMAIL) — skipping."
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

            app.logger.info(
                "Email notification sent successfully for lead %s",
                lead_id
            )

        except Exception as exc:

            app.logger.error(
                "Email notification failed for lead %s: %s",
                lead_id,
                exc
            )


# ============================================================
# WHATSAPP NOTIFICATION
# ============================================================

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

        if not all([
            sid,
            token,
            from_num,
            to_num
        ]):
            app.logger.info(
                "WhatsApp not configured "
                "(Twilio env vars) — skipping."
            )
            return

        try:
            from twilio.rest import Client

            client = Client(
                sid,
                token
            )

            client.messages.create(
                from_=from_num,
                to=to_num,
                body=_lead_summary(lead)
            )

            lead.whatsapp_sent = True
            db.session.commit()

            app.logger.info(
                "WhatsApp notification sent successfully "
                "for lead %s",
                lead_id
            )

        except Exception as exc:

            app.logger.error(
                "WhatsApp notification failed for lead %s: %s",
                lead_id,
                exc
            )


# ============================================================
# FIND UPLOADED PHOTO
# ============================================================

def _find_photo_file(app, lead):
    """
    Find the actual uploaded photo file for this lead.
    """

    if not lead.photos:
        return None

    upload_folder = app.config.get(
        "UPLOAD_FOLDER"
    )

    if not upload_folder:
        return None

    # Lead.photos can contain multiple filenames.
    # Example:
    # photo1.jpg,photo2.jpg
    filenames = [
        os.path.basename(
            item.strip()
        )
        for item in str(
            lead.photos
        ).split(",")
        if item.strip()
    ]

    if not filenames:
        return None

    # --------------------------------------------------------
    # First try the exact expected location
    # --------------------------------------------------------

    for filename in filenames:

        photo_path = os.path.join(
            upload_folder,
            filename
        )

        if os.path.isfile(photo_path):

            app.logger.info(
                "Found uploaded photo for lead %s: %s",
                lead.id,
                photo_path
            )

            return photo_path

    # --------------------------------------------------------
    # Fallback: search inside uploads directory
    # --------------------------------------------------------

    try:

        for root, dirs, files in os.walk(
            upload_folder
        ):

            for filename in filenames:

                if filename in files:

                    photo_path = os.path.join(
                        root,
                        filename
                    )

                    app.logger.info(
                        "Found uploaded photo through "
                        "fallback search for lead %s: %s",
                        lead.id,
                        photo_path
                    )

                    return photo_path

    except Exception as exc:

        app.logger.error(
            "Error searching for uploaded photo "
            "for lead %s: %s",
            lead.id,
            exc
        )

    app.logger.warning(
        "Uploaded photo file NOT found for lead %s. "
        "Stored value: %s",
        lead.id,
        lead.photos
    )

    return None


# ============================================================
# TELEGRAM HTTP REQUEST
# ============================================================

def _telegram_request(
    bot_token,
    method,
    fields=None,
    file_field=None,
    file_path=None
):
    """
    Send request to Telegram Bot API.

    Supports:
    - sendMessage
    - sendPhoto
    - sendDocument
    """

    url = (
        f"https://api.telegram.org/"
        f"bot{bot_token}/{method}"
    )

    # --------------------------------------------------------
    # Normal POST request
    # --------------------------------------------------------

    if not file_path:

        data = urllib.parse.urlencode(
            fields or {}
        ).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Content-Type":
                    "application/x-www-form-urlencoded"
            }
        )

        with urllib.request.urlopen(
            request,
            timeout=20
        ) as response:

            return response.read().decode(
                "utf-8",
                errors="replace"
            )

    # --------------------------------------------------------
    # Multipart file upload
    # --------------------------------------------------------

    boundary = (
        "----ChanduInteriorsTelegramBoundary"
    )

    body = bytearray()

    def add_field(name, value):

        body.extend(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; '
                f'name="{name}"\r\n'
                f"\r\n"
                f"{value}\r\n"
            ).encode("utf-8")
        )

    for name, value in (
        fields or {}
    ).items():

        add_field(
            name,
            value
        )

    filename = os.path.basename(
        file_path
    )

    with open(
        file_path,
        "rb"
    ) as file:

        file_data = file.read()

    body.extend(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; '
            f'name="{file_field}"; '
            f'filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n"
            f"\r\n"
        ).encode("utf-8")
    )

    body.extend(
        file_data
    )

    body.extend(
        (
            f"\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
    )

    request = urllib.request.Request(
        url,
        data=bytes(body),
        method="POST",
        headers={
            "Content-Type":
                f"multipart/form-data; boundary={boundary}"
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=30
    ) as response:

        return response.read().decode(
            "utf-8",
            errors="replace"
        )


# ============================================================
# TELEGRAM NOTIFICATION
# ============================================================

def send_telegram_notification(
    app,
    lead_id
):
    """
    Send lead details to Telegram.

    First:
        Send complete lead information.

    Then:
        Find uploaded image.

    Finally:
        Send actual image to Telegram.
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
                "(TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID) "
                "— skipping."
            )

            return

        try:

            # =================================================
            # 1. SEND TEXT
            # =================================================

            message = _lead_summary(
                lead
            )

            result = _telegram_request(
                bot_token=bot_token,
                method="sendMessage",
                fields={
                    "chat_id": str(chat_id),
                    "text": message
                }
            )

            app.logger.info(
                "Telegram text notification "
                "sent for lead %s: %s",
                lead_id,
                result
            )

            # =================================================
            # 2. FIND PHOTO
            # =================================================

            photo_path = _find_photo_file(
                app,
                lead
            )

            if not photo_path:

                app.logger.warning(
                    "No actual uploaded photo found "
                    "for lead %s",
                    lead_id
                )

                return

            # =================================================
            # 3. CHECK FILE
            # =================================================

            if not os.path.isfile(
                photo_path
            ):

                app.logger.warning(
                    "Photo path does not exist "
                    "for lead %s: %s",
                    lead_id,
                    photo_path
                )

                return

            filename = os.path.basename(
                photo_path
            )

            extension = os.path.splitext(
                filename
            )[1].lower()

            # =================================================
            # 4. SEND IMAGE
            # =================================================

            image_extensions = {
                ".jpg",
                ".jpeg",
                ".png",
                ".webp"
            }

            if extension in image_extensions:

                result = _telegram_request(
                    bot_token=bot_token,
                    method="sendPhoto",
                    fields={
                        "chat_id": str(chat_id),
                        "caption": (
                            f"📸 Photo for Lead #{lead_id}\n"
                            f"Name: {lead.name}\n"
                            f"Service: "
                            f"{lead.service or 'General'}"
                        )
                    },
                    file_field="photo",
                    file_path=photo_path
                )

                app.logger.info(
                    "Telegram PHOTO sent successfully "
                    "for lead %s: %s",
                    lead_id,
                    result
                )

            # =================================================
            # 5. SEND OTHER FILE TYPES
            # =================================================

            else:

                result = _telegram_request(
                    bot_token=bot_token,
                    method="sendDocument",
                    fields={
                        "chat_id": str(chat_id),
                        "caption": (
                            f"📎 Attachment for Lead #{lead_id}\n"
                            f"Name: {lead.name}\n"
                            f"Service: "
                            f"{lead.service or 'General'}"
                        )
                    },
                    file_field="document",
                    file_path=photo_path
                )

                app.logger.info(
                    "Telegram DOCUMENT sent successfully "
                    "for lead %s: %s",
                    lead_id,
                    result
                )

        except urllib.error.HTTPError as exc:

            try:

                error_body = (
                    exc.read()
                    .decode(
                        "utf-8",
                        errors="replace"
                    )
                )

            except Exception:

                error_body = (
                    "Unable to read Telegram error."
                )

            app.logger.error(
                "Telegram notification failed "
                "for lead %s: HTTP %s - %s",
                lead_id,
                exc.code,
                error_body
            )

        except Exception as exc:

            app.logger.error(
                "Telegram notification failed "
                "for lead %s: %s",
                lead_id,
                exc
            )


# ============================================================
# ALL NOTIFICATIONS
# ============================================================

def notify_new_lead(
    app,
    lead_id
):
    """
    Send Email, WhatsApp and Telegram
    notifications in background threads.

    Customer form does not need to wait
    for notifications to finish.
    """

    # --------------------------------------------------------
    # Email
    # --------------------------------------------------------

    threading.Thread(
        target=send_email_notification,
        args=(app, lead_id),
        daemon=True
    ).start()

    # --------------------------------------------------------
    # WhatsApp
    # --------------------------------------------------------

    threading.Thread(
        target=send_whatsapp_notification,
        args=(app, lead_id),
        daemon=True
    ).start()

    # --------------------------------------------------------
    # Telegram
    # --------------------------------------------------------

    threading.Thread(
        target=send_telegram_notification,
        args=(app, lead_id),
        daemon=True
    ).start()