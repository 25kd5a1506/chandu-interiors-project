import os
from functools import wraps

from flask import (
    Flask, request, jsonify, render_template, redirect,
    url_for, session, send_from_directory, flash
)
from flask_cors import CORS
from werkzeug.utils import secure_filename

from config import Config
from models import db, Lead
from notifications import notify_new_lead

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

with app.app_context():
    db.create_all()


# ---------------------------------------------------------------- helpers --

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]
    )


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


# --------------------------------------------------------------- api: lead --

@app.route("/api/quote", methods=["POST"])
def submit_quote():
    """Accepts the website's 'Get a Free Quote' form.
    Works with multipart/form-data (needed for photo uploads) or JSON."""
    if request.content_type and "multipart/form-data" in request.content_type:
        data = request.form
        files = request.files.getlist("Photos") or request.files.getlist("photos")
    else:
        data = request.get_json(silent=True) or {}
        files = []

    name = (data.get("Name") or data.get("name") or "").strip()
    phone = (data.get("Phone") or data.get("phone") or "").strip()

    if not name or not phone:
        return jsonify({"ok": False, "error": "Name and phone number are required."}), 400

    saved_filenames = []
    for f in files:
        if f and f.filename and allowed_file(f.filename):
            safe_name = secure_filename(f.filename)
            unique_name = f"{name.replace(' ', '_')}_{os.urandom(4).hex()}_{safe_name}"
            f.save(os.path.join(app.config["UPLOAD_FOLDER"], unique_name))
            saved_filenames.append(unique_name)

    lead = Lead(
        name=name,
        phone=phone,
        whatsapp=(data.get("WhatsApp") or data.get("whatsapp") or "").strip(),
        location=(data.get("Location") or data.get("location") or "").strip(),
        service=(data.get("Service Required") or data.get("service") or "").strip(),
        details=(data.get("Project Details") or data.get("details") or "").strip(),
        photos=",".join(saved_filenames) if saved_filenames else None,
    )
    db.session.add(lead)
    db.session.commit()

    notify_new_lead(app, lead.id)

    return jsonify({"ok": True, "message": "Thanks! We'll contact you shortly.", "lead_id": lead.id}), 201


@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# -------------------------------------------------------------- admin auth --

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == app.config["ADMIN_USERNAME"] and password == app.config["ADMIN_PASSWORD"]:
            session["is_admin"] = True
            return redirect(request.args.get("next") or url_for("admin_dashboard"))
        flash("Invalid username or password.")
    return render_template("login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin_login"))


# ------------------------------------------------------------ admin panel --

@app.route("/admin")
@login_required
def admin_dashboard():
    status_filter = request.args.get("status", "all")
    query = Lead.query.order_by(Lead.created_at.desc())
    if status_filter != "all":
        query = query.filter_by(status=status_filter)
    leads = query.all()

    counts = {
        "all": Lead.query.count(),
        "new": Lead.query.filter_by(status="new").count(),
        "contacted": Lead.query.filter_by(status="contacted").count(),
        "closed": Lead.query.filter_by(status="closed").count(),
    }
    return render_template("admin.html", leads=leads, counts=counts, active_filter=status_filter)


@app.route("/admin/leads/<int:lead_id>/status", methods=["POST"])
@login_required
def update_lead_status(lead_id):
    lead = db.session.get(Lead, lead_id)
    if lead is None:
        return jsonify({"ok": False, "error": "Lead not found"}), 404
    new_status = request.form.get("status")
    if new_status not in ("new", "contacted", "closed"):
        return jsonify({"ok": False, "error": "Invalid status"}), 400
    lead.status = new_status
    db.session.commit()
    return redirect(request.referrer or url_for("admin_dashboard"))


@app.route("/admin/leads/<int:lead_id>/delete", methods=["POST"])
@login_required
def delete_lead(lead_id):
    lead = db.session.get(Lead, lead_id)
    if lead:
        db.session.delete(lead)
        db.session.commit()
    return redirect(request.referrer or url_for("admin_dashboard"))


# ------------------------------------------------------------------ health --

@app.route("/api/health")
def health():
    return jsonify({"ok": True, "service": "chandu-interiors-backend"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
