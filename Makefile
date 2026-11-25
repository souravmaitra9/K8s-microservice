PYTHON ?= python3
export PYTHONPATH := services/guardrail/src:services/agent/src:services/kb/src:services/tickets/src:$(PYTHONPATH)

.PHONY: test lint fmt build up down helm-lint kind-load kind-install

test:
	$(PYTHON) -m pytest

lint:
	ruff check services tests
	ruff format --check services tests

fmt:
	ruff check --fix services tests
	ruff format services tests

build:
	docker build -t agent-platform/guardrail:dev services/guardrail
	docker build -t agent-platform/agent:dev services/agent
	docker build -t agent-platform/kb:dev services/kb
	docker build -t agent-platform/tickets:dev services/tickets

up:
	docker compose up --build

down:
	docker compose down --remove-orphans

helm-lint:
	helm lint deploy/helm/agent-platform
	helm template agent-platform deploy/helm/agent-platform --namespace agent-platform \
	  | kubeconform -strict -summary -kubernetes-version 1.31.0

kind-load:
	kind load docker-image agent-platform/guardrail:dev
	kind load docker-image agent-platform/agent:dev
	kind load docker-image agent-platform/kb:dev
	kind load docker-image agent-platform/tickets:dev

kind-install: kind-load
	kubectl apply -f deploy/manifests/namespace.yaml
	helm upgrade --install agent-platform deploy/helm/agent-platform \
	  --namespace agent-platform \
	  --values deploy/helm/agent-platform/values-kind.yaml
