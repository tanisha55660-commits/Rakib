# SHIHAB X HOSTING — Premium VPS Panel 3.0

## Visual upgrade
- Full black / orange / royal-gold UI direction.
- Animated Black Hole background.
- Emoji rain and golden rain effects.
- User-panel background controls.
- Image/video background upload (MP4/WebM/MOV + common image formats).
- Background opacity, speed and particle count controls.
- T10 SHIHAB credit branding.

## Reliability upgrade
- Persistent Flask session secret stored in `.secret_key` so normal restarts do not invalidate sessions.
- Automatic rotating `config.json` backups (up to 10 copies) in `backups/`.
- Existing server/file/package management remains intact.

## Run
```bash
pip install -r requirements.txt
python app.py
```

Default access passwords from the original source remain unchanged unless you update them in the panel.
