POETRY ?= poetry
YAMLLINT ?= $(POETRY) run yamllint
BPLINT ?= $(POETRY) run python scripts/ha_blueprint_lint.py
NATIVE ?= $(POETRY) run python scripts/ha_blueprint_native_check.py
PYTEST ?= $(POETRY) run pytest
JUNIT_XML ?= junit.xml

YAML_FILES ?= blueprints/motion-illuminance.yaml blueprints/button-sonoff-znzb-01p.yml
BPLINT_FLAGS ?=
YAMLLINT_FLAGS ?=

.PHONY: lint lint-yaml lint-blueprint lint-strict lint-native help install test test-native acceptance docker-acceptance

help:
	@echo "Targets:"
	@echo "  make lint            - yamllint + HA blueprint lint (warnings allowed)"
	@echo "  make lint-strict     - same but warnings fail (--warn-as-error)"
	@echo "  make lint-yaml       - yamllint only"
	@echo "  make lint-blueprint  - HA semantic lint only"
	@echo "  make lint-native     - native HA BLUEPRINT_SCHEMA + template compile (needs .venv)"
	@echo "  make test            - lightweight pytest (Jinja logic, no HA core import)"
	@echo "  make test-native     - pytest including native HA tests"
	@echo "  make acceptance      - dockerized HA check_config (opt-in, pulls ghcr.io/home-assistant/home-assistant:2025.1)"
	@echo "  make install         - poetry install"

install:
	$(POETRY) install --no-root --with dev

lint-yaml:
	$(YAMLLINT) $(YAMLLINT_FLAGS) $(YAML_FILES)

lint-blueprint:
	$(BPLINT) $(BPLINT_FLAGS) $(YAML_FILES)

lint-native:
	$(NATIVE) $(YAML_FILES)

lint: lint-yaml lint-blueprint

lint-strict: BPLINT_FLAGS=--warn-as-error
lint-strict: lint

test:
	$(PYTEST) -q --junitxml=$(JUNIT_XML) tests/test_motion_illuminance.py

test-native:
	$(PYTEST) -q --junitxml=$(JUNIT_XML) tests/

acceptance:
	$(POETRY) run python scripts/ha_acceptance_check.py --blueprint $(YAML_FILES)

docker-acceptance: acceptance
