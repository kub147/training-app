import os
from dotenv import load_dotenv

load_dotenv()

# Magia: Pobieramy dokładną ścieżkę do folderu, w którym leży ten plik
basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key'

    # ZMIANA: Sklejamy ścieżkę folderu z nazwą pliku bazy
    # Dzięki temu aplikacja zawsze trafi do tego samego pliku
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///' + os.path.join(basedir, 'training.db')

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    STRAVA_CLIENT_ID = os.environ.get('STRAVA_CLIENT_ID')
    STRAVA_CLIENT_SECRET = os.environ.get('STRAVA_CLIENT_SECRET')