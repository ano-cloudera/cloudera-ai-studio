.PHONY: bootstrap backend-start backend-status test-backend test-frontend build

bootstrap:
	./scripts/bootstrap/bootstrap-local.sh

backend-start:
	./scripts/dev-backend.sh start

backend-status:
	./scripts/dev-backend.sh status

test-backend:
	cd backend && env -u DEFAULT_PROJECT_SLUG -u OSSIE_PROJECT_ID -u PROJECT_ID -u DATABASE_URL -u STATE_STORE \
	  PYTHONPATH=. ../.venv/bin/pytest -q \
	  tests/test_s1_semantic_registry.py tests/test_s3_semantic_governance.py tests/test_s4_semantic_runtime.py \
	  tests/test_c1_connectors.py tests/test_m3a_prompts.py tests/test_m3b_skills.py tests/test_rag_service.py \
	  tests/test_m7a_ai_registry_unit.py tests/test_c5_datasource_router.py tests/test_chat_api.py

test-frontend:
	cd frontend && npm run test -- --run

build:
	cd frontend && npm run build
