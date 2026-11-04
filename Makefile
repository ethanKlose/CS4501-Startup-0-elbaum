PY=.venv/bin/python
.PHONY: setup run test seed reset
setup:
	python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && cp -n .env.example .env || true
seed:
	PYTHONPATH=. $(PY) scripts/seed.py
run: seed
	$(PY) -m uvicorn app.main:app --reload
test:
	.venv/bin/pytest -q
reset:
	rm -f platejoy.db && $(MAKE) seed
