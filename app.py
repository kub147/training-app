from flask import Flask, render_template, request, jsonify, redirect
from dotenv import load_dotenv
from models import db, Activity, Exercise, UserData
from config import Config
from strava_client import StravaClient
# from ai_coach import AICoach
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

strava = StravaClient(
    app.config['STRAVA_CLIENT_ID'],
    app.config['STRAVA_CLIENT_SECRET']
)


@app.route('/')
def index():
    user = UserData.query.first()

    # 1. Zmieniamy zakres na 30 dni dla widoku kalendarza
    cutoff_date = datetime.now() - timedelta(days=7)

    # Pobieramy aktywności
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


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5001, debug=True)