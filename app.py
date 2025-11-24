from flask import Flask, render_template, request, jsonify, redirect
from models import db, Activity, Exercise, UserData
from config import Config
from strava_client import StravaClient
from ai_coach import AICoach
from datetime import datetime

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

strava = StravaClient(
    app.config['STRAVA_CLIENT_ID'],
    app.config['STRAVA_CLIENT_SECRET']
)

coach = AICoach(app.config['GEMINI_API_KEY'])

@app.route('/')
def index():
    user = UserData.query.first()
    activities = Activity.query.order_by(Activity.start_time.desc()).limit(20).all()
    return render_template('index.html', user=user, activities=activities)

@app.route('/strava/connect')
def strava_connect():
    url = strava.get_authorization_url()
    return redirect(url)


@app.route('/strava/callback')
def strava_callback():
    code = request.args.get('code')
    error = request.args.get('error')

    print(f"Code: {code}")
    print(f"Error: {error}")

    if error:
        return f"Error: {error}", 400

    if not code:
        return "No code provided", 400

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

@app.route('/activity/<int:id>/exercises', methods=['POST'])
def add_exercises(id):
    data = request.json
    for ex in data.get('exercises', []):
        exercise = Exercise(
            activity_id=id,
            name=ex['name'],
            sets=ex['sets'],
            reps=ex['reps'],
            weight=ex['weight']
        )
        db.session.add(exercise)
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/plan/create', methods=['POST'])
def create_plan():
    data = request.json
    user = UserData.query.first()
    if not user:
        user = UserData()
    
    user.goal = data['goal']
    user.target_date = datetime.fromisoformat(data['target_date']).date()
    db.session.add(user)
    db.session.commit()
    
    activities = Activity.query.order_by(Activity.start_time.desc()).limit(20).all()
    plan = coach.generate_plan(user.goal, user.target_date, activities)
    
    return jsonify(plan)

@app.route('/workout/suggest')
def suggest_workout():
    workout_type = request.args.get('type', 'bieg')
    user = UserData.query.first()
    activities = Activity.query.order_by(Activity.start_time.desc()).limit(10).all()
    
    goal = user.goal if user else "Ogólna forma"
    workout = coach.suggest_workout(workout_type, goal, activities)
    
    return jsonify(workout)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
