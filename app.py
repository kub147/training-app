from flask import Flask, render_template, request, jsonify, redirect
from dotenv import load_dotenv
from models import db, Activity, Exercise, UserData
from config import Config
from strava_client import StravaClient
from ai_coach import AICoach  # <--- 1. Odkomentowane
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

strava = StravaClient(
    app.config['STRAVA_CLIENT_ID'],
    app.config['STRAVA_CLIENT_SECRET']
)

# 2. Inicjalizacja Trenera AI
coach = AICoach(app.config['GEMINI_API_KEY'])


@app.route('/')
def index():
    user = UserData.query.first()

    # Naprawione na 30 dni, zgodnie z nagłówkiem w HTML
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
    return render_template('activity.html', activity=activity)


# --- 3. PRZYWRÓCONE ENDPOINTY AI ---

@app.route('/plan/create', methods=['POST'])
def create_plan():
    data = request.json
    user = UserData.query.first()
    if not user:
        user = UserData()

    # Zapisujemy cel użytkownika
    user.goal = data['goal']
    if data.get('target_date'):
        user.target_date = datetime.fromisoformat(data['target_date']).date()

    db.session.add(user)
    db.session.commit()

    # Pobieramy historię do kontekstu dla AI
    activities = Activity.query.order_by(Activity.start_time.desc()).limit(20).all()

    # Generujemy plan
    # Domyślna data jeśli user nie poda (np. za miesiąc)
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