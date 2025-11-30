from flask import Flask, render_template, request, jsonify, redirect
from dotenv import load_dotenv
import os
import google.generativeai as genai
from datetime import datetime, timedelta

# Importy modeli (DODANO ChatMessage)
from models import db, Activity, Exercise, UserData, WorkoutPlan, PlanExercise, ChatMessage
from config import Config
from strava_client import StravaClient

# --- IMPORT DANYCH PRYWATNYCH ---
try:
    from user_profile import DATA as USER_PROFILE
except ImportError:
    USER_PROFILE = "Brak profilu użytkownika. Utwórz plik user_profile.py."

load_dotenv()

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

strava = StravaClient(
    app.config['STRAVA_CLIENT_ID'],
    app.config['STRAVA_CLIENT_SECRET']
)

# Konfiguracja AI
genai.configure(api_key=os.environ.get('GEMINI_API_KEY'))
model = genai.GenerativeModel('gemini-2.5-flash')  # Użyj sprawdzonego modelu (np. 1.5-flash lub pro)


def get_data_from_db(days=30):
    """Pobiera dane z bazy i formatuje do tekstu dla AI."""
    cutoff_date = datetime.now() - timedelta(days=days)
    activities = Activity.query.filter(Activity.start_time >= cutoff_date).order_by(Activity.start_time.asc()).all()

    if not activities:
        return "Brak treningów w tym okresie."

    data_text = "HISTORIA TRENINGÓW:\n"
    for act in activities:
        date_str = act.start_time.strftime('%Y-%m-%d')
        # Dodajemy tętno
        hr_info = f" | Śr. HR: {act.avg_hr} bpm" if act.avg_hr else ""

        data_text += f"- {date_str} | {act.activity_type} | {act.distance / 1000:.1f}km | {act.duration // 60}min{hr_info}\n"

        if act.notes:
            data_text += f"  Notatka: {act.notes}\n"
        if act.exercises:
            cwiczenia_str = ", ".join([f"{e.name} ({e.sets}x{e.reps}, {e.weight}kg)" for e in act.exercises])
            data_text += f"  Siłownia: {cwiczenia_str}\n"
    return data_text


# --- ROUTY APLIKACJI ---

@app.route('/')
def index():
    user = UserData.query.first()

    # 1. Statystyki z OSTATNICH 7 DNI
    cutoff_7d = datetime.now() - timedelta(days=7)
    acts_7d = Activity.query.filter(Activity.start_time >= cutoff_7d).all()

    # Inicjalizacja liczników
    stats = {
        'count': len(acts_7d),
        'distance': 0, 'hours': 0,
        'run_count': 0, 'run_dist': 0,
        'swim_count': 0, 'swim_dist': 0,
        'gym_count': 0, 'gym_time': 0,
        'ride_count': 0, 'ride_dist': 0
    }

    # Zliczanie
    for a in acts_7d:
        stats['distance'] += a.distance
        stats['hours'] += a.duration

        if a.activity_type == 'run':
            stats['run_count'] += 1
            stats['run_dist'] += a.distance
        elif a.activity_type == 'swim':
            stats['swim_count'] += 1
            stats['swim_dist'] += a.distance
        elif a.activity_type in ['weighttraining', 'workout']:
            stats['gym_count'] += 1
            stats['gym_time'] += a.duration
        elif a.activity_type == 'ride':
            stats['ride_count'] += 1
            stats['ride_dist'] += a.distance

    # Formatowanie
    stats['distance'] = round(stats['distance'] / 1000, 1)
    stats['hours'] = round(stats['hours'] / 3600, 1)
    stats['run_dist'] = round(stats['run_dist'] / 1000, 1)
    stats['swim_dist'] = round(stats['swim_dist'] / 1000, 1)
    stats['ride_dist'] = round(stats['ride_dist'] / 1000, 1)
    stats['gym_hours'] = round(stats['gym_time'] / 3600, 1)

    # Timeline (ostatnie 10)
    recent_activities = Activity.query.order_by(Activity.start_time.desc()).limit(10).all()

    return render_template('index.html', user=user, activities=recent_activities, stats=stats)


@app.route('/history')
def history():
    all_activities = Activity.query.order_by(Activity.start_time.desc()).all()
    return render_template('all_activities.html', activities=all_activities)


# --- ROUTY AI ---

@app.route('/api/chat/history', methods=['GET'])
def get_chat_history():
    """Zwraca ostatnie 20 wiadomości, żeby wyświetlić je po odświeżeniu strony"""
    messages = ChatMessage.query.order_by(ChatMessage.timestamp.asc()).all()
    # Limitujemy do ostatnich 50, żeby nie zapchać widoku
    messages = messages[-50:]

    history_data = [{'sender': m.sender, 'content': m.content} for m in messages]
    return jsonify(history_data)


@app.route('/api/chat', methods=['POST'])
def chat_with_coach():
    user_msg = request.json.get('message')

    # 1. Zapisz pytanie użytkownika
    user_message_db = ChatMessage(sender='user', content=user_msg)
    db.session.add(user_message_db)
    db.session.commit()

    # 2. Buduj kontekst (Pamięć rozmowy)
    # Pobieramy ostatnie 10 wiadomości (wymian zdań), żeby AI znało kontekst
    recent_messages = ChatMessage.query.order_by(ChatMessage.timestamp.asc()).limit(20).all()

    chat_history_text = "HISTORIA ROZMOWY (Chronologicznie):\n"
    for m in recent_messages:
        role = "Zawodnik" if m.sender == 'user' else "Trener"
        chat_history_text += f"{role}: {m.content}\n"

    # 3. Pobierz dane z bazy
    db_context = get_data_from_db(days=30)

    # 4. Prompt
    full_prompt = f"""
    Jesteś trenerem Jakuba Wilka.

    PROFIL ZAWODNIKA:
    {USER_PROFILE}

    DANE TRENINGOWE:
    {db_context}

    KONTEKST ROZMOWY:
    {chat_history_text}

    NOWE PYTANIE ZAWODNIKA:
    {user_msg}

    Odpowiedz krótko i konkretnie, nawiązując do kontekstu rozmowy jeśli to potrzebne.
    Używaj HTML do formatowania (<b>, <br>).
    """

    try:
        response = model.generate_content(full_prompt)
        clean_text = response.text.replace('```html', '').replace('```', '').replace('**', '')

        # 5. Zapisz odpowiedź AI
        ai_message_db = ChatMessage(sender='ai', content=clean_text)
        db.session.add(ai_message_db)
        db.session.commit()

        return jsonify({'response': clean_text})
    except Exception as e:
        return jsonify({'response': f"Błąd AI: {str(e)}"})


@app.route('/api/forecast', methods=['GET'])
def generate_forecast():
    db_context = get_data_from_db(days=14)
    today = datetime.now().strftime('%Y-%m-%d')

    prompt = f"""
    Jesteś trenerem. Stwórz plan dla Jakuba na 4 dni (start: {today}).
    {USER_PROFILE}
    {db_context}

    INSTRUKCJA FORMATOWANIA:
    1. Nie używaj Markdowna.
    2. Używaj TYLKO HTML.
    3. Daty pogrubiaj <b>Data</b>.
    4. Dni oddziel <br><br>.
    """

    try:
        response = model.generate_content(prompt)
        text = response.text.replace('```html', '').replace('```', '').replace('**', '')
        if '<br>' not in text: text = text.replace('\n', '<br>')
        return jsonify({'plan': text})
    except Exception as e:
        return jsonify({'plan': "Nie udało się wygenerować planu."})


# --- POZOSTAŁE ROUTY (Bez zmian) ---
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


@app.route('/plans/<int:id>/delete', methods=['POST'])
def delete_plan(id):
    plan = WorkoutPlan.query.get_or_404(id)
    db.session.delete(plan)
    db.session.commit()
    return redirect('/plans')


@app.route('/plans/exercise/<int:id>/delete', methods=['POST'])
def delete_plan_exercise(id):
    ex = PlanExercise.query.get_or_404(id)
    db.session.delete(ex)
    db.session.commit()
    return redirect('/plans')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5001, debug=True)