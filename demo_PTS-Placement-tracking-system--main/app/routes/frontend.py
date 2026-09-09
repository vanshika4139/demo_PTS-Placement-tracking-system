import os
import random
import string
import uuid
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import (
    ActivityLog,
    Batch,
    Candidate,
    CandidateFeedback,
    FollowUpCheckpoint,
    LoginHistory,
    Notification,
    Organization,
    PasswordResetOTP,
    Role,
    Scheme,
    User,
    UserPermissionOverride,
    UserRole,
    UserSettings,
)
from app.utils.email import send_otp_email
from app.utils.i18n import translate, get_current_language, SUPPORTED_LANGUAGES
from app.utils.permissions import has_permission, invalidate_role_permission_cache, invalidate_user_permission_cache, require_permission
from app.utils.rate_limit import rate_limit, get_rate_limit_overview, clear_rate_limit_key
from app.utils.feature_flags import AVAILABLE_FEATURES, get_organization_feature_map, is_feature_enabled, set_organization_feature
from app.utils.platform_settings import get_platform_settings, update_platform_settings
from app.utils.system_health import get_system_health
from app.utils.report_cache import (
    cached_report,
    clear_all_report_cache,
    delete_cache_key,
    get_cache_key_data,
    get_cache_overview,
    invalidate_report_cache,
)

frontend_bp = Blueprint("frontend", __name__, template_folder="../templates")


@frontend_bp.app_template_global("_")
def _translate(key):
    return translate(key)


@frontend_bp.app_template_global("current_language")
def _current_language():
    return get_current_language()


@frontend_bp.route("/lang/<lang_code>")
def set_language(lang_code):
    if lang_code in SUPPORTED_LANGUAGES:
        session["lang"] = lang_code
        session.permanent = True
    return redirect(request.referrer or url_for("frontend.candidate_login"))


def _parse_int(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _parse_date(value):
    from datetime import datetime
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


def super_admin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        user = session.get("user")
        if not user:
            flash("Please login first", "error")
            return redirect(url_for("frontend.login"))
        if not user.get("is_super_admin"):
            flash("Access denied - super admin only", "error")
            return redirect(url_for("frontend.login"))
        return view_func(*args, **kwargs)
    return wrapped


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            flash("Please login first", "error")
            return redirect(url_for("frontend.login"))
        return view_func(*args, **kwargs)
    return wrapped


def candidate_login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        session_candidate = session.get("candidate")
        if not session_candidate:
            flash("Please login first", "error")
            return redirect(url_for("frontend.candidate_login"))

        candidate = Candidate.query.filter_by(id=session_candidate.get("id"), is_deleted=False).first()
        if not candidate or candidate.account_status == "blocked":
            session.pop("candidate", None)
            flash("Your account has been blocked. Please contact your training center.", "error")
            return redirect(url_for("frontend.candidate_login"))

        return view_func(*args, **kwargs)
    return wrapped


def _create_notification(title, message, notif_type="info", user_id=None, organization_id=None):
    notif = Notification(
        title=title,
        message=message,
        type=notif_type,
        user_id=user_id,
        organization_id=str(organization_id) if organization_id else None,
    )
    db.session.add(notif)
    db.session.commit()


def _send_placement_email(candidate):
    """Emails relevant staff (org users + super admins) when a candidate gets placed.
    Only emails users who have email_notifications enabled in their settings.
    Never raises - a failed email should never break the candidate save flow."""
    from app.utils.email import send_notification_email

    try:
        org_users = User.query.filter(
            User.is_deleted == False,
            User.is_active == True,
            (User.organization_id == candidate.organization_id) | (User.is_super_admin == True),
        ).all()

        joining_str = candidate.joining_date.strftime("%d-%m-%Y") if candidate.joining_date else "N/A"
        subject = f"Candidate Placed: {candidate.full_name}"
        body = (
            f"Good news! A candidate has been placed.\n\n"
            f"Name: {candidate.full_name}\n"
            f"Registration No: {candidate.registration_number or '-'}\n"
            f"Employer: {candidate.employer_name}\n"
            f"Job Role: {candidate.job_role or 'N/A'}\n"
            f"Joining Date: {joining_str}\n\n"
            f"View full details in the Placement Tracking System."
        )

        for user in org_users:
            settings = UserSettings.query.filter_by(user_id=user.id).first()
            wants_email = settings.email_notifications if settings else True
            if not wants_email:
                continue
            try:
                send_notification_email(user.email, subject, body)
            except Exception:
                continue
    except Exception:
        pass


def _log_activity(action, details=None):
    user = session.get("user")
    log = ActivityLog(
        user_id=user.get("id") if user else None,
        action=action,
        details=details,
    )
    db.session.add(log)
    db.session.commit()


def _sync_overdue_notifications(user):
    """Create notifications for overdue checkpoints that don't already have one."""
    from datetime import datetime
    today = datetime.utcnow()

    candidate_query = Candidate.query.filter_by(is_deleted=False)
    if not user.get("is_super_admin"):
        candidate_query = candidate_query.filter_by(organization_id=user.get("organization_id"))
    candidates = candidate_query.all()
    candidate_map = {c.id: c for c in candidates}
    candidate_ids = list(candidate_map.keys())

    if not candidate_ids:
        return

    overdue_checkpoints = FollowUpCheckpoint.query.filter(
        FollowUpCheckpoint.candidate_id.in_(candidate_ids),
        FollowUpCheckpoint.status == "pending",
        FollowUpCheckpoint.due_date < today,
    ).all()

    for cp in overdue_checkpoints:
        candidate = candidate_map.get(cp.candidate_id)
        if not candidate:
            continue
        title = f"Overdue: {cp.label} for {candidate.full_name}"
        existing = Notification.query.filter_by(title=title, is_read=False).first()
        if existing:
            continue
        _create_notification(
            title=title,
            message=f"{candidate.full_name}'s {cp.label} follow-up was due on {cp.due_date.strftime('%d-%m-%Y')}.",
            notif_type="warning",
            organization_id=candidate.organization_id,
        )


@frontend_bp.route("/login", methods=["GET", "POST"])
@rate_limit("login", max_attempts=5, window_seconds=900)
def login():
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email, is_deleted=False).first()

        if not user or not check_password_hash(user.password_hash, password):
            error = "Invalid email or password"
            db.session.add(LoginHistory(
                email=email,
                full_name=user.full_name if user else None,
                user_id=user.id if user else None,
                ip_address=request.remote_addr,
                user_agent=request.headers.get("User-Agent", "")[:500],
                success=False,
                failure_reason="Invalid credentials",
            ))
            db.session.commit()
        elif not user.is_active:
            error = "Your account is inactive. Contact admin."
            db.session.add(LoginHistory(
                email=email,
                full_name=user.full_name,
                user_id=user.id,
                ip_address=request.remote_addr,
                user_agent=request.headers.get("User-Agent", "")[:500],
                success=False,
                failure_reason="Account inactive",
            ))
            db.session.commit()
        else:
            from datetime import datetime
            user.last_login_at = datetime.utcnow()
            db.session.add(LoginHistory(
                email=email,
                full_name=user.full_name,
                user_id=user.id,
                ip_address=request.remote_addr,
                user_agent=request.headers.get("User-Agent", "")[:500],
                success=True,
            ))
            db.session.commit()

            session["user"] = {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "is_super_admin": user.is_super_admin,
                "organization_id": user.organization_id,
            }
            session.permanent = True
            flash(f"Welcome back, {user.full_name}", "success")
            if user.is_super_admin:
                return redirect(url_for("frontend.super_admin_dashboard"))
            return redirect(url_for("frontend.organization_dashboard"))
    return render_template("auth/login.html", error=error)


@frontend_bp.route("/logout")
def logout():
    session.pop("user", None)
    flash("You have been logged out", "success")
    return redirect(url_for("frontend.login"))


def _generate_otp():
    return "".join(random.choices(string.digits, k=6))


@frontend_bp.route("/forgot-password", methods=["GET", "POST"])
@rate_limit("forgot_password", max_attempts=3, window_seconds=600)
def forgot_password():
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email, is_deleted=False).first()

        if not user:
            error = "No account found with this email address"
        else:
            otp_code = _generate_otp()
            otp_entry = PasswordResetOTP(
                email=email,
                otp_code=otp_code,
                expires_at=datetime.utcnow() + timedelta(minutes=10),
            )
            db.session.add(otp_entry)
            db.session.commit()

            try:
                send_otp_email(email, otp_code)
            except Exception:
                error = "Could not send OTP email. Please check SMTP configuration or try again later."
                return render_template("auth/forgot_password.html", error=error)

            session["reset_email"] = email
            flash("An OTP has been sent to your email address", "success")
            return redirect(url_for("frontend.verify_otp"))

    return render_template("auth/forgot_password.html", error=error)


@frontend_bp.route("/verify-otp", methods=["GET", "POST"])
@rate_limit("verify_otp", max_attempts=5, window_seconds=600)
def verify_otp():
    error = None
    email = session.get("reset_email")

    if not email:
        flash("Please start the password reset process again", "error")
        return redirect(url_for("frontend.forgot_password"))

    if request.method == "POST":
        entered_otp = request.form.get("otp", "").strip()

        otp_entry = (
            PasswordResetOTP.query.filter_by(email=email, otp_code=entered_otp, is_used=False)
            .order_by(PasswordResetOTP.created_at.desc())
            .first()
        )

        if not otp_entry or not otp_entry.is_valid():
            error = "Invalid or expired OTP. Please try again."
        else:
            otp_entry.is_used = True
            db.session.commit()
            session["reset_verified"] = True
            return redirect(url_for("frontend.reset_password"))

    return render_template("auth/verify_otp.html", error=error, email=email)


@frontend_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    error = None
    email = session.get("reset_email")
    verified = session.get("reset_verified")

    if not email or not verified:
        flash("Please verify your OTP first", "error")
        return redirect(url_for("frontend.forgot_password"))

    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(new_password) < 6:
            error = "Password must be at least 6 characters"
        elif new_password != confirm_password:
            error = "Passwords do not match"
        else:
            user = User.query.filter_by(email=email, is_deleted=False).first()
            if not user:
                error = "User not found"
            else:
                user.password_hash = generate_password_hash(new_password)
                db.session.commit()

                session.pop("reset_email", None)
                session.pop("reset_verified", None)

                flash("Password reset successfully. Please login with your new password.", "success")
                return redirect(url_for("frontend.login"))

    return render_template("auth/reset_password.html", error=error)


@frontend_bp.route("/super-admin/dashboard")
@super_admin_required
def super_admin_dashboard():
    data = get_super_admin_dashboard_data()
    return render_template("super_admin/dashboard.html", **data)


@cached_report(key_prefix="dashboard:super_admin")
def get_super_admin_dashboard_data():
    from datetime import datetime
    from dateutil.relativedelta import relativedelta

    total = Organization.query.count()
    active = Organization.query.filter_by(status=1).count()
    pending_kyc = Organization.query.filter_by(kyc_status="PENDING").count()
    pending_payment = Organization.query.filter_by(payment_status="PENDING").count()

    total_batches = Batch.query.count()
    total_schemes = Scheme.query.count()
    pending_placement = Candidate.query.filter(
        Candidate.is_deleted == False,
        (Candidate.employer_name.is_(None)) | (Candidate.employer_name == ""),
    ).count()
    placement_proof_uploaded = Candidate.query.filter_by(
        is_deleted=False, placement_proof_uploaded=True
    ).count()

    stats = [
        {"title": "Total Organizations", "value": str(total), "link": url_for("frontend.super_admin_organizations")},
        {"title": "Active Organizations", "value": str(active), "link": url_for("frontend.super_admin_organizations", filter="active")},
        {"title": "Pending KYC", "value": str(pending_kyc), "link": url_for("frontend.super_admin_organizations", filter="pending_kyc")},
        {"title": "Pending Payment", "value": str(pending_payment), "link": url_for("frontend.super_admin_organizations", filter="pending_payment")},
        {"title": "Total Batches", "value": str(total_batches), "link": url_for("frontend.organization_batches")},
        {"title": "Total Schemes", "value": str(total_schemes), "link": url_for("frontend.organization_schemes")},
        {"title": "Pending Placement", "value": str(pending_placement), "link": url_for("frontend.organization_candidates", placed="no")},
        {"title": "Placement Proof Uploaded", "value": str(placement_proof_uploaded), "link": url_for("frontend.organization_candidates", placement_proof="yes")},
    ]

    today = datetime.utcnow()
    months = []
    for i in range(5, -1, -1):
        month_date = today - relativedelta(months=i)
        months.append(month_date.strftime("%Y-%m"))

    org_growth_labels = []
    org_growth_data = []
    all_orgs = Organization.query.all()
    for month_key in months:
        year, month = map(int, month_key.split("-"))
        count = sum(1 for o in all_orgs if o.created_at and o.created_at.year == year and o.created_at.month == month)
        org_growth_labels.append(datetime(year, month, 1).strftime("%b %Y"))
        org_growth_data.append(count)

    placement_labels = []
    placement_data = []
    placed_candidates = Candidate.query.filter(
        Candidate.is_deleted == False,
        Candidate.joining_date.isnot(None),
    ).all()
    for month_key in months:
        year, month = map(int, month_key.split("-"))
        count = sum(1 for c in placed_candidates if c.joining_date.year == year and c.joining_date.month == month)
        placement_labels.append(datetime(year, month, 1).strftime("%b %Y"))
        placement_data.append(count)

    kyc_status_counts = {}
    payment_status_counts = {}
    for o in all_orgs:
        kyc_key = (o.kyc_status or "UNKNOWN").title()
        pay_key = (o.payment_status or "UNKNOWN").title()
        kyc_status_counts[kyc_key] = kyc_status_counts.get(kyc_key, 0) + 1
        payment_status_counts[pay_key] = payment_status_counts.get(pay_key, 0) + 1

    kyc_status_labels = list(kyc_status_counts.keys())
    kyc_status_data = list(kyc_status_counts.values())
    payment_status_labels = list(payment_status_counts.keys())
    payment_status_data = list(payment_status_counts.values())

    recent_organizations_raw = Organization.query.order_by(Organization.created_at.desc()).limit(5).all()
    recent_organizations = [
        {
            "id": o.id,
            "organization_name": o.organization_name,
            "organization_code": o.organization_code,
            "kyc_status": o.kyc_status,
            "payment_status": o.payment_status,
            "status": o.status,
            "created_at": o.created_at.strftime("%d-%m-%Y") if o.created_at else None,
        }
        for o in recent_organizations_raw
    ]

    # ---------------- Subscription expiry alerts ----------------
    EXPIRY_WINDOW_DAYS = 30
    expiry_cutoff = today.date() + relativedelta(days=EXPIRY_WINDOW_DAYS)
    expiring_subscriptions = []
    for o in all_orgs:
        if not o.subscription_expiry_date:
            continue
        exp_date = o.subscription_expiry_date
        if exp_date <= expiry_cutoff:
            days_left = (exp_date - today.date()).days
            expiring_subscriptions.append({
                "id": o.id,
                "organization_name": o.organization_name,
                "expiry_date": exp_date.strftime("%d-%m-%Y"),
                "days_left": days_left,
                "is_overdue": days_left < 0,
                "payment_status": o.payment_status,
            })
    expiring_subscriptions.sort(key=lambda x: x["days_left"])
    expiring_subscriptions = expiring_subscriptions[:10]

    # ---------------- Low credit balance alerts ----------------
    LOW_CREDIT_THRESHOLD = 50
    low_credit_organizations = []
    for o in all_orgs:
        low_items = []
        if (o.whatsapp_credits or 0) < LOW_CREDIT_THRESHOLD:
            low_items.append(("WhatsApp", o.whatsapp_credits or 0))
        if (o.sms_credits or 0) < LOW_CREDIT_THRESHOLD:
            low_items.append(("SMS", o.sms_credits or 0))
        if (o.email_credits or 0) < LOW_CREDIT_THRESHOLD:
            low_items.append(("Email", o.email_credits or 0))
        if low_items and o.status == 1:
            low_credit_organizations.append({
                "id": o.id,
                "organization_name": o.organization_name,
                "low_items": low_items,
            })
    low_credit_organizations = low_credit_organizations[:10]

    # ---------------- Failed login / brute-force monitoring ----------------
    last_24h = today - timedelta(hours=24)
    failed_logins_24h = LoginHistory.query.filter(
        LoginHistory.success == False,
        LoginHistory.created_at >= last_24h,
    ).count()
    successful_logins_24h = LoginHistory.query.filter(
        LoginHistory.success == True,
        LoginHistory.created_at >= last_24h,
    ).count()

    recent_failed_logins = (
        LoginHistory.query.filter(
            LoginHistory.success == False,
            LoginHistory.created_at >= last_24h,
        )
        .order_by(LoginHistory.created_at.desc())
        .limit(200)
        .all()
    )

    ip_failure_counts = {}
    for entry in recent_failed_logins:
        ip = entry.ip_address or "unknown"
        if ip not in ip_failure_counts:
            ip_failure_counts[ip] = {"ip": ip, "count": 0, "emails": set(), "last_attempt": entry.created_at}
        ip_failure_counts[ip]["count"] += 1
        ip_failure_counts[ip]["emails"].add(entry.email)
        if entry.created_at > ip_failure_counts[ip]["last_attempt"]:
            ip_failure_counts[ip]["last_attempt"] = entry.created_at

    suspicious_ips = [
        {
            "ip": data["ip"],
            "count": data["count"],
            "distinct_emails": len(data["emails"]),
            "last_attempt": data["last_attempt"].strftime("%d-%m-%Y %H:%M"),
        }
        for data in ip_failure_counts.values()
        if data["count"] >= 3
    ]
    suspicious_ips.sort(key=lambda x: x["count"], reverse=True)
    suspicious_ips = suspicious_ips[:10]

    return {
        "stats": stats,
        "org_growth_labels": org_growth_labels,
        "org_growth_data": org_growth_data,
        "placement_labels": placement_labels,
        "placement_data": placement_data,
        "kyc_status_labels": kyc_status_labels,
        "kyc_status_data": kyc_status_data,
        "payment_status_labels": payment_status_labels,
        "payment_status_data": payment_status_data,
        "recent_organizations": recent_organizations,
        "expiring_subscriptions": expiring_subscriptions,
        "low_credit_organizations": low_credit_organizations,
        "failed_logins_24h": failed_logins_24h,
        "successful_logins_24h": successful_logins_24h,
        "suspicious_ips": suspicious_ips,
    }


@frontend_bp.route("/super-admin/cache-monitor")
@super_admin_required
def super_admin_cache_monitor():
    overview = get_cache_overview()
    return render_template("super_admin/cache_monitor.html", overview=overview)


@frontend_bp.route("/super-admin/rate-limit-monitor")
@super_admin_required
def super_admin_rate_limit_monitor():
    overview = get_rate_limit_overview()
    return render_template("super_admin/rate_limit_monitor.html", overview=overview)


@frontend_bp.route("/super-admin/system-health")
@super_admin_required
def super_admin_system_health():
    health = get_system_health()
    return render_template("super_admin/system_health.html", health=health)


@frontend_bp.route("/super-admin/rate-limit-monitor/reset", methods=["POST"])
@super_admin_required
def super_admin_rate_limit_reset():
    key = request.form.get("key")
    if clear_rate_limit_key(key):
        flash("Rate limit cleared for that IP. They can try again immediately.", "success")
    else:
        flash("Could not clear that key - it may have already expired.", "error")
    return redirect(url_for("frontend.super_admin_rate_limit_monitor"))


@frontend_bp.route("/super-admin/settings/integrations", methods=["GET", "POST"])
@super_admin_required
def super_admin_integrations():
    """Lets the super admin configure platform-wide SMTP, WhatsApp, and SMS
    credentials from the UI instead of hand-editing .env. Secret fields
    (passwords/API keys) are left untouched if submitted blank, so the
    admin never has to re-type an existing secret just to change another field."""
    settings = get_platform_settings()

    if request.method == "POST":
        actor = session.get("user") or {}
        update_platform_settings(
            {
                "smtp_host": request.form.get("smtp_host", "").strip(),
                "smtp_port": request.form.get("smtp_port", "").strip(),
                "smtp_username": request.form.get("smtp_username", "").strip(),
                "smtp_password": request.form.get("smtp_password", "").strip() or settings.smtp_password,
                "whatsapp_api_key": request.form.get("whatsapp_api_key", "").strip() or settings.whatsapp_api_key,
                "whatsapp_phone_number_id": request.form.get("whatsapp_phone_number_id", "").strip(),
                "sms_api_key": request.form.get("sms_api_key", "").strip() or settings.sms_api_key,
                "sms_sender_id": request.form.get("sms_sender_id", "").strip(),
            },
            actor_id=actor.get("id"),
        )
        _log_activity("platform.integrations_updated", "Updated platform integration settings (SMTP / WhatsApp / SMS)")
        flash("Integration settings saved.", "success")
        return redirect(url_for("frontend.super_admin_integrations"))

    return render_template("super_admin/integrations.html", settings=settings)


@frontend_bp.route("/super-admin/cache-monitor/clear", methods=["POST"])
@super_admin_required
def super_admin_cache_clear():
    removed = clear_all_report_cache()

    if removed is False:
        flash("Could not clear cache - Redis is unreachable right now.", "error")
    else:
        flash(f"Cache cleared. {removed} key(s) removed.", "success")
        _log_activity("cache.clear", details=f"Manually cleared report cache ({removed} keys)")

    return redirect(url_for("frontend.super_admin_cache_monitor"))


@frontend_bp.route("/super-admin/cache-monitor/inspect")
@super_admin_required
def super_admin_cache_inspect():
    key = request.args.get("key", "")
    value = get_cache_key_data(key)
    return render_template("super_admin/cache_inspect.html", key=key, value=value)


@frontend_bp.route("/super-admin/cache-monitor/key/delete", methods=["POST"])
@super_admin_required
def super_admin_cache_delete_key():
    key = request.form.get("key", "")
    deleted = delete_cache_key(key)

    if deleted:
        flash(f"Deleted cache key: {key}", "success")
        _log_activity("cache.delete_key", details=f"Deleted cache key {key}")
    else:
        flash("Could not delete that key - it may already be gone, or Redis is unreachable.", "error")

    return redirect(url_for("frontend.super_admin_cache_monitor"))


@frontend_bp.route("/no-access")
@login_required
def no_access():
    """A permission-free landing page for a logged-in user who doesn't have
    the permission needed for whatever they tried to reach - e.g. an
    organization user who was created without any RBAC role assigned yet.
    This route deliberately has NO @require_permission check, so it can
    never itself cause a redirect loop."""
    return render_template("no_access.html")


@frontend_bp.route("/organization/dashboard")
@login_required
@require_permission("dashboard.view")
def organization_dashboard():
    user = session.get("user")
    org_id = user.get("organization_id")
    data = get_organization_dashboard_data(org_id)
    return render_template("organization/dashboard.html", **data)


@cached_report(key_prefix="dashboard:org")
def get_organization_dashboard_data(organization_id):
    from datetime import datetime
    from dateutil.relativedelta import relativedelta

    base_query = Candidate.query.filter_by(is_deleted=False)
    if organization_id:
        base_query = base_query.filter_by(organization_id=organization_id)

    all_candidates = base_query.all()
    total_candidates = len(all_candidates)
    placed = sum(1 for c in all_candidates if c.employer_name)
    pending = sum(1 for c in all_candidates if c.training_status == "training_started")
    verified = sum(1 for c in all_candidates if c.verification_status == "verified")
    placement_proof_uploaded = sum(1 for c in all_candidates if c.placement_proof_uploaded)

    stats = [
        {"title": "Total Candidates", "value": str(total_candidates), "link": url_for("frontend.organization_candidates")},
        {"title": "Placed", "value": str(placed), "link": url_for("frontend.organization_candidates", placed="yes")},
        {"title": "Pending Placement", "value": str(pending), "link": url_for("frontend.organization_candidates", training_status="training_started")},
        {"title": "Verified", "value": str(verified), "link": url_for("frontend.organization_candidates", verification_status="verified")},
        {"title": "Placement Proof Uploaded", "value": str(placement_proof_uploaded), "link": url_for("frontend.organization_candidates", placement_proof="yes")},
    ]

    today = datetime.utcnow()
    months = []
    for i in range(5, -1, -1):
        month_date = today - relativedelta(months=i)
        months.append(month_date.strftime("%Y-%m"))

    placement_labels = []
    placement_data = []
    placed_candidates = [c for c in all_candidates if c.joining_date]
    for month_key in months:
        year, month = map(int, month_key.split("-"))
        count = sum(1 for c in placed_candidates if c.joining_date.year == year and c.joining_date.month == month)
        placement_labels.append(datetime(year, month, 1).strftime("%b %Y"))
        placement_data.append(count)

    employer_counts = {}
    for c in all_candidates:
        if c.employer_name:
            employer_counts[c.employer_name] = employer_counts.get(c.employer_name, 0) + 1
    top_employers = sorted(employer_counts.items(), key=lambda x: x[1], reverse=True)[:6]
    employer_labels = [e[0] for e in top_employers]
    employer_data = [e[1] for e in top_employers]

    sector_counts = {}
    for c in all_candidates:
        key = c.sector or "Unspecified"
        sector_counts[key] = sector_counts.get(key, 0) + 1
    top_sectors = sorted(sector_counts.items(), key=lambda x: x[1], reverse=True)[:8]
    sector_labels = [s[0] for s in top_sectors]
    sector_data = [s[1] for s in top_sectors]

    verification_funnel_labels = ["Pending", "Verified"]
    verification_funnel_data = [
        sum(1 for c in all_candidates if (c.verification_status or "pending") == "pending"),
        sum(1 for c in all_candidates if c.verification_status == "verified"),
    ]

    return {
        "stats": stats,
        "placement_labels": placement_labels,
        "placement_data": placement_data,
        "employer_labels": employer_labels,
        "employer_data": employer_data,
        "sector_labels": sector_labels,
        "sector_data": sector_data,
        "verification_funnel_labels": verification_funnel_labels,
        "verification_funnel_data": verification_funnel_data,
    }


@frontend_bp.route("/super-admin/organizations")
@super_admin_required
def super_admin_organizations():
    filter_type = request.args.get("filter", "").strip()

    query = Organization.query
    if filter_type == "active":
        query = query.filter_by(status=1)
    elif filter_type == "pending_kyc":
        query = query.filter_by(kyc_status="PENDING")
    elif filter_type == "pending_payment":
        query = query.filter_by(payment_status="PENDING")

    organizations = query.order_by(Organization.created_at.desc()).all()
    return render_template(
        "super_admin/organizations/index.html",
        organizations=organizations,
        active_filter=filter_type,
        today=datetime.utcnow().date(),
    )


@frontend_bp.route("/super-admin/organizations/export.xlsx")
@super_admin_required
def super_admin_organizations_export():
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from io import BytesIO
    from flask import send_file

    filter_type = request.args.get("filter", "").strip()

    query = Organization.query
    if filter_type == "active":
        query = query.filter_by(status=1)
    elif filter_type == "pending_kyc":
        query = query.filter_by(kyc_status="PENDING")
    elif filter_type == "pending_payment":
        query = query.filter_by(payment_status="PENDING")

    organizations = query.order_by(Organization.created_at.desc()).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Organizations"

    headers = [
        "Code", "Name", "Registration No.", "GST Number", "PAN Number",
        "Contact Person", "Email", "Mobile", "Address",
        "KYC Status", "Payment Status", "Status",
        "Subscription Expiry", "Candidate Limit",
        "WhatsApp Credits", "SMS Credits", "Email Credits",
        "Created At",
    ]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for o in organizations:
        is_active = (o.status == 1)
        ws.append([
            o.organization_code or "-",
            o.organization_name or "-",
            o.registration_number or "-",
            o.gst_number or "-",
            o.pan_number or "-",
            o.contact_person or "-",
            o.email or "-",
            o.mobile or "-",
            o.address or "-",
            o.kyc_status or "-",
            o.payment_status or "-",
            "Active" if is_active else "Inactive",
            o.subscription_expiry_date.strftime("%d-%m-%Y") if o.subscription_expiry_date else "-",
            o.candidate_limit or 0,
            o.whatsapp_credits or 0,
            o.sms_credits or 0,
            o.email_credits or 0,
            o.created_at.strftime("%d-%m-%Y %H:%M") if o.created_at else "-",
        ])

    for col_cells in ws.columns:
        max_length = max(len(str(cell.value)) if cell.value else 0 for cell in col_cells)
        ws.column_dimensions[col_cells[0].column_letter].width = min(max_length + 2, 40)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    _log_activity("Exported organizations to Excel", f"{len(organizations)} organization(s)")

    return send_file(
        buffer,
        as_attachment=True,
        download_name="organizations_export.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@frontend_bp.route("/super-admin/organizations/bulk-topup", methods=["POST"])
@super_admin_required
def super_admin_organizations_bulk_topup():
    """Applies either a subscription extension or a credit top-up to every
    selected organization at once. Only ADDS to existing credits/expiry -
    never overwrites or reduces them, so it's safe to re-run."""
    org_ids = request.form.getlist("organization_ids")
    action = request.form.get("action")

    if not org_ids:
        flash("No organizations were selected.", "error")
        return redirect(url_for("frontend.super_admin_organizations"))

    organizations = Organization.query.filter(Organization.id.in_(org_ids)).all()
    if not organizations:
        flash("Selected organizations could not be found.", "error")
        return redirect(url_for("frontend.super_admin_organizations"))

    org_names = ", ".join(o.organization_name for o in organizations)
    today = datetime.utcnow().date()

    if action == "extend_subscription":
        try:
            days = int(request.form.get("extend_days") or 0)
        except ValueError:
            days = 0

        if days <= 0:
            flash("Enter a valid number of days to extend.", "error")
            return redirect(url_for("frontend.super_admin_organizations"))

        for org in organizations:
            # Extend from the existing expiry if it's still in the future,
            # otherwise extend from today - so an already-expired org gets
            # a fresh window starting now, not more days added to a stale date.
            base_date = org.subscription_expiry_date if (org.subscription_expiry_date and org.subscription_expiry_date >= today) else today
            org.subscription_expiry_date = base_date + timedelta(days=days)
        db.session.commit()

        _log_activity(
            "bulk.extend_subscription",
            f"Extended subscription by {days} day(s) for {len(organizations)} organization(s): {org_names}",
        )
        flash(f"Extended subscription by {days} day(s) for {len(organizations)} organization(s).", "success")

    elif action == "add_credits":
        def _to_int(val):
            try:
                v = int(val)
                return v if v > 0 else 0
            except (TypeError, ValueError):
                return 0

        wa = _to_int(request.form.get("whatsapp_credits"))
        sms = _to_int(request.form.get("sms_credits"))
        email = _to_int(request.form.get("email_credits"))

        if wa == 0 and sms == 0 and email == 0:
            flash("Enter at least one credit amount to add.", "error")
            return redirect(url_for("frontend.super_admin_organizations"))

        for org in organizations:
            org.whatsapp_credits = (org.whatsapp_credits or 0) + wa
            org.sms_credits = (org.sms_credits or 0) + sms
            org.email_credits = (org.email_credits or 0) + email
        db.session.commit()

        _log_activity(
            "bulk.add_credits",
            f"Added credits (WhatsApp:{wa}, SMS:{sms}, Email:{email}) to "
            f"{len(organizations)} organization(s): {org_names}",
        )
        flash(f"Added credits to {len(organizations)} organization(s).", "success")

    else:
        flash("Please choose a bulk action.", "error")
        return redirect(url_for("frontend.super_admin_organizations"))

    invalidate_report_cache("dashboard:super_admin")
    return redirect(url_for("frontend.super_admin_organizations"))


@frontend_bp.route("/super-admin/organizations/create", methods=["GET", "POST"])
@super_admin_required
def super_admin_create_organization():
    if request.method == "POST":
        org = Organization(
            organization_code=request.form.get("organization_code"),
            organization_name=request.form.get("organization_name"),
            registration_number=request.form.get("registration_number"),
            gst_number=request.form.get("gst_number"),
            pan_number=request.form.get("pan_number"),
            website=request.form.get("website"),
            email=request.form.get("email"),
            mobile=request.form.get("mobile"),
            contact_person=request.form.get("contact_person"),
            designation=request.form.get("designation"),
            address=request.form.get("address"),
            country_id=_parse_int(request.form.get("country_id")),
            state_id=_parse_int(request.form.get("state_id")),
            district_id=_parse_int(request.form.get("district_id")),
            pincode=request.form.get("pincode"),
            logo=request.form.get("logo"),
            subscription_plan_id=_parse_int(request.form.get("subscription_plan_id")),
            subscription_expiry_date=_parse_date(request.form.get("subscription_expiry_date")),
            storage_used=0,
            candidate_limit=_parse_int(request.form.get("candidate_limit")) or 0,
            whatsapp_credits=_parse_int(request.form.get("whatsapp_credits")) or 0,
            sms_credits=_parse_int(request.form.get("sms_credits")) or 0,
            email_credits=_parse_int(request.form.get("email_credits")) or 0,
            api_key=request.form.get("api_key"),
            webhook_url=request.form.get("webhook_url"),
            status=1,
            kyc_status="PENDING",
            payment_status="PENDING",
        )
        db.session.add(org)
        db.session.commit()
        _create_notification(
            title=f"New organization created: {org.organization_name}",
            message=f"Organization {org.organization_code} was added to the platform.",
            notif_type="success",
        )
        _log_activity("Created organization", f"{org.organization_name} ({org.organization_code})")
        invalidate_report_cache("dashboard:super_admin")
        flash("Organization created successfully", "success")
        return redirect(url_for("frontend.super_admin_organizations"))
    return render_template("super_admin/organizations/form.html", organization=None)


@frontend_bp.route("/super-admin/organizations/<int:organization_id>")
@super_admin_required
def super_admin_organization_detail(organization_id):
    organization = Organization.query.get_or_404(organization_id)
    feature_map = get_organization_feature_map(organization_id)
    return render_template(
        "super_admin/organizations/detail.html",
        organization=organization,
        feature_map=feature_map,
        available_features=AVAILABLE_FEATURES,
    )


@frontend_bp.route("/super-admin/organizations/<int:organization_id>/features/toggle", methods=["POST"])
@super_admin_required
def super_admin_organization_feature_toggle(organization_id):
    """Flips one feature flag for one organization. Uses a single POST per
    checkbox (auto-submitted by JS on change) so admins don't need a
    separate 'Save' step for this panel."""
    organization = Organization.query.get_or_404(organization_id)
    feature_key = request.form.get("feature_key")
    is_enabled = request.form.get("is_enabled") == "1"

    if feature_key not in AVAILABLE_FEATURES:
        flash("Unknown feature.", "error")
        return redirect(url_for("frontend.super_admin_organization_detail", organization_id=organization_id))

    actor = session.get("user") or {}
    set_organization_feature(organization_id, feature_key, is_enabled, actor_id=actor.get("id"))

    label = AVAILABLE_FEATURES[feature_key]["label"]
    _log_activity(
        "organization.feature_toggle",
        f"{'Enabled' if is_enabled else 'Disabled'} '{label}' for {organization.organization_name}",
    )

    flash(f"'{label}' {'enabled' if is_enabled else 'disabled'} for {organization.organization_name}.", "success")
    return redirect(url_for("frontend.super_admin_organization_detail", organization_id=organization_id))


@frontend_bp.route("/super-admin/organizations/<int:organization_id>/edit", methods=["GET", "POST"])
@super_admin_required
def super_admin_edit_organization(organization_id):
    organization = Organization.query.get_or_404(organization_id)
    if request.method == "POST":
        organization.organization_name = request.form.get("organization_name")
        organization.registration_number = request.form.get("registration_number")
        organization.gst_number = request.form.get("gst_number")
        organization.pan_number = request.form.get("pan_number")
        organization.website = request.form.get("website")
        organization.email = request.form.get("email")
        organization.mobile = request.form.get("mobile")
        organization.contact_person = request.form.get("contact_person")
        organization.designation = request.form.get("designation")
        organization.address = request.form.get("address")
        organization.country_id = _parse_int(request.form.get("country_id"))
        organization.state_id = _parse_int(request.form.get("state_id"))
        organization.district_id = _parse_int(request.form.get("district_id"))
        organization.pincode = request.form.get("pincode")
        organization.logo = request.form.get("logo")
        organization.subscription_plan_id = _parse_int(request.form.get("subscription_plan_id"))
        organization.subscription_expiry_date = _parse_date(request.form.get("subscription_expiry_date"))
        organization.candidate_limit = _parse_int(request.form.get("candidate_limit")) or 0
        organization.whatsapp_credits = _parse_int(request.form.get("whatsapp_credits")) or 0
        organization.sms_credits = _parse_int(request.form.get("sms_credits")) or 0
        organization.email_credits = _parse_int(request.form.get("email_credits")) or 0
        organization.api_key = request.form.get("api_key")
        organization.webhook_url = request.form.get("webhook_url")
        organization.kyc_status = request.form.get("kyc_status")
        organization.payment_status = request.form.get("payment_status")
        organization.status = 1 if request.form.get("status") == "active" else 0
        db.session.commit()
        _log_activity("Updated organization", f"{organization.organization_name}")
        invalidate_report_cache("dashboard:super_admin")
        flash("Organization updated successfully", "success")
        return redirect(url_for("frontend.super_admin_organization_detail", organization_id=organization.id))
    return render_template("super_admin/organizations/form.html", organization=organization)


@frontend_bp.route("/super-admin/organizations/<int:organization_id>/subscription", methods=["GET", "POST"])
@super_admin_required
def super_admin_subscription(organization_id):
    organization = Organization.query.get_or_404(organization_id)

    if request.method == "POST":
        organization.subscription_plan_id = _parse_int(request.form.get("subscription_plan_id"))
        organization.subscription_expiry_date = _parse_date(request.form.get("subscription_expiry_date"))
        organization.candidate_limit = _parse_int(request.form.get("candidate_limit")) or 0
        organization.whatsapp_credits = _parse_int(request.form.get("whatsapp_credits")) or 0
        organization.sms_credits = _parse_int(request.form.get("sms_credits")) or 0
        organization.email_credits = _parse_int(request.form.get("email_credits")) or 0
        organization.payment_status = request.form.get("payment_status")
        db.session.commit()
        _log_activity("Updated subscription", f"{organization.organization_name}")
        invalidate_report_cache("dashboard:super_admin")
        flash("Subscription updated successfully", "success")
        return redirect(url_for("frontend.super_admin_organization_detail", organization_id=organization.id))

    return render_template("super_admin/subscription.html", organization=organization)


@frontend_bp.route("/super-admin/roles-permissions", methods=["GET", "POST"])
@super_admin_required
def super_admin_roles_permissions():
    from app.models import Permission, Role, RolePermission

    roles = Role.query.filter_by(is_deleted=False).order_by(Role.name).all()

    selected_role_id = request.values.get("role_id") or (roles[0].id if roles else None)
    selected_role = Role.query.get(selected_role_id) if selected_role_id else None

    if request.method == "POST" and selected_role:
        checked_permission_ids = set(request.form.getlist("permission_ids"))

        existing_mappings = RolePermission.query.filter_by(role_id=selected_role.id, is_deleted=False).all()
        existing_permission_ids = {m.permission_id for m in existing_mappings}

        # Remove unchecked
        for mapping in existing_mappings:
            if mapping.permission_id not in checked_permission_ids:
                db.session.delete(mapping)

        # Add newly checked
        for perm_id in checked_permission_ids:
            if perm_id not in existing_permission_ids:
                db.session.add(RolePermission(
                    role_id=selected_role.id,
                    permission_id=perm_id,
                    created_by=session["user"]["id"],
                ))

        selected_role.modified_by = session["user"]["id"]

        db.session.commit()
        invalidate_role_permission_cache(selected_role.id)
        _log_activity("Updated role permissions", f"{selected_role.name}")
        flash(f"Permissions updated for '{selected_role.name}'", "success")
        return redirect(url_for("frontend.super_admin_roles_permissions", role_id=selected_role.id))

    all_permissions = Permission.query.filter_by(is_deleted=False).order_by(Permission.code).all()

    assigned_permission_ids = set()
    if selected_role:
        assigned_permission_ids = {
            m.permission_id
            for m in RolePermission.query.filter_by(role_id=selected_role.id, is_deleted=False).all()
        }

    # Group permissions by resource prefix (e.g. "candidate" from "candidate.view")
    grouped_permissions = {}
    for perm in all_permissions:
        resource = perm.code.split(".")[0]
        grouped_permissions.setdefault(resource, []).append(perm)

    # Permission Change Audit Timeline - pulled from the same ActivityLog
    # rows already written by the role/permission-editing routes above, no
    # separate audit table needed. Capped at 20 - this is a quick recent
    # history view, not a full report (use the main Activity Log page with
    # its 'role'/'permission' action search for anything older).
    PERMISSION_AUDIT_ACTIONS = (
        "Updated role permissions",
        "Created role",
        "Deactivated role",
        "Updated user permission overrides",
    )
    audit_entries_raw = (
        ActivityLog.query.filter(ActivityLog.action.in_(PERMISSION_AUDIT_ACTIONS))
        .order_by(ActivityLog.created_at.desc())
        .limit(20)
        .all()
    )
    audit_user_ids = {e.user_id for e in audit_entries_raw if e.user_id}
    audit_user_names = {
        u.id: u.full_name for u in User.query.filter(User.id.in_(audit_user_ids)).all()
    } if audit_user_ids else {}
    permission_audit_entries = [
        {
            "actor_name": audit_user_names.get(entry.user_id, "System"),
            "action": entry.action,
            "details": entry.details,
            "created_at": entry.created_at,
        }
        for entry in audit_entries_raw
    ]

    return render_template(
        "super_admin/roles_permissions.html",
        roles=roles,
        selected_role=selected_role,
        grouped_permissions=grouped_permissions,
        assigned_permission_ids=assigned_permission_ids,
        permission_audit_entries=permission_audit_entries,
    )


@frontend_bp.route("/super-admin/roles/create", methods=["POST"])
@super_admin_required
def super_admin_role_create():
    from app.models import Role
    import re

    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Role name is required.", "error")
        return redirect(url_for("frontend.super_admin_roles_permissions"))

    code = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    if not code:
        flash("Could not generate a valid role code from that name.", "error")
        return redirect(url_for("frontend.super_admin_roles_permissions"))

    # NOTE: Role.code is unique at the DB level across ALL rows, including
    # deactivated (is_deleted=True) ones. So we must check for ANY existing
    # row with this code, not just active ones, or the insert below raises
    # an IntegrityError (-> uncaught -> 500) whenever a previously
    # deactivated role had the same generated code.
    existing_role = Role.query.filter_by(code=code).first()
    if existing_role:
        if existing_role.is_deleted:
            flash(
                f"A deactivated role named '{existing_role.name}' already exists with this code. "
                "Reactivate it instead of creating a new one, or choose a different name.",
                "error",
            )
        else:
            flash(f"A role with code '{code}' already exists.", "error")
        return redirect(url_for("frontend.super_admin_roles_permissions"))

    new_role = Role(
        name=name,
        code=code,
        organization_id=None,
        is_deleted=False,
        created_by=session["user"]["id"],
    )
    try:
        db.session.add(new_role)
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Could not create the role due to a database error. Please try a different name.", "error")
        return redirect(url_for("frontend.super_admin_roles_permissions"))

    _log_activity("Created role", name)
    flash(f"Role '{name}' created. Now assign its permissions below.", "success")
    return redirect(url_for("frontend.super_admin_roles_permissions", role_id=new_role.id))


@frontend_bp.route("/super-admin/roles/<role_id>/deactivate", methods=["POST"])
@super_admin_required
def super_admin_role_deactivate(role_id):
    from app.models import Role, UserRole

    role = Role.query.get_or_404(role_id)

    active_user_count = UserRole.query.filter_by(role_id=role.id, is_deleted=False).count()
    if active_user_count > 0:
        flash(
            f"Cannot deactivate '{role.name}' - {active_user_count} user(s) are still assigned this role. "
            "Reassign them to a different role first.",
            "error",
        )
        return redirect(url_for("frontend.super_admin_roles_permissions"))

    role.is_deleted = True
    role.modified_by = session["user"]["id"]
    db.session.commit()
    _log_activity("Deactivated role", role.name)
    flash(f"Role '{role.name}' deactivated.", "success")
    return redirect(url_for("frontend.super_admin_roles_permissions"))


@frontend_bp.route("/super-admin/modules", methods=["GET"])
@super_admin_required
def super_admin_modules():
    from app.models import Module, SubModule

    modules = Module.query.filter_by(status=True).order_by(Module.order_no).all()
    sub_modules_by_module = {}
    for module in modules:
        sub_modules_by_module[module.id] = (
            SubModule.query.filter_by(module_id=module.id, status=True)
            .order_by(SubModule.sub_module_order_no)
            .all()
        )

    inactive_modules = Module.query.filter_by(status=False).order_by(Module.name).all()

    # Resolve created_by/modified_by user IDs to display names for the audit trail
    user_ids = set()
    for module in modules + inactive_modules:
        if module.created_by:
            user_ids.add(module.created_by)
        if module.modified_by:
            user_ids.add(module.modified_by)
    for sub_list in sub_modules_by_module.values():
        for sub in sub_list:
            if sub.created_by:
                user_ids.add(sub.created_by)
            if sub.modified_by:
                user_ids.add(sub.modified_by)

    user_name_by_id = {
        u.id: u.full_name for u in User.query.filter(User.id.in_(user_ids)).all()
    } if user_ids else {}

    return render_template(
        "super_admin/modules.html",
        modules=modules,
        sub_modules_by_module=sub_modules_by_module,
        inactive_modules=inactive_modules,
        user_name_by_id=user_name_by_id,
    )


@frontend_bp.route("/super-admin/modules/create", methods=["POST"])
@super_admin_required
def super_admin_module_create():
    from app.models import Module

    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Module name is required.", "error")
        return redirect(url_for("frontend.super_admin_modules"))

    max_order = db.session.query(db.func.max(Module.order_no)).scalar() or 0

    new_module = Module(
        name=name,
        order_no=max_order + 1,
        status=True,
        created_by=session["user"]["id"],
    )
    db.session.add(new_module)
    db.session.commit()
    _log_activity("Created module", name)
    flash(f"Module '{name}' created.", "success")
    return redirect(url_for("frontend.super_admin_modules"))


@frontend_bp.route("/super-admin/modules/<module_id>/deactivate", methods=["POST"])
@super_admin_required
def super_admin_module_deactivate(module_id):
    from app.models import Module

    module = Module.query.get_or_404(module_id)
    module.status = False
    module.modified_by = session["user"]["id"]
    db.session.commit()
    _log_activity("Deactivated module", module.name)
    flash(f"Module '{module.name}' deactivated.", "success")
    return redirect(url_for("frontend.super_admin_modules"))


@frontend_bp.route("/super-admin/modules/<module_id>/activate", methods=["POST"])
@super_admin_required
def super_admin_module_activate(module_id):
    from app.models import Module

    module = Module.query.get_or_404(module_id)
    module.status = True
    module.modified_by = session["user"]["id"]
    db.session.commit()
    _log_activity("Reactivated module", module.name)
    flash(f"Module '{module.name}' reactivated.", "success")
    return redirect(url_for("frontend.super_admin_modules"))


@frontend_bp.route("/super-admin/modules/<module_id>/sub-modules/create", methods=["POST"])
@super_admin_required
def super_admin_sub_module_create(module_id):
    from app.models import Module, SubModule

    module = Module.query.get_or_404(module_id)

    name = (request.form.get("name") or "").strip()
    sub_url = (request.form.get("sub_url") or "").strip()
    permission_key = (request.form.get("permission_key") or "").strip()

    if not name or not sub_url or not permission_key:
        flash("Name, URL, and permission key are all required for a sub-module.", "error")
        return redirect(url_for("frontend.super_admin_modules"))

    if SubModule.query.filter_by(permission_key=permission_key).first():
        flash(f"Permission key '{permission_key}' is already in use.", "error")
        return redirect(url_for("frontend.super_admin_modules"))

    max_order = (
        db.session.query(db.func.max(SubModule.sub_module_order_no))
        .filter(SubModule.module_id == module.id)
        .scalar()
        or 0
    )

    new_sub_module = SubModule(
        module_id=module.id,
        name=name,
        sub_url=sub_url,
        permission_key=permission_key,
        sub_module_order_no=max_order + 1,
        status=True,
        created_by=session["user"]["id"],
    )
    db.session.add(new_sub_module)
    db.session.commit()
    _log_activity("Created sub-module", f"{name} (under {module.name})")
    flash(f"Sub-module '{name}' added under '{module.name}'.", "success")
    return redirect(url_for("frontend.super_admin_modules"))


@frontend_bp.route("/super-admin/sub-modules/<sub_module_id>/deactivate", methods=["POST"])
@super_admin_required
def super_admin_sub_module_deactivate(sub_module_id):
    from app.models import SubModule

    sub_module = SubModule.query.get_or_404(sub_module_id)
    sub_module.status = False
    sub_module.modified_by = session["user"]["id"]
    db.session.commit()
    _log_activity("Deactivated sub-module", sub_module.name)
    flash(f"Sub-module '{sub_module.name}' deactivated.", "success")
    return redirect(url_for("frontend.super_admin_modules"))


@frontend_bp.route("/super-admin/users/<user_id>/permission-overrides", methods=["GET", "POST"])
@super_admin_required
def super_admin_user_permission_overrides(user_id):
    from app.models import Permission, Role, RolePermission, UserPermissionOverride, UserRole

    target_user = User.query.get_or_404(user_id)

    role_row = (
        db.session.query(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == target_user.id, UserRole.is_deleted == False)
        .first()
    )
    role_permission_ids = set()
    if role_row:
        role_permission_ids = {
            rp.permission_id
            for rp in RolePermission.query.filter_by(role_id=role_row.id, is_deleted=False).all()
        }

    all_permissions = Permission.query.filter_by(is_deleted=False).order_by(Permission.code).all()

    if request.method == "POST":
        existing_overrides = UserPermissionOverride.query.filter_by(
            user_id=target_user.id, is_deleted=False
        ).all()
        existing_by_permission = {o.permission_id: o for o in existing_overrides}

        for perm in all_permissions:
            choice = request.form.get(f"override_{perm.id}", "inherit")
            existing = existing_by_permission.get(perm.id)

            if choice == "inherit":
                if existing:
                    db.session.delete(existing)
            elif choice == "allow":
                if existing:
                    existing.is_allowed = True
                    existing.modified_by = session["user"]["id"]
                else:
                    db.session.add(UserPermissionOverride(
                        user_id=target_user.id,
                        permission_id=perm.id,
                        is_allowed=True,
                        created_by=session["user"]["id"],
                    ))
            elif choice == "deny":
                if existing:
                    existing.is_allowed = False
                    existing.modified_by = session["user"]["id"]
                else:
                    db.session.add(UserPermissionOverride(
                        user_id=target_user.id,
                        permission_id=perm.id,
                        is_allowed=False,
                        created_by=session["user"]["id"],
                    ))

        db.session.commit()
        invalidate_user_permission_cache(target_user.id)
        _log_activity("Updated user permission overrides", f"{target_user.full_name} ({target_user.email})")
        flash(f"Permission overrides updated for {target_user.full_name}", "success")
        return redirect(url_for("frontend.super_admin_user_permission_overrides", user_id=target_user.id))

    current_overrides = {
        o.permission_id: o.is_allowed
        for o in UserPermissionOverride.query.filter_by(user_id=target_user.id, is_deleted=False).all()
    }

    grouped_permissions = {}
    for perm in all_permissions:
        resource = perm.code.split(".")[0]
        grouped_permissions.setdefault(resource, []).append(perm)

    return render_template(
        "super_admin/user_permission_overrides.html",
        target_user=target_user,
        role_name=role_row.name if role_row else "No role assigned",
        grouped_permissions=grouped_permissions,
        role_permission_ids=role_permission_ids,
        current_overrides=current_overrides,
    )


@frontend_bp.route("/super-admin/activity-log")
@super_admin_required
def super_admin_activity_log():
    from app.models import ActivityLog

    page = _parse_int(request.args.get("page")) or 1
    per_page = 50
    action_filter = (request.args.get("action") or "").strip()
    user_filter = (request.args.get("user_id") or "").strip()
    organization_filter = _parse_int(request.args.get("organization_id"))

    query = ActivityLog.query.order_by(ActivityLog.created_at.desc())
    if action_filter:
        query = query.filter(ActivityLog.action.ilike(f"%{action_filter}%"))
    if user_filter:
        query = query.filter(ActivityLog.user_id == user_filter)

    selected_organization = None
    if organization_filter:
        selected_organization = Organization.query.get(organization_filter)
        # ActivityLog has no organization_id of its own - it's scoped through
        # the acting user, so we resolve "this org's activity" as "activity
        # by any user who belongs to this org" (soft-deleted users included,
        # since their past actions still matter for the audit trail).
        org_user_ids = [
            u.id for u in User.query.filter_by(organization_id=organization_filter).all()
        ]
        if org_user_ids:
            query = query.filter(ActivityLog.user_id.in_(org_user_ids))
        else:
            query = query.filter(ActivityLog.user_id == "__no_users__")  # no users -> no rows

    total_count = query.count()
    logs = query.offset((page - 1) * per_page).limit(per_page).all()

    user_ids = {log.user_id for log in logs if log.user_id}
    user_name_by_id = {
        u.id: u.full_name for u in User.query.filter(User.id.in_(user_ids)).all()
    } if user_ids else {}

    if organization_filter:
        all_users_for_filter = User.query.filter_by(
            is_deleted=False, organization_id=organization_filter
        ).order_by(User.full_name).all()
    else:
        all_users_for_filter = User.query.filter_by(is_deleted=False).order_by(User.full_name).all()

    total_pages = (total_count + per_page - 1) // per_page

    return render_template(
        "super_admin/activity_log.html",
        logs=logs,
        user_name_by_id=user_name_by_id,
        all_users_for_filter=all_users_for_filter,
        action_filter=action_filter,
        user_filter=user_filter,
        organization_filter=organization_filter,
        selected_organization=selected_organization,
        page=page,
        total_pages=total_pages,
        total_count=total_count,
    )


@frontend_bp.route("/super-admin/users")
@super_admin_required
def super_admin_users():
    users = User.query.filter_by(is_deleted=False).order_by(User.created_at.desc()).all()
    organizations = Organization.query.filter_by(status=1).all()
    org_map = {o.id: o.organization_name for o in organizations}
    return render_template("super_admin/users/index.html", users=users, org_map=org_map)


@frontend_bp.route("/super-admin/users/create", methods=["GET", "POST"])
@super_admin_required
def super_admin_create_user():
    organizations = Organization.query.filter_by(status=1).all()
    roles = Role.query.filter_by(is_deleted=False).order_by(Role.name).all()

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        username = request.form.get("username", "").strip().lower()
        dob = _parse_date(request.form.get("date_of_birth"))
        password = request.form.get("password", "")
        role = request.form.get("role")
        organization_id = request.form.get("organization_id") or None
        rbac_role_id = request.form.get("rbac_role_id") or None

        if not email or not first_name or not username or not password:
            flash("Please fill all required fields", "error")
            return render_template("super_admin/users/form.html", user=None, organizations=organizations, roles=roles)

        # NOTE: checks ALL users (including soft-deleted), not just active
        # ones - the database's UNIQUE constraint on email doesn't care
        # whether a matching row is soft-deleted, so a deleted user's email
        # is never actually free to reuse. Checking only active rows here
        # let a duplicate slip through and crash with a raw IntegrityError
        # instead of a friendly message.
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            if existing_email.is_deleted:
                flash("This email belongs to a previously deleted account and can't be reused. Use a different email, or ask a developer to permanently remove the old record.", "error")
            else:
                flash("A user with this email already exists", "error")
            return render_template("super_admin/users/form.html", user=None, organizations=organizations, roles=roles)

        existing_username = User.query.filter_by(username=username).first()
        if existing_username:
            if existing_username.is_deleted:
                flash("This username belongs to a previously deleted account and can't be reused. Please choose another.", "error")
            else:
                flash("This username is already taken. Please choose another.", "error")
            return render_template("super_admin/users/form.html", user=None, organizations=organizations, roles=roles)

        if role != "super_admin" and not organization_id:
            flash("Please select an organization for a non super-admin user", "error")
            return render_template("super_admin/users/form.html", user=None, organizations=organizations, roles=roles)

        # A non-super-admin user with no RBAC role has zero permissions and
        # will hit /no-access the moment they try to do anything - require a
        # role up front so nobody gets created in that dead-end state.
        if role != "super_admin" and not rbac_role_id:
            flash("Please select a role (Trainer, Recruiter, etc.) for this user.", "error")
            return render_template("super_admin/users/form.html", user=None, organizations=organizations, roles=roles)

        user = User(
            email=email,
            full_name=f"{first_name} {last_name}".strip(),
            first_name=first_name,
            last_name=last_name,
            username=username,
            date_of_birth=dob,
            password_hash=generate_password_hash(password),
            is_super_admin=(role == "super_admin"),
            organization_id=None if role == "super_admin" else _parse_int(organization_id),
            is_active=True,
        )
        db.session.add(user)
        db.session.flush()  # get user.id before the UserRole insert below

        if role != "super_admin" and rbac_role_id:
            db.session.add(UserRole(user_id=user.id, role_id=rbac_role_id))

        db.session.commit()
        _log_activity("Created user", f"{user.full_name} ({user.email})")
        flash("User created successfully", "success")
        return redirect(url_for("frontend.super_admin_users"))

    return render_template("super_admin/users/form.html", user=None, organizations=organizations, roles=roles)


@frontend_bp.route("/super-admin/users/<user_id>/edit", methods=["GET", "POST"])
@super_admin_required
def super_admin_edit_user(user_id):
    user = User.query.get_or_404(user_id)
    organizations = Organization.query.filter_by(status=1).all()
    roles = Role.query.filter_by(is_deleted=False).order_by(Role.name).all()

    current_user_role = (
        UserRole.query.filter_by(user_id=user.id, is_deleted=False).first()
        if not user.is_super_admin else None
    )
    current_role_id = current_user_role.role_id if current_user_role else None

    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        username = request.form.get("username", "").strip().lower()

        existing_username = User.query.filter(
            User.username == username, User.id != user.id
        ).first()
        if existing_username:
            if existing_username.is_deleted:
                flash("This username belongs to a previously deleted account and can't be reused. Please choose another.", "error")
            else:
                flash("This username is already taken. Please choose another.", "error")
            return render_template("super_admin/users/form.html", user=user, organizations=organizations, roles=roles, current_role_id=current_role_id)

        role = request.form.get("role")
        organization_id = request.form.get("organization_id") or None
        rbac_role_id = request.form.get("rbac_role_id") or None

        # Same dead-end-prevention as create: a non-super-admin with no RBAC
        # role has zero permissions and lands on /no-access for everything.
        if role != "super_admin" and not rbac_role_id:
            flash("Please select a role (Trainer, Recruiter, etc.) for this user.", "error")
            return render_template("super_admin/users/form.html", user=user, organizations=organizations, roles=roles, current_role_id=current_role_id)

        user.first_name = first_name
        user.last_name = last_name
        user.full_name = f"{first_name} {last_name}".strip()
        user.username = username
        user.date_of_birth = _parse_date(request.form.get("date_of_birth"))
        user.is_super_admin = (role == "super_admin")
        user.organization_id = None if role == "super_admin" else _parse_int(organization_id)

        new_password = request.form.get("password", "").strip()
        if new_password:
            user.password_hash = generate_password_hash(new_password)

        # Replace the user's RBAC role assignment if it changed. Super admins
        # don't need a Role row at all - is_super_admin already grants everything.
        if role == "super_admin":
            UserRole.query.filter_by(user_id=user.id, is_deleted=False).update({"is_deleted": True})
        elif rbac_role_id and rbac_role_id != current_role_id:
            UserRole.query.filter_by(user_id=user.id, is_deleted=False).update({"is_deleted": True})
            db.session.add(UserRole(user_id=user.id, role_id=rbac_role_id))

        db.session.commit()
        invalidate_user_permission_cache(user.id)
        _log_activity("Updated user", f"{user.full_name} ({user.email})")
        flash("User updated successfully", "success")
        return redirect(url_for("frontend.super_admin_users"))

    return render_template("super_admin/users/form.html", user=user, organizations=organizations, roles=roles, current_role_id=current_role_id)


@frontend_bp.route("/super-admin/users/<user_id>/toggle-active", methods=["POST"])
@super_admin_required
def super_admin_toggle_user_active(user_id):
    user = User.query.get_or_404(user_id)
    current_user = session.get("user")
    if user.id == current_user.get("id"):
        flash("You cannot deactivate your own account", "error")
        return redirect(url_for("frontend.super_admin_users"))

    user.is_active = not user.is_active
    db.session.commit()
    _log_activity("Toggled user active status", f"{user.full_name} -> {'active' if user.is_active else 'inactive'}")
    flash(f"User {'activated' if user.is_active else 'deactivated'} successfully", "success")
    return redirect(url_for("frontend.super_admin_users"))


@frontend_bp.route("/super-admin/users/<user_id>/delete", methods=["POST"])
@super_admin_required
def super_admin_delete_user(user_id):
    user = User.query.get_or_404(user_id)
    current_user = session.get("user")
    if user.id == current_user.get("id"):
        flash("You cannot delete your own account", "error")
        return redirect(url_for("frontend.super_admin_users"))

    user.is_deleted = True
    db.session.commit()
    _log_activity("Deleted user", f"{user.full_name} ({user.email})")
    flash("User deleted successfully", "success")
    return redirect(url_for("frontend.super_admin_users"))


@frontend_bp.route("/super-admin/users/deleted")
@super_admin_required
def super_admin_users_deleted():
    """Soft-deleted users - shown separately so their email/username can be
    freed up (via permanent delete) or the account restored, instead of
    them sitting invisible while still blocking that email/username forever."""
    deleted_users = User.query.filter_by(is_deleted=True).order_by(User.full_name).all()
    org_map = {o.id: o.organization_name for o in Organization.query.all()}
    return render_template("super_admin/users/deleted.html", users=deleted_users, org_map=org_map)


@frontend_bp.route("/super-admin/users/<user_id>/restore", methods=["POST"])
@super_admin_required
def super_admin_user_restore(user_id):
    user = User.query.filter_by(id=user_id, is_deleted=True).first_or_404()
    user.is_deleted = False
    db.session.commit()
    _log_activity("Restored user", f"{user.full_name} ({user.email})")
    flash(f"{user.full_name} restored successfully.", "success")
    return redirect(url_for("frontend.super_admin_users_deleted"))


@frontend_bp.route("/super-admin/users/<user_id>/purge", methods=["POST"])
@super_admin_required
def super_admin_user_purge(user_id):
    """Permanently removes a soft-deleted user AND every row that references
    them by foreign key (user_roles, user_settings, notifications), so the
    hard DELETE doesn't fail on a constraint violation. Their email and
    username become reusable again immediately after this.

    activity_logs rows are kept for the audit trail, but their user_id is
    set to NULL (the column is nullable=True) instead of being deleted, so
    the history of what was done isn't lost just because the actor's
    account is gone."""
    user = User.query.filter_by(id=user_id, is_deleted=True).first_or_404()

    full_name, email = user.full_name, user.email

    UserRole.query.filter_by(user_id=user.id).delete()
    UserPermissionOverride.query.filter_by(user_id=user.id).delete()
    UserSettings.query.filter_by(user_id=user.id).delete()
    Notification.query.filter_by(user_id=user.id).delete()
    ActivityLog.query.filter_by(user_id=user.id).update({"user_id": None})

    db.session.delete(user)
    db.session.commit()

    _log_activity("Permanently deleted user", f"{full_name} ({email}) - email/username freed for reuse")
    flash(f"{full_name} ({email}) permanently deleted. That email and username can be reused now.", "success")
    return redirect(url_for("frontend.super_admin_users_deleted"))


@frontend_bp.route("/super-admin/users/<user_id>/impersonate", methods=["POST"])
@super_admin_required
def super_admin_impersonate_user(user_id):
    """Lets a super admin temporarily view the app as another (non-super-admin)
    user, for support/debugging. The real super admin's session is stashed in
    session["impersonator"] so super_admin_stop_impersonating() can restore it."""
    if session.get("impersonator"):
        flash("You are already impersonating a user. Return to Super Admin first.", "error")
        return redirect(url_for("frontend.super_admin_users"))

    target = User.query.get_or_404(user_id)

    if target.is_super_admin:
        flash("You cannot impersonate another Super Admin.", "error")
        return redirect(url_for("frontend.super_admin_users"))

    if target.is_deleted or not target.is_active:
        flash("Cannot impersonate an inactive or deleted user.", "error")
        return redirect(url_for("frontend.super_admin_users"))

    real_admin = session.get("user")

    # Log while session["user"] still holds the real admin, so the audit
    # trail correctly attributes this action to them, not the target user.
    _log_activity(
        "impersonation.start",
        f"{real_admin.get('full_name')} started impersonating {target.full_name} ({target.email})",
    )

    session["impersonator"] = real_admin
    session["user"] = {
        "id": target.id,
        "email": target.email,
        "full_name": target.full_name,
        "is_super_admin": target.is_super_admin,
        "organization_id": target.organization_id,
    }
    session.permanent = True

    flash(f"You are now viewing as {target.full_name}.", "success")
    return redirect(url_for("frontend.organization_dashboard"))


@frontend_bp.route("/super-admin/stop-impersonating", methods=["POST"])
def super_admin_stop_impersonating():
    """Restores the real super admin's session. Deliberately NOT decorated
    with @super_admin_required, since while impersonating, session["user"]
    holds the impersonated (non-super-admin) user - that decorator would
    reject the very request meant to end impersonation."""
    real_admin = session.get("impersonator")
    if not real_admin:
        flash("You are not currently impersonating anyone.", "error")
        return redirect(url_for("frontend.login"))

    impersonated_user = session.get("user") or {}

    # Restore the real admin's session FIRST, then log - _log_activity reads
    # session["user"] internally, so logging must happen after the restore
    # or the action would be mis-attributed to the impersonated user.
    session["user"] = real_admin
    session.pop("impersonator", None)

    _log_activity(
        "impersonation.end",
        f"{real_admin.get('full_name')} stopped impersonating "
        f"{impersonated_user.get('full_name', 'unknown user')} ({impersonated_user.get('email', '-')})",
    )

    flash("You are back to your Super Admin account.", "success")
    return redirect(url_for("frontend.super_admin_dashboard"))


@frontend_bp.route("/organization/batches")
@login_required
def organization_batches():
    user = session.get("user")
    query = Batch.query
    if not user.get("is_super_admin"):
        query = query.filter_by(organization_id=user.get("organization_id"))
    batches = query.order_by(Batch.created_at.desc()).all()
    return render_template("organization/batches/index.html", batches=batches)


@frontend_bp.route("/organization/batches/create", methods=["GET", "POST"])
@login_required
@require_permission("batch.create")
def organization_batch_create():
    user = session.get("user")
    organizations = Organization.query.filter_by(status=1).all() if user.get("is_super_admin") else []

    if request.method == "POST":
        org_id = request.form.get("organization_id") if user.get("is_super_admin") else user.get("organization_id")
        if not org_id:
            flash("Please select an organization", "error")
            return render_template("organization/batches/form.html", batch=None, organizations=organizations)

        batch = Batch(
            organization_id=org_id,
            name=request.form.get("name"),
            training_center=request.form.get("training_center"),
            start_date=_parse_date(request.form.get("start_date")),
            end_date=_parse_date(request.form.get("end_date")),
        )
        db.session.add(batch)
        db.session.commit()
        _log_activity("Created batch", batch.name)
        invalidate_report_cache("reports")
        flash("Batch created successfully", "success")
        return redirect(url_for("frontend.organization_batches"))

    return render_template("organization/batches/form.html", batch=None, organizations=organizations)


@frontend_bp.route("/organization/batches/<batch_id>/edit", methods=["GET", "POST"])
@login_required
@require_permission("batch.update")
def organization_batch_edit(batch_id):
    user = session.get("user")
    batch = Batch.query.get_or_404(batch_id)
    organizations = Organization.query.filter_by(status=1).all() if user.get("is_super_admin") else []

    if request.method == "POST":
        if user.get("is_super_admin"):
            org_id = request.form.get("organization_id")
            if org_id:
                batch.organization_id = org_id
        batch.name = request.form.get("name")
        batch.training_center = request.form.get("training_center")
        batch.start_date = _parse_date(request.form.get("start_date"))
        batch.end_date = _parse_date(request.form.get("end_date"))
        db.session.commit()
        _log_activity("Updated batch", batch.name)
        invalidate_report_cache("reports")
        flash("Batch updated successfully", "success")
        return redirect(url_for("frontend.organization_batches"))

    return render_template("organization/batches/form.html", batch=batch, organizations=organizations)


@frontend_bp.route("/organization/batches/<batch_id>/delete", methods=["POST"])
@login_required
@require_permission("batch.delete")
def organization_batch_delete(batch_id):
    batch = Batch.query.get_or_404(batch_id)
    name = batch.name
    db.session.delete(batch)
    db.session.commit()
    _log_activity("Deleted batch", name)
    invalidate_report_cache("reports")
    flash("Batch deleted successfully", "success")
    return redirect(url_for("frontend.organization_batches"))


@frontend_bp.route("/organization/schemes")
@login_required
def organization_schemes():
    user = session.get("user")
    query = Scheme.query
    if not user.get("is_super_admin"):
        query = query.filter_by(organization_id=user.get("organization_id"))
    schemes = query.order_by(Scheme.created_at.desc()).all()
    return render_template("organization/schemes/index.html", schemes=schemes)


@frontend_bp.route("/organization/schemes/create", methods=["GET", "POST"])
@login_required
@require_permission("scheme.create")
def organization_scheme_create():
    user = session.get("user")
    organizations = Organization.query.filter_by(status=1).all() if user.get("is_super_admin") else []

    if request.method == "POST":
        org_id = request.form.get("organization_id") if user.get("is_super_admin") else user.get("organization_id")
        if not org_id:
            flash("Please select an organization", "error")
            return render_template("organization/schemes/form.html", scheme=None, organizations=organizations)

        scheme = Scheme(
            organization_id=org_id,
            name=request.form.get("name"),
            description=request.form.get("description"),
        )
        db.session.add(scheme)
        db.session.commit()
        _log_activity("Created scheme", scheme.name)
        invalidate_report_cache("reports")
        flash("Scheme created successfully", "success")
        return redirect(url_for("frontend.organization_schemes"))

    return render_template("organization/schemes/form.html", scheme=None, organizations=organizations)


@frontend_bp.route("/organization/schemes/<scheme_id>/edit", methods=["GET", "POST"])
@login_required
@require_permission("scheme.update")
def organization_scheme_edit(scheme_id):
    user = session.get("user")
    scheme = Scheme.query.get_or_404(scheme_id)
    organizations = Organization.query.filter_by(status=1).all() if user.get("is_super_admin") else []

    if request.method == "POST":
        if user.get("is_super_admin"):
            org_id = request.form.get("organization_id")
            if org_id:
                scheme.organization_id = org_id
        scheme.name = request.form.get("name")
        scheme.description = request.form.get("description")
        db.session.commit()
        _log_activity("Updated scheme", scheme.name)
        invalidate_report_cache("reports")
        flash("Scheme updated successfully", "success")
        return redirect(url_for("frontend.organization_schemes"))

    return render_template("organization/schemes/form.html", scheme=scheme, organizations=organizations)


@frontend_bp.route("/organization/schemes/<scheme_id>/delete", methods=["POST"])
@login_required
@require_permission("scheme.delete")
def organization_scheme_delete(scheme_id):
    scheme = Scheme.query.get_or_404(scheme_id)
    name = scheme.name
    db.session.delete(scheme)
    db.session.commit()
    _log_activity("Deleted scheme", name)
    invalidate_report_cache("reports")
    flash("Scheme deleted successfully", "success")
    return redirect(url_for("frontend.organization_schemes"))


@frontend_bp.route("/organization/candidates")
@login_required
@require_permission("candidate.view")
def organization_candidates():
    user = session.get("user")
    q = request.args.get("q", "").strip()
    training_status = request.args.get("training_status", "").strip()
    verification_status = request.args.get("verification_status", "").strip()
    placed_filter = request.args.get("placed", "").strip()
    sector_filter = request.args.get("sector", "").strip()
    proof_filter = request.args.get("placement_proof", "").strip()
    account_status_filter = request.args.get("account_status", "").strip()

    query = Candidate.query.filter_by(is_deleted=False)
    if not user.get("is_super_admin"):
        query = query.filter_by(organization_id=user.get("organization_id"))

    if q:
        query = query.filter(
            (Candidate.full_name.ilike(f"%{q}%"))
            | (Candidate.registration_number.ilike(f"%{q}%"))
            | (Candidate.mobile.ilike(f"%{q}%"))
            | (Candidate.email.ilike(f"%{q}%"))
        )

    if training_status:
        query = query.filter_by(training_status=training_status)

    if verification_status:
        query = query.filter_by(verification_status=verification_status)

    if placed_filter == "yes":
        query = query.filter(Candidate.employer_name.isnot(None), Candidate.employer_name != "")
    elif placed_filter == "no":
        query = query.filter((Candidate.employer_name.is_(None)) | (Candidate.employer_name == ""))

    if sector_filter:
        if sector_filter == "Unspecified":
            query = query.filter((Candidate.sector.is_(None)) | (Candidate.sector == ""))
        else:
            query = query.filter_by(sector=sector_filter)

    if proof_filter == "yes":
        query = query.filter_by(placement_proof_uploaded=True)

    if account_status_filter:
        query = query.filter_by(account_status=account_status_filter)

    candidates = query.order_by(Candidate.created_at.desc()).all()
    return render_template(
        "organization/candidates/index.html",
        candidates=candidates,
        search_query=q,
        training_status=training_status,
        verification_status=verification_status,
        account_status=account_status_filter,
    )


@frontend_bp.route("/organization/candidates/create", methods=["GET", "POST"])
@login_required
@require_permission("candidate.create")
def organization_candidate_create():
    user = session.get("user")
    organizations = Organization.query.filter_by(status=1).all() if user.get("is_super_admin") else []

    batch_query = Batch.query
    scheme_query = Scheme.query
    if not user.get("is_super_admin"):
        batch_query = batch_query.filter_by(organization_id=user.get("organization_id"))
        scheme_query = scheme_query.filter_by(organization_id=user.get("organization_id"))
    batches = batch_query.order_by(Batch.name).all()
    schemes = scheme_query.order_by(Scheme.name).all()

    if request.method == "POST":
        org_id = request.form.get("organization_id") if user.get("is_super_admin") else user.get("organization_id")
        if not org_id:
            flash("Please select an organization", "error")
            return render_template("organization/candidates/form.html", candidate=None, organizations=organizations, batches=batches, schemes=schemes)

        full_name_value = (request.form.get("full_name") or "").strip()
        mobile_check_value = (request.form.get("mobile") or "").strip()
        aadhaar_value = (request.form.get("aadhaar") or "").strip()
        registration_number_value = (request.form.get("registration_number") or "").strip()
        date_of_birth_value = (request.form.get("date_of_birth") or "").strip()
        gender_value = (request.form.get("gender") or "").strip()
        religion_value = (request.form.get("religion") or "").strip()
        current_address_value = (request.form.get("current_address") or "").strip()
        email_value = (request.form.get("email") or "").strip()
        pin_value = (request.form.get("pin") or "").strip()
        qualification_value = (request.form.get("qualification") or "").strip()
        board_value = (request.form.get("board") or "").strip()
        passing_year_value = (request.form.get("passing_year") or "").strip()
        percentage_value = (request.form.get("percentage") or "").strip()
        university_value = (request.form.get("university") or "").strip()

        required_fields = [
            (full_name_value, "Full Name"),
            (mobile_check_value, "Mobile"),
            (aadhaar_value, "Aadhaar"),
            (registration_number_value, "Registration Number"),
            (date_of_birth_value, "Date of Birth"),
            (gender_value, "Gender"),
            (religion_value, "Religion"),
            (current_address_value, "Current Address"),
            (email_value, "Email"),
            (pin_value, "Pincode"),
            (qualification_value, "Qualification"),
            (board_value, "Board"),
            (passing_year_value, "Passing Year"),
            (percentage_value, "Percentage"),
            (university_value, "University"),
        ]
        for value, label in required_fields:
            if not value:
                flash(f"{label} is required", "error")
                return render_template("organization/candidates/form.html", candidate=None, organizations=organizations, batches=batches, schemes=schemes)

        dup_mobile = Candidate.query.filter_by(mobile=mobile_check_value, is_deleted=False).first()
        if dup_mobile:
            flash(f"A candidate with this mobile number already exists: {dup_mobile.full_name} (Reg. No. {dup_mobile.registration_number or '-'})", "error")
            return render_template("organization/candidates/form.html", candidate=None, organizations=organizations, batches=batches, schemes=schemes)

        dup_aadhaar = Candidate.query.filter_by(aadhaar=aadhaar_value, is_deleted=False).first()
        if dup_aadhaar:
            flash(f"A candidate with this Aadhaar number already exists: {dup_aadhaar.full_name} (Reg. No. {dup_aadhaar.registration_number or '-'})", "error")
            return render_template("organization/candidates/form.html", candidate=None, organizations=organizations, batches=batches, schemes=schemes)

        dup_reg = Candidate.query.filter_by(registration_number=registration_number_value, is_deleted=False).first()
        if dup_reg:
            flash(f"A candidate with this Registration Number already exists: {dup_reg.full_name}", "error")
            return render_template("organization/candidates/form.html", candidate=None, organizations=organizations, batches=batches, schemes=schemes)

        dup_email = Candidate.query.filter_by(email=email_value, is_deleted=False).first()
        if dup_email:
            flash(f"A candidate with this email address already exists: {dup_email.full_name} (Reg. No. {dup_email.registration_number or '-'})", "error")
            return render_template("organization/candidates/form.html", candidate=None, organizations=organizations, batches=batches, schemes=schemes)

        offer_letter_url = None

        offer_file = request.files.get("offer_letter")
        if offer_file and offer_file.filename:
            filename = secure_filename(offer_file.filename)
            unique_name = f"{uuid.uuid4().hex}_{filename}"
            upload_dir = os.path.join("app", "static", "uploads", "offer_letters")
            os.makedirs(upload_dir, exist_ok=True)
            offer_file.save(os.path.join(upload_dir, unique_name))
            offer_letter_url = f"/static/uploads/offer_letters/{unique_name}"

        mobile_value = request.form.get("mobile") or ""
        default_password = mobile_value.strip() if mobile_value.strip() else "changeme123"

        candidate = Candidate(
            organization_id=org_id,
            registration_number=request.form.get("registration_number") or None,
            full_name=request.form.get("full_name"),
            father_name=request.form.get("father_name"),
            mother_name=request.form.get("mother_name"),
            gender=request.form.get("gender"),
            date_of_birth=_parse_date(request.form.get("date_of_birth")),
            aadhaar=request.form.get("aadhaar"),
            pan=request.form.get("pan"),
            mobile=request.form.get("mobile"),
            alternative_mobile=request.form.get("alternative_mobile"),
            email=request.form.get("email"),
            category=request.form.get("category"),
            religion=request.form.get("religion"),
            marital_status=request.form.get("marital_status"),
            blood_group=request.form.get("blood_group"),
            nationality=request.form.get("nationality"),
            current_address=request.form.get("current_address"),
            permanent_address=request.form.get("permanent_address"),
            village=request.form.get("village"),
            district=request.form.get("district"),
            state=request.form.get("state"),
            pin=request.form.get("pin"),
            qualification=request.form.get("qualification"),
            board=request.form.get("board"),
            passing_year=request.form.get("passing_year"),
            percentage=request.form.get("percentage"),
            university=request.form.get("university"),
            training_center=request.form.get("training_center"),
            training_batch=request.form.get("training_batch"),
            training_start_date=_parse_date(request.form.get("training_start_date")),
            training_end_date=_parse_date(request.form.get("training_end_date")),
            trainer=request.form.get("trainer"),
            sector=request.form.get("sector"),
            trade=request.form.get("trade"),
            course=request.form.get("course"),
            course_duration=request.form.get("course_duration"),
            training_status=request.form.get("training_status") or "training_started",
            bank_name=request.form.get("bank_name"),
            account_number=request.form.get("account_number"),
            ifsc=request.form.get("ifsc"),
            employer_name=request.form.get("employer_name"),
            job_role=request.form.get("job_role"),
            salary=request.form.get("salary"),
            joining_date=_parse_date(request.form.get("joining_date")),
            working_status=request.form.get("working_status"),
            location=request.form.get("location"),
            department=request.form.get("department"),
            manager=request.form.get("manager"),
            hr_contact=request.form.get("hr_contact"),
            verification_status="pending",
            batch_id=request.form.get("batch_id") or None,
            scheme_id=request.form.get("scheme_id") or None,
            offer_letter_url=offer_letter_url,
            placement_proof_uploaded=request.form.get("placement_proof_uploaded") == "on",
            password_hash=generate_password_hash(default_password),
        )
        db.session.add(candidate)
        db.session.commit()
        _create_notification(
            title=f"New candidate added: {candidate.full_name}",
            message=f"{candidate.full_name} was added to the candidate pool.",
            notif_type="info",
            organization_id=candidate.organization_id,
        )
        _log_activity("Created candidate", f"{candidate.full_name} ({candidate.registration_number or 'no reg. no.'})")
        invalidate_report_cache("reports")
        invalidate_report_cache("dashboard:org")
        invalidate_report_cache("dashboard:super_admin")
        flash("Candidate created successfully", "success")
        return redirect(url_for("frontend.organization_candidates"))

    return render_template("organization/candidates/form.html", candidate=None, organizations=organizations, batches=batches, schemes=schemes)


@frontend_bp.route("/organization/candidates/<candidate_id>")
@login_required
@require_permission("candidate.view")
def organization_candidate_detail(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    return render_template("organization/candidates/detail.html", candidate=candidate)


@frontend_bp.route("/organization/candidates/<candidate_id>/edit", methods=["GET", "POST"])
@login_required
@require_permission("candidate.update")
def organization_candidate_edit(candidate_id):
    user = session.get("user")
    candidate = Candidate.query.get_or_404(candidate_id)
    organizations = Organization.query.filter_by(status=1).all() if user.get("is_super_admin") else []

    batch_query = Batch.query
    scheme_query = Scheme.query
    if not user.get("is_super_admin"):
        batch_query = batch_query.filter_by(organization_id=user.get("organization_id"))
        scheme_query = scheme_query.filter_by(organization_id=user.get("organization_id"))
    batches = batch_query.order_by(Batch.name).all()
    schemes = scheme_query.order_by(Scheme.name).all()

    if request.method == "POST":
        was_placed = bool(candidate.employer_name)

        new_mobile = (request.form.get("mobile") or "").strip()
        new_email = (request.form.get("email") or "").strip()
        new_aadhaar = (request.form.get("aadhaar") or "").strip()
        new_reg_no = (request.form.get("registration_number") or "").strip()

        if new_mobile and new_mobile != candidate.mobile:
            dup_mobile = Candidate.query.filter(
                Candidate.mobile == new_mobile, Candidate.id != candidate.id, Candidate.is_deleted == False
            ).first()
            if dup_mobile:
                flash(f"A candidate with this mobile number already exists: {dup_mobile.full_name} (Reg. No. {dup_mobile.registration_number or '-'})", "error")
                return render_template("organization/candidates/form.html", candidate=candidate, organizations=organizations, batches=batches, schemes=schemes)

        if new_email and new_email != candidate.email:
            dup_email = Candidate.query.filter(
                Candidate.email == new_email, Candidate.id != candidate.id, Candidate.is_deleted == False
            ).first()
            if dup_email:
                flash(f"A candidate with this email address already exists: {dup_email.full_name} (Reg. No. {dup_email.registration_number or '-'})", "error")
                return render_template("organization/candidates/form.html", candidate=candidate, organizations=organizations, batches=batches, schemes=schemes)

        if new_aadhaar and new_aadhaar != candidate.aadhaar:
            dup_aadhaar = Candidate.query.filter(
                Candidate.aadhaar == new_aadhaar, Candidate.id != candidate.id, Candidate.is_deleted == False
            ).first()
            if dup_aadhaar:
                flash(f"A candidate with this Aadhaar number already exists: {dup_aadhaar.full_name} (Reg. No. {dup_aadhaar.registration_number or '-'})", "error")
                return render_template("organization/candidates/form.html", candidate=candidate, organizations=organizations, batches=batches, schemes=schemes)

        if new_reg_no and new_reg_no != candidate.registration_number:
            dup_reg = Candidate.query.filter(
                Candidate.registration_number == new_reg_no, Candidate.id != candidate.id, Candidate.is_deleted == False
            ).first()
            if dup_reg:
                flash(f"A candidate with this Registration Number already exists: {dup_reg.full_name}", "error")
                return render_template("organization/candidates/form.html", candidate=candidate, organizations=organizations, batches=batches, schemes=schemes)

        if user.get("is_super_admin"):
            org_id = request.form.get("organization_id")
            if org_id:
                candidate.organization_id = org_id
        candidate.registration_number = request.form.get("registration_number") or None
        candidate.full_name = request.form.get("full_name")
        candidate.father_name = request.form.get("father_name")
        candidate.mother_name = request.form.get("mother_name")
        candidate.gender = request.form.get("gender")
        candidate.date_of_birth = _parse_date(request.form.get("date_of_birth"))
        candidate.aadhaar = request.form.get("aadhaar")
        candidate.pan = request.form.get("pan")
        candidate.mobile = request.form.get("mobile")
        candidate.alternative_mobile = request.form.get("alternative_mobile")
        candidate.email = request.form.get("email")
        candidate.category = request.form.get("category")
        candidate.religion = request.form.get("religion")
        candidate.marital_status = request.form.get("marital_status")
        candidate.blood_group = request.form.get("blood_group")
        candidate.nationality = request.form.get("nationality")
        candidate.current_address = request.form.get("current_address")
        candidate.permanent_address = request.form.get("permanent_address")
        candidate.village = request.form.get("village")
        candidate.district = request.form.get("district")
        candidate.state = request.form.get("state")
        candidate.pin = request.form.get("pin")
        candidate.qualification = request.form.get("qualification")
        candidate.board = request.form.get("board")
        candidate.passing_year = request.form.get("passing_year")
        candidate.percentage = request.form.get("percentage")
        candidate.university = request.form.get("university")
        candidate.training_center = request.form.get("training_center")
        candidate.training_batch = request.form.get("training_batch")
        candidate.training_start_date = _parse_date(request.form.get("training_start_date"))
        candidate.training_end_date = _parse_date(request.form.get("training_end_date"))
        candidate.trainer = request.form.get("trainer")
        candidate.sector = request.form.get("sector")
        candidate.trade = request.form.get("trade")
        candidate.course = request.form.get("course")
        candidate.course_duration = request.form.get("course_duration")
        candidate.training_status = request.form.get("training_status")
        candidate.bank_name = request.form.get("bank_name")
        candidate.account_number = request.form.get("account_number")
        candidate.ifsc = request.form.get("ifsc")
        candidate.employer_name = request.form.get("employer_name")
        candidate.job_role = request.form.get("job_role")
        candidate.salary = request.form.get("salary")
        candidate.joining_date = _parse_date(request.form.get("joining_date"))
        candidate.working_status = request.form.get("working_status")
        candidate.location = request.form.get("location")
        candidate.department = request.form.get("department")
        candidate.manager = request.form.get("manager")
        candidate.hr_contact = request.form.get("hr_contact")
        candidate.verification_status = request.form.get("verification_status")
        candidate.batch_id = request.form.get("batch_id") or None
        candidate.scheme_id = request.form.get("scheme_id") or None
        candidate.placement_proof_uploaded = request.form.get("placement_proof_uploaded") == "on"

        offer_file = request.files.get("offer_letter")
        if offer_file and offer_file.filename:
            filename = secure_filename(offer_file.filename)
            unique_name = f"{uuid.uuid4().hex}_{filename}"
            upload_dir = os.path.join("app", "static", "uploads", "offer_letters")
            os.makedirs(upload_dir, exist_ok=True)
            offer_file.save(os.path.join(upload_dir, unique_name))
            candidate.offer_letter_url = f"/static/uploads/offer_letters/{unique_name}"

        if not candidate.password_hash and candidate.mobile:
            candidate.password_hash = generate_password_hash(candidate.mobile.strip())

        db.session.commit()

        is_placed_now = bool(candidate.employer_name)
        if is_placed_now and not was_placed:
            _create_notification(
                title=f"Candidate placed: {candidate.full_name}",
                message=f"{candidate.full_name} was placed at {candidate.employer_name} as {candidate.job_role or 'N/A'}.",
                notif_type="success",
                organization_id=candidate.organization_id,
            )
            _send_placement_email(candidate)

        _log_activity("Updated candidate", f"{candidate.full_name}")
        invalidate_report_cache("reports")
        invalidate_report_cache("dashboard:org")
        invalidate_report_cache("dashboard:super_admin")

        flash("Candidate updated successfully", "success")
        return redirect(url_for("frontend.organization_candidate_detail", candidate_id=candidate.id))

    return render_template("organization/candidates/form.html", candidate=candidate, organizations=organizations, batches=batches, schemes=schemes)


@frontend_bp.route("/organization/candidates/<candidate_id>/delete", methods=["POST"])
@login_required
@require_permission("candidate.delete")
def organization_candidate_delete(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    candidate.is_deleted = True
    db.session.commit()
    _log_activity("Deleted candidate", f"{candidate.full_name} ({candidate.registration_number or 'no reg. no.'})")
    invalidate_report_cache("reports")
    invalidate_report_cache("dashboard:org")
    invalidate_report_cache("dashboard:super_admin")
    flash("Candidate deleted successfully", "success")
    return redirect(url_for("frontend.organization_candidates"))


@frontend_bp.route("/organization/candidates/deleted")
@login_required
@require_permission("candidate.view_deleted")
def organization_candidates_deleted():
    user = session.get("user")
    query = Candidate.query.filter_by(is_deleted=True)
    if not user.get("is_super_admin"):
        query = query.filter_by(organization_id=user.get("organization_id"))
    candidates = query.order_by(Candidate.updated_at.desc()).all()
    return render_template("organization/candidates/deleted.html", candidates=candidates)


@frontend_bp.route("/organization/candidates/<candidate_id>/restore", methods=["POST"])
@login_required
@require_permission("candidate.update")
def organization_candidate_restore(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    candidate.is_deleted = False
    db.session.commit()
    _log_activity("Restored candidate", f"{candidate.full_name} ({candidate.registration_number or 'no reg. no.'})")
    invalidate_report_cache("reports")
    invalidate_report_cache("dashboard:org")
    invalidate_report_cache("dashboard:super_admin")
    flash(f"{candidate.full_name} restored successfully", "success")
    return redirect(url_for("frontend.organization_candidates_deleted"))


@frontend_bp.route("/organization/candidates/bulk-action", methods=["POST"])
@login_required
@require_permission("candidate.update")
def organization_candidates_bulk_action():
    user = session.get("user")
    action = request.form.get("action")
    candidate_ids = request.form.getlist("candidate_ids")

    if action == "delete" and not has_permission(user, "candidate.delete"):
        flash("You do not have permission to delete candidates.", "error")
        return redirect(url_for("frontend.organization_candidates"))

    if not candidate_ids:
        flash("No candidates selected", "error")
        return redirect(url_for("frontend.organization_candidates"))

    query = Candidate.query.filter(Candidate.id.in_(candidate_ids))
    if not user.get("is_super_admin"):
        query = query.filter_by(organization_id=user.get("organization_id"))
    candidates = query.all()

    if not candidates:
        flash("No matching candidates found", "error")
        return redirect(url_for("frontend.organization_candidates"))

    count = 0
    if action == "verify":
        for c in candidates:
            c.verification_status = "verified"
            count += 1
        _log_activity("Bulk verified candidates", f"{count} candidate(s)")
        flash(f"{count} candidate(s) marked as verified", "success")
    elif action == "block":
        for c in candidates:
            c.account_status = "blocked"
            count += 1
        _log_activity("Bulk blocked candidates", f"{count} candidate(s)")
        flash(f"{count} candidate(s) blocked", "success")
    elif action == "unblock":
        for c in candidates:
            c.account_status = "active"
            count += 1
        _log_activity("Bulk unblocked candidates", f"{count} candidate(s)")
        flash(f"{count} candidate(s) unblocked", "success")
    elif action == "delete":
        for c in candidates:
            c.is_deleted = True
            count += 1
        _log_activity("Bulk deleted candidates", f"{count} candidate(s)")
        flash(f"{count} candidate(s) deleted", "success")
    else:
        flash("Unknown bulk action", "error")
        return redirect(url_for("frontend.organization_candidates"))

    db.session.commit()
    invalidate_report_cache("reports")
    invalidate_report_cache("dashboard:org")
    invalidate_report_cache("dashboard:super_admin")
    return redirect(url_for("frontend.organization_candidates"))


@frontend_bp.route("/organization/candidates/export.xlsx")
@login_required
@require_permission("candidate.export")
def organization_candidates_export():
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from io import BytesIO
    from flask import send_file

    user = session.get("user")
    query = Candidate.query.filter_by(is_deleted=False)
    if not user.get("is_super_admin"):
        query = query.filter_by(organization_id=user.get("organization_id"))

    search_query = request.args.get("q", "").strip()
    training_status = request.args.get("training_status", "").strip()
    verification_status = request.args.get("verification_status", "").strip()
    account_status = request.args.get("account_status", "").strip()

    if search_query:
        query = query.filter(
            (Candidate.full_name.ilike(f"%{search_query}%"))
            | (Candidate.registration_number.ilike(f"%{search_query}%"))
            | (Candidate.mobile.ilike(f"%{search_query}%"))
        )
    if training_status:
        query = query.filter_by(training_status=training_status)
    if verification_status:
        query = query.filter_by(verification_status=verification_status)
    if account_status:
        query = query.filter_by(account_status=account_status)

    candidates = query.order_by(Candidate.created_at.desc()).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Candidates"

    headers = [
        "Registration No.", "Full Name", "Mobile", "Email", "Training Center",
        "Course", "Sector", "Training Status", "Employer", "Job Role",
        "Working Status", "Verification Status", "Account Status",
    ]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for c in candidates:
        ws.append([
            c.registration_number or "-",
            c.full_name or "-",
            c.mobile or "-",
            c.email or "-",
            c.training_center or "-",
            c.course or "-",
            c.sector or "-",
            c.training_status or "-",
            c.employer_name or "-",
            c.job_role or "-",
            c.working_status or "-",
            c.verification_status or "-",
            c.account_status or "-",
        ])

    for col_cells in ws.columns:
        max_length = max(len(str(cell.value)) if cell.value else 0 for cell in col_cells)
        ws.column_dimensions[col_cells[0].column_letter].width = min(max_length + 2, 40)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    _log_activity("Exported candidates to Excel", f"{len(candidates)} candidate(s)")

    return send_file(
        buffer,
        as_attachment=True,
        download_name="candidates_export.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@frontend_bp.route("/organization/candidates/export.pdf")
@login_required
@require_permission("candidate.export")
def organization_candidates_export_pdf():
    from io import BytesIO
    from datetime import datetime
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from flask import send_file

    user = session.get("user")
    query = Candidate.query.filter_by(is_deleted=False)
    if not user.get("is_super_admin"):
        query = query.filter_by(organization_id=user.get("organization_id"))

    search_query = request.args.get("q", "").strip()
    training_status = request.args.get("training_status", "").strip()
    verification_status = request.args.get("verification_status", "").strip()
    account_status = request.args.get("account_status", "").strip()

    if search_query:
        query = query.filter(
            (Candidate.full_name.ilike(f"%{search_query}%"))
            | (Candidate.registration_number.ilike(f"%{search_query}%"))
            | (Candidate.mobile.ilike(f"%{search_query}%"))
        )
    if training_status:
        query = query.filter_by(training_status=training_status)
    if verification_status:
        query = query.filter_by(verification_status=verification_status)
    if account_status:
        query = query.filter_by(account_status=account_status)

    candidates = query.order_by(Candidate.created_at.desc()).all()

    org_name = "Codevocado Placement Tracking System"
    if not user.get("is_super_admin"):
        org = Organization.query.get(user.get("organization_id"))
        if org:
            org_name = org.organization_name

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
    )
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(org_name, styles["Title"]))
    story.append(Paragraph("Candidates Report", styles["Heading2"]))
    story.append(Paragraph(f"Generated on: {datetime.utcnow().strftime('%d-%m-%Y %H:%M')} UTC | Total records: {len(candidates)}", styles["Normal"]))
    story.append(Spacer(1, 12))

    table_data = [[
        "Reg. No.", "Name", "Mobile", "Training Center", "Course", "Sector",
        "Training Status", "Employer", "Verification", "Account Status",
    ]]
    for c in candidates:
        table_data.append([
            c.registration_number or "-",
            c.full_name or "-",
            c.mobile or "-",
            c.training_center or "-",
            c.course or "-",
            c.sector or "-",
            c.training_status or "-",
            c.employer_name or "-",
            c.verification_status or "-",
            c.account_status or "-",
        ])

    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table)

    doc.build(story)
    buffer.seek(0)

    _log_activity("Exported candidates to PDF", f"{len(candidates)} candidate(s)")

    return send_file(
        buffer,
        as_attachment=True,
        download_name="candidates_report.pdf",
        mimetype="application/pdf",
    )


@frontend_bp.route("/organization/candidates/<candidate_id>/certificate.pdf")
@login_required
@require_permission("candidate.view")
def organization_candidate_certificate_pdf(candidate_id):
    from io import BytesIO
    from datetime import datetime
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from flask import send_file

    candidate = Candidate.query.get_or_404(candidate_id)
    if not candidate.employer_name:
        flash("This candidate has not been placed yet - certificate not available.", "error")
        return redirect(url_for("frontend.organization_candidate_detail", candidate_id=candidate_id))

    org_name = "Codevocado Placement Tracking System"
    organization = Organization.query.get(candidate.organization_id)
    if organization:
        org_name = organization.organization_name

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=25 * mm,
        bottomMargin=25 * mm,
        leftMargin=25 * mm,
        rightMargin=25 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("CertTitle", parent=styles["Title"], alignment=TA_CENTER, fontSize=22, spaceAfter=6)
    sub_style = ParagraphStyle("CertSub", parent=styles["Normal"], alignment=TA_CENTER, fontSize=11, textColor=colors.grey)
    body_style = ParagraphStyle("CertBody", parent=styles["Normal"], alignment=TA_CENTER, fontSize=13, leading=20, spaceBefore=16, spaceAfter=16)
    name_style = ParagraphStyle("CertName", parent=styles["Title"], alignment=TA_CENTER, fontSize=20, textColor=colors.HexColor("#2563eb"), spaceBefore=10, spaceAfter=10)

    story = []
    story.append(Paragraph(org_name, sub_style))
    story.append(Spacer(1, 20))
    story.append(Paragraph("CERTIFICATE OF PLACEMENT", title_style))
    story.append(Spacer(1, 30))
    story.append(Paragraph("This is to certify that", body_style))
    story.append(Paragraph(candidate.full_name, name_style))

    joining_str = candidate.joining_date.strftime("%d %B %Y") if candidate.joining_date else "N/A"
    body_text = (
        f"Registration No. <b>{candidate.registration_number or '-'}</b>, "
        f"has successfully completed training under the <b>{candidate.course or candidate.sector or '-'}</b> program "
        f"and has been placed as <b>{candidate.job_role or 'N/A'}</b> at "
        f"<b>{candidate.employer_name}</b>, joining on <b>{joining_str}</b>."
    )
    story.append(Paragraph(body_text, body_style))
    story.append(Spacer(1, 40))

    meta_table = Table(
        [
            ["Training Center", candidate.training_center or "-"],
            ["Sector", candidate.sector or "-"],
            ["Location", candidate.location or "-"],
            ["Certificate Generated On", datetime.utcnow().strftime("%d-%m-%Y")],
        ],
        colWidths=[60 * mm, 90 * mm],
    )
    meta_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
    ]))
    story.append(meta_table)

    doc.build(story)
    buffer.seek(0)

    _log_activity("Generated placement certificate", candidate.full_name)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"{candidate.full_name.replace(' ', '_')}_certificate.pdf",
        mimetype="application/pdf",
    )


@frontend_bp.route("/organization/candidates/<candidate_id>/toggle-status", methods=["POST"])
@login_required
@require_permission("candidate.update")
def organization_candidate_toggle_status(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    candidate.account_status = "blocked" if candidate.account_status == "active" else "active"
    db.session.commit()
    _log_activity("Toggled candidate account status", f"{candidate.full_name} -> {candidate.account_status}")

    flash(f"Candidate account {candidate.account_status}", "success")
    return redirect(url_for("frontend.organization_candidates"))


@frontend_bp.route("/organization/candidates/<candidate_id>/reset-password", methods=["POST"])
@login_required
@require_permission("candidate.update")
def organization_candidate_reset_password(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    if not candidate.mobile:
        flash("Cannot reset password - candidate has no mobile number on file", "error")
        return redirect(url_for("frontend.organization_candidates"))

    candidate.password_hash = generate_password_hash(candidate.mobile.strip())
    db.session.commit()
    _log_activity("Reset candidate password", candidate.full_name)

    flash(f"Password reset for {candidate.full_name}. New password: {candidate.mobile.strip()} (their mobile number)", "success")
    return redirect(url_for("frontend.organization_candidates"))


@frontend_bp.route("/organization/candidates/bulk-set-passwords", methods=["POST"])
@login_required
@require_permission("candidate.update")
def organization_candidates_bulk_set_passwords():
    """One-time helper: sets password = mobile number for any candidate that doesn't have one yet."""
    user = session.get("user")
    query = Candidate.query.filter_by(is_deleted=False, password_hash=None)
    if not user.get("is_super_admin"):
        query = query.filter_by(organization_id=user.get("organization_id"))

    candidates = query.all()
    updated = 0
    skipped = 0
    for candidate in candidates:
        if candidate.mobile and candidate.mobile.strip():
            candidate.password_hash = generate_password_hash(candidate.mobile.strip())
            updated += 1
        else:
            skipped += 1

    db.session.commit()
    _log_activity("Bulk-set candidate passwords", f"{updated} updated, {skipped} skipped (no mobile number)")
    flash(f"Passwords set for {updated} candidates. {skipped} skipped (no mobile number on file).", "success")
    return redirect(url_for("frontend.organization_candidates"))


@frontend_bp.route("/candidates/import", methods=["GET", "POST"])
@login_required
@require_permission("candidate.import")
def candidate_import():
    user = session.get("user")
    organizations = Organization.query.filter_by(status=1).all() if user.get("is_super_admin") else []
    summary = None

    # Non-super-admins are scoped to their own organization's feature flag.
    # Super admins pick the target org per-request (via the form), so this
    # check is enforced again below once org_id is known on POST.
    if not user.get("is_super_admin") and not is_feature_enabled(user.get("organization_id"), "candidate_import"):
        flash("Bulk candidate import is not enabled for your organization. Contact your Codevocado account manager.", "error")
        return redirect(url_for("frontend.organization_candidates"))

    if request.method == "POST":
        import csv
        import io

        org_id = request.form.get("organization_id") if user.get("is_super_admin") else user.get("organization_id")
        file = request.files.get("csv_file")

        if not org_id:
            flash("Please select an organization", "error")
            return render_template("organization/candidates/import.html", organizations=organizations, summary=None)

        if not is_feature_enabled(org_id, "candidate_import"):
            flash("Bulk candidate import is not enabled for that organization.", "error")
            return render_template("organization/candidates/import.html", organizations=organizations, summary=None)

        if not file or file.filename == "":
            flash("Please choose a CSV file to upload", "error")
            return render_template("organization/candidates/import.html", organizations=organizations, summary=None)

        try:
            stream = io.StringIO(file.stream.read().decode("utf-8-sig"))
            reader = csv.DictReader(stream)
        except Exception:
            flash("Could not read the file. Please upload a valid CSV.", "error")
            return render_template("organization/candidates/import.html", organizations=organizations, summary=None)

        total = 0
        valid = 0
        duplicate = 0
        invalid = 0

        for row in reader:
            total += 1
            full_name = (row.get("full_name") or "").strip()
            if not full_name:
                invalid += 1
                continue

            reg_no = (row.get("registration_number") or "").strip() or None
            if reg_no:
                existing = Candidate.query.filter_by(registration_number=reg_no).first()
                if existing:
                    duplicate += 1
                    continue

            mobile_value = (row.get("mobile") or "").strip() or None

            candidate = Candidate(
                organization_id=org_id,
                registration_number=reg_no,
                full_name=full_name,
                mobile=mobile_value,
                email=(row.get("email") or "").strip() or None,
                gender=(row.get("gender") or "").strip() or None,
                course=(row.get("course") or "").strip() or None,
                sector=(row.get("sector") or "").strip() or None,
                training_center=(row.get("training_center") or "").strip() or None,
                employer_name=(row.get("employer_name") or "").strip() or None,
                job_role=(row.get("job_role") or "").strip() or None,
                training_status="training_started",
                verification_status="pending",
                password_hash=generate_password_hash(mobile_value) if mobile_value else None,
            )
            db.session.add(candidate)
            valid += 1

        db.session.commit()
        _log_activity("Bulk imported candidates", f"{valid} added, {duplicate} duplicates, {invalid} invalid (of {total} rows)")
        _create_notification(
            title="Bulk candidate import completed",
            message=f"{valid} candidates imported successfully. {duplicate} duplicates and {invalid} invalid rows skipped.",
            notif_type="success",
            organization_id=org_id,
        )
        invalidate_report_cache("reports")
        invalidate_report_cache("dashboard:org")
        invalidate_report_cache("dashboard:super_admin")

        summary = {"total": total, "valid": valid, "duplicate": duplicate, "invalid": invalid}
        flash(f"Import complete: {valid} added, {duplicate} duplicates, {invalid} invalid", "success")

    return render_template("organization/candidates/import.html", organizations=organizations, summary=summary)


@frontend_bp.route("/candidates/import/template")
@login_required
@require_permission("candidate.import")
def candidate_import_template():
    from flask import Response
    csv_content = "registration_number,full_name,mobile,email,gender,course,sector,training_center,employer_name,job_role\n"
    csv_content += "REG001,John Doe,9876543210,john@example.com,male,Data Science,IT,AICTE,,\n"
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=candidate_import_template.csv"},
    )


@frontend_bp.route("/candidate/login", methods=["GET", "POST"])
def candidate_login():
    error = None
    if request.method == "POST":
        reg_no = request.form.get("registration_number", "").strip()
        password = request.form.get("password", "")

        candidate = Candidate.query.filter_by(registration_number=reg_no, is_deleted=False).first()

        if not candidate or not candidate.password_hash or not check_password_hash(candidate.password_hash, password):
            error = "Invalid registration number or password"
        elif candidate.account_status == "blocked":
            error = "Your account has been blocked. Please contact your training center."
        else:
            from datetime import datetime
            candidate.last_login_at = datetime.utcnow()
            db.session.commit()

            session["candidate"] = {
                "id": candidate.id,
                "full_name": candidate.full_name,
                "registration_number": candidate.registration_number,
            }
            session.permanent = True
            flash(f"Welcome, {candidate.full_name}", "success")
            return redirect(url_for("frontend.candidate_dashboard"))

    return render_template("candidate/login.html", error=error)


@frontend_bp.route("/candidate/logout")
def candidate_logout():
    session.pop("candidate", None)
    flash("You have been logged out", "success")
    return redirect(url_for("frontend.candidate_login"))


@frontend_bp.route("/candidate/dashboard", methods=["GET", "POST"])
@candidate_login_required
def candidate_dashboard():
    session_candidate = session.get("candidate")
    candidate = Candidate.query.get_or_404(session_candidate.get("id"))

    if request.method == "POST":
        candidate.mobile = request.form.get("mobile")
        candidate.alternative_mobile = request.form.get("alternative_mobile")
        candidate.email = request.form.get("email")
        candidate.current_address = request.form.get("current_address")
        candidate.permanent_address = request.form.get("permanent_address")
        candidate.bank_name = request.form.get("bank_name")
        candidate.account_number = request.form.get("account_number")
        candidate.ifsc = request.form.get("ifsc")
        db.session.commit()
        flash("Your details have been updated successfully", "success")
        return redirect(url_for("frontend.candidate_dashboard"))

    existing_feedback = CandidateFeedback.query.filter_by(candidate_id=candidate.id).first()
    return render_template("candidate/dashboard.html", candidate=candidate, existing_feedback=existing_feedback)


@frontend_bp.route("/candidate/change-password", methods=["POST"])
@candidate_login_required
def candidate_change_password():
    session_candidate = session.get("candidate")
    candidate = Candidate.query.get_or_404(session_candidate.get("id"))

    current = request.form.get("current_password")
    new = request.form.get("new_password")
    confirm = request.form.get("confirm_password")

    if not candidate.password_hash or not check_password_hash(candidate.password_hash, current):
        flash("Current password is incorrect", "error")
    elif new != confirm:
        flash("New passwords do not match", "error")
    elif len(new) < 6:
        flash("New password must be at least 6 characters", "error")
    else:
        candidate.password_hash = generate_password_hash(new)
        db.session.commit()
        flash("Password changed successfully", "success")

    return redirect(url_for("frontend.candidate_dashboard"))


@frontend_bp.route("/candidate/feedback", methods=["POST"])
@candidate_login_required
def candidate_feedback_submit():
    session_candidate = session.get("candidate")
    candidate = Candidate.query.get_or_404(session_candidate.get("id"))

    if not candidate.employer_name:
        flash("Feedback is available once you've been placed.", "error")
        return redirect(url_for("frontend.candidate_dashboard"))

    if CandidateFeedback.query.filter_by(candidate_id=candidate.id).first():
        flash(translate("feedback_already_submitted"), "info")
        return redirect(url_for("frontend.candidate_dashboard"))

    rating = _parse_int(request.form.get("rating"))
    if not rating or rating < 1 or rating > 5:
        flash("Please select a rating between 1 and 5 stars.", "error")
        return redirect(url_for("frontend.candidate_dashboard"))

    feedback = CandidateFeedback(
        candidate_id=candidate.id,
        organization_id=candidate.organization_id,
        rating=rating,
        comment=(request.form.get("comment") or "").strip() or None,
    )
    db.session.add(feedback)
    db.session.commit()

    _create_notification(
        title=f"New feedback from {candidate.full_name}",
        message=f"{candidate.full_name} rated their placement experience {rating}/5 stars.",
        notif_type="info",
        organization_id=candidate.organization_id,
    )

    flash(translate("feedback_thanks"), "success")
    return redirect(url_for("frontend.candidate_dashboard"))


@frontend_bp.route("/organization/feedback")
@login_required
@require_permission("placement.view")
def organization_feedback():
    user = session.get("user")
    query = CandidateFeedback.query
    if not user.get("is_super_admin"):
        query = query.filter_by(organization_id=user.get("organization_id"))
    feedback_rows = query.order_by(CandidateFeedback.created_at.desc()).all()

    candidate_ids = [f.candidate_id for f in feedback_rows]
    candidates_by_id = {
        c.id: c for c in Candidate.query.filter(Candidate.id.in_(candidate_ids)).all()
    } if candidate_ids else {}

    total_feedback = len(feedback_rows)
    avg_rating = round(sum(f.rating for f in feedback_rows) / total_feedback, 1) if total_feedback else None
    rating_counts = {i: sum(1 for f in feedback_rows if f.rating == i) for i in range(1, 6)}

    return render_template(
        "organization/feedback/index.html",
        feedback_rows=feedback_rows,
        candidates_by_id=candidates_by_id,
        avg_rating=avg_rating,
        rating_counts=rating_counts,
        total_feedback=total_feedback,
    )


@frontend_bp.route("/organization/placements")
@login_required
@require_permission("placement.view")
def organization_placements():
    user = session.get("user")
    query = Candidate.query.filter(
        Candidate.is_deleted == False,
        Candidate.employer_name.isnot(None),
        Candidate.employer_name != "",
    )
    if not user.get("is_super_admin"):
        query = query.filter_by(organization_id=user.get("organization_id"))
    placements = query.order_by(Candidate.joining_date.desc()).all()

    placement_data = []
    for candidate in placements:
        total = FollowUpCheckpoint.query.filter_by(candidate_id=candidate.id).count()
        done = FollowUpCheckpoint.query.filter_by(candidate_id=candidate.id, status="completed").count()
        placement_data.append({"candidate": candidate, "checkpoints_total": total, "checkpoints_done": done})

    return render_template("organization/placements/index.html", placement_data=placement_data)


@frontend_bp.route("/organization/placements/<candidate_id>")
@login_required
@require_permission("placement.view")
def organization_placement_detail(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    _ensure_checkpoints(candidate)
    checkpoints = FollowUpCheckpoint.query.filter_by(candidate_id=candidate.id).order_by(FollowUpCheckpoint.due_date.asc()).all()
    return render_template("organization/placements/detail.html", candidate=candidate, checkpoints=checkpoints)


@frontend_bp.route("/organization/placements/<candidate_id>/checkpoint/<checkpoint_id>", methods=["POST"])
@login_required
@require_permission("placement.update")
def organization_placement_checkpoint_update(checkpoint_id, candidate_id):
    checkpoint = FollowUpCheckpoint.query.get_or_404(checkpoint_id)
    new_status = request.form.get("status")
    if new_status in ("pending", "completed", "missed"):
        checkpoint.status = new_status
        db.session.commit()
        invalidate_report_cache("reports")
        invalidate_report_cache("dashboard:org")
        invalidate_report_cache("dashboard:super_admin")
        flash("Checkpoint updated", "success")
    return redirect(url_for("frontend.organization_placement_detail", candidate_id=candidate_id))


CHECKPOINT_LABELS = [
    ("Month 1", 30),
    ("Month 2", 60),
    ("Month 3", 90),
    ("Month 6", 180),
    ("Month 9", 270),
    ("Month 12", 365),
]


def _ensure_checkpoints(candidate):
    """Auto-create follow-up checkpoints for a placed candidate if none exist yet."""
    if not candidate.joining_date:
        return
    existing = FollowUpCheckpoint.query.filter_by(candidate_id=candidate.id).count()
    if existing > 0:
        return
    from datetime import timedelta
    for label, days in CHECKPOINT_LABELS:
        checkpoint = FollowUpCheckpoint(
            candidate_id=candidate.id,
            label=label,
            due_date=candidate.joining_date + timedelta(days=days),
            status="pending",
        )
        db.session.add(checkpoint)
    db.session.commit()


@frontend_bp.route("/organization/tracking")
@login_required
@require_permission("tracking.view")
def organization_tracking():
    from datetime import datetime
    user = session.get("user")
    today = datetime.utcnow()

    batch_filter = request.args.get("batch_id", "").strip()
    scheme_filter = request.args.get("scheme_id", "").strip()
    training_center_filter = request.args.get("training_center", "").strip()

    candidate_query = Candidate.query.filter_by(is_deleted=False)
    if not user.get("is_super_admin"):
        candidate_query = candidate_query.filter_by(organization_id=user.get("organization_id"))

    if batch_filter:
        candidate_query = candidate_query.filter_by(batch_id=batch_filter)
    if scheme_filter:
        candidate_query = candidate_query.filter_by(scheme_id=scheme_filter)
    if training_center_filter:
        candidate_query = candidate_query.filter_by(training_center=training_center_filter)

    all_candidates = candidate_query.all()
    candidate_ids = [c.id for c in all_candidates]

    stage_counts = [
        {"title": "Training Started", "value": sum(1 for c in all_candidates if c.training_status == "training_started"), "link": url_for("frontend.organization_candidates", training_status="training_started")},
        {"title": "Training Completed", "value": sum(1 for c in all_candidates if c.training_status == "training_completed"), "link": url_for("frontend.organization_candidates", training_status="training_completed")},
        {"title": "Dropped Out", "value": sum(1 for c in all_candidates if c.training_status == "dropped_out"), "link": url_for("frontend.organization_candidates", training_status="dropped_out")},
        {"title": "Placed", "value": sum(1 for c in all_candidates if c.employer_name), "link": url_for("frontend.organization_candidates", placed="yes")},
        {"title": "Verified", "value": sum(1 for c in all_candidates if c.verification_status == "verified"), "link": url_for("frontend.organization_candidates", verification_status="verified")},
        {"title": "Pending Placement", "value": sum(1 for c in all_candidates if not c.employer_name), "link": url_for("frontend.organization_candidates", placed="no")},
        {"title": "Placement Proof Uploaded", "value": sum(1 for c in all_candidates if c.placement_proof_uploaded), "link": url_for("frontend.organization_candidates", placement_proof="yes")},
    ]

    checkpoints = []
    if candidate_ids:
        checkpoints = FollowUpCheckpoint.query.filter(
            FollowUpCheckpoint.candidate_id.in_(candidate_ids)
        ).order_by(FollowUpCheckpoint.due_date.asc()).all()

    candidate_map = {c.id: c for c in all_candidates}

    overdue, upcoming, completed = [], [], []
    for cp in checkpoints:
        candidate = candidate_map.get(cp.candidate_id)
        if not candidate:
            continue
        item = {"checkpoint": cp, "candidate": candidate}
        if cp.status == "completed":
            completed.append(item)
        elif cp.status == "pending" and cp.due_date < today:
            overdue.append(item)
        else:
            upcoming.append(item)

    batch_query = Batch.query
    scheme_query = Scheme.query
    if not user.get("is_super_admin"):
        batch_query = batch_query.filter_by(organization_id=user.get("organization_id"))
        scheme_query = scheme_query.filter_by(organization_id=user.get("organization_id"))
    batches = batch_query.order_by(Batch.name).all()
    schemes = scheme_query.order_by(Scheme.name).all()

    training_center_query = Candidate.query.filter_by(is_deleted=False)
    if not user.get("is_super_admin"):
        training_center_query = training_center_query.filter_by(organization_id=user.get("organization_id"))
    training_centers = sorted(set(
        c.training_center for c in training_center_query.all() if c.training_center
    ))

    return render_template(
        "organization/tracking/index.html",
        stage_counts=stage_counts,
        overdue=overdue,
        upcoming=upcoming,
        completed=completed,
        batches=batches,
        schemes=schemes,
        training_centers=training_centers,
        batch_filter=batch_filter,
        scheme_filter=scheme_filter,
        training_center_filter=training_center_filter,
    )


@frontend_bp.route("/organization/tracking/checkpoint/<checkpoint_id>", methods=["POST"])
@login_required
@require_permission("tracking.view")
def organization_tracking_checkpoint_update(checkpoint_id):
    checkpoint = FollowUpCheckpoint.query.get_or_404(checkpoint_id)
    new_status = request.form.get("status")
    if new_status in ("pending", "completed", "missed"):
        checkpoint.status = new_status
        db.session.commit()
        invalidate_report_cache("reports")
        invalidate_report_cache("dashboard:org")
        invalidate_report_cache("dashboard:super_admin")
        flash("Checkpoint updated", "success")
    return redirect(url_for("frontend.organization_tracking"))


@frontend_bp.route("/organization/tracking/checkpoint/<checkpoint_id>/delete", methods=["POST"])
@login_required
@require_permission("tracking.view")
def organization_tracking_checkpoint_delete(checkpoint_id):
    checkpoint = FollowUpCheckpoint.query.get_or_404(checkpoint_id)
    db.session.delete(checkpoint)
    db.session.commit()
    _log_activity("Deleted follow-up checkpoint", checkpoint.label)
    invalidate_report_cache("reports")
    invalidate_report_cache("dashboard:org")
    invalidate_report_cache("dashboard:super_admin")
    flash("Checkpoint deleted", "success")
    return redirect(url_for("frontend.organization_tracking"))


@frontend_bp.route("/reports")
@login_required
@require_permission("report.view")
def reports():
    user = session.get("user")
    data = get_reports_data(user.get("is_super_admin"), user.get("organization_id"))
    return render_template(
        "reports/index.html",
        is_super_admin=user.get("is_super_admin"),
        **data,
    )


@cached_report(key_prefix="reports")
def get_reports_data(is_super_admin, organization_id):
    query = Candidate.query.filter_by(is_deleted=False)
    if not is_super_admin:
        query = query.filter_by(organization_id=organization_id)
    all_candidates = query.all()

    total = len(all_candidates)
    placed = sum(1 for c in all_candidates if c.employer_name)
    verified = sum(1 for c in all_candidates if c.verification_status == "verified")
    training_completed = sum(1 for c in all_candidates if c.training_status == "training_completed")
    dropped_out = sum(1 for c in all_candidates if c.training_status == "dropped_out")

    placement_rate = round((placed / total * 100), 1) if total else 0
    verification_rate = round((verified / total * 100), 1) if total else 0

    training_status_breakdown = {}
    for c in all_candidates:
        key = c.training_status or "unknown"
        training_status_breakdown[key] = training_status_breakdown.get(key, 0) + 1

    sector_breakdown = {}
    for c in all_candidates:
        key = c.sector or "Unspecified"
        sector_breakdown[key] = sector_breakdown.get(key, 0) + 1

    org_breakdown = []
    if is_super_admin:
        organizations = Organization.query.filter_by(status=1).all()
        for org in organizations:
            org_candidates = [c for c in all_candidates if c.organization_id == org.id]
            org_total = len(org_candidates)
            org_placed = sum(1 for c in org_candidates if c.employer_name)
            org_breakdown.append({
                "id": org.id,
                "name": org.organization_name,
                "total": org_total,
                "placed": org_placed,
                "placement_rate": round((org_placed / org_total * 100), 1) if org_total else 0,
            })
        # Leaderboard order: highest placement rate first. Organizations with
        # zero candidates have nothing meaningful to rank on, so they always
        # sink to the bottom regardless of their (meaningless) 0% rate.
        org_breakdown.sort(key=lambda o: (o["total"] > 0, o["placement_rate"], o["total"]), reverse=True)

    # --- Batch-wise placement performance ---
    from app.models import Batch
    batch_ids_in_use = {c.batch_id for c in all_candidates if c.batch_id}
    batches_by_id = {b.id: b for b in Batch.query.filter(Batch.id.in_(batch_ids_in_use)).all()} if batch_ids_in_use else {}
    batch_breakdown = []
    for batch_id, batch in batches_by_id.items():
        batch_candidates = [c for c in all_candidates if c.batch_id == batch_id]
        batch_total = len(batch_candidates)
        batch_placed = sum(1 for c in batch_candidates if c.employer_name)
        batch_breakdown.append({
            "id": batch_id,
            "name": batch.name,
            "total": batch_total,
            "placed": batch_placed,
            "placement_rate": round((batch_placed / batch_total * 100), 1) if batch_total else 0,
        })
    batch_breakdown.sort(key=lambda b: b["placement_rate"], reverse=True)
    unassigned_batch_count = sum(1 for c in all_candidates if not c.batch_id)

    # --- Average time-to-placement (training end -> joining date) ---
    placement_durations = []
    for c in all_candidates:
        if c.training_end_date and c.joining_date and c.joining_date >= c.training_end_date:
            placement_durations.append((c.joining_date - c.training_end_date).days)
    avg_time_to_placement = round(sum(placement_durations) / len(placement_durations), 1) if placement_durations else None

    # --- Attrition / exit tracking ---
    exited_candidates = [c for c in all_candidates if c.exit_date]
    attrition_count = len(exited_candidates)
    attrition_rate = round((attrition_count / placed * 100), 1) if placed else 0
    exit_reason_breakdown = {}
    for c in exited_candidates:
        key = c.exit_reason or "Not specified"
        exit_reason_breakdown[key] = exit_reason_breakdown.get(key, 0) + 1

    # --- Sector-wise average salary ---
    def _parse_salary(raw):
        if not raw:
            return None
        cleaned = "".join(ch for ch in raw if ch.isdigit() or ch == ".")
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None

    sector_salary_totals = {}
    sector_salary_counts = {}
    for c in all_candidates:
        parsed = _parse_salary(c.salary)
        if parsed is not None:
            key = c.sector or "Unspecified"
            sector_salary_totals[key] = sector_salary_totals.get(key, 0) + parsed
            sector_salary_counts[key] = sector_salary_counts.get(key, 0) + 1
    sector_avg_salary = {
        key: round(sector_salary_totals[key] / sector_salary_counts[key])
        for key in sector_salary_totals
    }

    return {
        "total": total,
        "placed": placed,
        "verified": verified,
        "training_completed": training_completed,
        "dropped_out": dropped_out,
        "placement_rate": placement_rate,
        "verification_rate": verification_rate,
        "training_status_breakdown": training_status_breakdown,
        "sector_breakdown": sector_breakdown,
        "org_breakdown": org_breakdown,
        "batch_breakdown": batch_breakdown,
        "unassigned_batch_count": unassigned_batch_count,
        "avg_time_to_placement": avg_time_to_placement,
        "attrition_count": attrition_count,
        "attrition_rate": attrition_rate,
        "exit_reason_breakdown": exit_reason_breakdown,
        "sector_avg_salary": sector_avg_salary,
    }


@frontend_bp.route("/notifications")
@login_required
@require_permission("notification.view")
def notifications():
    user = session.get("user")
    _sync_overdue_notifications(user)

    if user.get("is_super_admin"):
        all_notifs = Notification.query.order_by(Notification.created_at.desc()).all()
    else:
        all_notifs = Notification.query.filter(
            (Notification.user_id == user.get("id"))
            | (Notification.organization_id == str(user.get("organization_id")))
        ).order_by(Notification.created_at.desc()).all()

    unread_count = sum(1 for n in all_notifs if not n.is_read)

    return render_template("notifications/index.html", notifications=all_notifs, unread_count=unread_count)


@frontend_bp.route("/notifications/<notification_id>/read", methods=["POST"])
@login_required
@require_permission("notification.view")
def notification_mark_read(notification_id):
    notif = Notification.query.get_or_404(notification_id)
    notif.is_read = True
    db.session.commit()
    return redirect(url_for("frontend.notifications"))


@frontend_bp.route("/notifications/<notification_id>/open")
@login_required
@require_permission("notification.view")
def notification_open(notification_id):
    notif = Notification.query.get_or_404(notification_id)
    if not notif.is_read:
        notif.is_read = True
        db.session.commit()

    user = session.get("user")
    if notif.organization_id:
        if user.get("is_super_admin"):
            try:
                org_id_int = int(notif.organization_id)
                return redirect(url_for("frontend.super_admin_organization_detail", organization_id=org_id_int))
            except (TypeError, ValueError):
                pass
        return redirect(url_for("frontend.organization_candidates"))

    return redirect(url_for("frontend.notifications"))


@frontend_bp.route("/notifications/mark-all-read", methods=["POST"])
@login_required
@require_permission("notification.view")
def notifications_mark_all_read():
    user = session.get("user")
    if user.get("is_super_admin"):
        query = Notification.query
    else:
        query = Notification.query.filter(
            (Notification.user_id == user.get("id"))
            | (Notification.organization_id == str(user.get("organization_id")))
        )
    query.update({"is_read": True}, synchronize_session=False)
    db.session.commit()
    flash("All notifications marked as read", "success")
    return redirect(url_for("frontend.notifications"))


@frontend_bp.route("/api/notifications/unread-count")
@login_required
def api_unread_notification_count():
    user = session.get("user")
    if user.get("is_super_admin"):
        count = Notification.query.filter_by(is_read=False).count()
    else:
        count = Notification.query.filter(
            Notification.is_read == False,
            (Notification.user_id == user.get("id"))
            | (Notification.organization_id == str(user.get("organization_id")))
        ).count()
    return {"count": count}


def _get_or_create_settings(user_id):
    settings = UserSettings.query.filter_by(user_id=user_id).first()
    if not settings:
        settings = UserSettings(user_id=user_id)
        db.session.add(settings)
        db.session.commit()
    return settings


@frontend_bp.route("/settings/profile", methods=["GET", "POST"])
@login_required
@require_permission("settings.view")
def settings_profile():
    from app.models import Role, UserRole

    session_user = session.get("user")
    db_user = User.query.get_or_404(session_user.get("id"))
    organization = Organization.query.get(db_user.organization_id) if db_user.organization_id else None
    user_settings = _get_or_create_settings(db_user.id)

    if db_user.is_super_admin:
        display_role_name = "Super Admin"
    else:
        role_row = (
            db.session.query(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .filter(UserRole.user_id == db_user.id, UserRole.is_deleted == False, Role.is_deleted == False)
            .first()
        )
        display_role_name = role_row[0] if role_row else "No role assigned"

    if request.method == "POST":
        form_type = request.form.get("form_type")

        if form_type == "profile":
            new_full_name = (request.form.get("full_name") or "").strip()
            new_email = (request.form.get("email") or "").strip().lower()

            if not new_full_name:
                flash("Full Name is required", "error")
                return redirect(url_for("frontend.settings_profile"))

            if not new_email:
                flash("Email is required", "error")
                return redirect(url_for("frontend.settings_profile"))

            if new_email != db_user.email:
                existing_email = User.query.filter(
                    User.email == new_email, User.id != db_user.id, User.is_deleted == False
                ).first()
                if existing_email:
                    flash("This email is already in use by another account", "error")
                    return redirect(url_for("frontend.settings_profile"))
                db_user.email = new_email

            db_user.full_name = new_full_name

            db.session.commit()
            session["user"]["full_name"] = db_user.full_name
            session["user"]["email"] = db_user.email
            flash("Profile updated successfully", "success")

        elif form_type == "password":
            current = request.form.get("current_password")
            new = request.form.get("new_password")
            confirm = request.form.get("confirm_password")

            if not check_password_hash(db_user.password_hash, current):
                flash("Current password is incorrect", "error")
            elif new != confirm:
                flash("New passwords do not match", "error")
            elif len(new) < 6:
                flash("New password must be at least 6 characters", "error")
            else:
                db_user.password_hash = generate_password_hash(new)
                db.session.commit()
                _log_activity("Changed password")
                flash("Password changed successfully", "success")

        elif form_type == "notifications":
            user_settings.email_notifications = request.form.get("email_notifications") == "on"
            user_settings.sms_notifications = request.form.get("sms_notifications") == "on"
            user_settings.whatsapp_notifications = request.form.get("whatsapp_notifications") == "on"
            db.session.commit()
            flash("Notification preferences updated", "success")

        return redirect(url_for("frontend.settings_profile"))

    if db_user.is_super_admin:
        activity_logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(50).all()
        recent_logins = LoginHistory.query.order_by(LoginHistory.created_at.desc()).limit(20).all()
    else:
        activity_logs = ActivityLog.query.filter_by(user_id=db_user.id).order_by(ActivityLog.created_at.desc()).limit(50).all()
        recent_logins = LoginHistory.query.filter_by(user_id=db_user.id).order_by(LoginHistory.created_at.desc()).limit(20).all()

    return render_template(
        "settings/index.html",
        db_user=db_user,
        organization=organization,
        user_settings=user_settings,
        activity_logs=activity_logs,
        recent_logins=recent_logins,
        display_role_name=display_role_name,
    )


@frontend_bp.route("/help")
@login_required
def help_page():
    return render_template("help/index.html")


@frontend_bp.route("/search")
@login_required
def search():
    user = session.get("user")
    q = request.args.get("q", "").strip()

    candidates = []
    organizations = []

    if q:
        candidate_query = Candidate.query.filter(
            Candidate.is_deleted == False,
            (Candidate.full_name.ilike(f"%{q}%"))
            | (Candidate.registration_number.ilike(f"%{q}%"))
            | (Candidate.mobile.ilike(f"%{q}%"))
            | (Candidate.email.ilike(f"%{q}%")),
        )
        if not user.get("is_super_admin"):
            candidate_query = candidate_query.filter_by(organization_id=user.get("organization_id"))
        candidates = candidate_query.limit(20).all()

        if user.get("is_super_admin"):
            organizations = Organization.query.filter(
                (Organization.organization_name.ilike(f"%{q}%"))
                | (Organization.organization_code.ilike(f"%{q}%"))
            ).limit(20).all()

    return render_template(
        "search/results.html",
        query=q,
        candidates=candidates,
        organizations=organizations,
    )


@frontend_bp.route("/api/search-suggestions")
@login_required
def api_search_suggestions():
    user = session.get("user")
    q = request.args.get("q", "").strip()

    if not q or len(q) < 2:
        return {"candidates": [], "organizations": []}

    candidate_query = Candidate.query.filter(
        Candidate.is_deleted == False,
        (Candidate.full_name.ilike(f"%{q}%"))
        | (Candidate.registration_number.ilike(f"%{q}%"))
        | (Candidate.mobile.ilike(f"%{q}%"))
        | (Candidate.email.ilike(f"%{q}%")),
    )
    if not user.get("is_super_admin"):
        candidate_query = candidate_query.filter_by(organization_id=user.get("organization_id"))
    candidates = candidate_query.limit(5).all()

    organizations = []
    if user.get("is_super_admin"):
        organizations = Organization.query.filter(
            (Organization.organization_name.ilike(f"%{q}%"))
            | (Organization.organization_code.ilike(f"%{q}%"))
        ).limit(5).all()

    return {
        "candidates": [
            {
                "id": c.id,
                "name": c.full_name,
                "subtitle": f"{c.registration_number or 'No Reg. No.'} \u2022 {c.mobile or '-'}",
                "url": url_for("frontend.organization_candidate_detail", candidate_id=c.id),
            }
            for c in candidates
        ],
        "organizations": [
            {
                "id": o.id,
                "name": o.organization_name,
                "subtitle": o.organization_code or "-",
                "url": url_for("frontend.super_admin_organization_detail", organization_id=o.id),
            }
            for o in organizations
        ],
    }