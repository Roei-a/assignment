.DEFAULT_GOAL := help
VENV := .venv
PYTHON := $(VENV)/bin/python
SERVICES := epoch-service now-time-service

# Target image architecture for `up` / `build`. Empty = host architecture
# (the default). Accepts: amd | arm | a full platform string (e.g. linux/amd64).
# Example: `make up ARCH=amd`, `make build ARCH=arm`.
ARCH ?=
ifeq ($(ARCH),amd)
export DOCKER_DEFAULT_PLATFORM := linux/amd64
else ifeq ($(ARCH),arm)
export DOCKER_DEFAULT_PLATFORM := linux/arm64
else ifneq ($(ARCH),)
export DOCKER_DEFAULT_PLATFORM := $(ARCH)
endif

.PHONY: help venv fmt fmt-check lint test unit-test integration-test up down logs build run-epoch run-now-time ci

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

venv: ## Create a local virtualenv with all dev dependencies
	python3 -m venv $(VENV)
	$(PYTHON) -m pip install --quiet --upgrade pip
	$(PYTHON) -m pip install --quiet -r requirements-dev.txt

fmt: venv ## Auto-format all code
	$(VENV)/bin/ruff format .
	$(VENV)/bin/ruff check --fix .

fmt-check: venv ## Verify formatting (what CI runs)
	$(VENV)/bin/ruff format --check .

lint: venv ## Run lints (what CI runs)
	$(VENV)/bin/ruff check .

unit-test: venv ## Run unit tests for all services
	@for svc in $(SERVICES); do \
		echo "==> $$svc"; \
		(cd services/$$svc && ../../$(PYTHON) -m pytest -q) || exit 1; \
	done

test: unit-test ## Alias for unit-test

up: ## Build and start both services (waits until healthy)
	docker compose up -d --build --wait

down: ## Stop and remove the environment
	docker compose down

logs: ## Tail logs from both services
	docker compose logs -f

build: ## Build Docker images for both services
	docker compose build

integration-test: venv up ## Start the environment and run integration tests against it
	$(PYTHON) -m pytest -q tests/integration
	$(MAKE) down

run-epoch: venv ## Run epoch-service directly on the host (port 8080)
	cd services/epoch-service && ../../$(PYTHON) -m app.main

run-now-time: venv ## Run now-time-service directly on the host (port 8081)
	cd services/now-time-service && ../../$(PYTHON) -m app.main

ci: fmt-check lint unit-test ## Run the same checks CI runs on every PR
