PY=.venv/bin/python
.PHONY: setup run test test-integration test-e2e seed reset
setup:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements-dev.txt
	@test -e .env || cp .env.example .env
seed:
	PYTHONPATH=. $(PY) scripts/seed.py
run: seed
	$(PY) -m uvicorn app.main:app --reload
test:
	.venv/bin/pytest -q
test-integration:
	$(PY) -m pytest tests/integration -m integration -q --strict-markers --junitxml=test-results/integration.xml
reset:
	rm -f platejoy.db && $(MAKE) seed

test-e2e:
	npm run test:e2e
