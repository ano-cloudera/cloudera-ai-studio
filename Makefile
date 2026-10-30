.PHONY: bootstrap backend-start backend-status test-backend test-frontend build

bootstrap:
	./scripts/bootstrap/bootstrap-local.sh

backend-start:
	./scripts/dev-backend.sh start

backend-status:
	./scripts/dev-backend.sh status

test-backend:
	cd backend && PYTHONPATH=. ../.venv/bin/pytest -q

test-backend-integration:
	cd backend && PYTHONPATH=. ../.venv/bin/pytest -q -m integration

test-frontend:
	cd frontend && npm run test -- --run

build:
	cd frontend && npm run build
