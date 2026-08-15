from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Lead(db.Model):
    __tablename__ = "leads"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    whatsapp = db.Column(db.String(30))
    location = db.Column(db.String(200))
    service = db.Column(db.String(100))
    details = db.Column(db.Text)
    photos = db.Column(db.Text)          # comma-separated stored filenames
    status = db.Column(db.String(20), default="new")   # new / contacted / closed
    email_sent = db.Column(db.Boolean, default=False)
    whatsapp_sent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "whatsapp": self.whatsapp,
            "location": self.location,
            "service": self.service,
            "details": self.details,
            "photos": self.photos.split(",") if self.photos else [],
            "status": self.status,
            "email_sent": self.email_sent,
            "whatsapp_sent": self.whatsapp_sent,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M"),
        }
