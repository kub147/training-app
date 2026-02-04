import warnings

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

import csv
import io
import json
import os
import re
import smtplib
import ssl
import zipfile
from email.message import EmailMessage
from uuid import uuid4
from datetime import datetime, timedelta, date, timezone

from dotenv import load_dotenv
import google.generativeai as genai



from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import text, inspect
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

from models import db, User, UserProfile, UserState, GeneratedPlan, Activity, Exercise, WorkoutPlan, PlanExercise, \
    ChatMessage, TrainingCheckin
from ask_coach import build_chat_prompt, build_chat_history
from config import Config

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

app = Flask(__name__)
app.config.from_object(Config)

# --- DB ---
db.init_app(app)

# --- Auth (Flask-Login) ---
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

I18N = {
    "pl": {
        "nav_panel": "Panel",
        "nav_metrics": "Metryki",
        "nav_profile": "Profil",
        "nav_plans": "Plany siłowe",
        "nav_logout": "Wyloguj",
        "header_dashboard": "📅 Panel",
        "roadmap_title": "🧭 Plan tygodnia",
        "roadmap_refresh": "⚡ Generuj / odśwież plan",
        "roadmap_past": "Ostatnie 3 dni",
        "roadmap_today": "Dziś",
        "roadmap_next": "Najbliższe 3 dni",
        "roadmap_details": "szczegóły",
        "roadmap_today_badge": "DZIŚ",
        "roadmap_activities": "aktyw.",
        "week_goals_title": "🎯 Cele tygodnia",
        "coach_note_title": "🧠 Opinia trenera",
        "calendar_done": "Wykonane",
        "calendar_planned": "Plan",
        "calendar_empty": "Brak planu",
        "calendar_discuss": "Omów z trenerem",
        "calendar_swap_warning": "Uwaga: 2 ciężkie jednostki dzień po dniu.",
        "calendar_reorder_ok": "Plan zaktualizowany",
        "calendar_reorder_err": "Nie udało się zapisać zmiany",
        "calendar_weather_loading": "Pogoda...",
        "calendar_weather_error": "Brak pogody",
        "calendar_city_prompt": "Podaj miasto do prognozy pogody (np. Warszawa):",
        "calendar_city_not_found": "Nie znaleziono miasta",
        "calendar_progress": "Realizacja tygodnia",
        "calendar_goal_missing": "Ustaw cel tygodniowy w profilu, by lepiej śledzić postęp.",
        "calendar_copy_garmin": "Kopiuj pod Garmin",
        "calendar_copied": "Skopiowano opis treningu",
        "plan_warmup": "Rozgrzewka",
        "plan_main": "Trening główny",
        "plan_cooldown": "Schłodzenie",
        "add_title": "➕ Dodaj trening / raport",
        "tab_manual": "Ręcznie",
        "tab_checkin": "Raport",
        "opt_run": "Bieganie",
        "opt_ride": "Rower",
        "opt_swim": "Pływanie",
        "opt_gym": "Siłownia",
        "opt_yoga": "Joga",
        "opt_hike": "Wędrówka",
        "opt_walk": "Spacer",
        "opt_other": "Inne",
        "label_type": "Typ",
        "label_date": "Data",
        "label_time": "Godzina startu",
        "label_duration": "Czas (min)",
        "label_distance": "Dystans (km)",
        "label_notes": "Notatka",
        "btn_add": "Dodaj",
        "label_screenshot": "Zrzut ekranu (opcjonalnie)",
        "label_screenshot_read": "Odczytaj dane ze zdjęcia",
        "label_screenshot_apply_ok": "Dane ze zrzutu wczytane. Sprawdź i zatwierdź.",
        "label_screenshot_apply_fail": "Nie udało się odczytać danych ze zrzutu.",
        "label_confirm_data": "Potwierdź dane",
        "label_avg_hr": "Średnie tętno (opcjonalnie)",
        "label_avg_pace": "Średnie tempo min/km (opcjonalnie)",
        "label_checkin_desc": "Opis (2–3 zdania)",
        "btn_speak": "🎤 Mów",
        "btn_save": "Zapisz",
        "checkin_tip": "Wskazówka: raport to najlepszy sygnał dla AI (zmęczenie, ból, samopoczucie).",
        "latest_title": "🕑 Ostatnie aktywności",
        "all_btn": "Wszystkie →",
        "no_activities": "Brak aktywności.",
        "label_training": "Trening",
        "chat_title": "🤖 Trener",
        "chat_open": "Otwórz czat z trenerem",
        "chat_close": "Zamknij czat",
        "chat_ready": "Cześć! Jestem gotowy. Jak mogę pomóc?",
        "chat_placeholder": "Wpisz pytanie...",
        "chat_err": "Błąd.",
        "speech_unsupported": "Rozpoznawanie mowy nie jest wspierane w tej przeglądarce.",
        "status_generating": "Generuję plan…",
        "status_server_error": "Błąd serwera ({code})",
        "status_empty_plan": "Brak planu w odpowiedzi",
        "status_plan_updated": "Plan zaktualizowany",
        "status_connection_error": "Błąd połączenia",
        "modal_no_reason": "Brak uzasadnienia w planie.",
        "metrics_header": "📊 Metryki",
        "metrics_range": "📊 Metryki (ostatnie {days} dni)",
        "run_label": "Bieganie",
        "swim_label": "Basen",
        "gym_label": "Siłownia",
        "ride_label": "Rower",
        "goal_title": "🎯 Postęp (prosty cel biegowy tygodnia)",
        "goal_target": "Cel:",
        "goal_done": "Wykonano:",
        "goal_done_text": "Cel osiągnięty! 🎉",
        "goal_left_text": "Zostało: {count}",
        "goal_profile_hint": "Cel ustawisz w profilu",
        "goal_per_week_label": "Cel treningów / tydzień",
        "activity_count_title": "⏱️ Aktywności (liczba)",
        "km_chart_title": "📏 Kilometry według dyscypliny",
        "km_total_label": "Łącznie",
        "discipline_label": "Dyscyplina",
        "history_title": "📜 Pełna historia treningów",
    },
    "en": {
        "nav_panel": "Dashboard",
        "nav_metrics": "Metrics",
        "nav_profile": "Profile",
        "nav_plans": "Strength Plans",
        "nav_logout": "Logout",
        "header_dashboard": "📅 Dashboard",
        "roadmap_title": "🧭 Weekly roadmap",
        "roadmap_refresh": "⚡ Generate / refresh plan",
        "roadmap_past": "Last 3 days",
        "roadmap_today": "Today",
        "roadmap_next": "Next 3 days",
        "roadmap_details": "details",
        "roadmap_today_badge": "TODAY",
        "roadmap_activities": "activities",
        "week_goals_title": "🎯 Weekly goals",
        "coach_note_title": "🧠 Coach note",
        "calendar_done": "Done",
        "calendar_planned": "Plan",
        "calendar_empty": "No plan",
        "calendar_discuss": "Discuss with coach",
        "calendar_swap_warning": "Warning: 2 hard sessions on consecutive days.",
        "calendar_reorder_ok": "Plan updated",
        "calendar_reorder_err": "Could not save changes",
        "calendar_weather_loading": "Loading weather...",
        "calendar_weather_error": "No weather",
        "calendar_city_prompt": "Provide city for weather forecast (e.g. London):",
        "calendar_city_not_found": "City not found",
        "calendar_progress": "Weekly completion",
        "calendar_goal_missing": "Set weekly goal in profile to better track progress.",
        "calendar_copy_garmin": "Copy for Garmin",
        "calendar_copied": "Workout description copied",
        "plan_warmup": "Warm-up",
        "plan_main": "Main set",
        "plan_cooldown": "Cool-down",
        "add_title": "➕ Add workout / check-in",
        "tab_manual": "Manual",
        "tab_checkin": "Check-in",
        "opt_run": "Running",
        "opt_ride": "Cycling",
        "opt_swim": "Swimming",
        "opt_gym": "Gym",
        "opt_yoga": "Yoga",
        "opt_hike": "Hike",
        "opt_walk": "Walk",
        "opt_other": "Other",
        "label_type": "Type",
        "label_date": "Date",
        "label_time": "Start time",
        "label_duration": "Duration (min)",
        "label_distance": "Distance (km)",
        "label_notes": "Notes",
        "btn_add": "Add",
        "label_screenshot": "Screenshot (optional)",
        "label_screenshot_read": "Read data from screenshot",
        "label_screenshot_apply_ok": "Screenshot data loaded. Review and confirm.",
        "label_screenshot_apply_fail": "Could not read data from screenshot.",
        "label_confirm_data": "Confirm data",
        "label_avg_hr": "Average heart rate (optional)",
        "label_avg_pace": "Average pace min/km (optional)",
        "label_checkin_desc": "Description (2–3 sentences)",
        "btn_speak": "🎤 Speak",
        "btn_save": "Save",
        "checkin_tip": "Tip: check-in is the best AI signal (fatigue, pain, wellbeing).",
        "latest_title": "🕑 Recent activities",
        "all_btn": "All →",
        "no_activities": "No activities.",
        "label_training": "Workout",
        "chat_title": "🤖 Coach",
        "chat_open": "Open coach chat",
        "chat_close": "Close chat",
        "chat_ready": "Hi! I am ready. How can I help?",
        "chat_placeholder": "Type your question...",
        "chat_err": "Error.",
        "speech_unsupported": "Speech recognition is not supported in this browser.",
        "status_generating": "Generating plan…",
        "status_server_error": "Server error ({code})",
        "status_empty_plan": "No plan in response",
        "status_plan_updated": "Plan updated",
        "status_connection_error": "Connection error",
        "modal_no_reason": "No reason provided in the plan.",
        "metrics_header": "📊 Metrics",
        "metrics_range": "📊 Metrics (last {days} days)",
        "run_label": "Running",
        "swim_label": "Swimming",
        "gym_label": "Gym",
        "ride_label": "Cycling",
        "goal_title": "🎯 Progress (simple weekly running goal)",
        "goal_target": "Target:",
        "goal_done": "Completed:",
        "goal_done_text": "Goal achieved! 🎉",
        "goal_left_text": "Remaining: {count}",
        "goal_profile_hint": "Set your target in profile",
        "goal_per_week_label": "Workout goal / week",
        "activity_count_title": "⏱️ Activities (count)",
        "km_chart_title": "📏 Distance by discipline",
        "km_total_label": "Total",
        "discipline_label": "Discipline",
        "history_title": "📜 Full training history",
    },
}


@app.context_processor
def inject_lang():
    def tx(pl: str, en: str) -> str:
        return en if session.get("lang", "pl") == "en" else pl

    def t(key: str, **kwargs) -> str:
        lang = session.get("lang", "pl")
        text = I18N.get(lang, I18N["pl"]).get(key, I18N["pl"].get(key, key))
        try:
            return text.format(**kwargs)
        except Exception:
            return text

    return {"lang": session.get("lang", "pl"), "t": t, "tx": tx}


def tr(pl: str, en: str) -> str:
    return en if session.get("lang", "pl") == "en" else pl


def _clip(value: str | None, max_len: int) -> str:
    return (value or "").strip()[:max_len]


def _password_reset_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(app.config["SECRET_KEY"])


def _build_password_reset_token(user: User) -> str:
    payload = {
        "uid": user.id,
        "ph": (user.password_hash or "")[-16:],
    }
    return _password_reset_serializer().dumps(payload, salt="password-reset")


def _verify_password_reset_token(token: str, max_age_seconds: int = 3600) -> User | None:
    try:
        data = _password_reset_serializer().loads(token, salt="password-reset", max_age=max_age_seconds)
    except (SignatureExpired, BadSignature):
        return None

    user_id = data.get("uid")
    ph_tail = data.get("ph", "")
    if not user_id:
        return None

    user = db.session.get(User, int(user_id))
    if not user:
        return None
    if (user.password_hash or "")[-16:] != ph_tail:
        return None
    return user


def _send_password_reset_email(to_email: str, reset_url: str) -> bool:
    smtp_host = os.environ.get("MAIL_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("MAIL_PORT", "587"))
    smtp_user = os.environ.get("MAIL_USER")
    smtp_password = os.environ.get("MAIL_PASSWORD")
    mail_from = os.environ.get("MAIL_FROM") or smtp_user
    use_tls = os.environ.get("MAIL_USE_TLS", "1").lower() in {"1", "true", "yes"}

    if not smtp_user or not smtp_password or not mail_from:
        app.logger.warning("Password reset mail not sent: missing MAIL_USER/MAIL_PASSWORD/MAIL_FROM.")
        return False

    subject = tr("Reset hasła - Training App", "Password reset - Training App")
    body_text = tr(
        f"""Cześć!

Otrzymaliśmy prośbę o reset hasła.
Kliknij link, aby ustawić nowe hasło (link ważny 60 minut):
{reset_url}

Jeśli to nie Ty, zignoruj tę wiadomość.""",
        f"""Hi!

We received a password reset request.
Use the link below to set a new password (valid for 60 minutes):
{reset_url}

If this wasn't you, you can ignore this email.""",
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = to_email
    msg.set_content(body_text)

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            if use_tls:
                server.starttls(context=ssl.create_default_context())
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        return True
    except Exception as exc:
        app.logger.exception("SMTP mail send failed: %s", exc)
        return False


@app.route("/favicon.ico")
def favicon():
    # Optional: place favicon at ./static/favicon.ico
    static_dir = os.path.join(app.root_path, "static")
    icon_path = os.path.join(static_dir, "favicon.ico")
    if os.path.exists(icon_path):
        from flask import send_from_directory
        return send_from_directory(static_dir, "favicon.ico")
    return ("", 204)


def ensure_schema() -> None:
    """Minimalna migracja dla SQLite bez Alembic.

    - Tworzy brakujące tabele przez create_all()
    - Dodaje brakujące kolumny przez ALTER TABLE (SQLite).

    Dzięki temu unikniesz błędów typu "no such column" po zmianach modeli.
    """
    db.create_all()

    def columns(table: str) -> set[str]:
        rows = db.session.execute(text(f"PRAGMA table_info({table});")).fetchall()
        return {r[1] for r in rows}  # name

    def add_column(table: str, coldef: str) -> None:
        db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {coldef};"))

    # users
    if 'users' in inspect(db.engine).get_table_names():
        cols = columns('users')
        wanted = {
            'first_name': "first_name TEXT",
            'last_name': "last_name TEXT",
            'preferred_lang': "preferred_lang TEXT DEFAULT 'pl'",
            'created_at': "created_at DATETIME",
            'onboarding_completed': "onboarding_completed BOOLEAN DEFAULT 0",
        }
        for name, coldef in wanted.items():
            if name not in cols:
                add_column('users', coldef)

    # user_profiles
    if 'user_profiles' in inspect(db.engine).get_table_names():
        cols = columns('user_profiles')
        wanted = {
            'primary_sports': "primary_sports TEXT",
            'weekly_time_hours': "weekly_time_hours REAL",
            'weekly_distance_km': "weekly_distance_km REAL",
            'days_per_week': "days_per_week INTEGER",
            'weekly_goal_workouts': "weekly_goal_workouts INTEGER",
            'coach_style': "coach_style TEXT",
            'risk_tolerance': "risk_tolerance TEXT",
            'training_priority': "training_priority TEXT",
            'target_time_text': "target_time_text TEXT",
            'experience_text': "experience_text TEXT",
            'goals_text': "goals_text TEXT",
            'target_event': "target_event TEXT",
            'target_date': "target_date DATE",
            'preferences_text': "preferences_text TEXT",
            'constraints_text': "constraints_text TEXT",
            'updated_at': "updated_at DATETIME",
        }
        for name, coldef in wanted.items():
            if name not in cols:
                add_column('user_profiles', coldef)

    # generated_plans
    if 'generated_plans' in [r[0] for r in
                             db.session.execute(text("SELECT name FROM sqlite_master WHERE type='table';")).fetchall()]:
        cols = columns('generated_plans')
        wanted = {
            'created_at': "created_at DATETIME",
            'start_date': "start_date DATE",
            'horizon_days': "horizon_days INTEGER",
            'html_content': "html_content TEXT",
            'is_active': "is_active BOOLEAN",
        }
        for name, coldef in wanted.items():
            if name not in cols:
                add_column('generated_plans', coldef)


# Uruchom minimalną migrację przy starcie aplikacji (również na PythonAnywhere)
with app.app_context():
    ensure_schema()


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# --- AI ---
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
VISION_MODEL = os.environ.get("VISION_MODEL", os.environ.get("CHECKIN_MODEL", "gemini-2.5-flash-lite"))
CHAT_MODEL = os.environ.get("CHAT_MODEL", "gemini-2.5-flash")
PLAN_MODEL = os.environ.get("PLAN_MODEL", "gemini-2.5-flash")
vision_model = genai.GenerativeModel(VISION_MODEL)
chat_model = genai.GenerativeModel(CHAT_MODEL)
plan_model = genai.GenerativeModel(PLAN_MODEL)

# -------------------- DASHBOARD HELPERS --------------------

SPORT_STYLES = {
    "run": {"icon": "🏃", "color": "var(--color-run)"},
    "ride": {"icon": "🚴", "color": "var(--color-ride)"},
    "swim": {"icon": "🏊", "color": "var(--color-swim)"},
    "weighttraining": {"icon": "🏋️", "color": "var(--color-gym)"},
    "workout": {"icon": "🏋️", "color": "var(--color-gym)"},
    "yoga": {"icon": "🧘", "color": "var(--color-yoga)"},
    "hike": {"icon": "⛰️", "color": "var(--color-hike)"},
    "walk": {"icon": "🚶", "color": "var(--color-walk)"},
    "rowing": {"icon": "🚣", "color": "var(--color-row)"},
    "tennis": {"icon": "🎾", "color": "var(--color-tennis)"},
    "soccer": {"icon": "⚽", "color": "var(--color-soccer)"},
    "basketball": {"icon": "🏀", "color": "var(--color-basketball)"},
    "ski": {"icon": "🎿", "color": "var(--color-ski)"},
    "climb": {"icon": "🧗", "color": "var(--color-climb)"},
    "other": {"icon": "🏅", "color": "var(--color-default)"},
}

ACTIVITY_LABELS = {
    "pl": {
        "run": "Bieganie",
        "ride": "Rower",
        "swim": "Pływanie",
        "weighttraining": "Siłownia",
        "workout": "Trening",
        "yoga": "Joga",
        "hike": "Wędrówka",
        "walk": "Spacer",
        "other": "Inne",
    },
    "en": {
        "run": "Running",
        "ride": "Cycling",
        "swim": "Swimming",
        "weighttraining": "Gym",
        "workout": "Workout",
        "yoga": "Yoga",
        "hike": "Hike",
        "walk": "Walk",
        "other": "Other",
    },
}

WEEKDAYS_FULL = {
    "pl": ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
}

WEEKDAYS_SHORT = {
    "pl": ["pon", "wt", "śr", "czw", "pt", "sob", "nd"],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
}

MONTHS_FULL = {
    "pl": ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia", "września", "października", "listopada", "grudnia"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
}


def activity_label(activity_type: str | None) -> str:
    label_key = (activity_type or "").lower()
    lang = session.get("lang", "pl")
    labels = ACTIVITY_LABELS.get(lang, ACTIVITY_LABELS["pl"])
    fallback = "Other" if lang == "en" else "Inne"
    return labels.get(label_key, label_key or fallback)


app.jinja_env.globals["activity_label"] = activity_label


def format_dt(value: datetime | date | None, style: str = "list") -> str:
    if not value:
        return ""
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, datetime.min.time())

    lang = session.get("lang", "pl")
    if lang not in ("pl", "en"):
        lang = "pl"

    weekday = WEEKDAYS_FULL[lang][value.weekday()]
    if style == "long":
        month = MONTHS_FULL[lang][value.month - 1]
        return f"{weekday}, {value.day:02d} {month} {value.year}"
    return f"{value.day:02d}.{value.month:02d}.{value.year} ({weekday})"


app.jinja_env.globals["format_dt"] = format_dt


def classify_sport(text: str) -> str:
    t = (text or "").lower()
    # uwaga: to są heurystyki — lepsze mapowanie zrobimy później na podstawie activity_type z planu JSON
    if any(k in t for k in ["interwa", "tempo", "bieg", "easy run", "long run", "run "]):
        return "run"
    if any(k in t for k in ["rower", "ride", "kolar", "bike"]):
        return "ride"
    if any(k in t for k in ["pływ", "basen", "swim"]):
        return "swim"
    if any(k in t for k in ["siłown", "strength", "core", "gym", "weights", "workout"]):
        return "weighttraining"
    if any(k in t for k in ["joga", "yoga", "mobility", "stretch"]):
        return "yoga"
    if any(k in t for k in ["hike", "trek", "góry", "szlak"]):
        return "hike"
    if any(k in t for k in ["spacer", "walk"]):
        return "walk"
    if "tenis" in t or "tennis" in t:
        return "tennis"
    if any(k in t for k in ["piłka", "football", "soccer"]):
        return "soccer"
    if any(k in t for k in ["basket", "kosz"]):
        return "basketball"
    if any(k in t for k in ["ski", "narty"]):
        return "ski"
    if any(k in t for k in ["climb", "wspin"]):
        return "climb"
    return "other"


def normalize_activity_bucket(activity_type: str | None, notes: str | None = None) -> str:
    t = (activity_type or "").lower()
    n = (notes or "").lower()
    if t in {"run", "trailrun", "virtualrun"}:
        return "run"
    if t in {"ride", "virtualride"}:
        return "ride"
    if t in {"swim"}:
        return "swim"
    if t in {"yoga"}:
        return "mobility"
    if t in {"weighttraining", "workout", "strengthtraining", "gym"}:
        if any(k in n for k in ["mobility", "stabilizacja", "core", "rozciągan", "stretch", "rehab", "bioder", "stability"]):
            return "mobility"
        return "gym"
    return "other"


def _activity_start_dt(activity: Activity) -> datetime | None:
    dt = getattr(activity, "start_time", None)
    if isinstance(dt, datetime):
        return dt
    if isinstance(dt, str):
        try:
            return datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def _to_naive_utc(dt: datetime | None) -> datetime | None:
    if not dt:
        return None
    if getattr(dt, "tzinfo", None) is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _load_user_activities_with_fallback(
    *,
    user_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
    order_asc: bool = True,
    limit: int | None = None,
) -> list[Activity]:
    q = Activity.query.filter(Activity.user_id == user_id)
    if start is not None:
        q = q.filter(Activity.start_time >= start)
    if end is not None:
        q = q.filter(Activity.start_time < end)
    q = q.order_by(Activity.start_time.asc() if order_asc else Activity.start_time.desc())
    if limit:
        q = q.limit(limit)
    rows = q.all()
    if rows:
        return rows

    # Fallback for mixed datetime formats in SQLite (naive/aware/string).
    if start is None and end is None:
        return rows

    base_q = Activity.query.filter(Activity.user_id == user_id).order_by(Activity.start_time.asc() if order_asc else Activity.start_time.desc())
    base_rows = base_q.all()
    if not base_rows:
        return []

    start_n = _to_naive_utc(start)
    end_n = _to_naive_utc(end)
    filtered: list[Activity] = []
    for a in base_rows:
        dt = _to_naive_utc(_activity_start_dt(a))
        if not dt:
            continue
        if start_n and dt < start_n:
            continue
        if end_n and dt >= end_n:
            continue
        filtered.append(a)
        if limit and len(filtered) >= limit:
            break
    return filtered


def _extract_estimates_from_text(text: str | None) -> tuple[float | None, int | None]:
    raw = (text or "").lower()

    dist_match = re.search(r'(\d+(?:[.,]\d+)?)\s*km', raw)
    dist_km = None
    if dist_match:
        try:
            dist_km = float(dist_match.group(1).replace(",", "."))
        except Exception:
            dist_km = None

    dur_min = None
    hour_match = re.search(r'(\d+)\s*h(?:\s*(\d{1,2})\s*min)?', raw)
    min_match = re.search(r'(\d+)\s*min', raw)
    try:
        if hour_match:
            hours = int(hour_match.group(1))
            mins = int(hour_match.group(2) or 0)
            dur_min = hours * 60 + mins
        elif min_match:
            dur_min = int(min_match.group(1))
    except Exception:
        dur_min = None

    return dist_km, dur_min


def _split_details_sections(details: str | None) -> tuple[str | None, str | None, str | None]:
    txt = (details or "").strip()
    if not txt:
        return None, None, None

    def _part(pattern: str) -> str | None:
        m = re.search(pattern, txt, re.IGNORECASE | re.DOTALL)
        if not m:
            return None
        val = " ".join((m.group(1) or "").strip().split())
        return val or None

    warm = _part(
        r'(?:rozgrzewka|warm[\s-]?up)\s*[:\-]\s*(.+?)(?=(?:\n|\r|$)\s*(?:trening\s*główny|cz[eę][śs][ćc]\s*gł[óo]wna|main(?:\s*set)?|sch[łl]odzenie|cool[\s-]?down)\s*[:\-]|$)'
    )
    main = _part(
        r'(?:trening\s*główny|cz[eę][śs][ćc]\s*gł[óo]wna|main(?:\s*set)?)\s*[:\-]\s*(.+?)(?=(?:\n|\r|$)\s*(?:sch[łl]odzenie|cool[\s-]?down)\s*[:\-]|$)'
    )
    cool = _part(r'(?:sch[łl]odzenie|cool[\s-]?down)\s*[:\-]\s*(.+)$')
    return warm, main, cool


def parse_plan_html(html_content: str) -> list[dict]:
    """Parsuje zapis planu na listę dni.

    Obsługuje:
    - nowy format JSON (preferred)
    - legacy HTML (<b>YYYY-MM-DD</b> + Trening/Dlaczego)
    """
    if not html_content:
        return []

    # Preferred: JSON
    try:
        parsed = json.loads(html_content)
        if isinstance(parsed, dict) and isinstance(parsed.get("days"), list):
            items = parsed["days"]
        elif isinstance(parsed, list):
            items = parsed
        else:
            items = None
        if items is not None:
            out = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                date_str = (item.get("date") or "").strip() or None
                workout = (item.get("workout") or "").strip() or None
                why = (item.get("why") or "").strip() or None
                details = (item.get("details") or "").strip() or None
                intensity = (item.get("intensity") or "").strip() or None
                phase = (item.get("phase") or "").strip() or None
                goal_link = (item.get("goal_link") or "").strip() or None
                warmup = (item.get("warmup") or "").strip() or None
                main_set = (item.get("main_set") or item.get("main") or "").strip() or None
                cooldown = (item.get("cooldown") or "").strip() or None
                if details and (not warmup or not main_set or not cooldown):
                    sw, sm, sc = _split_details_sections(details)
                    warmup = warmup or sw
                    main_set = main_set or sm
                    cooldown = cooldown or sc
                sport = (item.get("activity_type") or item.get("sport") or "").strip().lower()
                sport = sport if sport else classify_sport((workout or "") + " " + (why or ""))
                source_facts = item.get("source_facts") or []
                dist_km = item.get("distance_km")
                dur_min = item.get("duration_min")
                parsed_dist, parsed_dur = _extract_estimates_from_text(workout)
                try:
                    dist_km = float(dist_km) if dist_km is not None else parsed_dist
                except Exception:
                    dist_km = parsed_dist
                try:
                    dur_min = int(round(float(dur_min))) if dur_min is not None else parsed_dur
                except Exception:
                    dur_min = parsed_dur
                out.append({
                    "date": date_str,
                    "workout": workout,
                    "why": why,
                    "sport": sport,
                    "details": details,
                    "intensity": intensity,
                    "phase": phase,
                    "goal_link": goal_link,
                    "warmup": warmup,
                    "main_set": main_set,
                    "cooldown": cooldown,
                    "distance_km": dist_km,
                    "duration_min": dur_min,
                    "source_facts": source_facts if isinstance(source_facts, list) else [],
                    "html": json.dumps(item, ensure_ascii=False),
                })
            if out:
                return out
    except Exception:
        pass

    # Normalizuj <br> na \n i usuń tagi HTML
    norm = html_content.replace("<br/>", "\n").replace("<br />", "\n").replace("<br>", "\n")
    text = re.sub(r'<[^>]+>', '', norm)
    text = re.sub(r'\s+', ' ', text).strip()

    # Podziel po datach (YYYY-MM-DD)
    date_pattern = r'(\d{4}-\d{2}-\d{2})'
    date_matches = list(re.finditer(date_pattern, text))

    if not date_matches:
        # Fallback: jeden blok bez daty
        sport = classify_sport(text)
        dist_km, dur_min = _extract_estimates_from_text(text)
        return [{
            "date": None,
            "workout": text[:200] if text else None,
            "why": None,
            "sport": sport,
            "details": None,
            "intensity": None,
            "phase": None,
            "goal_link": None,
            "warmup": None,
            "main_set": None,
            "cooldown": None,
            "distance_km": dist_km,
            "duration_min": dur_min,
            "source_facts": [],
            "html": html_content,
        }]

    blocks = []
    for idx_m, m in enumerate(date_matches):
        start = m.start()
        end = date_matches[idx_m + 1].start() if idx_m + 1 < len(date_matches) else len(text)
        chunk = text[start:end].strip()
        date_str = m.group(1)

        # Wyciągnij "Trening:" i "Dlaczego:"
        workout = None
        why = None

        # Szukaj po "Trening:"
        m_work = re.search(r'Trening\s*[:]\s*(.+?)(?=Dlaczego|$)', chunk, re.IGNORECASE | re.DOTALL)
        if m_work:
            workout = m_work.group(1).strip()
            workout = workout.replace("**", "").replace("DATA:", "").strip()
            # Ogranicz do jednej linii/300 znaków
            workout = ' '.join(workout.split())[:300]

        # Szukaj po "Dlaczego:"
        m_why = re.search(r'Dlaczego\s*[:]\s*(.+)', chunk, re.IGNORECASE | re.DOTALL)
        if m_why:
            why = m_why.group(1).strip()
            why = why.replace("**", "").replace("DATA:", "").strip()
            why = ' '.join(why.split())[:300]

        sport = classify_sport(chunk)
        dist_km, dur_min = _extract_estimates_from_text(workout or chunk)

        blocks.append({
            "date": date_str,
            "workout": workout,
            "why": why,
            "sport": sport,
            "details": None,
            "intensity": None,
            "phase": None,
            "goal_link": None,
            "warmup": None,
            "main_set": None,
            "cooldown": None,
            "distance_km": dist_km,
            "duration_min": dur_min,
            "source_facts": [],
            "html": chunk,  # Możesz zwrócić clean text zamiast HTML
        })

    return blocks


def compute_profile_defaults_from_history(user_id: int) -> None:
    """Wypełnia część profilu liczbami wyliczonymi z historii (ZIP), jeżeli user tego nie podał."""
    profile = UserProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.session.add(profile)
        db.session.commit()

    # weź ostatnie 12 tygodni
    cutoff = datetime.now() - timedelta(days=84)
    acts = (
        Activity.query
        .filter(Activity.user_id == user_id, Activity.start_time >= cutoff)
        .all()
    )
    if not acts:
        return

    # top sporty
    counts = {}
    for a in acts:
        counts[a.activity_type] = counts.get(a.activity_type, 0) + 1
    top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:4]
    top_sports = ",".join([t[0] for t in top])

    # tygodniowe agregaty: dystans (km) i czas (h) + dni aktywne
    # grupujemy po tygodniu (poniedziałek)
    buckets = {}
    for a in acts:
        start_dt = _activity_start_dt(a)
        if not start_dt:
            continue
        d = start_dt.date()
        week_start = d - timedelta(days=d.weekday())
        b = buckets.setdefault(week_start, {"dist_km": 0.0, "dur_h": 0.0, "days": set()})
        if a.distance:
            b["dist_km"] += (a.distance / 1000.0)
        if a.duration:
            b["dur_h"] += (a.duration / 3600.0)
        b["days"].add(d)

    weeks = list(buckets.values())
    if not weeks:
        return

    avg_dist = sum(w["dist_km"] for w in weeks) / len(weeks)
    avg_dur = sum(w["dur_h"] for w in weeks) / len(weeks)
    avg_days = sum(len(w["days"]) for w in weeks) / len(weeks)

    changed = False
    if profile.primary_sports in (None, "") and top_sports:
        profile.primary_sports = top_sports
        changed = True
    if profile.weekly_distance_km is None and avg_dist > 0:
        profile.weekly_distance_km = round(avg_dist, 1)
        changed = True
    if profile.weekly_time_hours is None and avg_dur > 0:
        profile.weekly_time_hours = round(avg_dur, 1)
        changed = True
    if profile.days_per_week is None and avg_days > 0:
        profile.days_per_week = int(round(avg_days))
        changed = True

    if changed:
        profile.updated_at = datetime.now(timezone.utc)
        db.session.commit()


# -------------------- ONBOARDING GUARD --------------------

@app.before_request
def enforce_onboarding():
    """Wymusza uzupełnienie ankiety przed wejściem na dashboard i inne widoki."""
    lang = request.args.get("lang")
    if lang in ("pl", "en"):
        session["lang"] = lang

    if not current_user.is_authenticated:
        return

    if session.get("lang") not in ("pl", "en"):
        session["lang"] = (getattr(current_user, "preferred_lang", None) or "pl")

    # endpoint może być None (np. statyczne pliki) — wtedy nie blokujemy
    endpoint = request.endpoint or ""

    allowed_endpoints = {
        "login",
        "register",
        "logout",
        "onboarding",
        "static",
    }

    # Dopuszczamy też requesty do API czatu/forecast, ale dopiero po onboardingu
    if endpoint.startswith("static"):
        return

    if current_user.onboarding_completed:
        return

    # jeśli użytkownik jeszcze nie przeszedł onboardingu, to poza dozwolonymi endpointami
    # przekierowujemy do /onboarding
    if endpoint not in allowed_endpoints:
        return redirect(url_for("onboarding"))


def get_weekly_aggregates(user_id: int, weeks: int = 12) -> str:
    """Agregaty tygodniowe zamiast wysyłania całej historii do AI."""
    # bierzemy okno tygodniowe (rolling): ostatnie N tygodni licząc od poniedziałku
    today = datetime.now().date()
    # poniedziałek bieżącego tygodnia
    monday = today - timedelta(days=today.weekday())
    start_date = monday - timedelta(weeks=weeks - 1)

    activities = _load_user_activities_with_fallback(
        user_id=user_id,
        start=datetime.combine(start_date, datetime.min.time()),
        order_asc=True,
    )

    # week_start (date) -> totals
    weeks_map = {}

    def week_start(d: date) -> date:
        return d - timedelta(days=d.weekday())

    for a in activities:
        start_dt = _activity_start_dt(a)
        if not start_dt:
            continue
        ws = week_start(start_dt.date())
        entry = weeks_map.setdefault(ws, {"count": 0, "duration": 0, "distance": 0.0, "by_type": {}})
        entry["count"] += 1
        entry["duration"] += int(a.duration or 0)
        entry["distance"] += float(a.distance or 0)
        t = (a.activity_type or "unknown").lower()
        bt = entry["by_type"].setdefault(t, {"count": 0, "duration": 0, "distance": 0.0})
        bt["count"] += 1
        bt["duration"] += int(a.duration or 0)
        bt["distance"] += float(a.distance or 0)

    # Uporządkuj: od najstarszego do najnowszego, ale pokaż też puste tygodnie
    lines = ["AGREGATY TYGODNIOWE (ostatnie %d tygodni):" % weeks]
    cur = start_date
    for _ in range(weeks):
        ws = cur
        entry = weeks_map.get(ws)
        if not entry:
            lines.append(f"- {ws.isoformat()} | 0 treningów")
        else:
            total_km = entry["distance"] / 1000.0
            total_h = entry["duration"] / 3600.0
            lines.append(f"- {ws.isoformat()} | {entry['count']} treningów | {total_km:.1f} km | {total_h:.1f} h")
        cur = cur + timedelta(weeks=1)
    return "\n".join(lines)


def get_recent_activity_details(user_id: int, days: int = 21, limit: int = 120) -> str:
    cutoff = datetime.now() - timedelta(days=days)
    activities = _load_user_activities_with_fallback(
        user_id=user_id,
        start=cutoff,
        order_asc=True,
        limit=limit,
    )

    if not activities:
        return "OSTATNIE TRENINGI: brak danych w tym oknie."

    out = [f"OSTATNIE TRENINGI (ostatnie {days} dni):"]
    for act in activities:
        start_dt = _activity_start_dt(act)
        if not start_dt:
            continue
        d = start_dt.strftime('%Y-%m-%d')
        t = (act.activity_type or 'unknown').lower()
        dist_km = (act.distance or 0) / 1000.0
        dur_min = int((act.duration or 0) // 60)
        hr = f" | HR {act.avg_hr}" if act.avg_hr else ""
        out.append(f"- {d} | {t} | {dist_km:.1f} km | {dur_min} min{hr}")
        if act.notes:
            out.append(f"  Notatka: {act.notes}")
    return "\n".join(out)


def get_recent_checkins_summary(user_id: int, days: int = 14, limit: int = 30) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        TrainingCheckin.query
        .filter(TrainingCheckin.user_id == user_id, TrainingCheckin.created_at >= cutoff)
        .order_by(TrainingCheckin.created_at.asc())
        .limit(limit)
        .all()
    )
    if not rows:
        return "CHECK-INY: brak ostatnich raportów."

    out = [f"CHECK-INY (ostatnie {days} dni):"]
    for r in rows:
        ts = r.created_at.strftime("%Y-%m-%d")
        note = (r.notes or "").strip()
        if len(note) > 220:
            note = note[:220] + "..."
        out.append(f"- {ts} | {note or 'brak opisu'}")
    return "\n".join(out)


def get_execution_context(user_id: int, days: int = 10) -> str:
    cutoff = datetime.now() - timedelta(days=days)
    acts = _load_user_activities_with_fallback(
        user_id=user_id,
        start=cutoff,
        order_asc=True,
    )
    if not acts:
        return "WYKONANE TRENINGI: brak danych."

    today_iso = datetime.now().strftime("%Y-%m-%d")
    counts = {"run": 0, "ride": 0, "swim": 0, "gym": 0, "mobility": 0, "other": 0}
    today_counts = {"run": 0, "ride": 0, "swim": 0, "gym": 0, "mobility": 0, "other": 0}
    lines = [f"WYKONANE TRENINGI (ostatnie {days} dni):"]

    for act in acts[-30:]:
        dt = _activity_start_dt(act)
        if not dt:
            continue
        ds = dt.strftime("%Y-%m-%d")
        b = normalize_activity_bucket(act.activity_type, act.notes)
        counts[b] = counts.get(b, 0) + 1
        if ds == today_iso:
            today_counts[b] = today_counts.get(b, 0) + 1

        dist_km = (act.distance or 0.0) / 1000.0
        dur_min = int((act.duration or 0) // 60)
        lines.append(f"- {ds} | {b} | {dist_km:.1f} km | {dur_min} min")

    lines.append(
        "PODSUMOWANIE TYPU: "
        + " | ".join([f"{k}={counts[k]}" for k in ("run", "ride", "swim", "gym", "mobility", "other")])
    )
    lines.append(
        "DZISIAJ WYKONANO: "
        + " | ".join([f"{k}={today_counts[k]}" for k in ("run", "ride", "swim", "gym", "mobility", "other")])
    )
    return "\n".join(lines)


def get_checkin_signal_snapshot(user_id: int, days: int = 14, limit: int = 30) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        TrainingCheckin.query
        .filter(TrainingCheckin.user_id == user_id, TrainingCheckin.created_at >= cutoff)
        .order_by(TrainingCheckin.created_at.asc())
        .limit(limit)
        .all()
    )
    if not rows:
        return {
            "status": "no_data",
            "window_days": days,
            "fatigue": "unknown",
            "pain": "unknown",
            "readiness": "unknown",
            "latest_notes": [],
        }

    fatigue_score = 0
    pain_score = 0
    readiness_score = 0

    fatigue_bad = ["zmęcz", "zmec", "fatigue", "tired", "brak sił", "brak sil", "wyczerp", "zajech"]
    fatigue_good = ["lekko", "śwież", "swiez", "easy", "dobrze", "dobry trening"]
    pain_bad = ["ból", "bol", "pain", "kontuz", "injury", "kolano", "achilles", "shin", "piszczel", "back pain"]
    readiness_good = ["gotow", "ready", "moc", "energia", "energ", "forma", "strong"]
    readiness_bad = ["słabo", "slabo", "zajech", "przemęcz", "przemecz", "bez energii", "masakra"]

    latest_notes = []
    for row in rows:
        note = (row.notes or "").strip()
        if not note:
            continue
        t = note.lower()
        if any(k in t for k in fatigue_bad):
            fatigue_score += 1
        if any(k in t for k in fatigue_good):
            fatigue_score -= 1
        if any(k in t for k in pain_bad):
            pain_score += 2
        if any(k in t for k in readiness_good):
            readiness_score += 1
        if any(k in t for k in readiness_bad):
            readiness_score -= 1
        latest_notes.append(note[:160])

    def _level(score: int, *, low: int = 1, high: int = 3) -> str:
        if score >= high:
            return "high"
        if score >= low:
            return "medium"
        return "low"

    if readiness_score >= 2:
        readiness = "up"
    elif readiness_score <= -2:
        readiness = "down"
    else:
        readiness = "flat"

    return {
        "status": "ok",
        "window_days": days,
        "fatigue": _level(max(0, fatigue_score)),
        "pain": _level(max(0, pain_score), low=1, high=2),
        "readiness": readiness,
        "latest_notes": latest_notes[-3:],
    }


def get_recent_weekly_volume_km(user_id: int, weeks: int = 4) -> dict:
    """Returns last/previous/average weekly distance in km for recent window."""
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    start_date = monday - timedelta(weeks=weeks - 1)

    acts = _load_user_activities_with_fallback(
        user_id=user_id,
        start=datetime.combine(start_date, datetime.min.time()),
        order_asc=True,
    )

    buckets = {}
    for a in acts:
        start_dt = _activity_start_dt(a)
        if not start_dt:
            continue
        d = start_dt.date()
        ws = d - timedelta(days=d.weekday())
        buckets[ws] = buckets.get(ws, 0.0) + float(a.distance or 0.0) / 1000.0

    ordered = []
    cur = start_date
    for _ in range(weeks):
        ordered.append(round(buckets.get(cur, 0.0), 1))
        cur += timedelta(weeks=1)

    avg = round(sum(ordered) / len(ordered), 1) if ordered else 0.0
    last_week = ordered[-1] if ordered else 0.0
    prev_week = ordered[-2] if len(ordered) > 1 else 0.0
    labels = []
    cur = start_date
    for _ in range(weeks):
        labels.append(cur.isoformat())
        cur += timedelta(weeks=1)
    return {
        "weekly_series": ordered,
        "weekly_labels": labels,
        "avg_week_km": avg,
        "last_week_km": last_week,
        "prev_week_km": prev_week,
    }


def build_goal_progress(user_id: int, profile_obj: UserProfile | None, range_days: int, stats: dict) -> dict | None:
    if not profile_obj or not profile_obj.target_date:
        return None

    today = datetime.now().date()
    days_left = (profile_obj.target_date - today).days
    vol = get_recent_weekly_volume_km(user_id=user_id, weeks=6)
    avg_week = float(vol.get("avg_week_km", 0.0) or 0.0)
    last_week = float(vol.get("last_week_km", 0.0) or 0.0)
    current_weekly = max(avg_week, last_week, 0.0)

    risk = (profile_obj.risk_tolerance or "balanced").lower()
    ramp_pct = {"conservative": 0.06, "aggressive": 0.14}.get(risk, 0.10)

    weeks_left = max(0, int(days_left // 7))
    target_weekly = float(profile_obj.weekly_distance_km or 0.0)
    if target_weekly <= 0:
        target_weekly = round(current_weekly * (1.0 + ramp_pct * min(weeks_left, 8)), 1)
    target_weekly = max(target_weekly, current_weekly)

    weekly_goal = int(profile_obj.weekly_goal_workouts or 3)
    weekly_goal = max(1, weekly_goal)
    workouts_done = int(stats.get("count", 0) or 0)
    goal_target = max(1, int(round((weekly_goal * range_days) / 7)))
    completion_pct = int(round(min(100.0, (workouts_done / max(1, goal_target)) * 100.0)))

    if days_left <= 0:
        phase = tr("po starcie", "post-race")
    elif days_left <= 14:
        phase = tr("taper", "taper")
    elif days_left <= 56:
        phase = tr("build", "build")
    else:
        phase = tr("base", "base")

    projected_4w = round(current_weekly * (1.0 + ramp_pct * min(4, weeks_left or 4)), 1)
    readiness_pct = 0
    if target_weekly > 0:
        readiness_pct = int(round(min(100.0, (current_weekly / target_weekly) * 100.0)))

    return {
        "event": profile_obj.target_event or tr("Cel", "Goal"),
        "target_date": profile_obj.target_date.isoformat(),
        "days_left": days_left,
        "phase": phase,
        "risk": risk,
        "weekly_volume_now": round(current_weekly, 1),
        "weekly_volume_target": round(target_weekly, 1),
        "weekly_volume_projected_4w": projected_4w,
        "target_time_text": profile_obj.target_time_text or "",
        "weekly_labels": vol.get("weekly_labels", []),
        "weekly_series": vol.get("weekly_series", []),
        "readiness_pct": readiness_pct,
        "completion_pct": completion_pct,
        "weekly_goal": weekly_goal,
    }


def get_training_phase_for_day(target_date: date | None, day_date: date) -> str:
    if not target_date:
        return "base"
    days_left = (target_date - day_date).days
    if days_left < 0:
        return "post-race"
    if days_left <= 14:
        return "taper"
    if days_left <= 56:
        return "build"
    return "base"


def build_goal_link_text(profile_obj: UserProfile | None, day_date: date) -> str:
    event = (profile_obj.target_event if profile_obj and profile_obj.target_event else tr("cel treningowy", "training goal"))
    if profile_obj and profile_obj.target_date:
        days_left = max(0, (profile_obj.target_date - day_date).days)
        return tr(
            f"Wspiera przygotowanie do: {event} (do startu: {days_left} dni).",
            f"Supports preparation for: {event} (days to event: {days_left}).",
        )
    return tr(
        f"Wspiera realizację celu: {event}.",
        f"Supports progress toward: {event}.",
    )


def get_profile_and_state_context(user: User) -> str:
    """Kontekst: FACTS + GOALS + STATE (czasowo wrażliwe)."""
    profile = user.profile
    lines = ["PROFIL ZAWODNIKA:"]

    if profile:
        # FACTS
        facts = []
        if profile.primary_sports:
            facts.append(f"Dyscypliny: {profile.primary_sports}")
        if profile.weekly_time_hours is not None:
            facts.append(f"Czas tygodniowo: {profile.weekly_time_hours} h")
        if profile.weekly_distance_km is not None:
            facts.append(f"Kilometry tygodniowo: {profile.weekly_distance_km} km")
        if profile.days_per_week is not None:
            facts.append(f"Dni treningowe/tydz.: {profile.days_per_week}")
        if profile.weekly_goal_workouts is not None:
            facts.append(f"Cel treningów/tydz.: {profile.weekly_goal_workouts}")
        if profile.experience_text:
            facts.append(f"Doświadczenie: {profile.experience_text}")
        lines.append("FACTS: " + (" | ".join(facts) if facts else "brak"))

        # GOALS
        goals = []
        if profile.goals_text:
            goals.append(profile.goals_text)
        if profile.target_event:
            goals.append(f"Wydarzenie docelowe: {profile.target_event}")
        if profile.target_date:
            goals.append(f"Data: {profile.target_date.isoformat()}")
        lines.append("GOALS: " + (" | ".join(goals) if goals else "brak"))

        if profile.preferences_text:
            lines.append(f"PREFERENCJE: {profile.preferences_text}")
        if profile.constraints_text:
            lines.append(f"OGRANICZENIA: {profile.constraints_text}")
        if profile.coach_style:
            lines.append(f"STYL TRENERA: {profile.coach_style}")
        if profile.risk_tolerance:
            lines.append(f"TOLERANCJA RYZYKA: {profile.risk_tolerance}")
        if profile.training_priority:
            lines.append(f"PRIORYTET: {profile.training_priority}")
        if profile.target_time_text:
            lines.append(f"CZAS DOCELOWY: {profile.target_time_text}")

        if profile.updated_at:
            lines.append(f"(Profil zaktualizowany: {profile.updated_at.date().isoformat()})")
    else:
        lines.append("Brak profilu (użytkownik nie ukończył onboardingu).")

    # STATE (time-sensitive)
    active_states = (
        UserState.query
        .filter(UserState.user_id == user.id, UserState.is_active == True)
        .order_by(UserState.updated_at.desc())
        .all()
    )

    def is_expired(st: UserState) -> bool:
        # Używamy datetime.now(timezone.utc) i usuwamy informację o strefie (replace),
        # aby uzyskać "naive UTC" zgodne z tym, co zwracała stara metoda utcnow().
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

        exp = st.expires_at
        if not exp:
            return False

        # Jeżeli data z bazy ma jednak tzinfo, normalizujemy ją do naive UTC.
        if getattr(exp, "tzinfo", None) is not None:
            exp = exp.astimezone(timezone.utc).replace(tzinfo=None)

        return exp < now_utc

    changed = False
    active_lines = []
    for st in active_states:
        if is_expired(st):
            st.is_active = False
            changed = True
            continue
        active_lines.append(
            f"- {st.kind}: {st.summary}"
            + (f" | severity={st.severity}" if st.severity is not None else "")
        )

    if changed:
        db.session.commit()

    if active_lines:
        lines.append("STATE:\n" + "\n".join(active_lines))
    else:
        lines.append("STATE: brak aktywnych wpisów.")

    return "\n".join(lines)


def set_or_refresh_injury_state(user_id: int, injuries_text: str) -> None:
    """Prosty mechanizm: jeżeli użytkownik poda kontuzje/urazy, traktuj to jako STATE z wygaśnięciem."""
    injuries_text = (injuries_text or "").strip()
    if not injuries_text:
        return

    now = datetime.now(timezone.utc)
    # 21 dni ważności bez aktualizacji
    expires = now + timedelta(days=21)

    existing = (
        UserState.query
        .filter_by(user_id=user_id, kind="injury", is_active=True)
        .order_by(UserState.updated_at.desc())
        .first()
    )

    if existing:
        existing.summary = injuries_text[:200]
        existing.details = injuries_text
        existing.updated_at = now
        existing.expires_at = expires
    else:
        st = UserState(
            user_id=user_id,
            kind="injury",
            summary=injuries_text[:200],
            details=injuries_text,
            severity=3,
            started_at=now,
            updated_at=now,
            expires_at=expires,
            is_active=True,
        )
        db.session.add(st)


def clear_active_injury_states(user_id: int) -> None:
    rows = (
        UserState.query
        .filter_by(user_id=user_id, kind="injury", is_active=True)
        .all()
    )
    now = datetime.now(timezone.utc)
    for row in rows:
        row.is_active = False
        row.updated_at = now
        row.expires_at = now


def get_current_injury_text(user_id: int) -> str:
    state = (
        UserState.query
        .filter_by(user_id=user_id, kind="injury", is_active=True)
        .order_by(UserState.updated_at.desc())
        .first()
    )
    if not state:
        return ""

    exp = state.expires_at
    if exp:
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        exp_cmp = exp.astimezone(timezone.utc).replace(tzinfo=None) if getattr(exp, "tzinfo", None) else exp
        if exp_cmp < now_utc:
            state.is_active = False
            db.session.commit()
            return ""

    return (state.details or state.summary or "").strip()


def import_strava_zip_for_user(zip_file, user_id: int) -> tuple[int, int]:
    """Importuje activities.csv z archiwum Stravy dla wskazanego usera.

    Zwraca: (added_count, skipped_count)
    """
    with zipfile.ZipFile(zip_file) as z:
        csv_filename = None
        for name in z.namelist():
            if name.endswith("activities.csv"):
                csv_filename = name
                break

        if not csv_filename:
            raise ValueError("Nie znaleziono pliku activities.csv w archiwum")

        with z.open(csv_filename) as f:
            csv_content = io.TextIOWrapper(f, encoding="utf-8")
            reader = csv.DictReader(csv_content)

            added_count = 0
            skipped_count = 0

            for row in reader:
                date_str = row.get("Activity Date", "")
                start_time_obj = None

                formats = [
                    "%b %d, %Y, %I:%M:%S %p",  # np. Apr 30, 2025, 7:59:42 PM
                    "%Y-%m-%d %H:%M:%S",
                ]

                for fmt in formats:
                    try:
                        start_time_obj = datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        continue

                if not start_time_obj:
                    continue

                existing = Activity.query.filter_by(user_id=user_id, start_time=start_time_obj).first()
                if existing:
                    skipped_count += 1
                    continue

                def clean_float(val):
                    if not val or val == "" or val == "nan":
                        return 0.0
                    return float(str(val).replace(",", ""))

                dist = clean_float(row.get("Distance", "0"))
                elapsed = clean_float(row.get("Elapsed Time", "0"))
                if dist < 500 and elapsed > 300:
                    dist = dist * 1000

                moving = clean_float(row.get("Moving Time", "0"))
                if moving == 0:
                    moving = elapsed

                avg_hr_val = row.get("Average Heart Rate", None)
                if avg_hr_val in [None, "", "nan"]:
                    avg_hr = None
                else:
                    avg_hr = int(float(avg_hr_val))

                desc = row.get("Activity Description", "")
                if desc == "nan":
                    desc = ""

                new_activity = Activity(
                    user_id=user_id,
                    activity_type=(row.get("Activity Type", "") or "").lower() or "run",
                    start_time=start_time_obj,
                    duration=int(moving),
                    distance=dist,
                    avg_hr=avg_hr,
                    notes=desc,
                )

                db.session.add(new_activity)
                added_count += 1

            db.session.commit()
            return added_count, skipped_count


# -------------------- AUTH --------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        preferred_lang = (request.form.get("preferred_lang") or "pl").strip().lower()
        if preferred_lang not in ("pl", "en"):
            preferred_lang = "pl"
        session["lang"] = preferred_lang

        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        first_name = (request.form.get("first_name") or "").strip()
        last_name = (request.form.get("last_name") or "").strip()

        zip_file = request.files.get("strava_zip")

        if not email or not password:
            flash(tr("Email i hasło są wymagane.", "Email and password are required."))
            return redirect(url_for("register"))

        if not zip_file or not getattr(zip_file, "filename", ""):
            flash(tr("Dodaj plik ZIP z archiwum Stravy, żeby rozpocząć.", "Add a Strava ZIP archive file to start."))
            return redirect(url_for("register"))

        if User.query.filter_by(email=email).first():
            flash(tr("Taki email już istnieje. Zaloguj się.", "This email already exists. Please sign in."))
            return redirect(url_for("login"))

        user = User(
            email=email,
            password_hash=generate_password_hash(password),
            first_name=first_name,
            last_name=last_name,
            preferred_lang=preferred_lang,
        )
        db.session.add(user)
        db.session.commit()

        profile = UserProfile(user_id=user.id)
        db.session.add(profile)
        db.session.commit()

        login_user(user)

        # Import ZIP od razu przy rejestracji
        try:
            added, skipped = import_strava_zip_for_user(zip_file, user.id)
            compute_profile_defaults_from_history(user.id)
            flash(
                tr(
                    f"Konto utworzone. Zaimportowano {added} aktywności (pominięto {skipped} duplikatów).",
                    f"Account created. Imported {added} activities (skipped {skipped} duplicates).",
                )
            )
        except Exception as e:
            app.logger.exception("ZIP import failed during registration: %s", e)
            flash(
                tr(
                    "Konto utworzone, ale import ZIP się nie udał.",
                    "Account created, but ZIP import failed.",
                )
            )

        return redirect(url_for("onboarding"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash(tr("Nieprawidłowy email lub hasło.", "Invalid email or password."))
            return redirect(url_for("login"))

        login_user(user)
        session["lang"] = (getattr(user, "preferred_lang", None) or "pl")
        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        user = User.query.filter_by(email=email).first()

        if user:
            token = _build_password_reset_token(user)
            reset_url = url_for("reset_password", token=token, _external=True)
            _send_password_reset_email(user.email, reset_url)

        flash(
            tr(
                "Jeśli konto istnieje, wysłaliśmy link do resetu hasła.",
                "If the account exists, we sent a password reset link.",
            )
        )
        return redirect(url_for("login"))

    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    user = _verify_password_reset_token(token)
    if not user:
        flash(
            tr(
                "Link do resetu jest nieprawidłowy albo wygasł. Spróbuj ponownie.",
                "The reset link is invalid or expired. Please try again.",
            )
        )
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        password = request.form.get("password") or ""
        password2 = request.form.get("password2") or ""

        if len(password) < 8:
            flash(tr("Hasło musi mieć co najmniej 8 znaków.", "Password must be at least 8 characters long."))
            return render_template("reset_password.html", token=token)

        if password != password2:
            flash(tr("Hasła nie są takie same.", "Passwords do not match."))
            return render_template("reset_password.html", token=token)

        user.password_hash = generate_password_hash(password)
        db.session.commit()
        flash(tr("Hasło zostało zresetowane. Możesz się zalogować.", "Password has been reset. You can sign in now."))
        return redirect(url_for("login"))

    return render_template("reset_password.html", token=token)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/onboarding", methods=["GET", "POST"])
@login_required
def onboarding():
    """Po rejestracji: użytkownik musi uzupełnić profil (FACTS/GOALS) + opcjonalny STATE."""
    profile = UserProfile.query.filter_by(user_id=current_user.id).first()
    if not profile:
        profile = UserProfile(user_id=current_user.id)
        db.session.add(profile)
        db.session.commit()

    if request.method == "POST":
        def _to_float(v):
            try:
                if v is None:
                    return None
                s = str(v).strip().replace(",", ".")
                return float(s) if s else None
            except Exception:
                return None

        def _to_int(v):
            try:
                if v is None:
                    return None
                s = str(v).strip()
                return int(s) if s else None
            except Exception:
                return None

        # FACTS (bardziej otwarte)
        profile.primary_sports = _clip(request.form.get("primary_sports"), 200)
        profile.weekly_time_hours = _to_float(request.form.get("weekly_time_hours"))
        profile.weekly_distance_km = _to_float(request.form.get("weekly_distance_km"))
        profile.days_per_week = _to_int(request.form.get("days_per_week"))
        profile.weekly_goal_workouts = _to_int(request.form.get("weekly_goal_workouts"))
        profile.coach_style = _clip(request.form.get("coach_style"), 40)
        profile.risk_tolerance = _clip(request.form.get("risk_tolerance"), 40)
        profile.training_priority = _clip(request.form.get("training_priority"), 40)
        profile.target_time_text = _clip(request.form.get("target_time_text"), 80)
        profile.experience_text = _clip(request.form.get("experience_text"), 10000)

        # GOALS
        profile.goals_text = _clip(request.form.get("goals_text"), 10000)
        profile.target_event = _clip(request.form.get("target_event"), 200) or None

        target_date_str = (request.form.get("target_date") or "").strip()
        if target_date_str:
            try:
                profile.target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
            except Exception:
                profile.target_date = None

        profile.preferences_text = _clip(request.form.get("preferences_text"), 10000)
        profile.constraints_text = _clip(request.form.get("constraints_text"), 10000)

        # STATE (czasowo wrażliwe) — zapisujemy osobno z TTL
        injuries_text = (request.form.get("injuries_text") or "").strip()
        if injuries_text:
            set_or_refresh_injury_state(current_user.id, injuries_text)

        current_user.onboarding_completed = True
        try:
            db.session.commit()
        except Exception as e:
            app.logger.exception("Onboarding save failed for user %s: %s", current_user.id, e)
            db.session.rollback()
            flash(tr("Nie udało się zapisać profilu. Skróć wpisy i spróbuj ponownie.", "Could not save profile. Please shorten inputs and try again."))
            return redirect(url_for("onboarding"))

        flash(tr("Dzięki! Profil zapisany. Możesz korzystać z dashboardu.", "Thanks! Profile saved. You can now use the dashboard."))
        return redirect(url_for("index"))

    return render_template("onboarding.html", profile=profile)


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """Ekran edycji danych osobistych (po onboardingu)."""
    profile_obj = UserProfile.query.filter_by(user_id=current_user.id).first()
    if not profile_obj:
        profile_obj = UserProfile(user_id=current_user.id)
        db.session.add(profile_obj)
        db.session.commit()

    if request.method == "POST":
        action = request.form.get("action") or "save"

        if action == "reimport_zip":
            zip_file = request.files.get("strava_zip")
            if not zip_file or not getattr(zip_file, "filename", ""):
                flash(tr("Wybierz plik ZIP do importu.", "Choose a ZIP file to import."))
                return redirect(url_for("profile"))
            try:
                added, skipped = import_strava_zip_for_user(zip_file, current_user.id)
                flash(
                    tr(
                        f"Zaimportowano {added} aktywności (pominięto {skipped} duplikatów).",
                        f"Imported {added} activities (skipped {skipped} duplicates).",
                    )
                )
            except Exception as e:
                app.logger.exception("ZIP reimport failed for user %s: %s", current_user.id, e)
                flash(tr("Import nieudany.", "Import failed."))
            return redirect(url_for("profile"))

        try:
            # save
            def _to_float(v):
                try:
                    if v is None:
                        return None
                    s = str(v).strip().replace(",", ".")
                    return float(s) if s else None
                except Exception:
                    return None

            def _to_int(v):
                try:
                    if v is None:
                        return None
                    s = str(v).strip()
                    return int(s) if s else None
                except Exception:
                    return None

            profile_obj.primary_sports = _clip(request.form.get("primary_sports"), 200)
            profile_obj.weekly_time_hours = _to_float(request.form.get("weekly_time_hours"))
            profile_obj.weekly_distance_km = _to_float(request.form.get("weekly_distance_km"))
            profile_obj.days_per_week = _to_int(request.form.get("days_per_week"))
            profile_obj.weekly_goal_workouts = _to_int(request.form.get("weekly_goal_workouts"))
            profile_obj.coach_style = _clip(request.form.get("coach_style"), 40)
            profile_obj.risk_tolerance = _clip(request.form.get("risk_tolerance"), 40)
            profile_obj.training_priority = _clip(request.form.get("training_priority"), 40)
            profile_obj.target_time_text = _clip(request.form.get("target_time_text"), 80)
            profile_obj.experience_text = _clip(request.form.get("experience_text"), 10000)

            profile_obj.goals_text = _clip(request.form.get("goals_text"), 10000)
            profile_obj.target_event = _clip(request.form.get("target_event"), 200) or None

            target_date_str = (request.form.get("target_date") or "").strip()
            if target_date_str:
                try:
                    profile_obj.target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
                except Exception:
                    profile_obj.target_date = None

            profile_obj.preferences_text = _clip(request.form.get("preferences_text"), 10000)
            profile_obj.constraints_text = _clip(request.form.get("constraints_text"), 10000)

            injuries_text = (request.form.get("injuries_text") or "").strip()
            if injuries_text:
                set_or_refresh_injury_state(current_user.id, injuries_text)
            else:
                clear_active_injury_states(current_user.id)

            db.session.commit()
        except Exception as e:
            app.logger.exception("Profile save failed for user %s: %s", current_user.id, e)
            db.session.rollback()
            flash(tr("Nie udało się zapisać profilu. Skróć wpisy i spróbuj ponownie.", "Could not save profile. Please shorten inputs and try again."))
            return redirect(url_for("profile"))

        flash(tr("Zapisano zmiany w profilu.", "Profile changes saved."))
        return redirect(url_for("profile"))

    try:
        return render_template("profile.html", profile=profile_obj, current_injury_text=get_current_injury_text(current_user.id))
    except Exception as e:
        app.logger.exception("Profile render failed for user %s: %s", current_user.id, e)
        return (
            tr(
                "Błąd renderowania profilu. Sprawdź logi serwera.",
                "Profile render error. Check server logs.",
            ),
            500,
        )


# -------------------- APP --------------------

def compute_stats(user_id: int, range_days: int) -> dict:
    cutoff = datetime.now() - timedelta(days=range_days)
    start_date = datetime.now().date() - timedelta(days=range_days - 1)

    acts = _load_user_activities_with_fallback(
        user_id=user_id,
        start=cutoff,
        order_asc=True,
    )

    # Dynamiczne kategorie (Strava ma wiele typów). Mapujemy najczęstsze + reszta do "other".
    def bucket(activity_type: str | None) -> str:
        t = (activity_type or "unknown").lower()
        if t in {"run", "trailrun", "virtualrun"}:
            return "run"
        if t in {"ride", "virtualride"}:
            return "ride"
        if t in {"swim"}:
            return "swim"
        if t in {"weighttraining", "workout", "strengthtraining", "gym"}:
            return "gym"
        return "other"

    buckets = {
        "run": {"count": 0, "distance": 0.0, "duration": 0},
        "ride": {"count": 0, "distance": 0.0, "duration": 0},
        "swim": {"count": 0, "distance": 0.0, "duration": 0},
        "gym": {"count": 0, "distance": 0.0, "duration": 0},
        "other": {"count": 0, "distance": 0.0, "duration": 0},
    }

    totals = {"count": 0, "distance": 0.0, "duration": 0}
    daily_bucket = {}
    daily_duration_bucket = {}

    for a in acts:
        b = bucket(a.activity_type)
        buckets[b]["count"] += 1
        buckets[b]["distance"] += float(a.distance or 0)
        buckets[b]["duration"] += int(a.duration or 0)

        totals["count"] += 1
        totals["distance"] += float(a.distance or 0)
        totals["duration"] += int(a.duration or 0)

        start_dt = _activity_start_dt(a)
        if start_dt:
            day_key = start_dt.date().isoformat()
            day_entry = daily_bucket.setdefault(day_key, {"run": 0.0, "ride": 0.0, "swim": 0.0, "gym": 0.0, "other": 0.0})
            day_entry[b] += float(a.distance or 0.0) / 1000.0
            dur_entry = daily_duration_bucket.setdefault(day_key, {"run": 0, "ride": 0, "swim": 0, "gym": 0, "other": 0})
            dur_entry[b] += int(a.duration or 0)

    daily_labels = []
    daily_km_by_sport = {"run": [], "ride": [], "swim": [], "gym": [], "other": [], "total": []}
    daily_hours_by_sport = {"run": [], "ride": [], "swim": [], "gym": [], "other": [], "total": []}
    cur = start_date
    for _ in range(range_days):
        key = cur.isoformat()
        daily_labels.append(key)
        row = daily_bucket.get(key, {})
        row_dur = daily_duration_bucket.get(key, {})
        total_km = 0.0
        total_h = 0.0
        for sport_key in ("run", "ride", "swim", "gym", "other"):
            v = round(float(row.get(sport_key, 0.0)), 2)
            daily_km_by_sport[sport_key].append(v)
            total_km += v
            h = round(float(row_dur.get(sport_key, 0)) / 3600.0, 2)
            daily_hours_by_sport[sport_key].append(h)
            total_h += h
        daily_km_by_sport["total"].append(round(total_km, 2))
        daily_hours_by_sport["total"].append(round(total_h, 2))
        cur = cur + timedelta(days=1)

    # POPRAWKA: Dodaj bezpośrednie klucze dla szablonu
    stats = {
        "today": datetime.now().strftime("%Y-%m-%d"),
        "range_days": range_days,
        "count": totals["count"],
        "distance_km": round(totals["distance"] / 1000.0, 1),
        "hours": round(totals["duration"] / 3600.0, 1),

        # Dodaj bezpośrednie wartości dla każdej kategorii
        "run_count": buckets["run"]["count"],
        "run_dist": round(buckets["run"]["distance"] / 1000.0, 1),
        "run_hours": round(buckets["run"]["duration"] / 3600.0, 1),

        "swim_count": buckets["swim"]["count"],
        "swim_dist": round(buckets["swim"]["distance"] / 1000.0, 1),
        "swim_hours": round(buckets["swim"]["duration"] / 3600.0, 1),

        "gym_count": buckets["gym"]["count"],
        "gym_dist": round(buckets["gym"]["distance"] / 1000.0, 1),
        "gym_hours": round(buckets["gym"]["duration"] / 3600.0, 1),

        "ride_count": buckets["ride"]["count"],
        "ride_dist": round(buckets["ride"]["distance"] / 1000.0, 1),
        "ride_hours": round(buckets["ride"]["duration"] / 3600.0, 1),

        # Zachowaj też buckets dla kompatybilności
        "buckets": {
            k: {
                "count": v["count"],
                "distance_km": round(v["distance"] / 1000.0, 1),
                "hours": round(v["duration"] / 3600.0, 1),
            }
            for k, v in buckets.items()
        },
        "daily_labels": daily_labels,
        "daily_km_by_sport": daily_km_by_sport,
        "daily_hours_by_sport": daily_hours_by_sport,
    }
    return stats


@app.route("/")
@login_required
def index():
    recent_activities = (
        Activity.query
        .filter_by(user_id=current_user.id)
        .order_by(Activity.start_time.desc())
        .limit(10)
        .all()
    )

    active_plan = (
        GeneratedPlan.query
        .filter_by(user_id=current_user.id, is_active=True)
        .order_by(GeneratedPlan.created_at.desc())
        .first()
    )

    plan_days = parse_plan_html(active_plan.html_content) if active_plan else []
    today = datetime.now().date()
    today_str = today.isoformat()
    week_start = today - timedelta(days=today.weekday())
    week_dates = [week_start + timedelta(days=i) for i in range(7)]
    week_end = week_start + timedelta(days=6)

    week_acts = _load_user_activities_with_fallback(
        user_id=current_user.id,
        start=datetime.combine(week_start, datetime.min.time()),
        end=datetime.combine(week_end + timedelta(days=1), datetime.min.time()),
        order_asc=True,
    )

    day_done = {
        d.isoformat(): {
            "count": 0,
            "dist_km": 0.0,
            "dur_min": 0,
            "hr_sum": 0,
            "hr_count": 0,
            "sport_counts": {},
            "activities": [],
        }
        for d in week_dates
    }

    def _normalize_sport(activity_type: str | None) -> str:
        t = (activity_type or "").lower()
        if t in SPORT_STYLES:
            return t
        return classify_sport(t)

    for act in week_acts:
        start_dt = _activity_start_dt(act)
        if not start_dt:
            continue
        ds = start_dt.date().isoformat()
        if ds not in day_done:
            continue
        entry = day_done[ds]
        sport = _normalize_sport(act.activity_type)
        entry["count"] += 1
        entry["dist_km"] += float(act.distance or 0.0) / 1000.0
        entry["dur_min"] += int((act.duration or 0) / 60)
        if act.avg_hr:
            entry["hr_sum"] += int(act.avg_hr)
            entry["hr_count"] += 1
        entry["sport_counts"][sport] = entry["sport_counts"].get(sport, 0) + 1
        entry["activities"].append({
            "id": act.id,
            "sport": sport,
            "label": activity_label(act.activity_type),
            "dist_km": round(float(act.distance or 0.0) / 1000.0, 2),
            "dur_min": int((act.duration or 0) / 60),
            "avg_hr": int(act.avg_hr) if act.avg_hr else None,
            "time": start_dt.strftime("%H:%M"),
        })

    plan_map = {}
    for item in plan_days:
        d = (item.get("date") or "").strip()
        if not d:
            continue
        try:
            d_obj = datetime.strptime(d, "%Y-%m-%d").date()
        except Exception:
            continue
        if d_obj < week_start or d_obj > week_end:
            continue
        plan_map[d] = {
            "sport": _normalize_sport(item.get("sport")),
            "workout": item.get("workout") or "",
            "why": item.get("why") or "",
            "details": item.get("details") or "",
            "intensity": (item.get("intensity") or "").lower(),
            "phase": item.get("phase") or "",
            "goal_link": item.get("goal_link") or "",
            "warmup": item.get("warmup") or "",
            "main_set": item.get("main_set") or "",
            "cooldown": item.get("cooldown") or "",
            "distance_km": item.get("distance_km"),
            "duration_min": item.get("duration_min"),
            "source_facts": item.get("source_facts") or [],
        }

    lang = session.get("lang", "pl")
    weekday_short = WEEKDAYS_SHORT.get(lang, WEEKDAYS_SHORT["pl"])
    week_days = []
    for d in week_dates:
        iso = d.isoformat()
        done = day_done[iso]
        plan = plan_map.get(iso)
        dominant_sport = "other"
        if done["sport_counts"]:
            dominant_sport = max(done["sport_counts"].items(), key=lambda x: x[1])[0]
        elif plan:
            dominant_sport = plan.get("sport") or "other"

        avg_hr = int(round(done["hr_sum"] / done["hr_count"])) if done["hr_count"] else None
        if done["count"] > 0:
            card_kind = "done"
        elif plan and d >= today:
            card_kind = "planned"
        else:
            card_kind = "empty"

        week_days.append({
            "date": iso,
            "weekday_short": weekday_short[d.weekday()],
            "is_today": d == today,
            "is_past": d < today,
            "drop_allowed": (d >= today and done["count"] == 0),
            "card_kind": card_kind,
            "sport": dominant_sport,
            "done": {
                "count": done["count"],
                "dist_km": round(done["dist_km"], 2),
                "dur_min": done["dur_min"],
                "avg_hr": avg_hr,
                "activities": done["activities"],
            },
            "plan": plan,
        })

    # Weekly goals + coach note
    planned_counts = {}
    for d, plan in plan_map.items():
        if d >= today_str:
            s = plan.get("sport") or "other"
            planned_counts[s] = planned_counts.get(s, 0) + 1
    weekly_goal_items = [f"{cnt}x {activity_label(s)}" for s, cnt in sorted(planned_counts.items(), key=lambda x: (-x[1], x[0]))]

    done_total = sum(day_done[d.isoformat()]["count"] for d in week_dates if d <= today)
    profile_obj = UserProfile.query.filter_by(user_id=current_user.id).first()
    weekly_goal_target = max(1, int(profile_obj.weekly_goal_workouts or max(3, len(planned_counts) or 1))) if profile_obj else max(1, len(planned_counts) or 3)
    completion_pct = int(round(min(100.0, (done_total / max(1, weekly_goal_target)) * 100.0)))
    days_left = (week_end - today).days

    if completion_pct >= 100:
        coach_note = tr(
            "Świetna robota — cel tygodnia już domknięty. Utrzymaj jakość i regenerację.",
            "Great work — weekly goal already completed. Keep quality and recovery high.",
        )
    elif days_left <= 2 and completion_pct < 60:
        coach_note = tr(
            "Końcówka tygodnia jest napięta. Postaw na 1 kluczową jednostkę + 1 krótszy trening.",
            "Week ending is tight. Focus on 1 key session + 1 shorter workout.",
        )
    else:
        coach_note = tr(
            "Plan wygląda stabilnie. Pilnuj regularności i unikaj dwóch ciężkich dni pod rząd.",
            "Plan looks stable. Stay consistent and avoid two hard days back-to-back.",
        )

    return render_template(
        "index.html",
        activities=recent_activities,
        active_plan=active_plan,
        week_days=week_days,
        weekly_goal_items=weekly_goal_items,
        weekly_goal_target=weekly_goal_target,
        weekly_done_total=done_total,
        weekly_completion_pct=completion_pct,
        coach_note=coach_note,
        today_str=today_str,
    )


@app.route("/metrics")
@login_required
def metrics():
    try:
        range_days = int(request.args.get("days", "7"))
    except Exception:
        range_days = 7
    if range_days not in (7, 30, 90, 365):
        range_days = 7

    stats = compute_stats(current_user.id, range_days)
    profile_obj = UserProfile.query.filter_by(user_id=current_user.id).first()
    weekly_goal = (profile_obj.weekly_goal_workouts if profile_obj and profile_obj.weekly_goal_workouts else 3)
    weekly_goal = max(1, int(weekly_goal))
    goal_target = max(1, int(round((weekly_goal * range_days) / 7)))

    goal_progress = build_goal_progress(
        user_id=current_user.id,
        profile_obj=profile_obj,
        range_days=range_days,
        stats=stats,
    )

    return render_template(
        "metrics.html",
        stats=stats,
        range_days=range_days,
        weekly_goal=weekly_goal,
        goal_target=goal_target,
        goal_progress=goal_progress,
    )


@app.route("/history")
@login_required
def history():
    all_activities = (
        Activity.query
        .filter_by(user_id=current_user.id)
        .order_by(Activity.start_time.desc())
        .all()
    )
    return render_template("all_activities.html", activities=all_activities)


# -------------------- AI --------------------

@app.route("/api/chat/history", methods=["GET"])
@login_required
def get_chat_history():
    messages = (
        ChatMessage.query
        .filter_by(user_id=current_user.id)
        .order_by(ChatMessage.timestamp.asc())
        .all()
    )
    messages = messages[-50:]
    history_data = [{"sender": m.sender, "content": m.content} for m in messages]
    return jsonify(history_data)


@app.route("/api/chat", methods=["POST"])
@login_required
def chat_with_coach():
    user_msg = (request.json or {}).get("message")
    if not user_msg:
        return jsonify({"response": tr("Brak wiadomości.", "Missing message.")})

    user_message_db = ChatMessage(user_id=current_user.id, sender="user", content=user_msg)
    db.session.add(user_message_db)
    db.session.commit()

    recent_messages = (
        ChatMessage.query
        .filter_by(user_id=current_user.id)
        .order_by(ChatMessage.timestamp.desc())
        .limit(20)
        .all()
    )

    chat_history_text = build_chat_history(recent_messages, max_age_days=14)

    # Kontekst warstwowy (bez zalewania całej bazy):
    profile_state = get_profile_and_state_context(current_user)
    weekly_agg = get_weekly_aggregates(user_id=current_user.id, weeks=12)
    recent_details = get_recent_activity_details(user_id=current_user.id, days=21)
    recent_checkins = get_recent_checkins_summary(user_id=current_user.id, days=14)
    execution_ctx = get_execution_context(user_id=current_user.id, days=10)
    checkin_signals = get_checkin_signal_snapshot(user_id=current_user.id, days=14)
    goal_progress = build_goal_progress(
        user_id=current_user.id,
        profile_obj=UserProfile.query.filter_by(user_id=current_user.id).first(),
        range_days=30,
        stats=compute_stats(current_user.id, 30),
    )

    today_iso = datetime.now().strftime("%Y-%m-%d")

    full_prompt = build_chat_prompt(
        today_iso=today_iso,
        profile_state=profile_state,
        weekly_agg=weekly_agg,
        recent_details=recent_details,
        recent_checkins=recent_checkins,
        execution_context=execution_ctx,
        checkin_signals=json.dumps(checkin_signals, ensure_ascii=False),
        goal_context=json.dumps(goal_progress, ensure_ascii=False) if goal_progress else "Brak aktywnego celu z datą.",
        chat_history=chat_history_text,
        user_msg=user_msg,
    )
    full_prompt += "\n\n" + tr(
        "ODPOWIADAJ WYŁĄCZNIE PO POLSKU.",
        "RESPOND ONLY IN ENGLISH.",
    )

    try:
        response = chat_model.generate_content(full_prompt)
        clean_text = (response.text or "").replace("```html", "").replace("```", "").replace("**", "")

        ai_message_db = ChatMessage(user_id=current_user.id, sender="ai", content=clean_text)
        db.session.add(ai_message_db)
        db.session.commit()

        return jsonify({"response": clean_text})
    except Exception as e:
        return jsonify({"response": tr(f"Błąd AI: {str(e)}", f"AI error: {str(e)}")})


@app.route("/api/forecast", methods=["GET"])
@login_required
def generate_forecast():
    """Generuje plan od dziś do końca tygodnia i zapisuje go jako aktywny."""
    profile_obj = UserProfile.query.filter_by(user_id=current_user.id).first()
    profile_state = get_profile_and_state_context(current_user)
    weekly_agg = get_weekly_aggregates(user_id=current_user.id, weeks=12)
    recent_details = get_recent_activity_details(user_id=current_user.id, days=21)
    recent_checkins = get_recent_checkins_summary(user_id=current_user.id, days=14)
    execution_ctx = get_execution_context(user_id=current_user.id, days=10)
    checkin_signals = get_checkin_signal_snapshot(user_id=current_user.id, days=14)
    goal_progress = build_goal_progress(
        user_id=current_user.id,
        profile_obj=profile_obj,
        range_days=30,
        stats=compute_stats(current_user.id, 30),
    )

    today_dt = datetime.now().date()
    today = today_dt.strftime("%Y-%m-%d")
    days_to_generate = max(1, 7 - today_dt.weekday())  # do niedzieli włącznie

    language_hint = tr(
        "Opis i uzasadnienie pisz po polsku.",
        "Write workout description and rationale in English.",
    )

    def _apply_plan_rules(days: list[dict]) -> list[dict]:
        """Rule layer: avoid obvious overload and improve consistency."""
        risk = (profile_obj.risk_tolerance or "balanced").lower() if profile_obj else "balanced"
        ramp_pct = {"conservative": 0.06, "aggressive": 0.14}.get(risk, 0.10)
        vol = get_recent_weekly_volume_km(user_id=current_user.id, weeks=4)
        base_week_km = max(float(vol.get("avg_week_km", 0.0) or 0.0), float(vol.get("last_week_km", 0.0) or 0.0))
        if profile_obj and profile_obj.weekly_distance_km:
            base_week_km = max(base_week_km, float(profile_obj.weekly_distance_km))
        allowed_week_km = max(6.0, round(base_week_km * (1.0 + ramp_pct), 1))
        allowed_window_km = round((allowed_week_km * float(days_to_generate)) / 7.0, 1)

        def parse_km(workout: str | None) -> float:
            txt = (workout or "").lower()
            vals = re.findall(r'(\d+(?:[.,]\d+)?)\s*km', txt)
            out = 0.0
            for raw in vals:
                try:
                    out += float(raw.replace(",", "."))
                except Exception:
                    continue
            return out

        def scale_first_km(workout: str | None, factor: float) -> str:
            if not workout:
                return ""
            def repl(match):
                raw = match.group(1)
                try:
                    val = float(raw.replace(",", "."))
                    scaled = max(2.0, round(val * factor, 1))
                    return f"{scaled} km"
                except Exception:
                    return match.group(0)
            return re.sub(r'(\d+(?:[.,]\d+)?)\s*km', repl, workout, count=1, flags=re.IGNORECASE)

        def is_hard(item: dict) -> bool:
            txt = " ".join([
                str(item.get("intensity") or ""),
                str(item.get("workout") or ""),
                str(item.get("why") or ""),
            ]).lower()
            hard_tokens = ["hard", "wysoka", "interwa", "interwał", "tempo", "threshold", "vo2", "maks", "max"]
            return any(t in txt for t in hard_tokens)

        out = []
        hard_count = 0
        for idx, day in enumerate(days):
            item = dict(day)
            km = parse_km(item.get("workout"))
            item["_km"] = km

            if idx > 0 and is_hard(out[-1]) and is_hard(item):
                # Soften consecutive hard session by changing intensity and adding rationale.
                item["intensity"] = "easy"
                why = (item.get("why") or "").strip()
                why += " " + tr(
                    "Skorygowano automatycznie: unikamy dwóch ciężkich jednostek dzień po dniu.",
                    "Auto-adjusted: avoid two hard sessions on consecutive days.",
                )
                item["why"] = why.strip()
            if is_hard(item):
                hard_count += 1
            out.append(item)

        # If event is close, keep max one hard day in a 4-day block.
        if profile_obj and profile_obj.target_date:
            days_left = (profile_obj.target_date - datetime.now().date()).days
            if days_left <= 14 and hard_count > 1:
                kept_hard = 0
                for item in out:
                    if is_hard(item):
                        kept_hard += 1
                        if kept_hard > 1:
                            item["intensity"] = "easy"
                            item["why"] = ((item.get("why") or "").strip() + " " + tr(
                                "Taper: zmniejszona intensywność przed startem.",
                                "Taper: lowered intensity before race day.",
                            )).strip()

        # Keep 4-day km load near safe ramp based on recent weeks.
        total_plan_km = sum(float(x.get("_km", 0.0) or 0.0) for x in out)
        if total_plan_km > 0 and total_plan_km > allowed_window_km:
            factor = max(0.55, allowed_window_km / total_plan_km)
            for item in out:
                item["workout"] = scale_first_km(item.get("workout"), factor)
                item["why"] = ((item.get("why") or "").strip() + " " + tr(
                    f"Dopasowano obciążenie (limit okna: {allowed_window_km} km).",
                    f"Load adjusted (window cap: {allowed_window_km} km).",
                )).strip()

        for item in out:
            item.pop("_km", None)
        return out

    prompt = f"""
Jesteś trenerem sportowym. Stwórz plan treningowy od dziś do końca tygodnia ({days_to_generate} dni, start: {today}).

WAŻNE:
- Uwzględnij ograniczenia i dostępność z PROFILU.
- Jeżeli STATE wskazuje aktywny uraz/ograniczenia — plan ma być konserwatywny.
- Uwzględnij WYKONANE TRENINGI: nie dubluj jednostek już wykonanych, chyba że to celowe.
- Jeśli dziś wykonano już siłę/mobility, jutro preferuj inną modalność (np. bieg easy / regeneracja), chyba że cel wymaga inaczej.

{profile_state}

{weekly_agg}

{recent_details}

{recent_checkins}

{execution_ctx}

SYGNAŁY CHECK-IN:
{json.dumps(checkin_signals, ensure_ascii=False)}

KONTEKST CELU:
{json.dumps(goal_progress, ensure_ascii=False) if goal_progress else "Brak aktywnego celu z datą."}

FORMAT (BARDZO WAŻNE):
- Zwróć WYŁĄCZNIE JSON (bez markdown, bez komentarzy) w formie:
  {{
    "days": [
      {{
        "date": "YYYY-MM-DD",
        "activity_type": "run|ride|swim|weighttraining|yoga|walk|other",
        "workout": "konkretna jednostka z czasem/dystansem",
        "details": "dokładny opis: rozgrzewka, część główna, schłodzenie",
        "warmup": "krótko: czas + tempo/tętno + dystans jeśli dotyczy",
        "main_set": "krótko: główna część treningu z parametrami",
        "cooldown": "krótko: schłodzenie z czasem/zakresem",
        "distance_km": number|null,
        "duration_min": number|null,
        "intensity": "easy|moderate|hard",
        "phase": "base|build|taper|post-race",
        "goal_link": "jedno zdanie jak ten trening wspiera cel użytkownika",
        "why": "krótkie uzasadnienie",
        "source_facts": ["3 krótkie fakty użyte do decyzji"]
      }}
    ]
  }}
- Dokładnie {days_to_generate} dni.
- {language_hint}
- Każdy dzień MUSI mieć: warmup, main_set, cooldown (bez pustych pól).
"""

    try:
        response = plan_model.generate_content(prompt)
        raw = (response.text or "").replace("```json", "").replace("```", "").strip()
        try:
            plan_json = json.loads(raw)
        except Exception:
            return jsonify({"plan": tr("Nie udało się wygenerować planu.", "Could not generate plan.")})

        days = []
        if isinstance(plan_json, dict) and isinstance(plan_json.get("days"), list):
            days = [d for d in plan_json["days"] if isinstance(d, dict)]
        if len(days) < 1:
            return jsonify({"plan": tr("Nie udało się wygenerować planu.", "Could not generate plan.")})

        days = _apply_plan_rules(days)[:days_to_generate]
        # Normalizuj daty do kolejnych dni od dziś, żeby kalendarz miał stabilny układ.
        for idx, item in enumerate(days):
            day_date = (datetime.now() + timedelta(days=idx)).date()
            item["date"] = day_date.strftime("%Y-%m-%d")
            if not item.get("phase"):
                item["phase"] = get_training_phase_for_day(
                    profile_obj.target_date if profile_obj else None,
                    day_date,
                )
            if not item.get("goal_link"):
                item["goal_link"] = build_goal_link_text(profile_obj, day_date)
            warmup = (item.get("warmup") or "").strip()
            main_set = (item.get("main_set") or "").strip()
            cooldown = (item.get("cooldown") or "").strip()
            details = (item.get("details") or "").strip()
            if details and (not warmup or not main_set or not cooldown):
                sw, sm, sc = _split_details_sections(details)
                warmup = warmup or (sw or "")
                main_set = main_set or (sm or "")
                cooldown = cooldown or (sc or "")
            item["warmup"] = warmup
            item["main_set"] = main_set
            item["cooldown"] = cooldown
            if not details:
                parts = []
                if warmup:
                    parts.append(f"{tr('Rozgrzewka', 'Warm-up')}: {warmup}")
                if main_set:
                    parts.append(f"{tr('Trening główny', 'Main set')}: {main_set}")
                if cooldown:
                    parts.append(f"{tr('Schłodzenie', 'Cool-down')}: {cooldown}")
                item["details"] = "\n".join(parts)
        text = json.dumps({"days": days}, ensure_ascii=False)

        # Zapisz jako aktywny plan (wyłącz poprzedni)
        GeneratedPlan.query.filter_by(user_id=current_user.id, is_active=True).update({"is_active": False})
        plan = GeneratedPlan(
            user_id=current_user.id,
            created_at=datetime.now(timezone.utc),
            start_date=datetime.now(timezone.utc).date(),
            horizon_days=days_to_generate,
            html_content=text,
            is_active=True,
        )
        db.session.add(plan)
        db.session.commit()

        return jsonify({"plan": text})
    except Exception:
        return jsonify({"plan": tr("Nie udało się wygenerować planu.", "Could not generate plan.")})


@app.route("/api/plan/move", methods=["POST"])
@login_required
def move_plan_day():
    payload = request.json or {}
    from_date = (payload.get("from_date") or "").strip()
    to_date = (payload.get("to_date") or "").strip()
    if not from_date or not to_date:
        return jsonify({"ok": False, "error": tr("Brak dat do zmiany.", "Missing dates.")}), 400

    active_plan = (
        GeneratedPlan.query
        .filter_by(user_id=current_user.id, is_active=True)
        .order_by(GeneratedPlan.created_at.desc())
        .first()
    )
    if not active_plan:
        return jsonify({"ok": False, "error": tr("Brak aktywnego planu.", "No active plan.")}), 404

    try:
        parsed = json.loads(active_plan.html_content or "{}")
    except Exception:
        return jsonify({"ok": False, "error": tr("Plan ma niepoprawny format.", "Plan has invalid format.")}), 400

    days = []
    if isinstance(parsed, dict) and isinstance(parsed.get("days"), list):
        days = [d for d in parsed["days"] if isinstance(d, dict)]
    if not days:
        return jsonify({"ok": False, "error": tr("Brak dni do modyfikacji.", "No days to move.")}), 400

    src_idx = next((i for i, d in enumerate(days) if (d.get("date") or "") == from_date), None)
    dst_idx = next((i for i, d in enumerate(days) if (d.get("date") or "") == to_date), None)
    if src_idx is None:
        return jsonify({"ok": False, "error": tr("Nie znaleziono dnia źródłowego.", "Source day not found.")}), 404

    if dst_idx is None:
        days[src_idx]["date"] = to_date
    else:
        days[src_idx]["date"], days[dst_idx]["date"] = days[dst_idx].get("date"), days[src_idx].get("date")

    try:
        days.sort(key=lambda d: d.get("date") or "")
    except Exception:
        pass

    active_plan.html_content = json.dumps({"days": days}, ensure_ascii=False)
    db.session.commit()
    return jsonify({"ok": True, "days": days})



def _guess_mime(path: str) -> str:
    ext = (os.path.splitext(path)[1] or "").lower()
    if ext in [".jpg", ".jpeg"]:
        return "image/jpeg"
    if ext in [".png"]:
        return "image/png"
    if ext in [".webp"]:
        return "image/webp"
    return "application/octet-stream"


def parse_strava_screenshot_to_activity_detailed(image_path: str) -> tuple[dict, str | None]:
    """Próbuje wyciągnąć zrzutu Stravy: typ, dystans, czas, tętno, data/godzina.

    Returns:
      (data, None) on success
      ({}, error_message) on failure
    """
    try:
        with open(image_path, "rb") as f:
            img_bytes = f.read()

        prompt = """
Masz zrzut ekranu aktywności ze Stravy (lub podobnej aplikacji).
Wyciągnij z niego dane i zwróć WYŁĄCZNIE JSON (bez markdown, bez komentarzy) w formacie:

{
  "activity_type": "run|ride|swim|workout|weighttraining|yoga|hike|walk|other",
  "distance_km": number|null,
  "duration_min": number|null,
  "avg_hr": number|null,
  "start_date": "YYYY-MM-DD"|null,
  "start_time": "HH:MM"|null
}

Zasady:
- distance_km ma być w kilometrach (np. 8.42)
- duration_min ma być w minutach (np. 46)
- avg_hr to średnie tętno (bpm)
- jeśli widzisz datę/godzinę rozpoczęcia, zwróć start_date i start_time
- jeśli nie widzisz wartości, daj null
        """.strip()

        resp = vision_model.generate_content([
            prompt,
            {"mime_type": _guess_mime(image_path), "data": img_bytes}
        ])

        raw = (getattr(resp, "text", None) or "").strip()
        try:
            data = json.loads(raw)
        except Exception:
            return {}, tr(
                "Model zwrócił nieczytelny format odpowiedzi (nie-JSON). Spróbuj wyraźniejszy screenshot.",
                "Model returned an unreadable response format (non-JSON). Try a clearer screenshot.",
            )

        # minimalna walidacja / normalizacja
        out = {}
        out["activity_type"] = (data.get("activity_type") or "other").strip().lower()
        try:
            out["distance_km"] = None if data.get("distance_km") is None else float(data.get("distance_km"))
        except Exception:
            out["distance_km"] = None
        try:
            out["duration_min"] = None if data.get("duration_min") is None else float(data.get("duration_min"))
        except Exception:
            out["duration_min"] = None
        try:
            out["avg_hr"] = None if data.get("avg_hr") is None else int(float(data.get("avg_hr")))
        except Exception:
            out["avg_hr"] = None
        out["start_date"] = (data.get("start_date") or "").strip() or None
        out["start_time"] = (data.get("start_time") or "").strip() or None

        has_any = (
            (out.get("distance_km") is not None and out.get("distance_km", 0) > 0)
            or (out.get("duration_min") is not None and out.get("duration_min", 0) > 0)
            or (out.get("avg_hr") is not None and out.get("avg_hr", 0) > 0)
            or (out.get("activity_type") and out.get("activity_type") != "other")
            or bool(out.get("start_date"))
            or bool(out.get("start_time"))
        )
        if not has_any:
            return {}, tr(
                "Nie udało się odczytać danych treningowych z tego screenshotu.",
                "Could not read training data from this screenshot.",
            )
        return out, None
    except Exception as e:
        msg = str(e).lower()
        if "429" in msg or "quota" in msg or "rate limit" in msg or "resource_exhausted" in msg:
            return {}, tr(
                "Limit modelu AI został chwilowo wyczerpany. Spróbuj ponownie za chwilę.",
                "AI model quota is temporarily exhausted. Please try again shortly.",
            )
        return {}, tr(
            "Błąd odczytu screenshotu (AI/API). Spróbuj ponownie za chwilę.",
            "Screenshot parsing failed (AI/API). Please try again shortly.",
        )


def parse_strava_screenshot_to_activity(image_path: str) -> dict:
    data, _err = parse_strava_screenshot_to_activity_detailed(image_path)
    return data


@app.route("/api/checkin/parse", methods=["POST"])
@login_required
def parse_checkin_screenshot():
    f = request.files.get("checkin_image")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": tr("Brak pliku obrazu.", "Missing image file.")}), 400

    os.makedirs("uploads", exist_ok=True)
    safe_name = f"parse_{current_user.id}_{int(datetime.now(timezone.utc).timestamp())}_{uuid4().hex[:8]}.png"
    image_path = os.path.join("uploads", safe_name)

    try:
        f.save(image_path)
        parsed, parse_error = parse_strava_screenshot_to_activity_detailed(image_path)
        if parse_error:
            return jsonify({"ok": False, "error": parse_error}), 422

        dist = parsed.get("distance_km")
        dur = parsed.get("duration_min")
        pace = None
        try:
            if dist and dist > 0 and dur and dur > 0:
                pace = round(float(dur) / float(dist), 2)
        except Exception:
            pace = None

        data = {
            "activity_type": parsed.get("activity_type") or "other",
            "date": parsed.get("start_date") or "",
            "time": parsed.get("start_time") or "",
            "duration_min": parsed.get("duration_min"),
            "distance_km": parsed.get("distance_km"),
            "avg_hr": parsed.get("avg_hr"),
            "avg_pace_min_km": pace,
        }
        return jsonify({"ok": True, "data": data})
    finally:
        try:
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception:
            pass

# -------------------- QUICK ADD --------------------

def _parse_date_time(date_str: str, time_str: str) -> datetime:
    date_str = (date_str or "").strip()
    time_str = (time_str or "").strip()
    try:
        if date_str and time_str:
            dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        elif date_str:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        else:
            dt = datetime.now(timezone.utc)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


def _looks_like_duplicate_activity(
    *,
    user_id: int,
    activity_type: str,
    start_time: datetime,
    duration_sec: int,
    distance_m: float,
    notes: str | None,
    window_seconds: int = 120,
) -> bool:
    """Best-effort dedupe guard for double form submit on slow mobile/web."""
    start_min = start_time - timedelta(seconds=window_seconds)
    start_max = start_time + timedelta(seconds=window_seconds)
    needle_notes = (notes or "").strip()

    q = (
        Activity.query
        .filter(
            Activity.user_id == user_id,
            Activity.activity_type == activity_type,
            Activity.start_time >= start_min,
            Activity.start_time <= start_max,
            Activity.duration == int(duration_sec or 0),
            Activity.distance == float(distance_m or 0.0),
        )
        .order_by(Activity.id.desc())
    )
    if needle_notes:
        q = q.filter(Activity.notes == needle_notes)

    return q.first() is not None

@app.route("/activity/manual", methods=["POST"])
@login_required
def add_activity_manual():
    """Szybkie dodanie treningu ręcznie lub po odczycie screenshotu."""
    act_type = (request.form.get("activity_type") or "other").strip().lower()
    date_str = (request.form.get("date") or "").strip()
    time_str = (request.form.get("time") or "").strip()
    notes = (request.form.get("notes") or "").strip()

    def _to_float(v):
        try:
            if v in (None, ""):
                return None
            return float(str(v).replace(",", "."))
        except Exception:
            return None

    duration_min = _to_float(request.form.get("duration_min"))
    distance_km = _to_float(request.form.get("distance_km"))
    avg_hr = _to_float(request.form.get("avg_hr"))
    avg_pace = _to_float(request.form.get("avg_pace_min_km"))

    # Optional screenshot: if provided, fill only missing fields from AI parse
    image_file = request.files.get("activity_image")
    if image_file and image_file.filename:
        os.makedirs("uploads", exist_ok=True)
        safe_name = f"manual_{current_user.id}_{int(datetime.now(timezone.utc).timestamp())}_{uuid4().hex[:8]}.png"
        image_path = os.path.join("uploads", safe_name)
        try:
            image_file.save(image_path)
            parsed = parse_strava_screenshot_to_activity(image_path) or {}
            act_type = act_type if act_type != "other" else (parsed.get("activity_type") or act_type)
            if not date_str and parsed.get("start_date"):
                date_str = parsed["start_date"]
            if not time_str and parsed.get("start_time"):
                time_str = parsed["start_time"]
            if duration_min is None and parsed.get("duration_min") is not None:
                duration_min = float(parsed["duration_min"])
            if distance_km is None and parsed.get("distance_km") is not None:
                distance_km = float(parsed["distance_km"])
            if avg_hr is None and parsed.get("avg_hr") is not None:
                avg_hr = float(parsed["avg_hr"])
        finally:
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
            except Exception:
                pass

    if duration_min is None and avg_pace is not None and distance_km and distance_km > 0:
        duration_min = float(avg_pace) * float(distance_km)

    duration_min = max(0.0, float(duration_min or 0.0))
    distance_km = max(0.0, float(distance_km or 0.0))
    avg_hr_int = int(round(avg_hr)) if avg_hr and avg_hr > 0 else None

    # data + godzina -> datetime aware (UTC)
    dt = _parse_date_time(date_str, time_str)

    act = Activity(
        user_id=current_user.id,
        activity_type=act_type,
        start_time=dt,
        duration=int(round(duration_min * 60)),
        distance=distance_km * 1000.0,
        avg_hr=avg_hr_int,
        notes=notes,
    )
    if _looks_like_duplicate_activity(
        user_id=current_user.id,
        activity_type=act.activity_type or "other",
        start_time=act.start_time,
        duration_sec=act.duration or 0,
        distance_m=act.distance or 0.0,
        notes=act.notes,
    ):
        flash(tr("Wykryto duplikat — trening już istnieje.", "Duplicate detected — workout already exists."))
        return redirect(url_for("index"))

    db.session.add(act)
    db.session.commit()
    flash(tr("Dodano trening.", "Workout added."))
    return redirect(url_for("index"))


@app.route("/checkin", methods=["POST"])
@login_required
def add_checkin():
    """Dodaj check-in po treningu (tekst + opcjonalny screenshot)."""
    text_note = (request.form.get("checkin_text") or "").strip()
    f = request.files.get("checkin_image")

    # Walidacja: przynajmniej jedno pole
    if not text_note and (not f or not f.filename):
        flash(tr("⚠️ Dodaj opis lub obrazek.", "⚠️ Add a description or screenshot."), "warning")
        return redirect(url_for("index"))

    # Zapisz screenshot jeśli jest
    image_path = None
    if f and f.filename:
        os.makedirs("uploads", exist_ok=True)
        safe_name = f"{current_user.id}_{int(datetime.now(timezone.utc).timestamp())}_{re.sub(r'[^a-zA-Z0-9._-]', '_', f.filename)}"
        image_path = os.path.join("uploads", safe_name)
        f.save(image_path)

    # Zapisz check-in (zawsze)
    entry = TrainingCheckin(
        user_id=current_user.id,
        created_at=datetime.now(timezone.utc),
        notes=text_note,
        image_path=image_path,
    )
    db.session.add(entry)

    # === PRÓBA UTWORZENIA ACTIVITY ===
    created_activity = False
    screenshot_failed = False
    screenshot_error_msg = None

    if image_path:
        try:
            parsed, screenshot_error_msg = parse_strava_screenshot_to_activity_detailed(image_path)
            act_type = (parsed.get("activity_type") or "").strip().lower()
            dur_min = parsed.get("duration_min")
            dist_km = parsed.get("distance_km")
            avg_hr = parsed.get("avg_hr")
            start_date = parsed.get("start_date") or ""
            start_time = parsed.get("start_time") or ""

            # Sprawdź czy AI cokolwiek wyciągnęło
            has_data = (
                (dur_min and dur_min > 0)
                or (dist_km and dist_km > 0)
                or (avg_hr and avg_hr > 0)
                or (act_type and act_type != "other")
            )

            if has_data:
                # Sukces parsowania - twórz Activity
                dt = _parse_date_time(start_date, start_time)
                prepared_type = act_type or "other"
                prepared_duration = max(0, int(round(dur_min or 0))) * 60
                prepared_distance = max(0.0, float(dist_km or 0.0)) * 1000.0
                prepared_notes = f"📸 Auto: {text_note}" if text_note else "📸 Auto-import ze screena"

                if not _looks_like_duplicate_activity(
                    user_id=current_user.id,
                    activity_type=prepared_type,
                    start_time=dt,
                    duration_sec=prepared_duration,
                    distance_m=prepared_distance,
                    notes=prepared_notes,
                ):
                    act = Activity(
                        user_id=current_user.id,
                        activity_type=prepared_type,
                        start_time=dt,
                        duration=prepared_duration,
                        distance=prepared_distance,
                        avg_hr=int(avg_hr) if avg_hr else None,
                        notes=prepared_notes,
                    )
                    db.session.add(act)
                    created_activity = True
            else:
                # AI nie wyciągnęło danych
                screenshot_failed = True

        except Exception as e:
            # Błąd parsowania (np. plik uszkodzony)
            print(f"⚠️ Błąd parsowania screenshota: {e}")
            screenshot_error_msg = tr(
                "Błąd techniczny podczas odczytu screenshotu.",
                "Technical error while parsing screenshot.",
            )
            screenshot_failed = True

    # Fallback: Utwórz Activity "other" jeśli screenshot się nie powiódł
    if not created_activity and text_note:
        fallback_dt = datetime.now(timezone.utc)
        if not _looks_like_duplicate_activity(
            user_id=current_user.id,
            activity_type="other",
            start_time=fallback_dt,
            duration_sec=0,
            distance_m=0.0,
            notes=text_note,
        ):
            act = Activity(
                user_id=current_user.id,
                activity_type="other",
                start_time=fallback_dt,
                duration=0,
                distance=0.0,
                avg_hr=None,
                notes=text_note,
            )
            db.session.add(act)
            created_activity = True

    db.session.commit()

    # === KOMUNIKATY DLA UŻYTKOWNIKA ===
    if created_activity and not screenshot_failed:
        # Sukces: Activity utworzona ze screena lub tekstu
        if image_path:
            flash(tr("✅ Check-in zapisany! Trening dodany automatycznie ze screenshota.", "✅ Check-in saved! Workout added automatically from screenshot."), "success")
        else:
            flash(tr("✅ Check-in zapisany jako trening 'other'. Uzupełnij szczegóły ręcznie.", "✅ Check-in saved as 'other' workout. Complete details manually."), "info")

    elif created_activity and screenshot_failed:
        # Częściowy sukces: Screenshot nie zadziałał, ale tekst zapisany
        flash(
            (
                tr(
                    "⚠️ Screenshot nie zawierał danych treningowych. Zapisano check-in jako trening 'other' - uzupełnij dane ręcznie.",
                    "⚠️ Screenshot did not contain workout data. Check-in was saved as 'other' workout - complete details manually.",
                )
                + (f" ({screenshot_error_msg})" if screenshot_error_msg else "")
            ),
            "warning")

    elif not created_activity:
        # Tylko check-in bez Activity (nie powinno się zdarzyć, ale zabezpieczenie)
        flash(tr("ℹ️ Check-in zapisany bez treningu. Dodaj trening ręcznie.", "ℹ️ Check-in saved without workout. Add workout manually."), "info")

    return redirect(url_for("index"))



# -------------------- ACTIVITIES --------------------

@app.route("/activity/<int:activity_id>")
@login_required
def activity_detail(activity_id: int):
    activity = Activity.query.filter_by(id=activity_id, user_id=current_user.id).first_or_404()
    plans = WorkoutPlan.query.filter_by(user_id=current_user.id).all()
    return render_template("activity.html", activity=activity, plans=plans)


@app.route("/import_zip", methods=["POST"])
@login_required
def import_zip():
    if "file" not in request.files:
        flash(tr("Nie wybrano pliku", "No file selected"))
        return redirect(url_for("index"))

    file = request.files["file"]
    if not file or file.filename == "":
        flash(tr("Nie wybrano pliku", "No file selected"))
        return redirect(url_for("index"))

    try:
        added_count, skipped_count = import_strava_zip_for_user(file, current_user.id)
        flash(
            tr(
                f"Sukces! Zaimportowano {added_count} treningów. Pominięto {skipped_count}.",
                f"Success! Imported {added_count} workouts. Skipped {skipped_count}.",
            )
        )
        try:
            compute_profile_defaults_from_history(current_user.id)
        except Exception:
            pass
    except Exception as e:
        app.logger.exception("ZIP import endpoint error for user %s: %s", current_user.id, e)
        flash(tr("Błąd pliku ZIP.", "ZIP file error."))

    return redirect(url_for("index"))


@app.route("/activity/<int:activity_id>/apply_plan", methods=["POST"])
@login_required
def apply_plan_to_activity(activity_id: int):
    activity = Activity.query.filter_by(id=activity_id, user_id=current_user.id).first_or_404()
    plan_id = request.form.get("plan_id")
    if not plan_id:
        return redirect(url_for("activity_detail", activity_id=activity_id))

    plan = WorkoutPlan.query.filter_by(id=int(plan_id), user_id=current_user.id).first_or_404()

    for template_ex in plan.exercises:
        last_entry = (
            Exercise.query
            .join(Activity)
            .filter(
                Exercise.user_id == current_user.id,
                Exercise.name == template_ex.name,
                Activity.user_id == current_user.id,
            )
            .order_by(Activity.start_time.desc())
            .first()
        )
        current_weight = last_entry.weight if last_entry else 0

        new_ex = Exercise(
            user_id=current_user.id,
            activity_id=activity.id,
            name=template_ex.name,
            sets=template_ex.default_sets,
            reps=template_ex.default_reps,
            weight=current_weight,
        )
        db.session.add(new_ex)

    db.session.commit()
    return redirect(url_for("activity_detail", activity_id=activity_id))


@app.route("/activity/<int:activity_id>/update", methods=["POST"])
@login_required
def update_activity(activity_id: int):
    activity = Activity.query.filter_by(id=activity_id, user_id=current_user.id).first_or_404()

    act_type = (request.form.get("activity_type") or activity.activity_type or "other").strip().lower()
    date_str = (request.form.get("date") or "").strip()
    time_str = (request.form.get("time") or "").strip()

    duration_min = request.form.get("duration_min")
    distance_km = request.form.get("distance_km")
    avg_hr = request.form.get("avg_hr")
    notes = request.form.get("notes")

    activity.activity_type = act_type
    activity.start_time = _parse_date_time(date_str, time_str)

    if duration_min not in (None, ""):
        activity.duration = max(0, int(float(duration_min))) * 60
    if distance_km not in (None, ""):
        activity.distance = max(0.0, float(distance_km)) * 1000.0
    if avg_hr not in (None, ""):
        activity.avg_hr = int(float(avg_hr))
    activity.notes = notes

    db.session.commit()
    flash(tr("Zapisano zmiany w treningu.", "Workout changes saved."), "success")
    return redirect(url_for("activity_detail", activity_id=activity_id))


@app.route("/activity/<int:activity_id>/delete", methods=["POST"])
@login_required
def delete_activity(activity_id: int):
    activity = Activity.query.filter_by(id=activity_id, user_id=current_user.id).first_or_404()
    db.session.delete(activity)
    db.session.commit()
    flash(tr("Usunięto trening.", "Workout deleted."), "success")
    return redirect(url_for("index"))


@app.route("/exercise/<int:exercise_id>/update", methods=["POST"])
@login_required
def update_exercise(exercise_id: int):
    ex = Exercise.query.filter_by(id=exercise_id, user_id=current_user.id).first_or_404()
    data = request.json or {}

    if "sets" in data:
        ex.sets = int(data["sets"]) if data["sets"] not in (None, "") else 0
    if "reps" in data:
        ex.reps = int(data["reps"]) if data["reps"] not in (None, "") else 0
    if "weight" in data:
        w = str(data["weight"]).replace(",", ".")
        ex.weight = float(w) if w not in ("", "None") else 0.0

    db.session.commit()
    return jsonify({"success": True})


@app.route("/exercise/<int:exercise_id>/delete", methods=["POST"])
@login_required
def delete_exercise(exercise_id: int):
    ex = Exercise.query.filter_by(id=exercise_id, user_id=current_user.id).first_or_404()
    aid = ex.activity_id
    db.session.delete(ex)
    db.session.commit()
    return redirect(url_for("activity_detail", activity_id=aid))


@app.route("/activity/<int:activity_id>/exercises", methods=["POST"])
@login_required
def add_exercise_api(activity_id: int):
    activity = Activity.query.filter_by(id=activity_id, user_id=current_user.id).first_or_404()
    data = request.json or {}

    for item in data.get("exercises", []):
        ex = Exercise(
            user_id=current_user.id,
            activity_id=activity.id,
            name=item.get("name"),
            sets=int(item.get("sets") or 0),
            reps=int(item.get("reps") or 0),
            weight=float(item.get("weight") or 0),
        )
        db.session.add(ex)

    db.session.commit()
    return jsonify({"status": "ok"})


# -------------------- PLANS --------------------

@app.route("/plans")
@login_required
def plans_list():
    plans = WorkoutPlan.query.filter_by(user_id=current_user.id).all()
    return render_template("plans.html", plans=plans)


@app.route("/plans/add", methods=["POST"])
@login_required
def add_plan():
    name = request.form.get("name")
    if name:
        new_plan = WorkoutPlan(user_id=current_user.id, name=name)
        db.session.add(new_plan)
        db.session.commit()
    return redirect(url_for("plans_list"))


@app.route("/plans/<int:plan_id>/add_exercise", methods=["POST"])
@login_required
def add_plan_exercise(plan_id: int):
    plan = WorkoutPlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()

    name = request.form.get("name")
    sets = request.form.get("sets")
    reps = request.form.get("reps")

    if name:
        ex = PlanExercise(
            user_id=current_user.id,
            plan=plan,
            name=name,
            default_sets=int(sets) if sets else 0,
            default_reps=int(reps) if reps else 0,
        )
        db.session.add(ex)
        db.session.commit()

    return redirect(url_for("plans_list"))


@app.route("/plans/<int:plan_id>/delete", methods=["POST"])
@login_required
def delete_plan(plan_id: int):
    plan = WorkoutPlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()
    db.session.delete(plan)
    db.session.commit()
    return redirect(url_for("plans_list"))


@app.route("/plans/exercise/<int:exercise_id>/delete", methods=["POST"])
@login_required
def delete_plan_exercise(exercise_id: int):
    ex = PlanExercise.query.filter_by(id=exercise_id, user_id=current_user.id).first_or_404()
    db.session.delete(ex)
    db.session.commit()
    return redirect(url_for("plans_list"))


if __name__ == "__main__":
    with app.app_context():
        ensure_schema()
    app.run(host="0.0.0.0", port=5001, debug=True)
