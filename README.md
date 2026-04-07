# Training App (AI-Powered Running Coach)

A full‑stack Flask web app for runners. It combines activity history (Strava or Garmin ZIP exports) with an AI coach to generate realistic weekly plans, track progress, and provide context‑aware guidance. The app includes a modern dashboard, training planner, check‑ins with screenshot parsing, and a bilingual UI (PL/EN).

## Highlights

- **AI Coach (Gemini)**: Chat with a coach that understands your profile, goals, history, and check‑ins.
- **Weekly Plan Engine**: Generates realistic weekly plans with safe progression, long‑run ratios, fatigue rules, and cadence drills.
- **Garmin + Strava ZIP Import**: Import historical activities and fill profile defaults.
- **Roadmap / Calendar View**: Plan overview with drag‑and‑drop scheduling and weather cues.
- **Check‑ins + Screenshot Parsing**: Upload a training screenshot to auto‑fill fields.
- **Metrics & Goal Preparation**: Weekly volume charts, progress toward goals, and training phases.
- **Bilingual UI**: Polish + English with per‑user preference.
- **Password Reset**: Email-based reset flow via SMTP.
- **Google Calendar Subscription**: Per‑user ICS feed for weekly plan syncing.

## Tech Stack

- **Backend**: Python, Flask, SQLAlchemy
- **Database**: SQLite (default)
- **AI**: Google Gemini (`google-generativeai`)
- **Frontend**: Server-rendered HTML + CSS + minimal JS

## Getting Started

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open: `http://127.0.0.1:5001`

## Live Demo

- https://jawilk123.pythonanywhere.com/

## Environment Variables

Create a `.env` file in the project root:

```
SECRET_KEY=your-secret
GEMINI_API_KEY=your-gemini-api-key

# Optional: override DB location
DATABASE_URL=sqlite:///training.db

# SMTP for password reset emails
MAIL_HOST=smtp.gmail.com
MAIL_PORT=587
MAIL_USER=your_email@gmail.com
MAIL_PASSWORD=your_app_password
MAIL_FROM=your_email@gmail.com
MAIL_USE_TLS=1
```

## Data Import (Strava / Garmin)

- **Strava**: Upload ZIP export (contains `activities.csv`)
- **Garmin**: Upload Garmin Connect export ZIP (`DI_CONNECT/DI-Connect-Fitness/…`)

Imports:
- activities (type, distance, time, HR, pace, etc.)
- profile defaults (weekly distance, common sports)

## Password Reset Flow

1. User requests reset on login page
2. App sends a time‑limited link via SMTP
3. User sets a new password

Make sure SMTP variables are configured.

## Project Structure (short)

```
app.py          # main Flask app (routes + logic)
models.py       # SQLAlchemy models
ask_coach.py    # prompt builders & AI logic
templates/      # HTML templates
static/         # CSS, JS, icons, manifest
```

## Notes

- The training engine plans the **week first** (run days, long run day, volume split) and only then generates session details.
- The app is optimized for realistic runner capacity, not overly conservative defaults.

## License

Private / internal project (update if you plan to open source).
