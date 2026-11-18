# SETU — one command per job. Judges: `make up` then open http://localhost:8000
PY ?= .venv/bin/python

.PHONY: setup web up dev seed test validate hrx-test bench licenses demo-reset clean docker

setup:            ## create the virtualenv and install backend + frontend dependencies
	uv venv -p 3.12 .venv 2>/dev/null || python3.12 -m venv .venv
	uv pip install -e '.[dev]' 2>/dev/null || .venv/bin/pip install -e '.[dev]'
	cd apps/web && npm install

web:              ## build the console into apps/web/dist (served by the API)
	cd apps/web && npm run build

up: web           ## run the platform on :8000 (seeds a fresh synthetic dataset on first start)
	$(PY) -m uvicorn apps.api.server:app --host 0.0.0.0 --port 8000

dev:              ## API with reload on :8000 and Vite on :5173
	$(PY) -m uvicorn apps.api.server:app --reload --port 8000 & cd apps/web && npm run dev

seed:             ## reset var/ and reseed the synthetic dataset
	$(PY) -m tools.seed

test:             ## the whole suite: policy, governance, workflows, chaos, property, contract
	$(PY) -m pytest

validate:         ## schema + invariants + governance lint (Prativaad gate C)
	./hrx validate

hrx-test:         ## replay synthetic runs under a retry storm; no duplicate side effects
	./hrx test --runs 6

bench:            ## every published number comes from here → bench/results/latest.md
	$(PY) -m bench.run

licenses:         ## licence audit: fails on any non-commercial licence
	$(PY) tools/ci/licenses.py

demo-reset:
	rm -rf var

docker:
	docker build -t setu . && docker run --rm -p 8000:8000 setu

clean:
	rm -rf var apps/web/dist .pytest_cache .hypothesis
