import base64
import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request


# ============================================================
# LEAD SUMMARY
# ============================================================

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
# FIND UPLOADED PHOTO
# ============================================================

def _find_photo_file(app, lead):
    """
    Find the actual uploaded photo belonging to this lead.
    """

    if not lead.photos:
        return None

    upload_folder = app.config.get("UPLOAD_FOLDER")

    if not upload_folder:
        return None

    filenames = [
        os.path.basename(item.strip())
        for item in str(lead.photos).split(",")
        if item.strip()
    ]

    if not filenames:
        return None

    # First: exact path
    for filename in filenames:
        photo_path = os.path.join(
            upload_folder,
            filename
        )

        if os.path.isfile(photo_path):
            app.logger.info(
                "Found uploaded file for lead %s: %s",
                lead.id,
                photo_path
            )
            return photo_path

    # Fallback: search uploads folder
    try:
        for root, dirs, files in os.walk(upload_folder):

            for filename in filenames:

                if filename in files:

                    photo_path = os.path.join(
                        root,
                        filename
                    )

                    app.logger.info(
                        "Found uploaded file through search "
                        "for lead %s: %s",
                        lead.id,
                        photo_path
                    )

                    return photo_path

    except Exception as exc:
        app.logger.error(
            "Error searching upload folder for lead %s: %s",
            lead.id,
            exc
        )

    app.logger.warning(
        "Uploaded file not found for lead %s. Stored photos: %s",
        lead.id,
        lead.photos
    )

    return None


# ============================================================
# RESEND EMAIL
# ============================================================

def send_email_notification(app, lead_id):
    """
    Send lead notification through Resend HTTPS API.

    This avoids Render Free's SMTP port restrictions.
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

        resend_api_key = os.environ.get(
            "RESEND_API_KEY",
            ""
        ).strip()

        notify_email = os.environ.get(
            "NOTIFY_EMAIL",
            ""
        ).strip()

        resend_from = os.environ.get(
            "RESEND_FROM_EMAIL",
            ""
        ).strip()

        if not resend_api_key:
            app.logger.info(
                "Email not configured: RESEND_API_KEY missing — skipping."
            )
            return

        if not notify_email:
            app.logger.info(
                "Email not configured: NOTIFY_EMAIL missing — skipping."
            )
            return

        if not resend_from:
            app.logger.info(
                "Email not configured: RESEND_FROM_EMAIL missing — skipping."
            )
            return

        try:

            photo_path = _find_photo_file(
                app,
                lead
            )

            email_text = _lead_summary(
                lead
            )

            # ------------------------------------------------
            # Build email payload
            # ------------------------------------------------

            payload = {
                "from": resend_from,
                "to": [notify_email],
                "subject": (
                    f"New Quote Request — "
                    f"{lead.name} "
                    f"({lead.service or 'General'})"
                ),
                "text": email_text
            }

            # ------------------------------------------------
            # Attach uploaded photo if available
            # ------------------------------------------------

            if photo_path and os.path.isfile(photo_path):

                try:

                    with open(
                        photo_path,
                        "rb"
                    ) as file:

                        file_data = file.read()

                    encoded_file = base64.b64encode(
                        file_data
                    ).decode("utf-8")

                    filename = os.path.basename(
                        photo_path
                    )

                    payload["attachments"] = [
                        {
                            "filename": filename,
                            "content": encoded_file
                        }
                    ]

                    app.logger.info(
                        "Attaching photo to email for lead %s: %s",
                        lead_id,
                        filename
                    )

                except Exception as exc:

                    app.logger.error(
                        "Could not attach photo for lead %s: %s",
                        lead_id,
                        exc
                    )

            # ------------------------------------------------
            # Send through Resend HTTPS API
            # ------------------------------------------------

            url = "https://api.resend.com/emails"

            data = json.dumps(
                payload
            ).encode("utf-8")

            request = urllib.request.Request(
                url,
                data=data,
                method="POST",
                headers={
                    "Authorization": (
                        f"Bearer {resend_api_key}"
                    ),
                    "Content-Type": "application/json"
                }
            )

            with urllib.request.urlopen(
                request,
                timeout=30
            ) as response:

                response_body = response.read().decode(
                    "utf-8",
                    errors="replace"
                )

            app.logger.info(
                "Email notification sent successfully "
                "for lead %s: %s",
                lead_id,
                response_body
            )

            lead.email_sent = True
            db.session.commit()

        except urllib.error.HTTPError as exc:

            try:
                error_body = exc.read().decode(
                    "utf-8",
                    errors="replace"
                )
            except Exception:
                error_body = "Unable to read email API error."

            app.logger.error(
                "Email notification failed for lead %s: "
                "HTTP %s - %s",
                lead_id,
                exc.code,
                error_body
            )

        except Exception as exc:

            app.logger.error(
                "Email notification failed for lead %s: %s",
                lead_id,
                exc
            )


# ============================================================
# WHATSAPP / TWILIO
# ============================================================

def send_whatsapp_notification(app, lead_id):
    """
    Send lead notification through Twilio WhatsApp.

    Note:
    Twilio trial accounts may reject WhatsApp messages.
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

        sid = cfg.get(
            "TWILIO_ACCOUNT_SID"
        )

        token = cfg.get(
            "TWILIO_AUTH_TOKEN"
        )

        from_num = cfg.get(
            "TWILIO_WHATSAPP_FROM"
        )

        to_num = cfg.get(
            "NOTIFY_WHATSAPP_TO"
        )

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
    # Normal request
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
    Send lead details and uploaded photo to Telegram.
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

            # ------------------------------------------------
            # 1. Lead text
            # ------------------------------------------------

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
                "Telegram text notification sent "
                "for lead %s: %s",
                lead_id,
                result
            )

            # ------------------------------------------------
            # 2. Find uploaded photo
            # ------------------------------------------------

            photo_path = _find_photo_file(
                app,
                lead
            )

            if not photo_path:

                app.logger.warning(
                    "No uploaded photo found "
                    "for lead %s",
                    lead_id
                )

                return

            # ------------------------------------------------
            # 3. Send photo/document
            # ------------------------------------------------

            filename = os.path.basename(
                photo_path
            )

            extension = os.path.splitext(
                filename
            )[1].lower()

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

                error_body = exc.read().decode(
                    "utf-8",
                    errors="replace"
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
# NOTIFY NEW LEAD
# ============================================================

def notify_new_lead(
    app,
    lead_id
):
    """
    Send Email, WhatsApp and Telegram
    notifications in background threads.
    """

    # Email
    threading.Thread(
        target=send_email_notification,
        args=(app, lead_id),
        daemon=True
    ).start()

    # WhatsApp
    threading.Thread(
        target=send_whatsapp_notification,
        args=(app, lead_id),
        daemon=True
    ).start()

    # Telegram
    threading.Thread(
        target=send_telegram_notification,
        args=(app, lead_id),
        daemon=True
    ).start()