import google.generativeai as genai
import json
from datetime import datetime

class AICoach:
    def __init__(self, api_key):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-pro')
    
    def generate_plan(self, goal, target_date, activities):
        acts = "\n".join([f"- {a.activity_type}: {a.duration//60}min, {a.distance/1000:.1f}km" 
                          for a in activities[:10]])
        
        days = (target_date - datetime.now().date()).days
        
        prompt = f"""Stwórz prosty plan treningowy na 7 dni.
Cel: {goal}
Dni do celu: {days}
Ostatnie treningi:
{acts}

Zwróć TYLKO JSON:
{{
  "days": [
    {{"day": 1, "type": "bieg/silownia/odpoczynek", "opis": "krótki opis"}},
    ...
  ]
}}"""
        
        response = self.model.generate_content(prompt)
        text = response.text
        
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        return {"days": []}
    
    def suggest_workout(self, activity_type, goal, last_activities):
        acts = "\n".join([f"- {a.activity_type}: {a.duration//60}min" 
                          for a in last_activities[:5]])
        
        prompt = f"""Zaproponuj trening na dziś.
Typ: {activity_type}
Cel: {goal}
Ostatnie treningi:
{acts}

Zwróć TYLKO JSON:
{{
  "rozgrzewka": "opis",
  "glowna_czesc": "opis",
  "chlodzenie": "opis",
  "czas": 60
}}"""
        
        response = self.model.generate_content(prompt)
        text = response.text
        
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        return {}
