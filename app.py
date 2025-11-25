from flask import Flask, render_template, request, jsonify, redirect
from dotenv import load_dotenv
# ZMIANA 1: Dodane WorkoutPlan i PlanExercise do importów
from models import db, Activity, Exercise, UserData, WorkoutPlan, PlanExercise
from config import Config
from strava_client import StravaClient
from ai_coach import AICoach
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

strava = StravaClient(
    app.config['STRAVA_CLIENT_ID'],
    app.config['STRAVA_CLIENT_SECRET']
)

# Inicjalizacja Trenera AI
coach = AICoach(app.config['GEMINI_API_KEY'])


@app.route('/')
def index():
    user = UserData.query.first()

    # Ostatnie 30 dni
    cutoff_date = datetime.now() - timedelta(days=30)

    activities = Activity.query.filter(Activity.start_time >= cutoff_date).order_by(Activity.start_time.desc()).all()

    stats = {
        'count': len(activities),
        'distance': round(sum(a.distance for a in activities) / 1000, 1),
        'hours': round(sum(a.duration for a in activities) / 60 / 60, 1)
    }

    return render_template('index.html', user=user, activities=activities, stats=stats)


@app.route('/strava/connect')
def strava_connect():
    url = strava.get_authorization_url()
    return redirect(url)


@app.route('/strava/callback')
def strava_callback():
    code = request.args.get('code')
    error = request.args.get('error')
    if error: return f"Error: {error}", 400
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
    # ZMIANA 2: Pobieramy listę dostępnych planów, by przekazać je do selecta w HTML
    plans = WorkoutPlan.query.all()
    return render_template('activity.html', activity=activity, plans=plans)


# --- NOWE FUNKCJE: ZARZĄDZANIE PLANAMI ---

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
        # Domyślne wartości 0 jeśli puste
        sets_val = int(sets) if sets else 0
        reps_val = int(reps) if reps else 0

        ex = PlanExercise(name=name, default_sets=sets_val, default_reps=reps_val, plan=plan)
        db.session.add(ex)
        db.session.commit()
    return redirect('/plans')


# --- NOWE FUNKCJE: OBSŁUGA AKTYWNOŚCI I NOTATEK ---

@app.route('/activity/<int:id>/apply_plan', methods=['POST'])
def apply_plan_to_activity(id):
    activity = Activity.query.get_or_404(id)
    plan_id = request.form.get('plan_id')

    if plan_id:
        plan = WorkoutPlan.query.get_or_404(plan_id)

        # Kopiujemy ćwiczenia z szablonu do aktualnego treningu
        for template_ex in plan.exercises:
            new_ex = Exercise(
                activity_id=activity.id,
                name=template_ex.name,
                sets=template_ex.default_sets,
                reps=template_ex.default_reps,
                weight=0  # Użytkownik uzupełni wagę sam w edycji
            )
            db.session.add(new_ex)

        db.session.commit()

    return redirect(f'/activity/{id}')


@app.route('/activity/<int:id>/update_notes', methods=['POST'])
def update_activity_notes(id):
    activity = Activity.query.get_or_404(id)
    notes = request.form.get('notes')
    activity.notes = notes
    db.session.commit()
    return redirect(f'/activity/{id}')


@app.route('/exercise/<int:ex_id>/delete', methods=['POST'])
def delete_exercise(ex_id):
    ex = Exercise.query.get_or_404(ex_id)
    activity_id = ex.activity_id
    db.session.delete(ex)
    db.session.commit()
    return redirect(f'/activity/{activity_id}')


@app.route('/exercise/<int:id>/update', methods=['POST'])
def update_exercise(id):
    ex = Exercise.query.get_or_404(id)
    data = request.json

    # Sprawdzamy co przyszło i aktualizujemy
    if 'sets' in data:
        ex.sets = int(data['sets'])
    if 'reps' in data:
        ex.reps = int(data['reps'])
    if 'weight' in data:
        # Obsługa przecinków i kropek dla wagi
        w = str(data['weight']).replace(',', '.')
        ex.weight = float(w) if w else 0.0

    db.session.commit()
    return jsonify({'success': True})

@app.route('/activity/<int:id>/exercises', methods=['POST'])
def add_exercise_api(id):
    # Zachowujemy stary endpoint API dla kompatybilności z JS w activity.html (przycisk "+")
    data = request.json
    activity = Activity.query.get_or_404(id)

    for item in data.get('exercises', []):
        ex = Exercise(
            activity_id=activity.id,
            name=item['name'],
            sets=item['sets'],
            reps=item['reps'],
            weight=item.get('weight', 0)
        )
        db.session.add(ex)

    db.session.commit()
    return jsonify({'status': 'ok'})


# --- ENDPOINTY AI (BEZ ZMIAN) ---

@app.route('/plan/create', methods=['POST'])
def create_plan():
    data = request.json
    user = UserData.query.first()
    if not user:
        user = UserData()

    user.goal = data['goal']
    if data.get('target_date'):
        user.target_date = datetime.fromisoformat(data['target_date']).date()

    db.session.add(user)
    db.session.commit()

    activities = Activity.query.order_by(Activity.start_time.desc()).limit(20).all()

    target_date = user.target_date or (datetime.now().date() + timedelta(days=30))
    plan = coach.generate_plan(user.goal, target_date, activities)

    return jsonify(plan)


@app.route('/workout/suggest')
def suggest_workout():
    workout_type = request.args.get('type', 'bieg')
    user = UserData.query.first()

    activities = Activity.query.order_by(Activity.start_time.desc()).limit(10).all()
    goal = user.goal if user and user.goal else "Utrzymanie formy"

    workout = coach.suggest_workout(workout_type, goal, activities)
    return jsonify(workout)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5001, debug=True)