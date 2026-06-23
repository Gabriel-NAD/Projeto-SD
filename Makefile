.PHONY: up down cliente test logs reset-db info

up:
	docker compose up -d --build

down:
	docker compose down

cliente:
	python3 frontend/cliente.py

test:
	python3 -m pytest backend/tests/ broker/tests/ frontend/tests/ -v

logs:
	docker compose logs -f

reset-db:
	docker compose down -v
	docker compose up -d --build

info:
	python3 scripts/info.py
