VENV     = .venv
PYTHON   = $(VENV)/bin/python3
PIP      = $(VENV)/bin/pip
SENTINEL = $(VENV)/.instalado

.PHONY: all venv test clean up down cliente logs reset-db info

all: venv test

venv: $(SENTINEL)

$(SENTINEL):
	@python3 -m venv $(VENV) || (echo "\nERRO: instale python3-venv antes de continuar:"; \
	  echo "  sudo apt install python3-venv\n"; exit 1)
	$(PIP) install --quiet --upgrade pip
	$(PIP) install --quiet -r backend/requirements.txt
	$(PIP) install --quiet -r broker/requirements.txt
	touch $(SENTINEL)

test: venv
	$(PYTHON) -m pytest backend/tests/ broker/tests/ frontend/tests/ -v

clean:
	rm -rf $(VENV)
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true

up:
	docker compose up -d --build

down:
	docker compose down

cliente:
	python3 frontend/cliente.py

logs:
	docker compose logs -f

reset-db:
	docker compose down -v
	docker compose up -d --build

info:
	python3 scripts/info.py
