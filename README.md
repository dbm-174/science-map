# GEPRIS Personenkarte – Quick Prototype

Ziel: Personen aus `gepris_persons.json` auf Karte darstellen, farblich nach Themen geclustert, Punktgröße = Anzahl Projekte.

## Voraussetzungen
- Python 3.10+
- pip: fastapi, uvicorn, requests, scikit-learn
- Internetzugang (Geocoding via Nominatim)
- Optional: .env mit `NOMINATIM_EMAIL`

## Installation
```bash
python -m venv .venv && source .venv/bin/activate
pip install fastapi uvicorn requests scikit-learn python-dotenv
chmod +x scripts/setup_project.sh
./scripts/setup_project.sh
# Kopiere deine gepris_persons.json nach app/backend/data/raw/

