PY ?= python3

install:
	$(PY) -m venv .venv
	.venv/bin/pip install -r requirements.txt

web:
	cd frontend && npm install && npm run build

run:
	.venv/bin/uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 1 --env-file .env

demo:
	MODEL_BACKEND=fake .venv/bin/uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --env-file .env

probe:
	.venv/bin/python scripts/probe_model.py

test:
	.venv/bin/python -m pytest -q

.PHONY: install web run demo probe test
