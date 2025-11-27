import os
import google.generativeai as genai
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Importujemy Twoją aplikację i modele, żeby mieć dostęp do bazy danych
from app import app
from models import Activity, Exercise, WorkoutPlan

# Ładujemy klucze (API KEY)
load_dotenv()

# Konfiguracja Gemini
genai.configure(api_key=os.environ.get('GEMINI_API_KEY'))
model = genai.GenerativeModel('models/gemini-2.5-pro')

# --- 1. TWOJA HISTORIA I PROFIL (Tutaj wpisz to, co chciałeś) ---
USER_PROFILE = """1. Dane ogólne

Imię i nazwisko: Jakub Wilk

Wiek: 20 lat (wiek sprawnościowy wg Garmin 18)

Płeć: mężczyzna

Wzrost: 176 cm

Masa: ~68 kg

Sprzęt: Garmin Forerunner 55, Asics Gel Pulse 15

Miejsce treningów: Porto – głównie asfalt, dobra pogoda, preferencja biegania bez deszczu

Preferowana pora: wieczory

Tryb życia: elastyczne popołudnia, zmienna liczba kroków (czasem 15–25k/dzień)

2. Parametry fizjologiczne

HR spoczynkowe: 67 bpm

HR średnie wysokie: 124 bpm

Średnia liczba oddechów: 13/min

Poziom stresu: 32/100

Szacowane HRmax: ~198 bpm (zmierzone podczas 10 km)

VO₂max: 55 (Garmin)

Forma: dobra, wysoka regeneracja, brak przetrenowania

3. Strefy tętna (Garmin / aktualne)

Z1: 101–120

Z2: 121–140

Z3: 141–160

Z4: 161–180

Z5: 181–198+

(profil AI bazujących na HR może używać tych stref bez korekt)

4. Wyniki sportowe

5 km: ~22:00

10 km: 52:00 (ostatni start – Porto 2025)

Prognozy Garmin:

5 km – 21 min

10 km – 46 min

21.1 km – 1:50

Maraton – 4:10

Najdłuższy bieg: 16 km

5. Obecny poziom aktywności

Średni kilometraż tygodniowy: ~9.5–10 km

Bieganie: 2–3 razy/tydzień

Siłownia: 2×/tydzień (preferowane oddzielone od biegania)

Basen: 1–2×/tydzień (ok. 2 km)

Inne aktywności: surfing, spacery, trekking, mobilność

Sen: 8–8.5 h

6. Trening siłowy

Czas: 90 min

Normy siłowe:

Wyciskanie: ~45 kg

Martwy ciąg: ~90 kg

Przysiad: 40–45 kg

Cel siłowni: wzmacnianie pod bieganie, ogólna siła, poprawa mobilności

Preferencja: nie łączyć biegania z siłownią w jeden dzień

7. Styl biegania i preferencje

Typy ulubione:

interwały krótkie (1–3 min),

easy run 30–40 min,

biegi tempowe,

1× długie wybieganie tygodniowo (do 90 min).

Problem na początku biegu: trudność w wejściu w stabilne tempo przez 5–10 min

Nawierzchnia: płasko, asfalt

Pogoda: unikanie deszczu

8. Ograniczenia i ryzyko kontuzji

Łatwo spięte: pachwiny, łydki

Historia: lekkie naderwanie pachwiny 2–3 lata temu (bez aktualnych ograniczeń)

Brak: przeciwwskazań zdrowotnych

Zalecenia: systematyczna mobilność + core + praca nad łydkami

9. Najtrudniejsze elementy podczas biegu

trudność w ustabilizowaniu tempa na początku

lekki dyskomfort nóg przy starcie biegu

preferowane spokojne wejście w trening (rozgrzewka 10 min)

10. Cele treningowe
Cele główne (TOP 3 priorytety AI):

Poprawa wyników

Zdrowie i brak kontuzji

Regularność i ogólna wydolność

Cele szczegółowe:

systematyczne zwiększanie kilometrażu (z 10 km → 20–30 km tygodniowo)

przygotowanie do półmaratonu w perspektywie 3–4 miesięcy

poprawa tempa biegowego

rozwój ogólnej wytrzymałości tlenowej

praca nad mobilnością

11. Możliwości czasowe

Bieganie: 30–50 min, 1× dłuższy bieg 75–90 min

Siłownia: 90 min

Basen: 45 min

12. Triathlon

luźna myśl, bez ustalonego dystansu

aktualnie brak dedykowanego planu tri

13. Rekomendowany przez AI mikrocykl treningowy (szablon)

(Twoja aplikacja może na tej podstawie generować dynamiczny harmonogram)

Tydzień – 3 biegi + 2 siłownie + 1 basen

Bieg 1: Easy 30–40 min (Z2) + 3–5 przebieżek

Bieg 2: Interwały (np. 6×1 min lub 5×2 min, Z4/Z5)

Bieg 3: Long Run 60–90 min (Z2)

Siłownia A: siła ogólna + core

Siłownia B: pośladki, stabilizacja, mobilność

Basen: 45 min tlenowo

Mobilność: 2–3 razy po 10–15 min

14. Charakterystyka pod AI

wysoka regeneracja

dobra zdolność do adaptacji i progresu

preferuje strukturę i różnorodność

treningi muszą być elastyczne względem pogody

zwykle trenowane wieczorem

mile widziane: czytelne, proste jednostki, bez skomplikowanych stref

15. Uwagi dla algorytmu AI

Nie łączyć siłowni i biegania w jeden dzień.

Zawsze 10 min rozgrzewki przed interwałami / tempem.

Ułatwić wejście w tempo – pierwsze 5–10 min bardzo spokojnie.

Stopniowe zwiększanie kilometrażu: +10% / tydzień, max +20% przy dobrym samopoczuciu.

Uwzględnić dni z basenem jako trening tlenowy.

W dłuższych biegach monitorować tętno – nie przekraczać Z2.

Dla półmaratonu plan 3–4 miesięczny → 4 tyg. base + 8–10 tyg. build.
"""


def get_data_from_db():
    """
    Ta funkcja wyciąga dane z Twojej bazy SQLite i zamienia je na tekst,
    który zrozumie AI. Pobieramy ostatnie 30 dni.
    """
    cutoff_date = datetime.now() - timedelta(days=30)

    # Pobieramy aktywności z bazy
    activities = Activity.query.filter(Activity.start_time >= cutoff_date).order_by(Activity.start_time.asc()).all()

    if not activities:
        return "Brak treningów w ostatnich 30 dniach."

    data_text = "OSTATNIE TRENINGI (z bazy danych):\n"

    for act in activities:
        # Formatowanie daty i podstawowych danych
        date_str = act.start_time.strftime('%Y-%m-%d')
        data_text += f"- Data: {date_str} | Typ: {act.activity_type} | Dystans: {act.distance / 1000:.1f}km | Czas: {act.duration // 60}min\n"

        # Dodajemy notatki, jeśli są
        if act.notes:
            data_text += f"  Notatka użytkownika: {act.notes}\n"

        # Dodajemy ćwiczenia siłowe, jeśli są
        if act.exercises:
            cwiczenia_str = ", ".join([f"{e.name} ({e.sets}x{e.reps}, {e.weight}kg)" for e in act.exercises])
            data_text += f"  Ćwiczenia: {cwiczenia_str}\n"

    return data_text


def ask_gemini(user_question):
    # 1. Pobieramy świeże dane z bazy
    db_context = get_data_from_db()

    # 2. Tworzymy Prompt (Instrukcję dla AI)
    # Łączymy Twój profil + Dane z bazy + Twoje pytanie
    full_prompt = f"""
    Jesteś doświadczonym trenerem sportowym. Analizujesz moje dane.

    {USER_PROFILE}

    {db_context}

    PYTANIE UŻYTKOWNIKA:
    {user_question}

    Odpowiedz krótko i konkretnie, opierając się na moich danych i profilu.
    """

    # Wyświetlmy w terminalu, co dokładnie idzie do AI (dla celów edukacyjnych)
    print("\n--- [DEBUG] WYSYŁAM DO GEMINI: ---")
    print(f"Profil długość: {len(USER_PROFILE)} znaków")
    print(f"Baza danych długość: {len(db_context)} znaków")
    print("----------------------------------\n")

    try:
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        return f"Błąd połączenia z AI: {e}"


if __name__ == "__main__":
    # WAŻNE: Musimy użyć app.app_context(), żeby skrypt widział bazę danych Flaska
    with app.app_context():
        print("🤖 Witaj w AI Coach Terminalu! (Ctrl+C aby wyjść)")
        print("Model ma dostęp do Twojej bazy danych i zdefiniowanego profilu.")

        while True:
            question = input("\nZadaj pytanie o swoje treningi: ")
            if question.lower() in ['exit', 'q', 'wyjscie']:
                break

            print("Myślę...")
            answer = ask_gemini(question)

            print("\n💡 ODPOWIEDŹ TRENERA:")
            print(answer)
            print("-" * 50)