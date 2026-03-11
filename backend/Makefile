# NCPI Search API - Docker Build & Deploy
# Usage: make <target>
#
# Prerequisites:
#   Prod: aws sso login --profile ncpi-prod-deployer
#
# Quick start:
#   make start          # start local API server (rebuilds index if needed)
#   make restart        # stop + start
#   make stop           # stop running server

# Image settings
IMAGE_NAME = ncpi-search-api
IMAGE_TAG ?= latest

# Dev environment
DEV_AWS_PROFILE = excira
DEV_ECR_REPO = 708377107803.dkr.ecr.us-east-1.amazonaws.com/jso-ncpi-dataset-catalog

# Prod environment (update after first terraform apply-prod)
PROD_AWS_PROFILE = ncpi-prod-deployer
PROD_ECR_REPO = 701973344956.dkr.ecr.us-east-1.amazonaws.com/5wu-ncpi-dataset-catalog

AWS_REGION = us-east-1
PID_FILE = .server.pid

# CloudWatch log groups (App Runner pipes stdout here)
DEV_LOG_GROUP = /aws/apprunner/jso-ncpi-dataset-catalog/59bf88e6efa543319f5c03df62cf0edd/application
PROD_LOG_GROUP = /aws/apprunner/5wu-ncpi-dataset-catalog/d2f7c9715dbc4d6d9b4c3af33f8eefd3/application

.PHONY: help build push-dev push-prod deploy-dev deploy-prod \
        start stop restart db-reload embeddings clean-embeddings evals lint format logs-dev logs-prod

# Default target
help:
	@echo "NCPI Search API"
	@echo ""
	@echo "Local development:"
	@echo "  start       - Start local API server on :8000 (background)"
	@echo "  stop        - Stop running local server"
	@echo "  restart     - Stop + start"
	@echo "  embeddings        - Generate concept embeddings (uses GPU if available)"
	@echo "  db-reload         - Rebuild DuckDB index and restart server (needs embeddings)"
	@echo "  clean-embeddings  - Delete cached embedding files (forces regeneration)"
	@echo "  evals             - Run extract agent evals"
	@echo "  lint              - Run ruff linter"
	@echo "  format            - Run ruff formatter"
	@echo ""
	@echo "Docker deploy:"
	@echo "  build       - Build Docker image locally"
	@echo "  deploy-dev  - Build + push to dev ECR"
	@echo "  deploy-prod - Build + push to prod ECR"
	@echo ""
	@echo "Logs:"
	@echo "  logs-dev    - Tail dev search logs (Ctrl-C to stop)"
	@echo "  logs-prod   - Tail prod search logs (Ctrl-C to stop)"

# --- Local development -------------------------------------------------

# Start API server in background
start: stop
	@echo "Starting API server on http://localhost:8000 ..."
	@uv run python -m uvicorn concept_search.api:app \
		--host 0.0.0.0 --port 8000 > .server.log 2>&1 & echo $$! > $(PID_FILE)
	@sleep 2
	@if kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
		echo "Server running (PID $$(cat $(PID_FILE))), log: backend/.server.log"; \
	else \
		echo "Server failed to start. Check backend/.server.log"; \
		cat .server.log; \
		rm -f $(PID_FILE); \
		exit 1; \
	fi

# Stop running server
stop:
	@if [ -f $(PID_FILE) ]; then \
		kill $$(cat $(PID_FILE)) 2>/dev/null && echo "Server stopped." || true; \
		rm -f $(PID_FILE); \
	fi
	@lsof -ti :8000 | xargs kill 2>/dev/null || true

# Stop + start
restart: stop start

# Rebuild DuckDB index and restart server (requires pre-built embeddings: make embeddings)
db-reload: stop
	@echo "Deleting cached DuckDB index..."
	@rm -f ../catalog/concept-search.duckdb
	@echo "Rebuilding index (this may take a moment)..."
	@uv run python -c "import logging; logging.basicConfig(level=logging.INFO); from concept_search.index import get_index; idx = get_index(); print(f'Index rebuilt: {idx.store.study_count} studies')"
	@$(MAKE) start

# Generate concept embeddings using GPU torch (separate venv from backend)
embeddings:
	cd generate_embeddings && uv sync --quiet && uv run python generate_embeddings.py

# Delete cached embedding files so db-reload regenerates them
clean-embeddings:
	@rm -f ../catalog-build/classification/output/concept-embeddings.npy
	@rm -f ../catalog-build/classification/output/concept-embeddings.sha256
	@echo "Embedding cache cleared."

# Run extract, resolve, and end-to-end pipeline evals
evals:
	uv run python -m concept_search.eval_extract
	uv run python -m concept_search.eval_resolve
	uv run python -m concept_search.eval_pipeline

# Lint Python files with ruff
lint:
	uv run ruff check concept_search/ tests/

# Format Python files with ruff
format:
	uv run ruff format concept_search/ tests/

# --- Docker deploy ------------------------------------------------------

# Build Docker image (bakes in git SHA for /health endpoint)
build:
	@if [ ! -f ../catalog/concept-search.duckdb ]; then \
		echo "Error: catalog/concept-search.duckdb not found. Run 'make db-reload' first."; \
		exit 1; \
	fi
	@if [ -n "$$(git -C .. status --porcelain -uno)" ]; then \
		echo "Error: uncommitted changes. Commit or stash before deploying."; \
		exit 1; \
	fi
	@echo "Building Docker image..."
	docker build --platform linux/amd64 \
		--build-arg GIT_SHA=$$(git -C .. rev-parse --short HEAD) \
		-t $(IMAGE_NAME):$(IMAGE_TAG) -f Dockerfile ..

# Push to dev ECR
push-dev:
	@echo "Pushing to dev ECR..."
	@eval "$$(aws configure export-credentials --profile $(DEV_AWS_PROFILE) --format env)" && \
	aws ecr get-login-password --region $(AWS_REGION) | \
		docker login --username AWS --password-stdin $(DEV_ECR_REPO) && \
	docker tag $(IMAGE_NAME):$(IMAGE_TAG) $(DEV_ECR_REPO):$(IMAGE_TAG) && \
	docker push $(DEV_ECR_REPO):$(IMAGE_TAG)

# Push to prod ECR
push-prod:
	@echo "Pushing to prod ECR..."
	@eval "$$(aws configure export-credentials --profile $(PROD_AWS_PROFILE) --format env)" && \
	aws ecr get-login-password --region $(AWS_REGION) | \
		docker login --username AWS --password-stdin $(PROD_ECR_REPO) && \
	docker tag $(IMAGE_NAME):$(IMAGE_TAG) $(PROD_ECR_REPO):$(IMAGE_TAG) && \
	docker push $(PROD_ECR_REPO):$(IMAGE_TAG)

# All-in-one: build + push to dev
deploy-dev: build push-dev
	@echo "Deploy to dev complete."

# All-in-one: build + push to prod
deploy-prod: build push-prod
	@echo "Deploy to prod complete."

# --- Logs -----------------------------------------------------------------

# Tail dev search logs (Ctrl-C to stop)
logs-dev:
	aws logs tail "$(DEV_LOG_GROUP)" \
		--follow --filter-pattern "search_" \
		--profile $(DEV_AWS_PROFILE) --region $(AWS_REGION)

# Tail prod search logs (Ctrl-C to stop)
logs-prod:
	aws logs tail "$(PROD_LOG_GROUP)" \
		--follow --filter-pattern "search_" \
		--profile $(PROD_AWS_PROFILE) --region $(AWS_REGION)
