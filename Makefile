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

test-backend-tempo:
	cd backend && PYTHONPATH=. ../.venv/bin/pytest -q -m tempo_domain

test-frontend:
	cd frontend && npm run test -- --run

build:
	cd frontend && npm run build

amp-readiness:
	.venv/bin/python scripts/demo/run_amp_accelerator_readiness.py

amp-demo-profile:
	.venv/bin/python scripts/demo/apply_accelerator_demo_profile.py

amp-bootstrap:
	.venv/bin/python scripts/demo/bootstrap_golden_banking.py --apply && .venv/bin/python scripts/demo/apply_accelerator_demo_profile.py
