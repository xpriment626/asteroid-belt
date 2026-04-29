.PHONY: install dev test lint format ingest run serve api-gen check

install:
	uv pip install -e ".[dev]"
	cd web && pnpm install
	pre-commit install

dev:
	npx concurrently \
		--names "api,web" --prefix-colors "blue,magenta" \
		"uvicorn asteroid_belt.server.app:app --reload --port 8000" \
		"cd web && pnpm dev --port 5173"

test:
	pytest tests/
	cd web 2>/dev/null && pnpm check 2>/dev/null || true

lint:
	ruff check asteroid_belt tests
	mypy asteroid_belt

format:
	ruff format asteroid_belt tests
	ruff check --fix asteroid_belt tests

check: lint test

ingest:
	belt ingest --pool $(POOL) --start $(START) --end $(END)

run:
	belt run --config $(CONFIG)

serve:
	uvicorn asteroid_belt.server.app:app --port 8000

api-gen:
	cd web && pnpm openapi-typescript http://localhost:8000/api/v1/openapi.json -o src/lib/api/types.ts
