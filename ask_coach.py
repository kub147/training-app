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
    execution_context: str,
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

{execution_context}

SYGNAŁY CHECK-IN (JSON):
{checkin_signals}

KONTEKST CELU (JSON):
{goal_context}

{chat_history}

NOWE PYTANIE:
{user_msg}

ZASADY ODPOWIEDZI:
- Pisz naturalnie, jak realny trener w rozmowie 1:1. Nie brzmisz jak sztywny formularz.
- Najpierw odpowiedz bezpośrednio na pytanie użytkownika (2-6 krótkich zdań), dopiero potem ewentualne wskazówki.
- Nie używaj stałego szablonu nagłówków w każdej odpowiedzi. To ma być konwersacja, nie raport.
- Jeśli użytkownik pyta o <konkretny trening/plan tygodnia>, wtedy użyj lekkiej struktury:
  <b>Plan</b>, <b>Dlaczego</b>, <b>Na podstawie czego</b>, <b>Na co uważać</b>.
- Jeśli użytkownik pyta ogólnie (motywacja, sens planu, regeneracja, ból, technika), odpowiadaj po ludzku bez formalnych sekcji.
- Uzasadniaj rekomendacje faktami z kontekstu, ale wplecionymi naturalnie (1-3 najważniejsze fakty, bez długiej listy).
- Respektuj pole <STYL TRENERA> z profilu (concise/motivating/technical/balanced), ale nadal odpowiadaj ludzko i jasno.
- Gdy ma to sens, odnieś odpowiedź do celu i fazy przygotowania (base/build/taper/post-race), ale tylko jeśli pomaga zrozumieć odpowiedź.
- Jeśli brakuje krytycznej informacji, zadaj maksymalnie 1 krótkie pytanie doprecyzowujące.
- Używaj prostego HTML tylko gdy pomaga czytelności (<b>, <br>, opcjonalnie <ul><li>). Bez Markdown.
- Unikaj powtórzeń, sztucznego tonu i klisz typu "na podstawie wskazane regularne elementy".
"""
