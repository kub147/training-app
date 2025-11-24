import requests
from models import db, Activity, UserData
from datetime import datetime
import time


class StravaClient:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = 'https://www.strava.com/api/v3'

    def get_authorization_url(self):
        return (f'https://www.strava.com/oauth/authorize?'
                f'client_id={self.client_id}&'
                f'response_type=code&'
                f'redirect_uri=http://127.0.0.1:5000/strava/callback&'
                f'scope=activity:read_all')

    def exchange_code(self, code):
        response = requests.post('https://www.strava.com/oauth/token', data={
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'grant_type': 'authorization_code'
        })

        print("Strava response status:", response.status_code)
        print("Strava response:", response.json())

        token = response.json()

        # Sprawdź czy są błędy
        if 'errors' in token or 'message' in token:
            raise Exception(f"Strava error: {token}")

        user = UserData.query.first()
        if not user:
            user = UserData()

        user.strava_access_token = token['access_token']
        user.strava_refresh_token = token['refresh_token']
        user.strava_expires_at = token['expires_at']

        db.session.add(user)
        db.session.commit()

        return token

    def refresh_token(self, user):
        if user.strava_expires_at < time.time():
            response = requests.post('https://www.strava.com/oauth/token', data={
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'refresh_token': user.strava_refresh_token,
                'grant_type': 'refresh_token'
            })

            token = response.json()
            user.strava_access_token = token['access_token']
            user.strava_refresh_token = token['refresh_token']
            user.strava_expires_at = token['expires_at']
            db.session.commit()

    def get_activities(self, limit=30):
        user = UserData.query.first()
        if not user or not user.strava_access_token:
            return []

        self.refresh_token(user)

        headers = {'Authorization': f'Bearer {user.strava_access_token}'}
        response = requests.get(
            f'{self.base_url}/athlete/activities',
            headers=headers,
            params={'per_page': limit}
        )

        activities = response.json()
        saved = []

        for act in activities:
            existing = Activity.query.filter_by(strava_id=act['id']).first()
            if existing:
                continue

            activity = Activity(
                strava_id=act['id'],
                activity_type=act['type'].lower(),
                start_time=datetime.fromisoformat(act['start_date_local'].replace('Z', '+00:00')),
                duration=act.get('elapsed_time', 0),
                distance=act.get('distance', 0),
                avg_hr=act.get('average_heartrate')
            )
            db.session.add(activity)
            saved.append(activity)

        db.session.commit()
        return saved