import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    # =========================================================
    # Database
    # =========================================================

    database_url = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(BASE_DIR, 'leads.db')}"
    )

    # Render may provide postgres://
    # SQLAlchemy requires postgresql://
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql://",
            1
        )

    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Keep PostgreSQL connections healthy on Render
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    # =========================================================
    # File uploads
    # =========================================================

    UPLOAD_FOLDER = os.path.join(
        BASE_DIR,
        "static",
        "uploads"
    )

    ALLOWED_EXTENSIONS = {
        "png",
        "jpg",
        "jpeg",
        "webp",
        "gif",
        "pdf"
    }

    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB

    # =========================================================
    # Email notifications
    # =========================================================

    SMTP_HOST = os.environ.get(
        "SMTP_HOST",
        "smtp.gmail.com"
    )

    SMTP_PORT = int(
        os.environ.get(
            "SMTP_PORT",
            587
        )
    )

    SMTP_USER = os.environ.get(
        "SMTP_USER",
        ""
    )

    SMTP_PASSWORD = os.environ.get(
        "SMTP_PASSWORD",
        ""
    )

    NOTIFY_EMAIL = os.environ.get(
        "NOTIFY_EMAIL",
        ""
    )

    # =========================================================
    # WhatsApp notifications - Twilio
    # =========================================================

    # Telegram notifications
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

    TWILIO_ACCOUNT_SID = os.environ.get(
        "TWILIO_ACCOUNT_SID",
        ""
    )

    TWILIO_AUTH_TOKEN = os.environ.get(
        "TWILIO_AUTH_TOKEN",
        ""
    )

    TWILIO_WHATSAPP_FROM = os.environ.get(
        "TWILIO_WHATSAPP_FROM",
        ""
    )

    NOTIFY_WHATSAPP_TO = os.environ.get(
        "NOTIFY_WHATSAPP_TO",
        ""
    )

    # =========================================================
    # Admin panel login
    # =========================================================

    ADMIN_USERNAME = os.environ.get(
        "ADMIN_USERNAME",
        "admin"
    )

    ADMIN_PASSWORD = os.environ.get(
        "ADMIN_PASSWORD",
        "change-me"
    )

    # =========================================================
    # CORS
    # =========================================================

    CORS_ORIGINS = os.environ.get(
        "CORS_ORIGINS",
        "*"
    )