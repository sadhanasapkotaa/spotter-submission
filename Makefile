# Usage: make <target> ENV=<local|dev|staging|prod>
ENV ?= local
VALID_ENVS := local dev staging prod
ifeq ($(filter $(ENV),$(VALID_ENVS)),)
$(error ENV must be one of: $(VALID_ENVS))
endif

COMPOSE = docker compose -p spotter-$(ENV) -f compose.yaml -f compose.$(ENV).yaml
# Locally the source is bind-mounted, so run one-off commands as the host user (file ownership).
RUN_AS = $(if $(filter local,$(ENV)),--user $$(id -u):$$(id -g),)
MANAGE = $(COMPOSE) run --rm $(RUN_AS) web python manage.py

.PHONY: help env build up down destroy logs shell psql migrate makemigrations superuser test lint format lock

help:  ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-18s %s\n", $$1, $$2}'

env:  ## Create envs/$(ENV).env from the example (random secrets for non-local)
	@python3 scripts/make_env.py $(ENV)

build: env  ## Build images
	$(COMPOSE) build

up: env  ## Start the stack (detached)
	$(COMPOSE) up -d --build

down:  ## Stop the stack
	$(COMPOSE) down

destroy:  ## Stop the stack AND delete its database volume
	$(COMPOSE) down -v

logs:  ## Tail web logs
	$(COMPOSE) logs -f web

shell: env  ## Django shell in the web container
	$(MANAGE) shell

psql:  ## psql inside the database container
	docker exec -it spotter-$(ENV)-db sh -c 'psql -U $$POSTGRES_USER -d $$POSTGRES_DB'

migrate: env  ## Run migrations (explicit release step in prod)
	$(COMPOSE) run --rm web python manage.py migrate --noinput

makemigrations: env  ## Create migrations (local)
	$(MANAGE) makemigrations $(ARGS)

superuser: env  ## Create a superuser
	$(MANAGE) createsuperuser

test: env  ## Run tests in the local container (needs PostGIS)
	$(COMPOSE) run --rm -e DJANGO_SETTINGS_MODULE=config.settings.test web pytest $(ARGS)

lint:  ## Lint + format check (host)
	uv run ruff check . && uv run ruff format --check .

format:  ## Auto-fix and format (host)
	uv run ruff check --fix . && uv run ruff format .

lock:  ## Update uv.lock
	uv lock --upgrade
