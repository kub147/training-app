import warnings

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

import csv
import io
import json
import os
import re
import zipfile
from datetime import datetime, timedelta, date, timezone

from dotenv import load_dotenv
import google.generativeai as genai



from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import text, inspect

from models import db, User, UserProfile, UserState, GeneratedPlan, Activity, Exercise, WorkoutPlan, PlanExercise, \
    ChatMessage, TrainingCheckin
from ask_coach import build_chat_prompt, build_chat_history
from config import Config

load_dotenv()

app = Flask(__name__)
app.config.from_object(Config)

# --- DB ---
db.init_app(app)

# --- Auth (Flask-Login) ---
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


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
model = genai.GenerativeModel("gemini-2.5-flash")

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


def parse_plan_html(html_content: str) -> list[dict]:
    """Parsuje HTML planu na listę dni - ULEPSZONA WERSJA."""
    if not html_content:
        return []

    # Usuń nadmiarowe tagi <b> i </b> które psują formatowanie
    html_content = html_content.replace('</b>', '').strip()

    # Normalizuj <br> na \n
    norm = html_content.replace("<br/>", "\n").replace("<br />", "\n").replace("<br>", "\n")

    # Usuń wszystkie tagi HTML oprócz <b>
    text = re.sub(r'<(?!b|/b)[^>]+>', '', norm)
    text = re.sub(r'<b>', '\n**DATA**: ', text)
    text = re.sub(r'\s+', ' ', text).strip()

    # Podziel po datach (YYYY-MM-DD)
    date_pattern = r'(\d{4}-\d{2}-\d{2})'
    date_matches = list(re.finditer(date_pattern, text))

    if not date_matches:
        # Fallback: jeden blok bez daty
        sport = classify_sport(text)
        return [{
            "date": None,
            "workout": text[:200] if text else None,
            "why": None,
            "sport": sport,
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
            # Ogranicz do jednej linii/300 znaków
            workout = ' '.join(workout.split())[:300]

        # Szukaj po "Dlaczego:"
        m_why = re.search(r'Dlaczego\s*[:]\s*(.+)', chunk, re.IGNORECASE | re.DOTALL)
        if m_why:
            why = m_why.group(1).strip()
            why = ' '.join(why.split())[:300]

        sport = classify_sport(chunk)

        blocks.append({
            "date": date_str,
            "workout": workout,
            "why": why,
            "sport": sport,
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
        d = a.start_time.date()
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
    if not current_user.is_authenticated:
        return

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


def get_user_profile_text(user: User) -> str:
    """Buduje tekst profilu do promptu na podstawie danych użytkownika i ankiety."""
    profile = UserProfile.query.filter_by(user_id=user.id).first()

    parts = []
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    if name:
        parts.append(f"Imię i nazwisko: {name}")
    parts.append(f"Email: {user.email}")

    if profile:
        if profile.about:
            parts.append(f"O mnie: {profile.about}")
        if profile.goal:
            parts.append(f"Cel: {profile.goal}")
        if profile.target_date:
            parts.append(f"Data docelowa: {profile.target_date.isoformat()}")
        if profile.primary_sport:
            parts.append(f"Główna dyscyplina: {profile.primary_sport}")
        if profile.weekly_distance_km is not None:
            parts.append(f"Deklarowany kilometraż/tydzień: {profile.weekly_distance_km} km")
        if profile.days_per_week is not None:
            parts.append(f"Dostępne dni treningowe/tydzień: {profile.days_per_week}")
        if profile.experience_years is not None:
            parts.append(f"Staż treningowy: {profile.experience_years} lat")
        if profile.injuries:
            parts.append(f"Kontuzje/ograniczenia: {profile.injuries}")
        if profile.preferences:
            parts.append(f"Preferencje: {profile.preferences}")
        if profile.answers_json:
            parts.append(f"Dodatkowe informacje (JSON): {profile.answers_json}")

    return "\n".join([p for p in parts if p])


def get_data_from_db(user_id: int, days: int = 30) -> str:
    """Pobiera dane użytkownika z bazy i formatuje do tekstu dla AI."""
    cutoff_date = datetime.now() - timedelta(days=days)

    activities = (
        Activity.query
        .filter(Activity.user_id == user_id, Activity.start_time >= cutoff_date)
        .order_by(Activity.start_time.asc())
        .all()
    )

    if not activities:
        return "Brak treningów w tym okresie."

    data_text = "HISTORIA TRENINGÓW:\n"
    for act in activities:
        if not act.start_time:
            continue

        date_str = act.start_time.strftime("%Y-%m-%d")
        hr_info = f" | Śr. HR: {act.avg_hr} bpm" if act.avg_hr else ""

        dist_km = (act.distance or 0) / 1000
        dur_min = int((act.duration or 0) // 60)
        data_text += f"- {date_str} | {act.activity_type} | {dist_km:.1f}km | {dur_min}min{hr_info}\n"

        if act.notes:
            data_text += f"  Notatka: {act.notes}\n"

        if act.exercises:
            cwiczenia_str = ", ".join(
                [f"{e.name} ({e.sets}x{e.reps}, {e.weight}kg)" for e in act.exercises]
            )
            data_text += f"  Siłownia: {cwiczenia_str}\n"

    return data_text


def get_weekly_aggregates(user_id: int, weeks: int = 12) -> str:
    """Agregaty tygodniowe zamiast wysyłania całej historii do AI."""
    # bierzemy okno tygodniowe (rolling): ostatnie N tygodni licząc od poniedziałku
    today = datetime.now().date()
    # poniedziałek bieżącego tygodnia
    monday = today - timedelta(days=today.weekday())
    start_date = monday - timedelta(weeks=weeks - 1)

    activities = (
        Activity.query
        .filter(Activity.user_id == user_id, Activity.start_time >= datetime.combine(start_date, datetime.min.time()))
        .order_by(Activity.start_time.asc())
        .all()
    )

    # week_start (date) -> totals
    weeks_map = {}

    def week_start(d: date) -> date:
        return d - timedelta(days=d.weekday())

    for a in activities:
        if not a.start_time:
            continue
        ws = week_start(a.start_time.date())
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
    activities = (
        Activity.query
        .filter(Activity.user_id == user_id, Activity.start_time >= cutoff)
        .order_by(Activity.start_time.asc())
        .limit(limit)
        .all()
    )

    if not activities:
        return "OSTATNIE TRENINGI: brak danych w tym oknie."

    out = [f"OSTATNIE TRENINGI (ostatnie {days} dni):"]
    for act in activities:
        if not act.start_time:
            continue
        d = act.start_time.strftime('%Y-%m-%d')
        t = (act.activity_type or 'unknown').lower()
        dist_km = (act.distance or 0) / 1000.0
        dur_min = int((act.duration or 0) // 60)
        hr = f" | HR {act.avg_hr}" if act.avg_hr else ""
        out.append(f"- {d} | {t} | {dist_km:.1f} km | {dur_min} min{hr}")
        if act.notes:
            out.append(f"  Notatka: {act.notes}")
    return "\n".join(out)


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
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        first_name = (request.form.get("first_name") or "").strip()
        last_name = (request.form.get("last_name") or "").strip()

        zip_file = request.files.get("strava_zip")

        if not email or not password:
            flash("Email i hasło są wymagane.")
            return redirect(url_for("register"))

        if not zip_file or not getattr(zip_file, "filename", ""):
            flash("Dodaj plik ZIP z archiwum Stravy, żeby rozpocząć.")
            return redirect(url_for("register"))

        if User.query.filter_by(email=email).first():
            flash("Taki email już istnieje. Zaloguj się.")
            return redirect(url_for("login"))

        user = User(
            email=email,
            password_hash=generate_password_hash(password),
            first_name=first_name,
            last_name=last_name,
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
            flash(f"Konto utworzone. Zaimportowano {added} aktywności (pominięto {skipped} duplikatów).")
        except Exception as e:
            flash(f"Konto utworzone, ale import ZIP się nie udał: {e}")

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
            flash("Nieprawidłowy email lub hasło.")
            return redirect(url_for("login"))

        login_user(user)
        return redirect(url_for("index"))

    return render_template("login.html")


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
        profile.primary_sports = (request.form.get("primary_sports") or "").strip()
        profile.weekly_time_hours = _to_float(request.form.get("weekly_time_hours"))
        profile.weekly_distance_km = _to_float(request.form.get("weekly_distance_km"))
        profile.days_per_week = _to_int(request.form.get("days_per_week"))
        profile.experience_text = (request.form.get("experience_text") or "").strip()

        # GOALS
        profile.goals_text = (request.form.get("goals_text") or "").strip()
        profile.target_event = (request.form.get("target_event") or "").strip() or None

        target_date_str = (request.form.get("target_date") or "").strip()
        if target_date_str:
            try:
                profile.target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
            except Exception:
                profile.target_date = None

        profile.preferences_text = (request.form.get("preferences_text") or "").strip()
        profile.constraints_text = (request.form.get("constraints_text") or "").strip()

        # STATE (czasowo wrażliwe) — zapisujemy osobno z TTL
        injuries_text = (request.form.get("injuries_text") or "").strip()
        if injuries_text:
            set_or_refresh_injury_state(current_user.id, injuries_text)

        current_user.onboarding_completed = True
        db.session.commit()

        flash("Dzięki! Profil zapisany. Możesz korzystać z dashboardu.")
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
                flash("Wybierz plik ZIP do importu.")
                return redirect(url_for("profile"))
            try:
                added, skipped = import_strava_zip_for_user(zip_file, current_user.id)
                flash(f"Zaimportowano {added} aktywności (pominięto {skipped} duplikatów).")
            except Exception as e:
                flash(f"Import nieudany: {e}")
            return redirect(url_for("profile"))

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

        profile_obj.primary_sports = (request.form.get("primary_sports") or "").strip()
        profile_obj.weekly_time_hours = _to_float(request.form.get("weekly_time_hours"))
        profile_obj.weekly_distance_km = _to_float(request.form.get("weekly_distance_km"))
        profile_obj.days_per_week = _to_int(request.form.get("days_per_week"))
        profile_obj.experience_text = (request.form.get("experience_text") or "").strip()

        profile_obj.goals_text = (request.form.get("goals_text") or "").strip()
        profile_obj.target_event = (request.form.get("target_event") or "").strip() or None

        target_date_str = (request.form.get("target_date") or "").strip()
        if target_date_str:
            try:
                profile_obj.target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
            except Exception:
                profile_obj.target_date = None

        profile_obj.preferences_text = (request.form.get("preferences_text") or "").strip()
        profile_obj.constraints_text = (request.form.get("constraints_text") or "").strip()

        injuries_text = (request.form.get("injuries_text") or "").strip()
        if injuries_text:
            set_or_refresh_injury_state(current_user.id, injuries_text)

        db.session.commit()
        flash("Zapisano zmiany w profilu.")
        return redirect(url_for("profile"))

    return render_template("profile.html", profile=profile_obj)


# -------------------- APP --------------------

@app.route("/")
@login_required
def index():
    # Zakres stats: rolling window (7/30/90) przez query param
    try:
        range_days = int(request.args.get("days", "7"))
    except Exception:
        range_days = 7
    if range_days not in (7, 30, 90, 365):
        range_days = 7

    cutoff = datetime.now() - timedelta(days=range_days)

    acts = (
        Activity.query
        .filter(Activity.user_id == current_user.id, Activity.start_time >= cutoff)
        .all()
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

    buckets = {"run": {"count": 0, "distance": 0.0, "duration": 0},
               "ride": {"count": 0, "distance": 0.0, "duration": 0},
               "swim": {"count": 0, "distance": 0.0, "duration": 0},
               "gym": {"count": 0, "distance": 0.0, "duration": 0},
               "other": {"count": 0, "distance": 0.0, "duration": 0}}

    totals = {"count": 0, "distance": 0.0, "duration": 0}

    for a in acts:
        b = bucket(a.activity_type)
        buckets[b]["count"] += 1
        buckets[b]["distance"] += float(a.distance or 0)
        buckets[b]["duration"] += int(a.duration or 0)

        totals["count"] += 1
        totals["distance"] += float(a.distance or 0)
        totals["duration"] += int(a.duration or 0)

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
        }
    }

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
    today_str = datetime.now().strftime("%Y-%m-%d")
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    plan_today = next((d for d in plan_days if d.get("date") == today_str), None)
    plan_tomorrow = next((d for d in plan_days if d.get("date") == tomorrow_str), None)

    # Future: kolejne 3 dni od dziś (włącznie), jeśli są w planie
    future_days = []
    for offset in range(0, 3):
        d = (datetime.now() + timedelta(days=offset)).strftime("%Y-%m-%d")
        item = next((x for x in plan_days if x.get("date") == d), None)
        if item:
            future_days.append(item)

    # Past roadmap: 7 dni wstecz (agregujemy per dzień po top aktywności)
    past_cutoff = datetime.now() - timedelta(days=7)
    past_acts = (
        Activity.query
        .filter(Activity.user_id == current_user.id, Activity.start_time >= past_cutoff)
        .order_by(Activity.start_time.desc())
        .all()
    )
    day_bucket = {}
    for a in past_acts:
        ds = a.start_time.strftime("%Y-%m-%d")
        b = day_bucket.setdefault(ds, {"date": ds, "sport": a.activity_type, "count": 0, "dist_km": 0.0, "dur_min": 0})
        b["count"] += 1
        if a.distance:
            b["dist_km"] += a.distance / 1000.0
        if a.duration:
            b["dur_min"] += int(a.duration / 60)
        # sport: weź dominujący (najpierw zmapuj)
        b["sport"] = b["sport"] or a.activity_type

    past_days = sorted(day_bucket.values(), key=lambda x: x["date"])
    for b in past_days:
        b["sport"] = b["sport"] if b["sport"] in SPORT_STYLES else classify_sport(b["sport"])
        b["dist_km"] = round(b["dist_km"], 1)

    return render_template(
        "index.html",
        activities=recent_activities,
        stats=stats,
        active_plan=active_plan,
        plan_today=plan_today,
        plan_tomorrow=plan_tomorrow,
        past_days=past_days,
        future_days=future_days,
        today_str=today_str,
        range_days=range_days,
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
        return jsonify({"response": "Brak wiadomości."})

    user_message_db = ChatMessage(user_id=current_user.id, sender="user", content=user_msg)
    db.session.add(user_message_db)
    db.session.commit()

    recent_messages = (
        ChatMessage.query
        .filter_by(user_id=current_user.id)
        .order_by(ChatMessage.timestamp.asc())
        .limit(20)
        .all()
    )

    chat_history_text = build_chat_history(recent_messages, max_age_days=14)

    # Kontekst warstwowy (bez zalewania całej bazy):
    profile_state = get_profile_and_state_context(current_user)
    weekly_agg = get_weekly_aggregates(user_id=current_user.id, weeks=12)
    recent_details = get_recent_activity_details(user_id=current_user.id, days=21)

    today_iso = datetime.now().strftime("%Y-%m-%d")

    full_prompt = build_chat_prompt(
        today_iso=today_iso,
        profile_state=profile_state,
        weekly_agg=weekly_agg,
        recent_details=recent_details,
        chat_history=chat_history_text,
        user_msg=user_msg,
    )

    try:
        response = model.generate_content(full_prompt)
        clean_text = (response.text or "").replace("```html", "").replace("```", "").replace("**", "")

        ai_message_db = ChatMessage(user_id=current_user.id, sender="ai", content=clean_text)
        db.session.add(ai_message_db)
        db.session.commit()

        return jsonify({"response": clean_text})
    except Exception as e:
        return jsonify({"response": f"Błąd AI: {str(e)}"})


@app.route("/api/forecast", methods=["GET"])
@login_required
def generate_forecast():
    """Generuje plan na najbliższe 4 dni i zapisuje go jako aktywny (stan), żeby dashboard był stabilny."""
    profile_state = get_profile_and_state_context(current_user)
    weekly_agg = get_weekly_aggregates(user_id=current_user.id, weeks=12)
    recent_details = get_recent_activity_details(user_id=current_user.id, days=21)

    today = datetime.now().strftime("%Y-%m-%d")

    prompt = f"""
Jesteś trenerem sportowym. Stwórz plan treningowy na 4 dni (start: {today}).

WAŻNE:
- Uwzględnij ograniczenia i dostępność z PROFILU.
- Jeżeli STATE wskazuje aktywny uraz/ograniczenia — plan ma być konserwatywny.

{profile_state}

{weekly_agg}

{recent_details}

FORMAT (BARDZO WAŻNE):
- Bez Markdown. Tylko HTML.
- Każdy dzień musi mieć 3 linie:
  <b>YYYY-MM-DD</b><br>
  <b>Trening:</b> ...<br>
  <b>Dlaczego:</b> ...<br><br>
- Trening ma być konkretny: intensywność, czas/dystans, ewentualnie rozgrzewka/schłodzenie.
"""

    try:
        response = model.generate_content(prompt)
        text = (response.text or "").replace("```html", "").replace("```", "").replace("**", "")
        if "<br>" not in text:
            text = text.replace("\n", "<br>")

        # Zapisz jako aktywny plan (wyłącz poprzedni)
        GeneratedPlan.query.filter_by(user_id=current_user.id, is_active=True).update({"is_active": False})
        plan = GeneratedPlan(
            user_id=current_user.id,
            created_at=datetime.now(timezone.utc),
            start_date=datetime.now(timezone.utc).date(),
            horizon_days=4,
            html_content=text,
            is_active=True,
        )
        db.session.add(plan)
        db.session.commit()

        return jsonify({"plan": text})
    except Exception:
        return jsonify({"plan": "Nie udało się wygenerować planu."})



def _guess_mime(path: str) -> str:
    ext = (os.path.splitext(path)[1] or "").lower()
    if ext in [".jpg", ".jpeg"]:
        return "image/jpeg"
    if ext in [".png"]:
        return "image/png"
    if ext in [".webp"]:
        return "image/webp"
    return "application/octet-stream"


def parse_strava_screenshot_to_activity(image_path: str) -> dict:
    """Próbuje wyciągnąć zrzutu Stravy: typ, dystans, czas. Zwraca dict."""
    try:
        with open(image_path, "rb") as f:
            img_bytes = f.read()

        prompt = """
Masz zrzut ekranu aktywności ze Stravy (lub podobnej aplikacji).
Wyciągnij z niego dane i zwróć WYŁĄCZNIE JSON (bez markdown, bez komentarzy) w formacie:

{
  "activity_type": "run|ride|swim|workout|weighttraining|yoga|hike|walk|other",
  "distance_km": number|null,
  "duration_min": number|null
}

Zasady:
- distance_km ma być w kilometrach (np. 8.42)
- duration_min ma być w minutach (np. 46)
- jeśli nie widzisz wartości, daj null
        """.strip()

        resp = model.generate_content([
            prompt,
            {"mime_type": _guess_mime(image_path), "data": img_bytes}
        ])

        raw = (getattr(resp, "text", None) or "").strip()
        data = json.loads(raw)

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

        return out
    except Exception:
        return {}

# -------------------- QUICK ADD --------------------

@app.route("/activity/manual", methods=["POST"])
@login_required
def add_activity_manual():
    """Szybkie dodanie treningu ręcznie (bez Stravy)."""
    act_type = (request.form.get("activity_type") or "other").strip().lower()

    date_str = (request.form.get("date") or "").strip()
    time_str = (request.form.get("time") or "").strip()  # NOWE

    duration_min = int(float(request.form.get("duration_min") or 0))
    distance_km = float(request.form.get("distance_km") or 0)
    notes = (request.form.get("notes") or "").strip()

    # data + godzina -> datetime aware (UTC)
    try:
        if date_str and time_str:
            dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        elif date_str:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        else:
            dt = datetime.now(timezone.utc)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except Exception:
        dt = datetime.now(timezone.utc)

    act = Activity(
        user_id=current_user.id,
        activity_type=act_type,
        start_time=dt,
        duration=max(0, duration_min) * 60,
        distance=max(0.0, distance_km) * 1000.0,
        avg_hr=None,
        notes=notes,
    )
    db.session.add(act)
    db.session.commit()
    flash("Dodano trening.")
    return redirect(url_for("index"))



@app.route("/checkin", methods=["POST"])
@login_required
def add_checkin():
    """Dodaj check-in po treningu (tekst + opcjonalny screenshot).
    Jeśli jest screenshot — spróbuj automatycznie utworzyć Activity.
    """
    text_note = (request.form.get("checkin_text") or "").strip()
    if not text_note and "checkin_image" not in request.files:
        flash("Dodaj opis lub obrazek.")
        return redirect(url_for("index"))

    image_path = None
    f = request.files.get("checkin_image")
    if f and f.filename:
        os.makedirs("uploads", exist_ok=True)
        safe_name = f"{current_user.id}_{int(datetime.now(timezone.utc).timestamp())}_{re.sub(r'[^a-zA-Z0-9._-]', '_', f.filename)}"
        image_path = os.path.join("uploads", safe_name)
        f.save(image_path)

    entry = TrainingCheckin(
        user_id=current_user.id,
        created_at=datetime.now(timezone.utc),
        notes=text_note,
        image_path=image_path,
    )
    db.session.add(entry)

    # NOWE: jeśli jest screenshot -> spróbuj dodać aktywność
    created_activity = False
    if image_path:
        parsed = parse_strava_screenshot_to_activity(image_path)
        act_type = (parsed.get("activity_type") or "other").strip().lower()
        dur_min = parsed.get("duration_min")
        dist_km = parsed.get("distance_km")

        # jeśli cokolwiek wyciągnęliśmy, tworzymy Activity
        if dur_min is not None or dist_km is not None or act_type != "other":
            act = Activity(
                user_id=current_user.id,
                activity_type=act_type,
                start_time=datetime.now(timezone.utc),  # screenshot zwykle nie ma startu — dajemy "teraz"
                duration=max(0, int(round(dur_min or 0))) * 60,
                distance=max(0.0, float(dist_km or 0.0)) * 1000.0,
                avg_hr=None,
                notes=("AUTO (screenshot): " + text_note).strip(),
            )
            db.session.add(act)
            created_activity = True

    db.session.commit()

    if image_path and not created_activity:
        flash("Zapisano check-in, ale nie udało się odczytać danych ze screena (dodaj trening ręcznie).")
    elif created_activity:
        flash("Zapisano check-in i dodano trening ze screena.")
    else:
        flash("Zapisano check-in.")

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
        flash("Nie wybrano pliku")
        return redirect(url_for("index"))

    file = request.files["file"]
    if not file or file.filename == "":
        flash("Nie wybrano pliku")
        return redirect(url_for("index"))

    try:
        with zipfile.ZipFile(file) as z:
            csv_filename = next((name for name in z.namelist() if name.endswith("activities.csv")), None)
            if not csv_filename:
                flash("Nie znaleziono pliku activities.csv w archiwum!")
                return redirect(url_for("index"))

            with z.open(csv_filename) as f:
                csv_content = io.TextIOWrapper(f, encoding="utf-8")
                reader = csv.DictReader(csv_content)

                added_count = 0
                skipped_count = 0

                formats = [
                    "%b %d, %Y, %I:%M:%S %p",
                    "%Y-%m-%d %H:%M:%S",
                ]

                def clean_float(val):
                    if val in (None, "", "nan"):
                        return 0.0
                    return float(str(val).replace(",", ""))

                for row in reader:
                    try:
                        date_str = row.get("Activity Date", "")
                        start_time_obj = None
                        for fmt in formats:
                            try:
                                start_time_obj = datetime.strptime(date_str, fmt)
                                break
                            except ValueError:
                                continue
                        if not start_time_obj:
                            continue

                        existing = Activity.query.filter_by(user_id=current_user.id, start_time=start_time_obj).first()
                        if existing:
                            skipped_count += 1
                            continue

                        dist = clean_float(row.get("Distance", "0"))
                        elapsed = clean_float(row.get("Elapsed Time", "0"))
                        if dist < 500 and elapsed > 300:
                            dist = dist * 1000

                        moving = clean_float(row.get("Moving Time", "0"))
                        if moving == 0:
                            moving = elapsed

                        avg_hr_val = row.get("Average Heart Rate", None)
                        if avg_hr_val in (None, "", "nan"):
                            avg_hr = None
                        else:
                            avg_hr = int(float(avg_hr_val))

                        desc = row.get("Activity Description", "")
                        if desc == "nan":
                            desc = ""

                        new_activity = Activity(
                            user_id=current_user.id,
                            activity_type=row.get("Activity Type", "Run"),
                            start_time=start_time_obj,
                            duration=int(moving),
                            distance=dist,
                            avg_hr=avg_hr,
                            notes=desc,
                        )
                        db.session.add(new_activity)
                        added_count += 1

                    except Exception:
                        continue

                db.session.commit()
                flash(f"Sukces! Zaimportowano {added_count} treningów. Pominięto {skipped_count}.")
                try:
                    compute_profile_defaults_from_history(current_user.id)
                except Exception:
                    pass

    except Exception as e:
        flash(f"Błąd pliku: {e}")

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


@app.route("/activity/<int:activity_id>/update_notes", methods=["POST"])
@login_required
def update_activity_notes(activity_id: int):
    activity = Activity.query.filter_by(id=activity_id, user_id=current_user.id).first_or_404()
    activity.notes = request.form.get("notes")
    db.session.commit()
    return redirect(url_for("activity_detail", activity_id=activity_id))


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