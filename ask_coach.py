from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable


def build_chat_history(messages: Iterable, max_age_days: int = 14) -> str:
    """Buduje historię czatu do promptu.

    Zasada: zachowujemy ciągłość, ale ograniczamy ryzyko 'zalegających' faktów typu
    'jutro jadę do Walencji' — dlatego:
    - podajemy datę każdej wiadomości,
    - ucinamy bardzo stare wiadomości (domyślnie >14 dni),
    - prosimy model, żeby traktował stare, czasowo-wrażliwe treści jako NIEAKTUALNE,
      o ile użytkownik ich nie potwierdzi.
    """
    now = datetime.utcnow()
    kept = []
    for m in messages:
        ts = getattr(m, "timestamp", None) or getattr(m, "created_at", None) or now
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except Exception:
                ts = now
        if (now - ts) <= timedelta(days=max_age_days):
            kept.append((ts, m))

    kept.sort(key=lambda x: x[0])

    out = []
    out.append("HISTORIA ROZMOWY (z datami):")
    out.append("WAŻNE: Jeśli w historii padają zwroty typu 'jutro', 'za tydzień', traktuj je względem DATY danej wiadomości, nie względem dziś.")
    out.append("WAŻNE: Stare informacje czasowo-wrażliwe (podróże, krótkie plany, 'niedawno') uznaj za nieaktualne, jeśli użytkownik ich dziś nie potwierdzi.")
    for ts, m in kept:
        role = "Zawodnik" if getattr(m, "sender", "") == "user" else "Trener"
        out.append(f"[{ts.strftime('%Y-%m-%d')}] {role}: {getattr(m, 'content', '')}")
    return "\n".join(out)


def build_chat_prompt(
    *,
    today_iso: str,
    profile_state: str,
    weekly_agg: str,
    recent_details: str,
    recent_checkins: str,
    checkin_signals: str,
    goal_context: str,
    chat_history: str,
    user_msg: str,
) -> str:
    return f"""Jesteś doświadczonym trenerem sportowym.

DZIŚ: {today_iso}

KONTEKST (warstwowo, nie pełna baza):
{profile_state}

{weekly_agg}

{recent_details}

{recent_checkins}

SYGNAŁY CHECK-IN (JSON):
{checkin_signals}

KONTEKST CELU (JSON):
{goal_context}

{chat_history}

NOWE PYTANIE:
{user_msg}

ZASADY ODPOWIEDZI:
- Krótko i konkretnie.
- Jeśli potrzebujesz doprecyzowania (np. ból, dostępność), zadaj 1-2 pytania.
- Używaj HTML do formatowania (<b>, <br>, <ul><li>). Bez Markdown.
- Każdą rekomendację uzasadnij: <b>Dlaczego</b> + <b>Na podstawie czego</b> (profil, ostatnie treningi, check-iny).
- Trzymaj się stałego kontraktu odpowiedzi (zawsze, w tej kolejności):
  1) <b>Plan</b> (maks 3 krótkie punkty),
  2) <b>Faza przygotowania</b> (base/build/taper/post-race + 1 zdanie),
  3) <b>Dlaczego</b>,
  4) <b>Na podstawie czego</b> (minimum 3 fakty w <ul><li>),
  5) <b>Ryzyko / uwaga</b> (1 krótki punkt),
  6) <b>Pytanie kontrolne</b> (dokładnie 1 pytanie).
"""
