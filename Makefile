# Mac/Linux shortcuts. Run `make help`.
PY := .venv/bin/python
CC := .venv/bin/carecompanion

.PHONY: help setup test lint check index chat discharge eval-offline eval-baseline eval-hardened eval-injection compare api api-test reset clean-cloud

help:            ## show this help
	@grep -E '^[a-z-]+:.*##' Makefile | sed 's/:.*##/\t/'

setup:           ## create .venv and install everything
	python3 -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev,telemetry]"
	@test -f .env || cp .env.example .env && echo "Edit .env with your Foundry endpoints"

test:            ## unit tests (offline)
	$(PY) -m pytest -q

lint:            ## static checks
	.venv/bin/ruff check src tests

check:           ## verify Azure sign-in, endpoints and model
	$(CC) check

index:           ## build the policy knowledge base
	$(CC) index

chat:            ## talk to the assistant
	$(CC) chat

discharge:       ## discharge note -> structured data -> summary -> verification
	$(CC) discharge

eval-offline:    ## safety-layer evaluation, no cloud needed
	$(CC) eval --suite deterministic --label offline

eval-baseline:   ## live evaluation WITHOUT the guardrails (the "before")
	$(CC) eval --suite core --label baseline --no-guardrails

eval-hardened:   ## live evaluation WITH the guardrails (the "after")
	$(CC) eval --suite core --label hardened

eval-injection:  ## indirect prompt-injection evaluation (needs the poisoned index)
	$(CC) index --agent-name elmfield-policy-agent-injtest --include-safety-fixture
	$(CC) eval --suite injection --label injection

compare:         ## before/after table
	$(CC) eval-compare reports/baseline.json reports/hardened.json

api:             ## run the .NET appointments service (needs the .NET 8 SDK)
	cd services/appointments-api/src/Elmfield.Appointments.Api && Clock__FixedDate=2026-09-28 Api__Key=change-me dotnet run

api-test:        ## .NET unit tests
	cd services/appointments-api/tests/Elmfield.Appointments.Tests && dotnet test

reset:           ## clear local state (appointments, audit log, callbacks)
	$(CC) reset-data

clean-cloud:     ## delete vector stores and agents this project created
	$(CC) cleanup
