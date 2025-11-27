from flask import Flask, render_template, request, jsonify, redirect
from dotenv import load_dotenv
import os
import google.generativeai as genai
from datetime import datetime, timedelta

# Importujemy modele bazy danych
from models import db, Activity, Exercise, UserData, WorkoutPlan, PlanExercise
from config import Config
from strava_client import StravaClient

# (Możemy pominąć import AICoach z ai_coach.py, bo przenosimy logikę tutaj,
#  ale zostawiam importy modeli, bo są potrzebne)

load_dotenv()

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

strava = StravaClient(
    app.config['STRAVA_CLIENT_ID'],
    app.config['STRAVA_CLIENT_SECRET']
)

# --- KONFIGURACJA AI (Prosto z Twojego skryptu ask_coach.py) ---
genai.configure(api_key=os.environ.get('GEMINI_API_KEY'))

# Używamy modelu 1.5-flash (jest szybki i dobry do czatu).
# Jeśli będziesz miał błąd 404, zmień na 'gemini-pro' lub zaktualizuj bibliotekę.
model = genai.GenerativeModel('gemini-2.5-pro')

# --- TWÓJ PROFIL UŻYTKOWNIKA ---
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
Typy ulubione: interwały krótkie (1–3 min), easy run 30–40 min, biegi tempowe, 1× długie wybieganie tygodniowo (do 90 min).
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
Cele główne: Poprawa wyników, Zdrowie i brak kontuzji, Regularność i ogólna wydolność
Cele szczegółowe: zwiększanie kilometrażu (z 10 km -> 20-30 km), półmaraton za 3-4 miesiące, poprawa tempa.

11. Możliwości czasowe
Bieganie: 30–50 min, 1× dłuższy bieg 75–90 min
Siłownia: 90 min
Basen: 45 min

13. Rekomendowany szablon tygodnia
Tydzień – 3 biegi + 2 siłownie + 1 basen
Bieg 1: Easy 30–40 min (Z2) + przebieżki
Bieg 2: Interwały (np. 6×1 min, Z4/Z5)
Bieg 3: Long Run 60–90 min (Z2)
Siłownia A: siła ogólna + core
Siłownia B: pośladki, stabilizacja, mobilność
Basen: 45 min tlenowo
Mobilność: 2–3 razy po 10–15 min

15. Uwagi dla algorytmu AI
Nie łączyć siłowni i biegania w jeden dzień.
Zawsze 10 min rozgrzewki przed interwałami.
Pierwsze 5–10 min biegu bardzo spokojnie.
Stopniowe zwiększanie kilometrażu (+10%/tydzień).
"""


def get_data_from_db():
    """
    Pobiera dane z bazy (ostatnie 30 dni) i formatuje do tekstu dla AI.
    """
    cutoff_date = datetime.now() - timedelta(days=30)

    # Pobieramy aktywności z bazy
    activities = Activity.query.filter(Activity.start_time >= cutoff_date).order_by(Activity.start_time.asc()).all()

    if not activities:
        return "Brak treningów w ostatnich 30 dniach."

    data_text = "OSTATNIE TRENINGI (z bazy danych):\n"

    for act in activities:
        date_str = act.start_time.strftime('%Y-%m-%d')
        data_text += f"- Data: {date_str} | Typ: {act.activity_type} | Dystans: {act.distance / 1000:.1f}km | Czas: {act.duration // 60}min\n"

        if act.notes:
            data_text += f"  Notatka użytkownika: {act.notes}\n"

        if act.exercises:
            cwiczenia_str = ", ".join([f"{e.name} ({e.sets}x{e.reps}, {e.weight}kg)" for e in act.exercises])
            data_text += f"  Ćwiczenia: {cwiczenia_str}\n"

    return data_text


# --- ROUTY APLIKACJI ---

@app.route('/')
def index():
    user = UserData.query.first()
    cutoff_date = datetime.now() - timedelta(days=30)
    activities = Activity.query.filter(Activity.start_time >= cutoff_date).order_by(Activity.start_time.desc()).all()

    stats = {
        'count': len(activities),
        'distance': round(sum(a.distance for a in activities) / 1000, 1),
        'hours': round(sum(a.duration for a in activities) / 60 / 60, 1)
    }
    return render_template('index.html', user=user, activities=activities, stats=stats)


# --- NOWE ROUTY AI (CZAT + PLAN) ---

@app.route('/api/chat', methods=['POST'])
def chat_with_coach():
    user_msg = request.json.get('message')

    # 1. Pobieramy kontekst z bazy
    db_context = get_data_from_db()

    # 2. Tworzymy Prompt
    full_prompt = f"""
    Jesteś doświadczonym trenerem sportowym Jakuba Wilka.

    {USER_PROFILE}

    {db_context}

    PYTANIE UŻYTKOWNIKA:
    {user_msg}

    Odpowiedz krótko i konkretnie. Jeśli pytanie dotyczy planu, sugeruj się moim profilem.
    Formatuj odpowiedź używając HTML (np. <b>pogrubienie</b>, <br> nowa linia).
    """

    try:
        response = model.generate_content(full_prompt)
        # Zamieniamy \n na <br> dla czytelności w HTML, jeśli model zwrócił czysty tekst
        formatted_text = response.text.replace('\n', '<br>')
        return jsonify({'response': formatted_text})
    except Exception as e:
        return jsonify({'response': f"Błąd AI: {str(e)}"})


@app.route('/api/forecast', methods=['GET'])
def generate_forecast():
    # Generujemy plan na najbliższe 4 dni
    db_context = get_data_from_db()
    today = datetime.now().strftime('%Y-%m-%d')

    prompt = f"""
    Jesteś trenerem. Stwórz plan treningowy dla Jakuba na najbliższe 4 dni (zaczynając od dziś: {today}).

    {USER_PROFILE}

    HISTORIA OSTATNICH TRENINGÓW:
    {db_context}

    ZADANIE:
    Wypisz plan dzień po dniu.
    - Jeśli wczoraj był mocny trening, daj dziś lżej.
    - Przestrzegaj zasady: nie łącz siłowni i biegania w jeden dzień.
    - Używaj pogrubień (<b>) dla dat.
    - Formatuj jako prostą listę HTML (<ul>, <li>).
    """

    try:
        response = model.generate_content(prompt)
        # Formatowanie
        formatted_text = response.text.replace('\n', '<br>')
        return jsonify({'plan': formatted_text})
    except Exception as e:
        return jsonify({'plan': "Nie udało się wygenerować planu."})


# --- POZOSTAŁE ROUTY (BEZ ZMIAN) ---

@app.route('/strava/connect')
def strava_connect():
    url = strava.get_authorization_url()
    return redirect(url)


@app.route('/strava/callback')
def strava_callback():
    code = request.args.get('code')
    if not code: return "No code provided", 400
    try:
        strava.exchange_code(code)
        return redirect('/')
    except Exception as e:
        return f"Error: {str(e)}", 500


@app.route('/strava/sync')
def strava_sync():
    new_activities = strava.get_activities()
    return jsonify({'synced': len(new_activities)})


@app.route('/activity/<int:id>')
def activity_detail(id):
    activity = Activity.query.get_or_404(id)
    plans = WorkoutPlan.query.all()
    return render_template('activity.html', activity=activity, plans=plans)


@app.route('/activity/<int:id>/apply_plan', methods=['POST'])
def apply_plan_to_activity(id):
    activity = Activity.query.get_or_404(id)
    plan_id = request.form.get('plan_id')
    if plan_id:
        plan = WorkoutPlan.query.get_or_404(plan_id)
        for template_ex in plan.exercises:
            last_entry = Exercise.query.join(Activity).filter(Exercise.name == template_ex.name).order_by(
                Activity.start_time.desc()).first()
            current_weight = last_entry.weight if last_entry else 0
            new_ex = Exercise(activity_id=activity.id, name=template_ex.name, sets=template_ex.default_sets,
                              reps=template_ex.default_reps, weight=current_weight)
            db.session.add(new_ex)
        db.session.commit()
    return redirect(f'/activity/{id}')


@app.route('/activity/<int:id>/update_notes', methods=['POST'])
def update_activity_notes(id):
    activity = Activity.query.get_or_404(id)
    activity.notes = request.form.get('notes')
    db.session.commit()
    return redirect(f'/activity/{id}')


@app.route('/exercise/<int:id>/update', methods=['POST'])
def update_exercise(id):
    ex = Exercise.query.get_or_404(id)
    data = request.json
    if 'sets' in data: ex.sets = int(data['sets'])
    if 'reps' in data: ex.reps = int(data['reps'])
    if 'weight' in data:
        w = str(data['weight']).replace(',', '.')
        ex.weight = float(w) if w else 0.0
    db.session.commit()
    return jsonify({'success': True})


@app.route('/exercise/<int:ex_id>/delete', methods=['POST'])
def delete_exercise(ex_id):
    ex = Exercise.query.get_or_404(ex_id)
    aid = ex.activity_id
    db.session.delete(ex)
    db.session.commit()
    return redirect(f'/activity/{aid}')


@app.route('/activity/<int:id>/exercises', methods=['POST'])
def add_exercise_api(id):
    data = request.json
    activity = Activity.query.get_or_404(id)
    for item in data.get('exercises', []):
        ex = Exercise(activity_id=activity.id, name=item['name'], sets=item['sets'], reps=item['reps'],
                      weight=item.get('weight', 0))
        db.session.add(ex)
    db.session.commit()
    return jsonify({'status': 'ok'})


@app.route('/plans')
def plans_list():
    plans = WorkoutPlan.query.all()
    return render_template('plans.html', plans=plans)


@app.route('/plans/add', methods=['POST'])
def add_plan():
    name = request.form.get('name')
    if name:
        new_plan = WorkoutPlan(name=name)
        db.session.add(new_plan)
        db.session.commit()
    return redirect('/plans')


@app.route('/plans/<int:id>/add_exercise', methods=['POST'])
def add_plan_exercise(id):
    plan = WorkoutPlan.query.get_or_404(id)
    name = request.form.get('name')
    sets = request.form.get('sets')
    reps = request.form.get('reps')
    if name:
        ex = PlanExercise(name=name, default_sets=int(sets) if sets else 0, default_reps=int(reps) if reps else 0,
                          plan=plan)
        db.session.add(ex)
        db.session.commit()
    return redirect('/plans')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5001, debug=True)