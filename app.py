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
try:
    from fitparse import FitFile
except Exception:  # optional dependency for Garmin route/stat parsing
    FitFile = None



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
        "calendar_goal_missing": "Ustaw cele tygodniowe w profilu, by lepiej śledzić postęp.",
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
        "goal_per_week_label": "Cel biegów / tydzień",
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
        "calendar_goal_missing": "Set weekly goals in profile to better track progress.",
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
        "goal_per_week_label": "Run goal / week",
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


def _parse_decimal_input(value) -> float | None:
    """Parse decimal values from user/AI input, accepting both dot and comma."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except Exception:
            return None

    raw = str(value).strip().lower()
    if not raw:
        return None

    norm = raw.replace("−", "-").replace("\u202f", " ").replace("\xa0", " ")
    m = re.search(r"-?\d[\d\s.,]*", norm)
    if not m:
        return None

    token = m.group(0).strip().replace(" ", "")
    if not token:
        return None

    # both separators -> last one is decimal separator
    if "," in token and "." in token:
        if token.rfind(",") > token.rfind("."):
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    elif "," in token:
        # 1,425 -> thousand grouping, 5,5 -> decimal
        if re.fullmatch(r"-?\d{1,3}(,\d{3})+", token):
            token = token.replace(",", "")
        else:
            token = token.replace(",", ".")
    elif "." in token:
        # 1.425 -> thousand grouping in some locales
        if re.fullmatch(r"-?\d{1,3}(\.\d{3})+", token):
            token = token.replace(".", "")

    try:
        return float(token)
    except Exception:
        return None


def _parse_distance_km_input(value, activity_type: str | None = None) -> float | None:
    """Parse distance and normalize to km from mixed strings (km/m, EN/PL)."""
    if value is None:
        return None

    raw = str(value).strip().lower()
    if not raw:
        return None

    # Ignore pure pace strings like "7:00 /km" or "1:52 /100m".
    if ("/km" in raw or "/100m" in raw) and ("distance" not in raw and "dystans" not in raw):
        return None

    num = _parse_decimal_input(raw)
    if num is None:
        return None

    has_km = bool(re.search(r"\bkm\b|kilometr", raw))
    has_m = bool(re.search(r"(^|[^a-z])m($|[^a-z])|metr", raw)) and not has_km

    if has_km:
        dist_km = num
    elif has_m:
        dist_km = num / 1000.0
    else:
        dist_km = num

    t = (activity_type or "").lower()
    # Safety net for meters accidentally interpreted as km.
    if dist_km and dist_km > 0:
        if t == "swim" and dist_km > 20:
            dist_km = dist_km / 1000.0
        elif t in {"run", "walk", "hike", "yoga", "weighttraining", "workout", "other"} and dist_km > 120:
            dist_km = dist_km / 1000.0

    return dist_km


def _parse_minutes_input(value) -> float | None:
    """Parse duration in minutes from flexible formats (e.g. 45, 45.5, 45,5, 1:15:00)."""
    if value is None:
        return None

    raw = str(value).strip().lower()
    if not raw:
        return None

    s = raw.replace(",", ".")

    # Clock formats: MM:SS or HH:MM:SS (e.g. 49:06, 1:24:18)
    m_clock = re.search(r"\b(\d{1,2}:\d{2}(?::\d{2})?)\b", s)
    if m_clock:
        parts = m_clock.group(1).split(":")
        try:
            nums = [float(p) for p in parts]
            if len(nums) == 2:
                return nums[0] + (nums[1] / 60.0)
            if len(nums) == 3:
                return nums[0] * 60.0 + nums[1] + (nums[2] / 60.0)
        except Exception:
            pass

    # "1h 20min 6s", "49min 6s", "1 godz 24 min" styles
    h_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|godz)", s)
    m_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:m|min|mins|minut)", s)
    s_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:s|sec|secs|sek)", s)
    if h_match or m_match or s_match:
        hours = _parse_decimal_input(h_match.group(1)) if h_match else 0.0
        mins = _parse_decimal_input(m_match.group(1)) if m_match else 0.0
        secs = _parse_decimal_input(s_match.group(1)) if s_match else 0.0
        return float(hours or 0.0) * 60.0 + float(mins or 0.0) + float(secs or 0.0) / 60.0

    return _parse_decimal_input(s)


def _normalize_date_input(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None

    s = raw.lower().strip()
    today = datetime.now().date()
    if any(k in s for k in ("today", "dzis", "dziś")):
        return today.isoformat()
    if "yesterday" in s or "wczoraj" in s:
        return (today - timedelta(days=1)).isoformat()

    # Trim trailing noise like "at 8:31 PM - Porto".
    candidates = [raw]
    for sep in (" at ", " @ ", " - ", " • "):
        if sep in raw:
            candidates.append(raw.split(sep)[0].strip())

    for cand in candidates:
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%Y", "%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"):
            try:
                return datetime.strptime(cand, fmt).strftime("%Y-%m-%d")
            except Exception:
                continue

    month_map = {
        "jan": 1, "january": 1, "stycz": 1, "sty": 1,
        "feb": 2, "february": 2, "lut": 2, "luty": 2,
        "mar": 3, "march": 3, "marz": 3,
        "apr": 4, "april": 4, "kwi": 4, "kwiec": 4,
        "may": 5, "maj": 5,
        "jun": 6, "june": 6, "cze": 6,
        "jul": 7, "july": 7, "lip": 7,
        "aug": 8, "august": 8, "sie": 8,
        "sep": 9, "sept": 9, "september": 9, "wrz": 9,
        "oct": 10, "october": 10, "paz": 10, "paź": 10,
        "nov": 11, "november": 11, "lis": 11,
        "dec": 12, "december": 12, "gru": 12,
    }
    m = re.search(r"\b(\d{1,2})\s+([a-ząćęłńóśźż]+)\s*(\d{4})?\b", s)
    if m:
        day = int(m.group(1))
        month_token = m.group(2)
        year = int(m.group(3)) if m.group(3) else today.year
        month = month_map.get(month_token)
        if month is None:
            month = month_map.get(month_token[:3])
        if month:
            try:
                d = date(year, month, day)
                return d.isoformat()
            except Exception:
                pass
    return None


def _normalize_time_input(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None

    # Support embedded text like "Today at 8:31 PM".
    m_ampm = re.search(r"(\d{1,2}[:.]\d{2}(?::\d{2})?\s*[ap]m)", raw, re.IGNORECASE)
    m_24 = re.search(r"\b(\d{1,2}[:.]\d{2}(?::\d{2})?)\b", raw)
    extracted = m_ampm.group(1) if m_ampm else (m_24.group(1) if m_24 else raw)

    candidates = [
        extracted,
        extracted.replace(".", ":"),
        extracted.replace(" ", ""),
    ]

    for c in candidates:
        for fmt in ("%H:%M", "%H:%M:%S", "%I:%M%p", "%I:%M %p"):
            try:
                return datetime.strptime(c, fmt).strftime("%H:%M")
            except Exception:
                continue

    # "1730" -> "17:30", "830" -> "08:30"
    digits = re.sub(r"\D", "", raw)
    if re.fullmatch(r"\d{3,4}", digits):
        if len(digits) == 3:
            hhmm = f"0{digits[0]}:{digits[1:]}"
        else:
            hhmm = f"{digits[:2]}:{digits[2:]}"
        try:
            return datetime.strptime(hhmm, "%H:%M").strftime("%H:%M")
        except Exception:
            pass

    return None


def _normalize_activity_type_value(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return "other"
    if any(k in raw for k in ("swim", "pływ", "plyw", "basen")):
        return "swim"
    if any(k in raw for k in ("run", "bieg", "jog")):
        return "run"
    if any(k in raw for k in ("ride", "rower", "bike", "cycling")):
        return "ride"
    if any(k in raw for k in ("walk", "spacer")):
        return "walk"
    if any(k in raw for k in ("workout", "sił", "sil", "gym", "strength", "weight")):
        return "weighttraining"
    if any(k in raw for k in ("yoga", "joga")):
        return "yoga"
    if any(k in raw for k in ("hike", "trek", "gór", "gor", "szlak")):
        return "hike"
    return "other"


def _extract_activity_from_free_text(raw: str) -> dict:
    """Fallback when model returns non-JSON text."""
    txt = (raw or "").strip()
    low = txt.lower()
    out: dict = {
        "activity_type": _normalize_activity_type_value(txt),
        "distance_km": None,
        "duration_min": None,
        "avg_hr": None,
        "start_date": _normalize_date_input(txt),
        "start_time": _normalize_time_input(txt),
    }

    # distance with units (skip pace fragments like "/100m")
    for m in re.finditer(r"(\d[\d., ]*)\s*(km|m)\b", low):
        start = m.start()
        if start > 0 and low[start - 1] == "/":
            continue
        num_txt, unit = m.group(1), m.group(2)
        parsed = _parse_distance_km_input(f"{num_txt} {unit}", out["activity_type"])
        if parsed is not None and parsed > 0:
            out["distance_km"] = parsed
            break

    # duration: prefer clock-like values near explicit duration labels.
    duration_label_hits = []
    clock_matches = list(re.finditer(r"\b(\d{1,2}:\d{2}(?::\d{2})?)\b", txt))
    for m in clock_matches:
        start = m.start()
        end = m.end()
        ctx = txt[max(0, start - 30): min(len(txt), end + 30)].lower()
        tail = txt[start:start + 12].lower()

        if "/km" in tail or "/100m" in tail:
            continue
        # Skip clock-times like "Today at 11:53 AM" / "@ 20:31"
        if re.search(r"(today at|dzisiaj o|dziś o| at |\bam\b|\bpm\b|@\s*$)", txt[max(0, start - 12):start].lower()):
            continue

        mins = _parse_minutes_input(m.group(1))
        if not mins or mins <= 0:
            continue

        if any(k in ctx for k in ("moving time", "elapsed time", "czas", "całkowity", "calkowity", "duration")):
            duration_label_hits.append(mins)

    if duration_label_hits:
        out["duration_min"] = max(duration_label_hits)
    else:
        # Fallback: pick a sensible non-pace clock value.
        candidates = []
        for m in clock_matches:
            start = m.start()
            tail = txt[start:start + 12].lower()
            if "/km" in tail or "/100m" in tail:
                continue
            if re.search(r"(today at|dzisiaj o|dziś o| at |\bam\b|\bpm\b|@\s*$)", txt[max(0, start - 12):start].lower()):
                continue
            mins = _parse_minutes_input(m.group(1))
            if mins and mins > 0:
                candidates.append(mins)
        if candidates:
            out["duration_min"] = max(candidates)

    if out["duration_min"] is None:
        mins = _parse_minutes_input(txt)
        if mins and mins > 0:
            out["duration_min"] = mins

    # avg hr (average only)
    hr_patterns = [
        r"(?:avg(?:\.|\s)?heart(?:\s)?rate|average(?:\s)?heart(?:\s)?rate|avg hr|średnie(?:\s)?tętno|sr\.?\s*t[ęe]tno)\D{0,10}(\d{2,3})",
        r"(\d{2,3})\s*bpm",
    ]
    for pat in hr_patterns:
        m = re.search(pat, low, re.IGNORECASE)
        if m:
            hr = _parse_decimal_input(m.group(1))
            if hr and 40 <= hr <= 230:
                out["avg_hr"] = int(round(hr))
                break

    return out


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
            'weekly_focus_sports': "weekly_focus_sports TEXT",
            'weekly_run_sessions': "weekly_run_sessions INTEGER",
            'weekly_gym_sessions': "weekly_gym_sessions INTEGER",
            'weekly_swim_sessions': "weekly_swim_sessions INTEGER",
            'weekly_mobility_sessions': "weekly_mobility_sessions INTEGER",
            'weekly_ride_sessions': "weekly_ride_sessions INTEGER",
            'gender': "gender TEXT",
            'birth_date': "birth_date DATE",
            'height_cm': "height_cm REAL",
            'weight_kg': "weight_kg REAL",
            'vo2max': "vo2max REAL",
            'resting_hr': "resting_hr INTEGER",
            'avg_sleep_hours': "avg_sleep_hours REAL",
            'avg_daily_steps': "avg_daily_steps INTEGER",
            'avg_daily_stress': "avg_daily_stress REAL",
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

    # activities
    if 'activities' in inspect(db.engine).get_table_names():
        cols = columns('activities')
        wanted = {
            'max_hr': "max_hr INTEGER",
            'moving_duration': "moving_duration INTEGER",
            'elapsed_duration': "elapsed_duration INTEGER",
            'avg_speed_mps': "avg_speed_mps REAL",
            'max_speed_mps': "max_speed_mps REAL",
            'elevation_gain': "elevation_gain REAL",
            'elevation_loss': "elevation_loss REAL",
            'calories': "calories REAL",
            'steps': "steps INTEGER",
            'vo2max': "vo2max REAL",
            'start_lat': "start_lat REAL",
            'start_lng': "start_lng REAL",
            'end_lat': "end_lat REAL",
            'end_lng': "end_lng REAL",
            'route_points_json': "route_points_json TEXT",
            'source': "source TEXT DEFAULT 'manual'",
            'external_id': "external_id TEXT",
            'device_id': "device_id TEXT",
            'sport_type': "sport_type TEXT",
            'metadata_json': "metadata_json TEXT",
        }
        for name, coldef in wanted.items():
            if name not in cols:
                add_column('activities', coldef)


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
        "gym": "Siłownia",
        "mobility": "Mobilność",
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
        "gym": "Gym",
        "mobility": "Mobility",
        "weighttraining": "Gym",
        "workout": "Workout",
        "yoga": "Yoga",
        "hike": "Hike",
        "walk": "Walk",
        "other": "Other",
    },
}

TARGET_SPORT_FIELDS = {
    "run": "weekly_run_sessions",
    "gym": "weekly_gym_sessions",
    "swim": "weekly_swim_sessions",
    "mobility": "weekly_mobility_sessions",
    "ride": "weekly_ride_sessions",
}

TARGET_SPORT_ORDER = ["run", "gym", "swim", "mobility", "ride"]

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


def _format_duration_hms(seconds_value) -> str | None:
    total_seconds = _safe_int(seconds_value)
    if total_seconds is None or total_seconds < 0:
        return None
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    if h > 0:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s"


def _format_number(value, decimals: int = 1) -> str | None:
    num = _safe_float(value)
    if num is None:
        return None
    if decimals <= 0:
        return str(int(round(num)))
    text = f"{num:.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _parse_route_points_json(raw_json: str | None) -> list[list[float]]:
    if not raw_json:
        return []
    try:
        data = json.loads(raw_json)
    except Exception:
        return []
    if not isinstance(data, list):
        return []

    points: list[list[float]] = []
    for item in data:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        lat = _normalize_gps_coord(item[0])
        lng = _normalize_gps_coord(item[1])
        if lat is None or lng is None:
            continue
        points.append([lat, lng])
    return points


def _build_activity_detail_payload(activity: Activity) -> list[dict]:
    meta = _safe_json_dict(activity.metadata_json)
    cards: list[dict] = []

    def add_card(pl: str, en: str, value_text: str | None):
        if not value_text:
            return
        cards.append({"pl": pl, "en": en, "value": value_text})

    # Core activity metrics
    add_card("Maks. tętno", "Max HR", (f"{int(activity.max_hr)} bpm" if activity.max_hr else None))
    add_card("Czas ruchu", "Moving time", _format_duration_hms(activity.moving_duration))
    add_card("Czas całkowity", "Elapsed time", _format_duration_hms(activity.elapsed_duration))
    add_card("Śr. prędkość", "Avg speed", (f"{_format_number((activity.avg_speed_mps or 0) * 3.6, 2)} km/h" if activity.avg_speed_mps else None))
    add_card("Maks. prędkość", "Max speed", (f"{_format_number((activity.max_speed_mps or 0) * 3.6, 2)} km/h" if activity.max_speed_mps else None))
    add_card("Przewyższenie +", "Elevation gain", (f"{_format_number(activity.elevation_gain, 1)} m" if activity.elevation_gain is not None else None))
    add_card("Przewyższenie -", "Elevation loss", (f"{_format_number(activity.elevation_loss, 1)} m" if activity.elevation_loss is not None else None))
    add_card("Kalorie", "Calories", (f"{_format_number(activity.calories, 0)} kcal" if activity.calories is not None else None))
    add_card("Kroki", "Steps", (_format_number(activity.steps, 0) if activity.steps is not None else None))
    add_card("VO2max", "VO2max", (f"{_format_number(activity.vo2max, 1)}" if activity.vo2max is not None else None))

    known_meta = [
        ("avgRunCadence", "Śr. kadencja biegu", "Avg run cadence", 1, "spm"),
        ("maxRunCadence", "Maks. kadencja biegu", "Max run cadence", 1, "spm"),
        ("avgStrideLength", "Śr. długość kroku", "Avg stride length", 1, "cm"),
    ]

    for key, label_pl, label_en, decimals, unit in known_meta:
        if key not in meta:
            continue
        value = meta.get(key)
        if decimals < 0:
            text = _format_duration_hms(value)
        else:
            text = _format_number(value, decimals)
            if text and unit:
                text = f"{text} {unit}"
        add_card(label_pl, label_en, text)

    return cards


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


def _load_exercise_map(activity_ids: list[int]) -> dict[int, list[Exercise]]:
    if not activity_ids:
        return {}
    rows = Exercise.query.filter(Exercise.activity_id.in_(activity_ids)).all()
    out: dict[int, list[Exercise]] = {}
    for ex in rows:
        out.setdefault(ex.activity_id, []).append(ex)
    return out


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
    """Auto-uzupełnia profil po imporcie historii.

    Priorytet:
    - ostatnie 3 tygodnie (bardziej aktualny poziom),
    - fallback: ostatnie 12 tygodni, gdy danych jest mało.
    """
    profile = UserProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.session.add(profile)
        db.session.commit()

    now = datetime.now()
    recent_acts = _load_user_activities_with_fallback(
        user_id=user_id,
        start=now - timedelta(days=21),
        order_asc=True,
    )
    acts = recent_acts
    if len(acts) < 3:
        acts = _load_user_activities_with_fallback(
            user_id=user_id,
            start=now - timedelta(days=84),
            order_asc=True,
        )
    if not acts:
        return

    # top sporty
    counts = {}
    bucket_counts = {"run": 0, "gym": 0, "swim": 0, "mobility": 0, "ride": 0}
    for a in acts:
        key = (a.activity_type or "other").lower()
        counts[key] = counts.get(key, 0) + 1
        bucket = normalize_activity_bucket(a.activity_type, a.notes)
        if bucket in bucket_counts:
            bucket_counts[bucket] += 1
    top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:4]
    top_sports = ",".join([t[0] for t in top])

    # tygodniowe agregaty: dystans (km), czas (h), dni aktywne, liczba treningów
    # grupujemy po tygodniu (poniedziałek)
    buckets = {}
    for a in acts:
        start_dt = _activity_start_dt(a)
        if not start_dt:
            continue
        d = start_dt.date()
        week_start = d - timedelta(days=d.weekday())
        b = buckets.setdefault(week_start, {"dist_km": 0.0, "dur_h": 0.0, "days": set(), "count": 0})
        if a.distance:
            b["dist_km"] += (a.distance / 1000.0)
        if a.duration:
            b["dur_h"] += (a.duration / 3600.0)
        b["days"].add(d)
        b["count"] += 1

    weeks = list(buckets.values())
    if not weeks:
        return

    avg_dist = sum(w["dist_km"] for w in weeks) / len(weeks)
    avg_days = sum(len(w["days"]) for w in weeks) / len(weeks)
    avg_count = sum(w["count"] for w in weeks) / len(weeks)

    # Days per week based on last 7 days (unique active days)
    last_week_acts = _load_user_activities_with_fallback(
        user_id=user_id,
        start=now - timedelta(days=7),
        order_asc=True,
    )
    last_week_days = set()
    for a in last_week_acts:
        start_dt = _activity_start_dt(a)
        if start_dt:
            last_week_days.add(start_dt.date())
    days_last_7 = len(last_week_days)

    changed = False
    if profile.primary_sports in (None, "") and top_sports:
        profile.primary_sports = top_sports
        changed = True
    if profile.weekly_distance_km is None and avg_dist > 0:
        profile.weekly_distance_km = round(avg_dist, 1)
        changed = True
    if profile.days_per_week is None and days_last_7 > 0:
        profile.days_per_week = int(days_last_7)
        changed = True
    if profile.weekly_goal_workouts is None and avg_count > 0:
        profile.weekly_goal_workouts = max(1, int(round(avg_count)))
        changed = True
    for bucket, field_name in TARGET_SPORT_FIELDS.items():
        if getattr(profile, field_name, None) is not None:
            continue
        bucket_total = bucket_counts.get(bucket, 0)
        if bucket_total <= 0:
            continue
        avg_bucket_sessions = bucket_total / max(1, len(weeks))
        setattr(profile, field_name, max(1, int(round(avg_bucket_sessions))))
        changed = True
    if not (profile.weekly_focus_sports or "").strip():
        inferred_focus = [k for k in TARGET_SPORT_ORDER if bucket_counts.get(k, 0) > 0]
        if inferred_focus:
            profile.weekly_focus_sports = ",".join(inferred_focus)
            changed = True

    if changed:
        _sync_legacy_weekly_goal(profile)
        profile.updated_at = datetime.now(timezone.utc)
        db.session.commit()


# -------------------- ONBOARDING GUARD --------------------

@app.before_request
def enforce_onboarding():
    """Ustawienia języka i miękkie przypomnienie o onboardingu (bez twardego blokowania)."""
    lang = request.args.get("lang")
    if lang in ("pl", "en"):
        session["lang"] = lang

    if not current_user.is_authenticated:
        return

    if session.get("lang") not in ("pl", "en"):
        session["lang"] = (getattr(current_user, "preferred_lang", None) or "pl")

    return


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

    exercise_map = _load_exercise_map([a.id for a in activities])

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
        pace = ""
        if getattr(act, "avg_speed_mps", None) and float(act.avg_speed_mps) > 0:
            sec_per_km = 1000.0 / float(act.avg_speed_mps)
            mm = int(sec_per_km // 60)
            ss = int(round(sec_per_km % 60))
            pace = f" | tempo {mm}:{ss:02d}/km"
        elev = f" | +{int(round(act.elevation_gain))}m" if getattr(act, "elevation_gain", None) else ""
        out.append(f"- {d} | {t} | {dist_km:.1f} km | {dur_min} min{hr}{pace}{elev}")
        if act.notes:
            out.append(f"  Notatka: {act.notes}")
        exercises = exercise_map.get(act.id) or []
        if exercises:
            parts = []
            for ex in exercises[:8]:
                name = (ex.name or "").strip()
                if not name:
                    continue
                sets = ex.sets or 0
                reps = ex.reps or 0
                weight = ex.weight if ex.weight is not None else None
                if weight is not None and weight > 0:
                    parts.append(f"{name} ({sets}x{reps}, {weight}kg)")
                else:
                    parts.append(f"{name} ({sets}x{reps})")
            if parts:
                out.append(f"  Ćwiczenia: {', '.join(parts)}")
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

    exercise_map = _load_exercise_map([a.id for a in acts])

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
        exercises = exercise_map.get(act.id) or []
        if exercises:
            parts = []
            for ex in exercises[:8]:
                name = (ex.name or "").strip()
                if not name:
                    continue
                sets = ex.sets or 0
                reps = ex.reps or 0
                weight = ex.weight if ex.weight is not None else None
                if weight is not None and weight > 0:
                    parts.append(f"{name} ({sets}x{reps}, {weight}kg)")
                else:
                    parts.append(f"{name} ({sets}x{reps})")
            if parts:
                lines.append(f"  Ćwiczenia: {', '.join(parts)}")

    lines.append(
        "PODSUMOWANIE TYPU: "
        + " | ".join([f"{k}={counts[k]}" for k in ("run", "ride", "swim", "gym", "mobility", "other")])
    )
    lines.append(
        "DZISIAJ WYKONANO: "
        + " | ".join([f"{k}={today_counts[k]}" for k in ("run", "ride", "swim", "gym", "mobility", "other")])
    )
    return "\n".join(lines)


def get_week_execution_context(user_id: int, week_start: date, week_end: date) -> str:
    start_dt = datetime.combine(week_start, datetime.min.time())
    end_dt = datetime.combine(week_end + timedelta(days=1), datetime.min.time())
    acts = _load_user_activities_with_fallback(
        user_id=user_id,
        start=start_dt,
        end=end_dt,
        order_asc=True,
    )
    if not acts:
        return "W TYM TYGODNIU: brak wykonanych treningów."

    exercise_map = _load_exercise_map([a.id for a in acts])
    lines = [f"WYKONANE W TYM TYGODNIU ({week_start.isoformat()} → {week_end.isoformat()}):"]
    for act in acts:
        start_act = _activity_start_dt(act)
        if not start_act:
            continue
        d = start_act.strftime("%Y-%m-%d")
        b = normalize_activity_bucket(act.activity_type, act.notes)
        dist_km = (act.distance or 0.0) / 1000.0
        dur_min = int((act.duration or 0) // 60)
        lines.append(f"- {d} | {b} | {dist_km:.1f} km | {dur_min} min")
        exercises = exercise_map.get(act.id) or []
        if exercises:
            parts = []
            for ex in exercises[:8]:
                name = (ex.name or "").strip()
                if not name:
                    continue
                sets = ex.sets or 0
                reps = ex.reps or 0
                weight = ex.weight if ex.weight is not None else None
                if weight is not None and weight > 0:
                    parts.append(f"{name} ({sets}x{reps}, {weight}kg)")
                else:
                    parts.append(f"{name} ({sets}x{reps})")
            if parts:
                lines.append(f"  Ćwiczenia: {', '.join(parts)}")
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


def get_recent_weekly_volume_km(user_id: int, weeks: int = 4, include_types: set[str] | None = None) -> dict:
    """Returns last/previous/average weekly distance in km for recent window."""
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    start_date = monday - timedelta(weeks=weeks - 1)
    allowed = {t.lower() for t in include_types} if include_types else None

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
        if allowed is not None:
            at = (a.activity_type or "").lower()
            if at not in allowed:
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


def _infer_goal_discipline(profile_obj: UserProfile | None) -> str:
    if not profile_obj:
        return "run"

    txt = " ".join([
        profile_obj.target_event or "",
        profile_obj.goals_text or "",
        profile_obj.primary_sports or "",
    ]).lower()

    if any(k in txt for k in ("marathon", "maraton", "half marathon", "półmaraton", "polmaraton", "10k", "5k", "run", "bieg")):
        return "run"
    if any(k in txt for k in ("ride", "rower", "bike", "cycling", "kolar")):
        return "ride"
    if any(k in txt for k in ("swim", "pływ", "plyw", "basen")):
        return "swim"
    return "run"


def _infer_goal_distance_km(profile_obj: UserProfile | None) -> float | None:
    if not profile_obj:
        return None

    txt = " ".join([
        profile_obj.target_event or "",
        profile_obj.goals_text or "",
    ]).lower()

    if any(k in txt for k in ("half marathon", "półmaraton", "polmaraton", "21k", "21.1")):
        return 21.1
    if any(k in txt for k in ("marathon", "maraton", "42k", "42.2")):
        return 42.2

    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:km|k)\b", txt)
    if m:
        try:
            val = float(m.group(1).replace(",", "."))
            if 3 <= val <= 120:
                return val
        except Exception:
            pass
    return None


def _recommended_weekly_volume_range_km(goal_discipline: str, goal_distance_km: float | None, days_per_week: int | None) -> tuple[float, float]:
    dpw = max(2, min(7, int(days_per_week or 4)))
    factor_map = {2: 0.75, 3: 0.88, 4: 1.0, 5: 1.12, 6: 1.22, 7: 1.30}
    f = factor_map.get(dpw, 1.0)

    if goal_discipline == "run":
        dist = float(goal_distance_km or 0.0)
        if dist >= 40:
            base_low, base_high = 42.0, 82.0
        elif dist >= 20:
            base_low, base_high = 28.0, 62.0
        elif dist >= 10:
            base_low, base_high = 18.0, 44.0
        elif dist >= 5:
            base_low, base_high = 14.0, 32.0
        else:
            base_low, base_high = 16.0, 36.0
    elif goal_discipline == "ride":
        base_low, base_high = 80.0, 260.0
    elif goal_discipline == "swim":
        base_low, base_high = 4.0, 18.0
    else:
        return 0.0, 0.0

    return round(base_low * f, 1), round(base_high * f, 1)


def _target_bucket_label(bucket: str) -> str:
    labels = {
        "run": tr("Bieganie", "Running"),
        "gym": tr("Siłownia", "Gym"),
        "swim": tr("Pływanie", "Swimming"),
        "mobility": tr("Mobilność", "Mobility"),
        "ride": tr("Rower", "Cycling"),
    }
    return labels.get(bucket, bucket)


def _normalize_focus_sports(raw_values: list[str] | tuple[str, ...] | None) -> list[str]:
    if not raw_values:
        return ["run"]

    out = []
    seen = set()
    for raw in raw_values:
        if raw is None:
            continue
        parts = str(raw).split(",")
        for part in parts:
            key = part.strip().lower()
            if key not in TARGET_SPORT_FIELDS:
                continue
            if key in seen:
                continue
            out.append(key)
            seen.add(key)
    return out or ["run"]


def _get_focus_sports(profile_obj: UserProfile | None, weekly_targets: dict[str, int] | None = None) -> list[str]:
    if weekly_targets is None:
        weekly_targets = _get_weekly_session_targets(profile_obj)

    if profile_obj and getattr(profile_obj, "weekly_focus_sports", None):
        selected = _normalize_focus_sports([profile_obj.weekly_focus_sports])
        if selected:
            return selected

    inferred = [k for k in TARGET_SPORT_ORDER if int(weekly_targets.get(k, 0) or 0) > 0]
    if inferred:
        return inferred
    return ["run"]


def _build_weekly_target_form_context(profile_obj: UserProfile | None) -> tuple[list[str], dict[str, int]]:
    targets = _get_weekly_session_targets(profile_obj)
    focus_sports = _get_focus_sports(profile_obj, targets)
    return focus_sports, targets


def _get_weekly_session_targets(profile_obj: UserProfile | None) -> dict[str, int]:
    targets = {k: 0 for k in TARGET_SPORT_FIELDS}
    if profile_obj:
        for key, field in TARGET_SPORT_FIELDS.items():
            val = getattr(profile_obj, field, None)
            try:
                targets[key] = max(0, int(val or 0))
            except Exception:
                targets[key] = 0

        if not any(targets.values()):
            fallback = int(profile_obj.weekly_goal_workouts or 0)
            if fallback <= 0:
                fallback = int(profile_obj.days_per_week or 0)
            if fallback <= 0:
                fallback = 3
            targets["run"] = fallback
    else:
        targets["run"] = 3

    return targets


def _sync_legacy_weekly_goal(profile_obj: UserProfile) -> None:
    targets = _get_weekly_session_targets(profile_obj)
    total = sum(targets.values())
    if total > 0:
        profile_obj.weekly_goal_workouts = total


def _count_week_sessions_by_target(user_id: int, week_start: date, week_end: date | None = None) -> dict[str, int]:
    if week_end is None:
        week_end = week_start + timedelta(days=6)
    acts = _load_user_activities_with_fallback(
        user_id=user_id,
        start=datetime.combine(week_start, datetime.min.time()),
        end=datetime.combine(week_end + timedelta(days=1), datetime.min.time()),
        order_asc=True,
    )
    out = {k: 0 for k in TARGET_SPORT_ORDER}
    for a in acts:
        b = normalize_activity_bucket(a.activity_type, a.notes)
        if b in out:
            out[b] += 1
    return out


def build_goal_progress(user_id: int, profile_obj: UserProfile | None, range_days: int, stats: dict) -> dict | None:
    if not profile_obj or not profile_obj.target_date:
        return None

    today = datetime.now().date()
    days_left = (profile_obj.target_date - today).days

    goal_discipline = _infer_goal_discipline(profile_obj)
    include_types = None
    if goal_discipline == "run":
        include_types = {"run", "trailrun", "virtualrun"}
    elif goal_discipline == "ride":
        include_types = {"ride", "virtualride"}
    elif goal_discipline == "swim":
        include_types = {"swim"}

    vol = get_recent_weekly_volume_km(user_id=user_id, weeks=6, include_types=include_types)
    avg_week = float(vol.get("avg_week_km", 0.0) or 0.0)
    last_week = float(vol.get("last_week_km", 0.0) or 0.0)
    declared_weekly = float(profile_obj.weekly_distance_km or 0.0)
    current_weekly = max(avg_week, last_week, declared_weekly, 0.0)
    if current_weekly <= 0 and vol.get("weekly_series"):
        current_weekly = max(float(x or 0.0) for x in vol["weekly_series"])

    risk = (profile_obj.risk_tolerance or "balanced").lower()
    ramp_pct = {"conservative": 0.05, "aggressive": 0.11}.get(risk, 0.08)

    weeks_left = max(0, int((days_left + 6) // 7))
    low_rec, high_rec = _recommended_weekly_volume_range_km(
        goal_discipline=goal_discipline,
        goal_distance_km=_infer_goal_distance_km(profile_obj),
        days_per_week=profile_obj.days_per_week,
    )

    bias = {"conservative": 0.35, "aggressive": 0.75}.get(risk, 0.55)
    recommended_peak = low_rec + (high_rec - low_rec) * bias if high_rec > 0 else 0.0
    if declared_weekly > 0:
        recommended_peak = max(recommended_peak, declared_weekly)
    if recommended_peak <= 0:
        recommended_peak = max(current_weekly, declared_weekly)

    growth_weeks = max(1, min(10, weeks_left))
    safe_cap = current_weekly * (1.0 + ramp_pct * growth_weeks) if current_weekly > 0 else recommended_peak

    target_weekly = min(recommended_peak, safe_cap) if recommended_peak > 0 else safe_cap
    if current_weekly > 0:
        target_weekly = max(target_weekly, current_weekly)

    if current_weekly > 0:
        projected_cap = current_weekly * (1.0 + ramp_pct * min(4, growth_weeks))
        projected_4w = min(target_weekly, projected_cap)
    else:
        projected_4w = target_weekly

    weekly_targets = _get_weekly_session_targets(profile_obj)
    focus_sports = _get_focus_sports(profile_obj, weekly_targets)
    weekly_goal = max(1, sum(int(weekly_targets.get(k, 0) or 0) for k in focus_sports))
    week_start = today - timedelta(days=today.weekday())
    done_targets = _count_week_sessions_by_target(user_id=user_id, week_start=week_start, week_end=today)
    workouts_done = sum(int(done_targets.get(k, 0) or 0) for k in focus_sports)
    completion_pct = int(round(min(100.0, (workouts_done / max(1, weekly_goal)) * 100.0)))

    if days_left <= 0:
        phase = tr("po starcie", "post-race")
    elif days_left <= 14:
        phase = tr("taper", "taper")
    elif days_left <= 84:
        phase = tr("build", "build")
    else:
        phase = tr("base", "base")

    readiness_pct = 0
    if target_weekly > 0:
        readiness_pct = int(round(min(100.0, (current_weekly / target_weekly) * 100.0)))

    return {
        "event": profile_obj.target_event or tr("Cel", "Goal"),
        "target_date": profile_obj.target_date.isoformat(),
        "target_date_pretty": format_dt(profile_obj.target_date, "long"),
        "days_left": max(0, days_left),
        "phase": phase,
        "risk": risk,
        "goal_discipline": goal_discipline,
        "volume_source": tr("profil + ostatnie 6 tygodni", "profile + last 6 weeks"),
        "weekly_volume_now": round(current_weekly, 1),
        "weekly_volume_target": round(target_weekly, 1),
        "weekly_volume_target_min": round(low_rec, 1) if high_rec > 0 else None,
        "weekly_volume_target_max": round(high_rec, 1) if high_rec > 0 else None,
        "weekly_volume_safe_cap": round(safe_cap, 1),
        "weekly_volume_projected_4w": round(projected_4w, 1),
        "target_time_text": profile_obj.target_time_text or "",
        "weekly_labels": vol.get("weekly_labels", []),
        "weekly_series": vol.get("weekly_series", []),
        "readiness_pct": readiness_pct,
        "completion_pct": completion_pct,
        "weekly_goal": weekly_goal,
        "workouts_done_this_week": workouts_done,
        "weekly_targets": weekly_targets,
        "weekly_done_targets": done_targets,
        "focus_sports": focus_sports,
        "updated_on": today.isoformat(),
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
        if profile.height_cm is not None:
            facts.append(f"Wzrost: {profile.height_cm} cm")
        if profile.weight_kg is not None:
            facts.append(f"Waga: {profile.weight_kg} kg")
        if profile.gender:
            facts.append(f"Płeć: {profile.gender}")
        if profile.vo2max is not None:
            facts.append(f"VO2max: {profile.vo2max}")
        if profile.resting_hr is not None:
            facts.append(f"Tętno spoczynkowe: {profile.resting_hr}")
        if profile.avg_sleep_hours is not None:
            facts.append(f"Śr. sen: {profile.avg_sleep_hours} h")
        if profile.avg_daily_steps is not None:
            facts.append(f"Śr. kroki/dzień: {profile.avg_daily_steps}")
        if profile.avg_daily_stress is not None:
            facts.append(f"Śr. stres dzienny: {profile.avg_daily_stress}")
        if profile.days_per_week is not None:
            facts.append(f"Dni treningowe/tydz.: {profile.days_per_week}")
        if profile.weekly_goal_workouts is not None:
            facts.append(f"Cel treningów/tydz.: {profile.weekly_goal_workouts}")
        weekly_targets = _get_weekly_session_targets(profile)
        focus_sports = _get_focus_sports(profile, weekly_targets)
        if focus_sports:
            freq_parts = [f"{sport} {weekly_targets.get(sport, 0)}" for sport in focus_sports]
            facts.append("Preferowana częstotliwość/tydz.: " + ", ".join(freq_parts))
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


def _rewind_fileobj(file_obj) -> None:
    try:
        file_obj.seek(0)
    except Exception:
        pass


def detect_activity_archive_type(zip_file) -> str:
    """Detect import archive type from ZIP contents."""
    _rewind_fileobj(zip_file)
    try:
        with zipfile.ZipFile(zip_file) as z:
            names = [n.lower() for n in z.namelist()]
    finally:
        _rewind_fileobj(zip_file)

    if any(n.endswith("activities.csv") for n in names):
        return "strava"
    if any(n.endswith("_summarizedactivities.json") and "di-connect-fitness" in n for n in names):
        return "garmin"
    if any(n.endswith(".fit") for n in names):
        return "garmin_fit_only"
    return "unknown"


def _garmin_activity_type_to_app(activity_type: str | None, sport_type: str | None, name: str | None) -> str:
    t = (activity_type or "").strip().lower()
    s = (sport_type or "").strip().lower()
    n = (name or "").strip().lower()

    direct = {
        "running": "run",
        "treadmill_running": "run",
        "track_running": "run",
        "cycling": "ride",
        "lap_swimming": "swim",
        "open_water_swimming": "swim",
        "swimming": "swim",
        "walking": "walk",
        "hiking": "hike",
        "yoga": "yoga",
        "breathwork": "yoga",
        "strength_training": "weighttraining",
        "fitness_equipment": "workout",
        "cardio_training": "workout",
    }
    if t in direct:
        return direct[t]

    if t == "other":
        if any(k in s for k in ("swim",)):
            return "swim"
        if any(k in s for k in ("run", "track", "treadmill")):
            return "run"
        if any(k in s for k in ("cycle", "bike")):
            return "ride"
        if any(k in s for k in ("walk", "steps")):
            return "walk"
        if any(k in s for k in ("train", "strength", "generic", "invalid")):
            return "workout"
        if any(k in n for k in ("sił", "sil", "gym", "strength", "core", "mobility", "joga", "yoga")):
            return "workout"

    return "other"


def _load_json_member_from_zip(z: zipfile.ZipFile, member_name: str):
    with z.open(member_name) as f:
        return json.load(io.TextIOWrapper(f, encoding="utf-8"))


def _safe_float(value) -> float | None:
    try:
        if value in (None, "", "nan"):
            return None
        return float(value)
    except Exception:
        return None


def _safe_int(value) -> int | None:
    try:
        if value in (None, "", "nan"):
            return None
        return int(round(float(value)))
    except Exception:
        return None


def _ms_to_datetime_utc(ms_value) -> datetime | None:
    ms = _safe_float(ms_value)
    if ms is None:
        return None
    try:
        # Keep naive UTC to stay compatible with existing DB rows.
        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).replace(tzinfo=None)
    except Exception:
        return None


def _to_meters_from_garmin_distance(raw_distance) -> float:
    # Garmin summarized exports distance in centimeters.
    val = _safe_float(raw_distance)
    if val is None:
        return 0.0
    return max(0.0, val / 100.0)


def _to_seconds_from_ms(raw_ms) -> int:
    val = _safe_float(raw_ms)
    if val is None:
        return 0
    return max(0, int(round(val / 1000.0)))


def _to_naive_utc(dt_value: datetime | None) -> datetime | None:
    if not isinstance(dt_value, datetime):
        return None
    if dt_value.tzinfo is None:
        return dt_value
    return dt_value.astimezone(timezone.utc).replace(tzinfo=None)


def _normalize_gps_coord(raw_value) -> float | None:
    value = _safe_float(raw_value)
    if value is None:
        return None
    if abs(value) > 180:
        # FIT stores coordinates as semicircles.
        value = value * (180.0 / 2147483648.0)
    if abs(value) > 180:
        return None
    return round(value, 7)


def _compact_route_points(points: list[list[float]], max_points: int = 1200) -> list[list[float]]:
    if len(points) <= max_points:
        return points

    out: list[list[float]] = []
    step = (len(points) - 1) / float(max_points - 1)
    for i in range(max_points):
        idx = int(round(i * step))
        idx = min(max(idx, 0), len(points) - 1)
        out.append(points[idx])

    # remove duplicates generated by index rounding
    deduped: list[list[float]] = []
    prev = None
    for p in out:
        if prev is None or p[0] != prev[0] or p[1] != prev[1]:
            deduped.append(p)
            prev = p
    return deduped


def _extract_fit_activity_payload(fit_blob: bytes, source_name: str) -> dict | None:
    if FitFile is None or not fit_blob:
        return None

    try:
        try:
            fit_file = FitFile(io.BytesIO(fit_blob), check_crc=False)
        except TypeError:
            fit_file = FitFile(io.BytesIO(fit_blob))

        session_values = {}
        for session_msg in fit_file.get_messages("session"):
            try:
                session_values = session_msg.get_values() or {}
            except Exception:
                session_values = {}
            break

        start_time = _to_naive_utc(session_values.get("start_time"))
        route_points: list[list[float]] = []
        hr_values: list[int] = []
        cad_values: list[float] = []
        power_values: list[float] = []
        first_ts = None

        for rec in fit_file.get_messages("record"):
            try:
                values = rec.get_values() or {}
            except Exception:
                continue

            if first_ts is None:
                first_ts = _to_naive_utc(values.get("timestamp"))

            lat = _normalize_gps_coord(values.get("position_lat"))
            lng = _normalize_gps_coord(values.get("position_long"))
            if lat is not None and lng is not None:
                route_points.append([lat, lng])

            hr = _safe_int(values.get("heart_rate"))
            if hr is not None and hr > 0:
                hr_values.append(hr)

            cadence = _safe_float(values.get("cadence") or values.get("fractional_cadence"))
            if cadence is not None and cadence > 0:
                cad_values.append(cadence)

            power = _safe_float(values.get("power"))
            if power is not None and power > 0:
                power_values.append(power)

        if not start_time:
            start_time = first_ts

        fit_meta = {}
        important_fields = (
            "sport",
            "sub_sport",
            "total_distance",
            "total_elapsed_time",
            "total_timer_time",
            "total_ascent",
            "total_descent",
            "total_calories",
            "total_steps",
            "avg_speed",
            "max_speed",
            "avg_heart_rate",
            "max_heart_rate",
            "avg_cadence",
            "max_cadence",
            "avg_running_cadence",
            "max_running_cadence",
            "avg_power",
            "max_power",
            "normalized_power",
            "training_stress_score",
            "total_training_effect",
            "aerobic_training_effect",
            "anaerobic_training_effect",
            "avg_stroke_distance",
            "avg_stroke_count",
            "avg_stroke_rate",
            "max_stroke_rate",
        )
        for key in important_fields:
            value = session_values.get(key)
            if value in (None, ""):
                continue
            fit_meta[f"fit_{key}"] = value

        if "fit_avg_heart_rate" not in fit_meta and hr_values:
            fit_meta["fit_avg_heart_rate"] = round(sum(hr_values) / len(hr_values), 1)
        if "fit_max_heart_rate" not in fit_meta and hr_values:
            fit_meta["fit_max_heart_rate"] = max(hr_values)
        if "fit_avg_cadence" not in fit_meta and cad_values:
            fit_meta["fit_avg_cadence"] = round(sum(cad_values) / len(cad_values), 1)
        if "fit_max_cadence" not in fit_meta and cad_values:
            fit_meta["fit_max_cadence"] = max(cad_values)
        if "fit_avg_power" not in fit_meta and power_values:
            fit_meta["fit_avg_power"] = round(sum(power_values) / len(power_values), 1)
        if "fit_max_power" not in fit_meta and power_values:
            fit_meta["fit_max_power"] = max(power_values)

        route_points = _compact_route_points(route_points, max_points=1200)
        start_lat = route_points[0][0] if route_points else None
        start_lng = route_points[0][1] if route_points else None
        end_lat = route_points[-1][0] if route_points else None
        end_lng = route_points[-1][1] if route_points else None

        return {
            "source_name": source_name,
            "start_time": start_time,
            "route_points": route_points,
            "start_lat": start_lat,
            "start_lng": start_lng,
            "end_lat": end_lat,
            "end_lng": end_lng,
            "meta": fit_meta,
            "_used": False,
        }
    except Exception:
        return None


def _iter_fit_blobs_from_zip(z: zipfile.ZipFile):
    names = z.namelist()
    for member in names:
        lower = member.lower()
        if lower.endswith(".fit"):
            try:
                yield member, z.read(member)
            except Exception:
                continue
            continue

        # Garmin export often stores FIT files in nested UploadedFiles_*.zip archives.
        if lower.endswith(".zip") and ("uploadedfiles" in lower or "fit" in lower):
            try:
                nested_raw = z.read(member)
                with zipfile.ZipFile(io.BytesIO(nested_raw)) as nested:
                    for n2 in nested.namelist():
                        if not n2.lower().endswith(".fit"):
                            continue
                        try:
                            yield f"{member}::{n2}", nested.read(n2)
                        except Exception:
                            continue
            except Exception:
                continue


def _build_fit_payload_index(z: zipfile.ZipFile) -> tuple[list[dict], dict[int, list[int]]]:
    if FitFile is None:
        return [], {}

    payloads: list[dict] = []
    minute_index: dict[int, list[int]] = {}

    for source_name, fit_blob in _iter_fit_blobs_from_zip(z):
        payload = _extract_fit_activity_payload(fit_blob, source_name)
        if not payload or not payload.get("start_time"):
            continue
        payloads.append(payload)
        idx = len(payloads) - 1
        minute_key = int(payload["start_time"].timestamp() // 60)
        minute_index.setdefault(minute_key, []).append(idx)

    return payloads, minute_index


def _match_fit_payload(start_dt: datetime | None, fit_payloads: list[dict], minute_index: dict[int, list[int]]) -> dict | None:
    if not start_dt or not fit_payloads or not minute_index:
        return None

    base_key = int(start_dt.timestamp() // 60)
    best_idx = None
    best_diff = None

    for delta in range(0, 61):  # +/- 60 minutes tolerance
        keys = [base_key] if delta == 0 else [base_key - delta, base_key + delta]
        for key in keys:
            for idx in minute_index.get(key, []):
                item = fit_payloads[idx]
                if item.get("_used"):
                    continue
                item_start = item.get("start_time")
                if not item_start:
                    continue
                diff = abs((item_start - start_dt).total_seconds())
                if diff > 3600:
                    continue
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    best_idx = idx
        if best_idx is not None and best_diff is not None and best_diff <= 120:
            break

    if best_idx is None:
        return None

    fit_payloads[best_idx]["_used"] = True
    return fit_payloads[best_idx]


def _load_garmin_profile_snapshot(z: zipfile.ZipFile) -> dict:
    snapshot = {
        "first_name": None,
        "last_name": None,
        "gender": None,
        "birth_date": None,
        "height_cm": None,
        "weight_kg": None,
        "vo2max": None,
        "resting_hr": None,
        "avg_sleep_hours": None,
        "avg_daily_steps": None,
        "avg_daily_stress": None,
    }
    names = z.namelist()
    lower_map = {n.lower(): n for n in names}

    # Basic identity from Garmin profile files.
    user_profile_member = lower_map.get("di_connect/di-connect-user/user_profile.json")
    if user_profile_member:
        try:
            data = _load_json_member_from_zip(z, user_profile_member)
            if isinstance(data, dict):
                snapshot["first_name"] = (data.get("firstName") or "").strip() or None
                snapshot["gender"] = (data.get("gender") or "").strip() or None
                snapshot["birth_date"] = (data.get("birthDate") or "").strip() or None
        except Exception:
            pass

    customer_member = lower_map.get("customer_data/customer.json")
    if customer_member:
        try:
            data = _load_json_member_from_zip(z, customer_member)
            if isinstance(data, dict):
                if not snapshot["first_name"]:
                    snapshot["first_name"] = (data.get("firstName") or "").strip() or None
                last_name = (data.get("lastName") or "").strip()
                snapshot["last_name"] = last_name or snapshot["last_name"]
                if not snapshot["birth_date"]:
                    dob = (data.get("dateOfBirth") or "").strip()
                    snapshot["birth_date"] = dob[:10] if dob else None
                if not snapshot["gender"]:
                    snapshot["gender"] = (data.get("gender") or "").strip() or None
        except Exception:
            pass

    # Body metrics.
    bio_metric_member = next(
        (n for n in names if n.lower().endswith("_userbiometricprofiledata.json")),
        None,
    )
    if bio_metric_member:
        try:
            data = _load_json_member_from_zip(z, bio_metric_member)
            row = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else None)
            if isinstance(row, dict):
                snapshot["height_cm"] = _safe_float(row.get("height"))
                w = _safe_float(row.get("weight"))
                if w is not None:
                    snapshot["weight_kg"] = round(w / 1000.0, 1) if w > 200 else round(w, 1)
                snapshot["vo2max"] = _safe_float(row.get("vo2Max"))
        except Exception:
            pass

    # Daily wellness aggregates (steps/stress/resting HR).
    uds_members = [n for n in names if "/di-connect-aggregator/udsfile_" in n.lower() and n.lower().endswith(".json")]
    daily_rows = {}
    for member in uds_members:
        try:
            payload = _load_json_member_from_zip(z, member)
            if not isinstance(payload, list):
                continue
            for row in payload:
                if not isinstance(row, dict):
                    continue
                d = (row.get("calendarDate") or "").strip()
                if not d:
                    continue
                daily_rows[d] = row
        except Exception:
            continue

    if daily_rows:
        steps = []
        stresses = []
        resting_hr = []
        for row in daily_rows.values():
            st = _safe_int(row.get("totalSteps"))
            if st is not None:
                steps.append(st)

            rh = _safe_int(row.get("restingHeartRate"))
            if rh is not None and rh > 0:
                resting_hr.append(rh)

            all_day_stress = row.get("allDayStress") or {}
            agg = all_day_stress.get("aggregatorList") if isinstance(all_day_stress, dict) else None
            if isinstance(agg, list):
                total = next((x for x in agg if isinstance(x, dict) and (x.get("type") or "").upper() == "TOTAL"), None)
                if total:
                    avg_stress = _safe_float(total.get("averageStressLevel"))
                    if avg_stress is not None:
                        stresses.append(avg_stress)

        if steps:
            snapshot["avg_daily_steps"] = int(round(sum(steps) / len(steps)))
        if stresses:
            snapshot["avg_daily_stress"] = round(sum(stresses) / len(stresses), 1)
        if resting_hr:
            snapshot["resting_hr"] = int(round(sum(resting_hr) / len(resting_hr)))

    # Sleep files: compute average sleep duration in hours.
    sleep_members = [n for n in names if "/di-connect-wellness/" in n.lower() and "sleepdata" in n.lower() and n.lower().endswith(".json")]
    sleep_hours = []
    for member in sleep_members:
        try:
            payload = _load_json_member_from_zip(z, member)
            if not isinstance(payload, list):
                continue
            for row in payload:
                if not isinstance(row, dict):
                    continue
                start_ts = (row.get("sleepStartTimestampGMT") or "").strip()
                end_ts = (row.get("sleepEndTimestampGMT") or "").strip()
                if start_ts and end_ts:
                    try:
                        start = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
                        end = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
                        delta_h = (end - start).total_seconds() / 3600.0
                        if 1.0 <= delta_h <= 16.0:
                            sleep_hours.append(delta_h)
                        continue
                    except Exception:
                        pass

                total_sec = 0
                for key in ("deepSleepSeconds", "lightSleepSeconds", "remSleepSeconds", "awakeSleepSeconds"):
                    v = _safe_float(row.get(key))
                    if v is not None:
                        total_sec += max(0.0, v)
                if total_sec > 0:
                    sleep_hours.append(total_sec / 3600.0)
        except Exception:
            continue

    if sleep_hours:
        snapshot["avg_sleep_hours"] = round(sum(sleep_hours) / len(sleep_hours), 1)

    return snapshot


def _apply_imported_profile_snapshot(user_id: int, snapshot: dict) -> None:
    user = db.session.get(User, int(user_id))
    if not user:
        return

    profile = UserProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.session.add(profile)

    first_name = (snapshot.get("first_name") or "").strip()
    last_name = (snapshot.get("last_name") or "").strip()
    if first_name and not (user.first_name or "").strip():
        user.first_name = first_name
    if last_name and not (user.last_name or "").strip():
        user.last_name = last_name

    if snapshot.get("gender") and not profile.gender:
        profile.gender = str(snapshot["gender"]).strip()[:20]

    birth_date = (snapshot.get("birth_date") or "").strip()
    if birth_date:
        try:
            profile_birth = datetime.strptime(birth_date[:10], "%Y-%m-%d").date()
            if not profile.birth_date:
                profile.birth_date = profile_birth
        except Exception:
            pass

    if snapshot.get("height_cm") is not None:
        profile.height_cm = round(float(snapshot["height_cm"]), 1)
    if snapshot.get("weight_kg") is not None:
        profile.weight_kg = round(float(snapshot["weight_kg"]), 1)
    if snapshot.get("vo2max") is not None:
        profile.vo2max = round(float(snapshot["vo2max"]), 1)
    if snapshot.get("resting_hr") is not None:
        profile.resting_hr = int(snapshot["resting_hr"])
    if snapshot.get("avg_sleep_hours") is not None:
        profile.avg_sleep_hours = round(float(snapshot["avg_sleep_hours"]), 1)
    if snapshot.get("avg_daily_steps") is not None:
        profile.avg_daily_steps = int(snapshot["avg_daily_steps"])
    if snapshot.get("avg_daily_stress") is not None:
        profile.avg_daily_stress = round(float(snapshot["avg_daily_stress"]), 1)

    profile.updated_at = datetime.now(timezone.utc)
    db.session.commit()


def _safe_json_dict(raw_value) -> dict:
    if isinstance(raw_value, dict):
        return dict(raw_value)
    if not raw_value:
        return {}
    try:
        data = json.loads(raw_value)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _prune_meta(meta: dict) -> dict:
    out = {}
    for key, value in (meta or {}).items():
        if value in (None, ""):
            continue
        if isinstance(value, (list, dict)) and len(value) == 0:
            continue
        out[key] = value
    return out


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
                external_id = (row.get("Activity ID") or row.get("Activity Id") or "").strip() or None

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

                if external_id:
                    existing = Activity.query.filter_by(
                        user_id=user_id,
                        source="strava",
                        external_id=external_id,
                    ).first()
                else:
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

                max_hr_val = row.get("Max Heart Rate", None)
                if max_hr_val in [None, "", "nan"]:
                    max_hr = None
                else:
                    max_hr = int(float(max_hr_val))

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
                    max_hr=max_hr,
                    moving_duration=int(moving),
                    elapsed_duration=int(elapsed),
                    source="strava",
                    external_id=external_id,
                    notes=desc,
                )

                db.session.add(new_activity)
                added_count += 1

            db.session.commit()
            return added_count, skipped_count


def import_garmin_zip_for_user(zip_file, user_id: int) -> tuple[int, int]:
    """Import Garmin data-export ZIP for given user.

    Source of activities:
    - DI_CONNECT/DI-Connect-Fitness/*_summarizedActivities.json
    """
    with zipfile.ZipFile(zip_file) as z:
        names = z.namelist()
        summary_members = [
            n for n in names
            if n.lower().endswith("_summarizedactivities.json") and "di-connect-fitness" in n.lower()
        ]
        if not summary_members:
            raise ValueError("Nie znaleziono plików *_summarizedActivities.json w archiwum Garmina")

        summarized_rows = []
        for member in summary_members:
            try:
                payload = _load_json_member_from_zip(z, member)
            except Exception:
                continue
            if isinstance(payload, list):
                for item in payload:
                    if isinstance(item, dict) and isinstance(item.get("summarizedActivitiesExport"), list):
                        summarized_rows.extend(item["summarizedActivitiesExport"])
            elif isinstance(payload, dict) and isinstance(payload.get("summarizedActivitiesExport"), list):
                summarized_rows.extend(payload["summarizedActivitiesExport"])

        if not summarized_rows:
            raise ValueError("Pliki Garmina nie zawierają żadnych aktywności do importu")

        # Import profile/wellness snapshot first (optional, best effort).
        try:
            snapshot = _load_garmin_profile_snapshot(z)
            _apply_imported_profile_snapshot(user_id=user_id, snapshot=snapshot)
        except Exception:
            # Do not fail activity import if profile snapshot fails.
            pass

        fit_payloads: list[dict] = []
        fit_minute_index: dict[int, list[int]] = {}
        if FitFile is not None:
            try:
                fit_payloads, fit_minute_index = _build_fit_payload_index(z)
            except Exception as e:
                app.logger.warning("Garmin FIT parse skipped for user %s: %s", user_id, e)

        # Deduplicate by Garmin activityId.
        added_count = 0
        skipped_count = 0
        seen_external = set()
        for row in summarized_rows:
            if not isinstance(row, dict):
                continue

            external_id = str(row.get("activityId") or "").strip()
            if not external_id:
                skipped_count += 1
                continue
            if external_id in seen_external:
                skipped_count += 1
                continue
            seen_external.add(external_id)

            start_dt = _ms_to_datetime_utc(row.get("startTimeGmt") or row.get("startTimeLocal") or row.get("beginTimestamp"))
            if not start_dt:
                skipped_count += 1
                continue

            existing = Activity.query.filter_by(
                user_id=user_id,
                source="garmin",
                external_id=external_id,
            ).first()

            raw_type = (row.get("activityType") or "").strip()
            sport_type = (row.get("sportType") or "").strip()
            activity_name = (row.get("name") or "").strip()
            mapped_type = _garmin_activity_type_to_app(raw_type, sport_type, activity_name)

            distance_m = _to_meters_from_garmin_distance(row.get("distance"))
            duration_s = _to_seconds_from_ms(row.get("duration"))
            moving_s = _to_seconds_from_ms(row.get("movingDuration")) or duration_s
            elapsed_s = _to_seconds_from_ms(row.get("elapsedDuration")) or duration_s

            avg_speed_mps = (distance_m / moving_s) if (distance_m > 0 and moving_s > 0) else None
            max_speed_raw = _safe_float(row.get("maxSpeed"))
            max_speed_mps = (max_speed_raw * 10.0) if max_speed_raw is not None else None
            elev_gain_raw = _safe_float(row.get("elevationGain"))
            elev_loss_raw = _safe_float(row.get("elevationLoss"))

            notes_parts = []
            if activity_name:
                notes_parts.append(activity_name)
            location = (row.get("locationName") or "").strip()
            if location:
                notes_parts.append(location)
            notes = " | ".join(notes_parts)[:1000] if notes_parts else None

            meta = {
                "eventTypeId": row.get("eventTypeId"),
                "manufacturer": row.get("manufacturer"),
                "lapCount": row.get("lapCount"),
                "averagePace": row.get("averagePace"),
                "averageMovingPace": row.get("averageMovingPace"),
                "bestLapTime": row.get("bestLapTime"),
                "moderateIntensityMinutes": row.get("moderateIntensityMinutes"),
                "vigorousIntensityMinutes": row.get("vigorousIntensityMinutes"),
                "differenceBodyBattery": row.get("differenceBodyBattery"),
                "avgRunCadence": row.get("avgRunCadence"),
                "maxRunCadence": row.get("maxRunCadence"),
                "avgStrideLength": row.get("avgStrideLength"),
                "avgPower": row.get("avgPower"),
                "maxPower": row.get("maxPower"),
                "normPower": row.get("normPower"),
                "aerobicTrainingEffect": row.get("aerobicTrainingEffect"),
                "anaerobicTrainingEffect": row.get("anaerobicTrainingEffect"),
                "trainingStressScore": row.get("trainingStressScore"),
                "workoutFeel": row.get("workoutFeel"),
                "workoutRpe": row.get("workoutRpe"),
                "splitSummaries": row.get("splitSummaries"),
                "sportTypeRaw": row.get("sportType"),
                "activityTypeRaw": row.get("activityType"),
            }
            fit_payload = _match_fit_payload(start_dt, fit_payloads, fit_minute_index)
            route_points = None
            if fit_payload:
                meta.update(_prune_meta(fit_payload.get("meta") or {}))
                route_points = fit_payload.get("route_points") or None

                # Fill route endpoints from FIT when available.
                if fit_payload.get("start_lat") is not None:
                    meta["fitRouteStartLat"] = fit_payload.get("start_lat")
                if fit_payload.get("start_lng") is not None:
                    meta["fitRouteStartLng"] = fit_payload.get("start_lng")
                if fit_payload.get("end_lat") is not None:
                    meta["fitRouteEndLat"] = fit_payload.get("end_lat")
                if fit_payload.get("end_lng") is not None:
                    meta["fitRouteEndLng"] = fit_payload.get("end_lng")

            meta = _prune_meta(meta)
            start_lat = _normalize_gps_coord(row.get("startLatitude"))
            start_lng = _normalize_gps_coord(row.get("startLongitude"))
            end_lat = _normalize_gps_coord(row.get("endLatitude"))
            end_lng = _normalize_gps_coord(row.get("endLongitude"))
            if fit_payload:
                if fit_payload.get("start_lat") is not None:
                    start_lat = fit_payload.get("start_lat")
                if fit_payload.get("start_lng") is not None:
                    start_lng = fit_payload.get("start_lng")
                if fit_payload.get("end_lat") is not None:
                    end_lat = fit_payload.get("end_lat")
                if fit_payload.get("end_lng") is not None:
                    end_lng = fit_payload.get("end_lng")

            route_points_json = None
            if route_points:
                try:
                    route_points_json = json.dumps(route_points, ensure_ascii=False, separators=(",", ":"))
                except Exception:
                    route_points_json = None

            if existing:
                # Keep manual edits, but enrich existing Garmin rows with extra stats and route.
                if not existing.activity_type or existing.activity_type == "other":
                    existing.activity_type = mapped_type
                if not existing.start_time:
                    existing.start_time = start_dt
                if (existing.duration or 0) <= 0 and duration_s > 0:
                    existing.duration = duration_s
                if (existing.distance or 0) <= 0 and distance_m > 0:
                    existing.distance = distance_m
                if existing.avg_hr is None:
                    existing.avg_hr = _safe_int(row.get("avgHr"))
                if existing.max_hr is None:
                    existing.max_hr = _safe_int(row.get("maxHr"))
                if (existing.moving_duration or 0) <= 0 and moving_s > 0:
                    existing.moving_duration = moving_s
                if (existing.elapsed_duration or 0) <= 0 and elapsed_s > 0:
                    existing.elapsed_duration = elapsed_s
                if existing.avg_speed_mps is None and avg_speed_mps is not None:
                    existing.avg_speed_mps = round(avg_speed_mps, 3)
                if existing.max_speed_mps is None and max_speed_mps is not None:
                    existing.max_speed_mps = round(max_speed_mps, 3)
                if existing.elevation_gain is None and elev_gain_raw is not None:
                    existing.elevation_gain = round(elev_gain_raw / 100.0, 2)
                if existing.elevation_loss is None and elev_loss_raw is not None:
                    existing.elevation_loss = round(elev_loss_raw / 100.0, 2)
                if existing.calories is None:
                    existing.calories = _safe_float(row.get("calories"))
                if existing.steps is None:
                    existing.steps = _safe_int(row.get("steps"))
                if existing.vo2max is None:
                    existing.vo2max = _safe_float(row.get("vO2MaxValue"))
                if existing.start_lat is None and start_lat is not None:
                    existing.start_lat = start_lat
                if existing.start_lng is None and start_lng is not None:
                    existing.start_lng = start_lng
                if existing.end_lat is None and end_lat is not None:
                    existing.end_lat = end_lat
                if existing.end_lng is None and end_lng is not None:
                    existing.end_lng = end_lng
                if not existing.route_points_json and route_points_json:
                    existing.route_points_json = route_points_json
                if not existing.device_id and row.get("deviceId") is not None:
                    existing.device_id = str(row.get("deviceId"))
                if not existing.sport_type and sport_type:
                    existing.sport_type = sport_type
                if not (existing.notes or "").strip() and notes:
                    existing.notes = notes

                merged_meta = _safe_json_dict(existing.metadata_json)
                merged_meta.update(meta)
                existing.metadata_json = json.dumps(_prune_meta(merged_meta), ensure_ascii=False)
                skipped_count += 1
                continue

            act = Activity(
                user_id=user_id,
                activity_type=mapped_type,
                start_time=start_dt,
                duration=duration_s,
                distance=distance_m,
                avg_hr=_safe_int(row.get("avgHr")),
                max_hr=_safe_int(row.get("maxHr")),
                moving_duration=moving_s,
                elapsed_duration=elapsed_s,
                avg_speed_mps=round(avg_speed_mps, 3) if avg_speed_mps is not None else None,
                max_speed_mps=round(max_speed_mps, 3) if max_speed_mps is not None else None,
                elevation_gain=(round(elev_gain_raw / 100.0, 2) if elev_gain_raw is not None else None),
                elevation_loss=(round(elev_loss_raw / 100.0, 2) if elev_loss_raw is not None else None),
                calories=_safe_float(row.get("calories")),
                steps=_safe_int(row.get("steps")),
                vo2max=_safe_float(row.get("vO2MaxValue")),
                start_lat=start_lat,
                start_lng=start_lng,
                end_lat=end_lat,
                end_lng=end_lng,
                route_points_json=route_points_json,
                source="garmin",
                external_id=external_id,
                device_id=str(row.get("deviceId")) if row.get("deviceId") is not None else None,
                sport_type=sport_type or None,
                metadata_json=json.dumps(meta, ensure_ascii=False),
                notes=notes,
            )
            db.session.add(act)
            added_count += 1

        db.session.commit()
        return added_count, skipped_count


def import_activity_archive_for_user(zip_file, user_id: int) -> tuple[str, int, int]:
    """Auto-detect archive source and import workouts.

    Returns: (source_kind, added_count, skipped_count)
    """
    source_kind = detect_activity_archive_type(zip_file)
    _rewind_fileobj(zip_file)
    if source_kind == "strava":
        added, skipped = import_strava_zip_for_user(zip_file, user_id)
        return source_kind, added, skipped
    if source_kind == "garmin":
        added, skipped = import_garmin_zip_for_user(zip_file, user_id)
        return source_kind, added, skipped
    if source_kind == "garmin_fit_only":
        raise ValueError(
            "Wykryto ZIP z samymi plikami .fit (częściowy eksport Garmina). "
            "Prześlij pełne archiwum Garmin Export z DI_CONNECT/DI-Connect-Fitness."
        )
    raise ValueError("Nie rozpoznano formatu ZIP (obsługiwane: Strava lub Garmin)")


def import_activity_archive_for_user_resilient(zip_file, user_id: int) -> tuple[str, int, int]:
    """Robust wrapper for archive import.

    Some hosting/platform setups expose upload streams in ways that occasionally fail
    on first pass. We retry by buffering bytes in-memory.
    """
    try:
        return import_activity_archive_for_user(zip_file, user_id)
    except Exception:
        _rewind_fileobj(zip_file)
        blob = None
        try:
            blob = zip_file.read()
        except Exception:
            blob = None
        if not blob:
            raise
        buf = io.BytesIO(blob)
        return import_activity_archive_for_user(buf, user_id)


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
        selected_sports = _normalize_focus_sports(request.form.getlist("weekly_focus_sports"))

        zip_file = request.files.get("strava_zip")

        if not email or not password:
            flash(tr("Email i hasło są wymagane.", "Email and password are required."))
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

        profile = UserProfile(
            user_id=user.id,
            weekly_focus_sports=",".join(selected_sports),
            primary_sports=",".join(selected_sports),
        )
        for sport in selected_sports:
            field_name = TARGET_SPORT_FIELDS.get(sport)
            if field_name:
                setattr(profile, field_name, 1)
        _sync_legacy_weekly_goal(profile)
        db.session.add(profile)
        db.session.commit()

        login_user(user)
        session["profile_prompt_seen"] = False

        # ZIP jest opcjonalny podczas rejestracji.
        if zip_file and getattr(zip_file, "filename", ""):
            try:
                source_kind, added, skipped = import_activity_archive_for_user_resilient(zip_file, user.id)
                compute_profile_defaults_from_history(user.id)
                flash(
                    tr(
                        f"Konto utworzone. ZIP ({source_kind}) zaimportowany: {added} aktywności (pominięto {skipped} duplikatów).",
                        f"Account created. ZIP ({source_kind}) imported: {added} activities (skipped {skipped} duplicates).",
                    )
                )
            except Exception as e:
                app.logger.exception("ZIP import failed during registration: %s", e)
                flash(
                    tr(
                        f"Konto utworzone, ale import ZIP się nie udał ({str(e)[:180]}).",
                        f"Account created, but ZIP import failed ({str(e)[:180]}).",
                    )
                )
        else:
            flash(
                tr(
                    "Konto utworzone. Możesz od razu zacząć i uzupełnić profil później.",
                    "Account created. You can start now and complete your profile later.",
                )
            )

        return redirect(url_for("index"))

    return render_template(
        "register.html",
        target_sport_keys=TARGET_SPORT_ORDER,
        focus_sports=["run", "gym"],
    )


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
        if user.onboarding_completed:
            session["profile_prompt_seen"] = True
        else:
            session.setdefault("profile_prompt_seen", False)
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
        selected_sports = _normalize_focus_sports(request.form.getlist("weekly_focus_sports"))
        profile.weekly_focus_sports = ",".join(selected_sports)
        for sport, field_name in TARGET_SPORT_FIELDS.items():
            if sport in selected_sports:
                setattr(profile, field_name, _to_int(request.form.get(field_name)) or 0)
            else:
                setattr(profile, field_name, 0)
        profile.coach_style = _clip(request.form.get("coach_style"), 40)
        profile.risk_tolerance = _clip(request.form.get("risk_tolerance"), 40)
        profile.training_priority = _clip(request.form.get("training_priority"), 40)
        profile.target_time_text = _clip(request.form.get("target_time_text"), 80)
        experience_text = _clip(request.form.get("experience_text"), 10000)
        context_text = _clip(request.form.get("context_text"), 10000)
        if experience_text and context_text:
            profile.experience_text = (experience_text + "\n" + context_text).strip()[:10000]
        else:
            profile.experience_text = experience_text or context_text

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

        _sync_legacy_weekly_goal(profile)
        current_user.onboarding_completed = True
        try:
            db.session.commit()
        except Exception as e:
            app.logger.exception("Onboarding save failed for user %s: %s", current_user.id, e)
            db.session.rollback()
            flash(tr("Nie udało się zapisać profilu. Skróć wpisy i spróbuj ponownie.", "Could not save profile. Please shorten inputs and try again."))
            return redirect(url_for("onboarding"))

        session["profile_prompt_seen"] = True
        flash(tr("Dzięki! Profil zapisany. Możesz korzystać z dashboardu.", "Thanks! Profile saved. You can now use the dashboard."))
        return redirect(url_for("index"))

    focus_sports, target_values = _build_weekly_target_form_context(profile)
    return render_template(
        "onboarding.html",
        profile=profile,
        target_sport_keys=TARGET_SPORT_ORDER,
        target_sport_fields=TARGET_SPORT_FIELDS,
        focus_sports=focus_sports,
        target_values=target_values,
    )


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
                source_kind, added, skipped = import_activity_archive_for_user_resilient(zip_file, current_user.id)
                compute_profile_defaults_from_history(current_user.id)
                flash(
                    tr(
                        f"Zaimportowano {added} aktywności z archiwum {source_kind} (pominięto {skipped} duplikatów).",
                        f"Imported {added} activities from {source_kind} archive (skipped {skipped} duplicates).",
                    )
                )
            except Exception as e:
                app.logger.exception("ZIP reimport failed for user %s: %s", current_user.id, e)
                flash(tr(f"Import nieudany: {str(e)[:180]}", f"Import failed: {str(e)[:180]}"))
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
            selected_sports = _normalize_focus_sports(request.form.getlist("weekly_focus_sports"))
            profile_obj.weekly_focus_sports = ",".join(selected_sports)
            for sport, field_name in TARGET_SPORT_FIELDS.items():
                if sport in selected_sports:
                    setattr(profile_obj, field_name, _to_int(request.form.get(field_name)) or 0)
                else:
                    setattr(profile_obj, field_name, 0)
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

            _sync_legacy_weekly_goal(profile_obj)
            db.session.commit()
        except Exception as e:
            app.logger.exception("Profile save failed for user %s: %s", current_user.id, e)
            db.session.rollback()
            flash(tr("Nie udało się zapisać profilu. Skróć wpisy i spróbuj ponownie.", "Could not save profile. Please shorten inputs and try again."))
            return redirect(url_for("profile"))

        flash(tr("Zapisano zmiany w profilu.", "Profile changes saved."))
        return redirect(url_for("profile"))

    try:
        focus_sports, target_values = _build_weekly_target_form_context(profile_obj)
        return render_template(
            "profile.html",
            profile=profile_obj,
            current_injury_text=get_current_injury_text(current_user.id),
            target_sport_keys=TARGET_SPORT_ORDER,
            target_sport_fields=TARGET_SPORT_FIELDS,
            focus_sports=focus_sports,
            target_values=target_values,
        )
    except Exception as e:
        app.logger.exception("Profile render failed for user %s: %s", current_user.id, e)
        return (
            tr(
                "Błąd renderowania profilu. Sprawdź logi serwera.",
                "Profile render error. Check server logs.",
            ),
            500,
        )


@app.route("/profile/delete_account", methods=["POST"])
@login_required
def delete_account():
    password = (request.form.get("password") or "").strip()
    confirm_phrase = (request.form.get("confirm_phrase") or "").strip().lower()
    allowed_phrases = {"usun konto", "usuń konto", "delete account"}

    if not password:
        flash(tr("Podaj hasło, aby usunąć konto.", "Enter your password to delete account."))
        return redirect(url_for("profile"))

    if confirm_phrase not in allowed_phrases:
        flash(
            tr(
                "Wpisz dokładnie „USUN KONTO” w potwierdzeniu usunięcia.",
                "Type exactly “DELETE ACCOUNT” in the confirmation field.",
            )
        )
        return redirect(url_for("profile"))

    if not check_password_hash(current_user.password_hash, password):
        flash(tr("Nieprawidłowe hasło.", "Invalid password."))
        return redirect(url_for("profile"))

    user_id = current_user.id
    try:
        logout_user()
        user = db.session.get(User, int(user_id))
        if user:
            db.session.delete(user)
            db.session.commit()
        flash(tr("Konto zostało usunięte.", "Account has been deleted."))
        return redirect(url_for("register"))
    except Exception as e:
        app.logger.exception("Delete account failed for user %s: %s", user_id, e)
        db.session.rollback()
        flash(tr("Nie udało się usunąć konta.", "Could not delete account."))
        return redirect(url_for("profile"))


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
    show_profile_prompt = (not current_user.onboarding_completed) and (not session.get("profile_prompt_seen", False))
    if show_profile_prompt:
        session["profile_prompt_seen"] = True

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
    profile_obj = UserProfile.query.filter_by(user_id=current_user.id).first()
    weekly_targets = _get_weekly_session_targets(profile_obj)
    weekly_done = _count_week_sessions_by_target(
        user_id=current_user.id,
        week_start=week_start,
        week_end=today,
    )
    focus_sports = _get_focus_sports(profile_obj, weekly_targets)

    weekly_goal_items = []
    for bucket in focus_sports:
        target_val = int(weekly_targets.get(bucket, 0) or 0)
        if target_val <= 0:
            continue
        done_val = int(weekly_done.get(bucket, 0) or 0)
        weekly_goal_items.append(f"{_target_bucket_label(bucket)}: {done_val}/{target_val}")

    done_total = sum(int(weekly_done.get(k, 0) or 0) for k in focus_sports)
    weekly_goal_target = max(1, sum(int(weekly_targets.get(k, 0) or 0) for k in focus_sports))
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
        show_profile_prompt=show_profile_prompt,
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
    weekly_targets = _get_weekly_session_targets(profile_obj)
    weekly_goal = int(weekly_targets.get("run", 0) or 0)
    if weekly_goal <= 0:
        weekly_goal = int(profile_obj.weekly_goal_workouts or 3) if profile_obj else 3
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
    today_dt = datetime.now().date()
    week_execution_ctx = get_week_execution_context(
        user_id=current_user.id,
        week_start=today_dt - timedelta(days=today_dt.weekday()),
        week_end=today_dt,
    )
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
    today_dt = datetime.now().date()
    checkin_signals = get_checkin_signal_snapshot(user_id=current_user.id, days=14)
    goal_progress = build_goal_progress(
        user_id=current_user.id,
        profile_obj=profile_obj,
        range_days=30,
        stats=compute_stats(current_user.id, 30),
    )

    today = today_dt.strftime("%Y-%m-%d")
    days_to_generate = max(1, 7 - today_dt.weekday())  # do niedzieli włącznie
    week_start = today_dt - timedelta(days=today_dt.weekday())
    weekly_targets = _get_weekly_session_targets(profile_obj)
    weekly_done = _count_week_sessions_by_target(
        user_id=current_user.id,
        week_start=week_start,
        week_end=today_dt,
    )
    focus_sports = _get_focus_sports(profile_obj, weekly_targets)
    weekly_remaining = {
        k: max(0, int(weekly_targets.get(k, 0) or 0) - int(weekly_done.get(k, 0) or 0))
        for k in focus_sports
    }
    weekly_target_context = {
        "week_start": week_start.isoformat(),
        "today": today_dt.isoformat(),
        "selected_sports": focus_sports,
        "targets": {k: int(weekly_targets.get(k, 0) or 0) for k in focus_sports},
        "done_until_today": {k: int(weekly_done.get(k, 0) or 0) for k in focus_sports},
        "remaining_to_fill": weekly_remaining,
    }

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

{week_execution_ctx}

SYGNAŁY CHECK-IN:
{json.dumps(checkin_signals, ensure_ascii=False)}

KONTEKST CELU:
{json.dumps(goal_progress, ensure_ascii=False) if goal_progress else "Brak aktywnego celu z datą."}

CELE TYGODNIOWE UŻYTKOWNIKA (MUSISZ UWZGLĘDNIĆ):
{json.dumps(weekly_target_context, ensure_ascii=False)}

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
- Priorytet: plan na pozostałe dni tygodnia powinien dążyć do domknięcia `remaining_to_fill`.
- Nie dokładamy zbędnie modalności z `remaining_to_fill = 0`, chyba że wymagają tego regeneracja lub bezpieczeństwo.
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
Masz screenshot aktywności z Garmin/Strava (PL lub EN). Wyciągnij dane i zwróć WYŁĄCZNIE JSON (bez markdown).

FORMAT:
{
  "activity_type": "run|ride|swim|workout|weighttraining|yoga|hike|walk|other",
  "distance_km": number|null,
  "duration_min": number|null,
  "avg_hr": number|null,
  "start_date": "YYYY-MM-DD"|null,
  "start_time": "HH:MM"|null,
  "distance_raw": "string|null",
  "duration_raw": "string|null",
  "avg_hr_raw": "string|null"
}

ZASADY:
- Obsługuj etykiety PL i EN (np. Dystans/Distance, Czas/Moving Time/Elapsed Time, Średnie tętno/Avg Heart Rate).
- distance_km zawsze w kilometrach. Jeśli widać metry (m), przelicz na km.
- duration_min zawsze w minutach (może pochodzić z MM:SS lub HH:MM:SS).
- avg_hr = ŚREDNIE tętno (nie max).
- Nie myl kalorii, przewyższenia, tempa ani max HR z dystansem/czasem/avg_hr.
- start_date/start_time wyciągaj z linii typu: "Today at 11:53 AM", "4 lut @ 20:31", "January 29, 2026 at 6:51 PM".
- Jeśli brak wartości, daj null.
        """.strip()

        resp = vision_model.generate_content([
            prompt,
            {"mime_type": _guess_mime(image_path), "data": img_bytes}
        ])

        raw = (getattr(resp, "text", None) or "").strip()

        def _load_json_relaxed(txt: str):
            try:
                return json.loads(txt)
            except Exception:
                pass
            m = re.search(r"\{.*\}", txt, re.DOTALL)
            if not m:
                return None
            try:
                return json.loads(m.group(0))
            except Exception:
                return None

        data = _load_json_relaxed(raw)
        if not isinstance(data, dict):
            # Fallback: best-effort regex extraction from free text.
            fallback = _extract_activity_from_free_text(raw)
            has_any_fallback = any([
                fallback.get("distance_km"),
                fallback.get("duration_min"),
                fallback.get("avg_hr"),
                fallback.get("start_date"),
                fallback.get("start_time"),
                fallback.get("activity_type") not in (None, "", "other"),
            ])
            if has_any_fallback:
                return fallback, None
            return {}, tr(
                "Model zwrócił nieczytelny format odpowiedzi (nie-JSON). Spróbuj wyraźniejszy screenshot.",
                "Model returned an unreadable response format (non-JSON). Try a clearer screenshot.",
            )

        # Normalization with key fallbacks (model can use slightly different keys).
        out = {
            "activity_type": _normalize_activity_type_value(
                data.get("activity_type")
                or data.get("activity")
                or data.get("type")
                or data.get("sport")
            ),
            "distance_km": None,
            "duration_min": None,
            "avg_hr": None,
            "start_date": None,
            "start_time": None,
        }

        # Distance
        distance_sources = [
            ("distance_km", "km"),
            ("distance", None),
            ("distance_raw", None),
            ("distance_text", None),
            ("dystans", None),
            ("distance_m", "m"),
            ("meters", "m"),
            ("metres", "m"),
        ]
        for key, unit_hint in distance_sources:
            if key not in data or data.get(key) in (None, ""):
                continue
            if unit_hint == "m":
                meters = _parse_decimal_input(data.get(key))
                dist_km = (meters / 1000.0) if meters is not None else None
            elif unit_hint == "km":
                dist_km = _parse_decimal_input(data.get(key))
            else:
                dist_km = _parse_distance_km_input(data.get(key), out["activity_type"])
            if dist_km is not None and dist_km >= 0:
                out["distance_km"] = dist_km
                break

        # Duration
        duration_sources = [
            "duration_min",
            "moving_time",
            "elapsed_time",
            "duration",
            "duration_raw",
            "duration_text",
            "czas",
        ]
        for key in duration_sources:
            if key not in data or data.get(key) in (None, ""):
                continue
            dur = _parse_minutes_input(data.get(key))
            if dur is not None and dur >= 0:
                out["duration_min"] = dur
                break

        # HR (average only)
        hr_sources = [
            "avg_hr",
            "avg_heart_rate",
            "average_heart_rate",
            "avg_hr_raw",
            "srednie_tetno",
            "średnie_tętno",
        ]
        for key in hr_sources:
            if key not in data or data.get(key) in (None, ""):
                continue
            hr = _parse_decimal_input(data.get(key))
            if hr is not None and 40 <= hr <= 230:
                out["avg_hr"] = int(round(hr))
                break

        date_sources = ["start_date", "activity_date", "date", "workout_date", "start_datetime", "when"]
        for key in date_sources:
            if key not in data or data.get(key) in (None, ""):
                continue
            parsed_date = _normalize_date_input(str(data.get(key)))
            if parsed_date:
                out["start_date"] = parsed_date
                break

        time_sources = ["start_time", "activity_time", "clock_time", "start_datetime", "when"]
        for key in time_sources:
            if key not in data or data.get(key) in (None, ""):
                continue
            parsed_time = _normalize_time_input(str(data.get(key)))
            if parsed_time:
                out["start_time"] = parsed_time
                break

        # Fill missing fields from free-text fallback extracted from raw model response.
        fb = _extract_activity_from_free_text(raw)
        if out.get("activity_type") in ("", "other") and fb.get("activity_type") not in ("", "other", None):
            out["activity_type"] = fb.get("activity_type")
        for field in ("distance_km", "duration_min", "avg_hr", "start_date", "start_time"):
            if out.get(field) in (None, "") and fb.get(field) not in (None, ""):
                out[field] = fb.get(field)

        # Sanity bounds.
        if out["distance_km"] is not None and out["distance_km"] > 2000:
            out["distance_km"] = out["distance_km"] / 1000.0
        if out["duration_min"] is not None and out["duration_min"] > 24 * 60:
            # Likely seconds accidentally parsed as minutes.
            out["duration_min"] = out["duration_min"] / 60.0
        if out["avg_hr"] is not None and not (40 <= out["avg_hr"] <= 230):
            out["avg_hr"] = None

        # Prefer "today" if screenshot text implies it, or if date is likely unreliable.
        base_any = (
            (out.get("distance_km") is not None and out.get("distance_km", 0) > 0)
            or (out.get("duration_min") is not None and out.get("duration_min", 0) > 0)
            or (out.get("avg_hr") is not None and out.get("avg_hr", 0) > 0)
            or (out.get("activity_type") and out.get("activity_type") != "other")
        )
        if base_any:
            raw_lower = raw.lower()
            today = datetime.now().date()
            if any(k in raw_lower for k in ("today", "dzis", "dziś")):
                out["start_date"] = today.isoformat()
            elif "yesterday" in raw_lower or "wczoraj" in raw_lower:
                out["start_date"] = (today - timedelta(days=1)).isoformat()
            else:
                if not out.get("start_date"):
                    out["start_date"] = today.isoformat()
                else:
                    try:
                        parsed = date.fromisoformat(out["start_date"])
                        has_year = re.search(r"\b20\d{2}\b", raw_lower) is not None
                        month_tokens = (
                            "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
                            "sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paz", "paź", "lis", "gru",
                        )
                        has_month_hint = any(tok in raw_lower for tok in month_tokens)
                        if (not has_year and not has_month_hint) and abs((today - parsed).days) > 60:
                            out["start_date"] = today.isoformat()
                    except Exception:
                        out["start_date"] = today.isoformat()

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
    date_str = _normalize_date_input(date_str) or ""
    time_str = _normalize_time_input(time_str) or ""
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

    duration_min = _parse_minutes_input(request.form.get("duration_min"))
    distance_km = _parse_decimal_input(request.form.get("distance_km"))
    avg_hr = _parse_decimal_input(request.form.get("avg_hr"))
    avg_pace = _parse_decimal_input(request.form.get("avg_pace_min_km"))

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
        source="manual",
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
                        source="checkin",
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
                source="checkin",
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
    metric_cards = _build_activity_detail_payload(activity)
    return render_template(
        "activity.html",
        activity=activity,
        plans=plans,
        metric_cards=metric_cards,
    )


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
        source_kind, added_count, skipped_count = import_activity_archive_for_user_resilient(file, current_user.id)
        flash(
            tr(
                f"Sukces! Zaimportowano {added_count} treningów z archiwum {source_kind}. Pominięto {skipped_count}.",
                f"Success! Imported {added_count} workouts from {source_kind} archive. Skipped {skipped_count}.",
            )
        )
        try:
            compute_profile_defaults_from_history(current_user.id)
        except Exception:
            pass
    except Exception as e:
        app.logger.exception("ZIP import endpoint error for user %s: %s", current_user.id, e)
        flash(tr(f"Błąd pliku ZIP: {str(e)[:180]}", f"ZIP file error: {str(e)[:180]}"))

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

    duration_val = _parse_minutes_input(duration_min)
    if duration_min not in (None, "") and duration_val is not None:
        activity.duration = max(0, int(round(duration_val * 60)))

    distance_val = _parse_decimal_input(distance_km)
    if distance_km not in (None, "") and distance_val is not None:
        activity.distance = max(0.0, distance_val) * 1000.0

    hr_val = _parse_decimal_input(avg_hr)
    if avg_hr not in (None, "") and hr_val is not None:
        activity.avg_hr = int(round(hr_val))

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
        try:
            ex.sets = max(0, int(data["sets"]))
        except Exception:
            ex.sets = 0
    if "reps" in data:
        try:
            ex.reps = max(0, int(data["reps"]))
        except Exception:
            ex.reps = 0
    if "weight" in data:
        w = str(data["weight"]).replace(",", ".")
        try:
            val = float(w)
            ex.weight = max(0.0, val)
        except Exception:
            ex.weight = 0.0

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
        try:
            sets_val = max(0, int(item.get("sets") or 0))
        except Exception:
            sets_val = 0
        try:
            reps_val = max(0, int(item.get("reps") or 0))
        except Exception:
            reps_val = 0
        try:
            weight_val = float(item.get("weight") or 0)
            weight_val = max(0.0, weight_val)
        except Exception:
            weight_val = 0.0

        ex = Exercise(
            user_id=current_user.id,
            activity_id=activity.id,
            name=item.get("name"),
            sets=sets_val,
            reps=reps_val,
            weight=weight_val,
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
