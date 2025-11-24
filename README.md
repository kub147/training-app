# Training App - Prosty menedżer treningów

## Instalacja

1. Uruchom ten skrypt:
   chmod +x setup.sh
   ./setup.sh

2. Zainstaluj zależności:
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # lub: venv\Scripts\activate  # Windows
   pip install -r requirements.txt

3. Skonfiguruj .env:
   cp .env.example .env
   # Edytuj .env i dodaj klucze API

4. Uruchom:
   python app.py

5. Otwórz: http://localhost:5000

## Jak zdobyć klucze API:

Gemini:
- https://makersuite.google.com/app/apikey

Strava:
- https://www.strava.com/settings/api
- Stwórz aplikację
- Authorization Callback Domain: localhost
