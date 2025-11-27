import google.generativeai as genai
import json
from datetime import datetime


class AICoach:
    def __init__(self, api_key):
        genai.configure(api_key=api_key)
        # ZMIANA: Używamy nowszego i szybszego modelu
        self.model = genai.GenerativeModel('gemini-2.5-pro')

    def generate_plan(self, goal, target_date, activities):
        # Formatujemy historię aktywności
        acts = "\n".join([f"- {a.activity_type}: {a.duration // 60}min, {a.distance / 1000:.1f}km"
                          for a in activities[:10]])

        days_left = (target_date - datetime.now().date()).days

        prompt = f"""Jesteś trenerem personalnym. Stwórz plan treningowy na 7 dni w formacie JSON.
Cel użytkownika: {goal}
Dni do celu: {days_left}
Ostatnie 10 treningów:
{acts}

Wymagany format JSON (zwróć TYLKO czysty JSON, bez znaczników markdown ```json):
{{
  "days": [
    {{"day": 1, "type": "bieg/rower/siłownia/odpoczynek", "opis": "szczegóły treningu"}},
    ...
  ]
}}"""

        try:
            response = self.model.generate_content(prompt)
            text = response.text

            # Czyszczenie odpowiedzi z ewentualnych znaczników markdown
            text = text.replace('```json', '').replace('```', '').strip()

            return json.loads(text)
        except Exception as e:
            print(f"Błąd AI: {e}")
            return {"days": []}

    def suggest_workout(self, activity_type, goal, last_activities):
        acts = "\n".join([f"- {a.activity_type}: {a.duration // 60}min"
                          for a in last_activities[:5]])

        prompt = f"""Jesteś trenerem. Zaproponuj jeden konkretny trening na dziś w formacie JSON.
Typ treningu: {activity_type}
Cel użytkownika: {goal}
Ostatnie treningi:
{acts}

Wymagany format JSON (zwróć TYLKO czysty JSON, bez znaczników markdown):
{{
  "rozgrzewka": "dokładny opis rozgrzewki",
  "glowna_czesc": "szczegóły głównego zadania",
  "chlodzenie": "opis wyciszenia",
  "czas": 60
}}"""

        try:
            response = self.model.generate_content(prompt)
            text = response.text

            # Czyszczenie odpowiedzi
            text = text.replace('```json', '').replace('```', '').strip()

            return json.loads(text)
        except Exception as e:
            print(f"Błąd AI: {e}")
            return {}