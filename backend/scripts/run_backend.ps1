python -m pip install -r requirements.txt
alembic upgrade head
python scripts/seed_defaults.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
